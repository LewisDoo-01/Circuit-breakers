"""Regression tests for P1-5 (retrying non-retryable errors) and P1-6 (silent None)."""
import pytest

from jitter import RETRYABLE_EXCEPTIONS, retry_with_exponential_backoff_and_jitter as retry


class AuthError(Exception):
    """A permanent error: retrying can never make it succeed."""


class APIError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


# ---------------------------------------------------------------------------
# P1-5: only retry what is actually retryable
# ---------------------------------------------------------------------------

def test_permanent_error_is_not_retried():
    # ORIGINAL BUG: `except Exception` retried everything, so an invalid API key
    # was tried 5 times - 5x the wait, 5x the cost, and the real error reached
    # the user 5 backoffs late.
    calls = []

    def bad_key():
        calls.append(1)
        raise AuthError("401 Invalid API key")

    with pytest.raises(AuthError):
        retry(bad_key, max_attempts=5, base_delay=0.01)

    assert len(calls) == 1, f"permanent error retried {len(calls)} times"


def test_programming_errors_are_not_retried_or_swallowed():
    # ORIGINAL BUG: a TypeError in your own code was retried like a network
    # blip, which hides the bug and delays the traceback.
    calls = []

    def broken():
        calls.append(1)
        raise TypeError("unsupported operand")

    with pytest.raises(TypeError):
        retry(broken, max_attempts=4, base_delay=0.01)

    assert len(calls) == 1


@pytest.mark.parametrize("exc", [ConnectionError("refused"), TimeoutError("timed out")])
def test_transient_errors_are_still_retried(exc):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise exc
        return "ok"

    assert retry(flaky, max_attempts=5, base_delay=0.01, max_delay=0.02) == "ok"
    assert len(calls) == 3


def test_retryable_exceptions_is_configurable():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise AuthError("temporarily flaky in this deployment")
        return "ok"

    result = retry(flaky, max_attempts=4, base_delay=0.01,
                   retryable_exceptions=(AuthError,))
    assert result == "ok"
    assert len(calls) == 2


def test_is_retryable_predicate_discriminates_by_status_code():
    # The real-world case: providers wrap every failure in ONE exception class
    # and only the status code says whether retrying is worth anything.
    retryable = lambda e: isinstance(e, APIError) and e.status in (429, 500, 503)

    rate_limited = []

    def throttled():
        rate_limited.append(1)
        if len(rate_limited) < 3:
            raise APIError(429)
        return "ok"

    assert retry(throttled, max_attempts=5, base_delay=0.01,
                 is_retryable=retryable) == "ok"
    assert len(rate_limited) == 3

    forbidden = []

    def denied():
        forbidden.append(1)
        raise APIError(403)

    with pytest.raises(APIError):
        retry(denied, max_attempts=5, base_delay=0.01, is_retryable=retryable)
    assert len(forbidden) == 1


def test_default_retryable_set_excludes_bare_exception():
    # Guards the fix itself: if Exception ever creeps back into the default,
    # every permanent error becomes retryable again.
    assert Exception not in RETRYABLE_EXCEPTIONS
    assert BaseException not in RETRYABLE_EXCEPTIONS


# ---------------------------------------------------------------------------
# P1-6: no silent None
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [0, -1, -10])
def test_non_positive_max_attempts_raises(bad):
    # ORIGINAL BUG: the for loop never ran, the function fell off the end and
    # returned None - indistinguishable from a successful call returning None.
    calls = []

    with pytest.raises(ValueError, match="max_attempts"):
        retry(lambda: calls.append(1), max_attempts=bad)

    assert calls == [], "func must not be called at all"


def test_single_attempt_still_works():
    assert retry(lambda: "ok", max_attempts=1) == "ok"


def test_exhausting_retries_reraises_the_last_error():
    def always_fail():
        raise ConnectionError("still down")

    with pytest.raises(ConnectionError, match="still down"):
        retry(always_fail, max_attempts=3, base_delay=0.01, max_delay=0.02)


def test_traceback_is_preserved_on_exhaustion():
    # `raise e` restarts the traceback at the retry helper; bare `raise` keeps
    # the frame where the error actually happened.
    def deep():
        raise ConnectionError("boom")

    with pytest.raises(ConnectionError) as excinfo:
        retry(deep, max_attempts=2, base_delay=0.01)

    frames = [tb.name for tb in excinfo.traceback]
    assert "deep" in frames, f"original frame lost: {frames}"


def test_library_does_not_write_to_stdout(capsys):
    # Same defect class as P0-1: a retry helper runs on the request path.
    with pytest.raises(ConnectionError):
        retry(lambda: (_ for _ in ()).throw(ConnectionError("x")),
              max_attempts=2, base_delay=0.01)
    assert capsys.readouterr().out == ""
