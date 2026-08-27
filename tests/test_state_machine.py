"""Regression tests for P0-1 (print() on the request path) and P0-2 (thread safety).

Each test states the original buggy behaviour it pins down.
"""
import io
import sys
import threading
import time

import pytest

from state_machine import CircuitBreaker, CircuitOpenError, CircuitState


def _dead():
    raise ConnectionError("503 Service Unavailable")


def _alive():
    return "ok"


def _trip(breaker):
    """Drive the breaker to OPEN."""
    for _ in range(breaker.failure_threshold):
        with pytest.raises(ConnectionError):
            breaker.call(_dead)


# ---------------------------------------------------------------------------
# P0-1: library code must never write to stdout
# ---------------------------------------------------------------------------

class _Cp1252Stream(io.TextIOBase):
    """A stdout that behaves like a default Windows console."""

    def write(self, s):
        s.encode("cp1252")  # raises UnicodeEncodeError on Vietnamese diacritics
        return len(s)


def test_library_never_writes_to_stdout(capsys):
    # ORIGINAL BUG: record_failure()/call() called print() with Vietnamese text
    # straight from the request path, so this captured output was non-empty.
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0.05,
                             expected_exceptions=(ConnectionError,))
    _trip(breaker)
    with pytest.raises(CircuitOpenError):
        breaker.call(_dead)

    captured = capsys.readouterr()
    assert captured.out == "", f"library wrote to stdout: {captured.out!r}"


def test_correct_exception_survives_a_console_that_cannot_encode(monkeypatch):
    # ORIGINAL BUG: on a cp1252 console the print() inside record_failure raised
    # UnicodeEncodeError *after* the state mutation, and that exception replaced
    # the ConnectionError the caller was catching -> the gateway died.
    monkeypatch.setattr(sys, "stdout", _Cp1252Stream())
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.05,
                             expected_exceptions=(ConnectionError,))

    with pytest.raises(ConnectionError):
        breaker.call(_dead)

    time.sleep(0.1)
    # The OPEN -> HALF_OPEN transition also used to print.
    with pytest.raises(ConnectionError):
        breaker.call(_dead)


# ---------------------------------------------------------------------------
# P0-2: thread safety
# ---------------------------------------------------------------------------

def test_half_open_admits_exactly_one_probe():
    # ORIGINAL BUG: 20 concurrent requests in HALF_OPEN ALL reached the dead
    # downstream - the exact thundering herd a circuit breaker exists to stop.
    n_threads = 20
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0.1,
                             success_threshold=n_threads + 1,  # stay in HALF_OPEN
                             probe_timeout_seconds=60.0,
                             expected_exceptions=(ConnectionError,))
    _trip(breaker)
    time.sleep(0.15)  # let the reset timeout elapse

    reached = []
    reached_lock = threading.Lock()
    release_probe = threading.Event()
    barrier = threading.Barrier(n_threads)

    def downstream():
        with reached_lock:
            reached.append(1)
        release_probe.wait(5.0)  # hold the probe slot open
        return "ok"

    denied = []

    def worker():
        barrier.wait(5.0)  # make all threads race at the same instant
        try:
            breaker.call(downstream)
        except CircuitOpenError as exc:
            denied.append(exc.reason)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    # Give the losers time to be denied while the winner still holds the slot.
    time.sleep(0.3)
    admitted = len(reached)
    release_probe.set()
    for t in threads:
        t.join(5.0)

    assert admitted == 1, f"{admitted} requests reached the downstream, expected 1"
    assert denied.count("HALF_OPEN_BUSY") == n_threads - 1


def test_lock_is_not_held_across_fn():
    # REGRESSION GUARD (this one also passed before the fix, because there was
    # no lock at all): holding the lock across fn() would serialise every
    # request through the gateway. 10 x 0.3s must stay ~0.3s, not ~3.0s.
    breaker = CircuitBreaker(failure_threshold=100,
                             expected_exceptions=(ConnectionError,))

    def slow():
        time.sleep(0.3)
        return "ok"

    start = time.monotonic()
    threads = [threading.Thread(target=lambda: breaker.call(slow)) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10.0)
    elapsed = time.monotonic() - start

    assert elapsed < 1.5, f"calls were serialised: {elapsed:.2f}s for 10 x 0.3s"


def test_stale_result_cannot_close_the_circuit():
    # ORIGINAL BUG: a request admitted while CLOSED that returned long after the
    # circuit had tripped was still recorded, so a stale success could close the
    # circuit back onto a downstream that was still dead.
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10.0,
                             success_threshold=1,
                             expected_exceptions=(ConnectionError,))
    gate = threading.Event()
    result = []

    def slow_success():
        gate.wait(5.0)
        return "stale-ok"

    worker = threading.Thread(target=lambda: result.append(breaker.call(slow_success)))
    worker.start()
    time.sleep(0.05)  # ensure it was admitted while CLOSED

    _trip(breaker)
    assert breaker.snapshot()["state"] is CircuitState.OPEN

    gate.set()
    worker.join(5.0)

    # The stale call still returns its value to its own caller - stale is not an
    # error - but it must not speak for the circuit.
    assert result == ["stale-ok"]
    assert breaker.snapshot()["state"] is CircuitState.OPEN


def test_reset_timeout_ignores_wall_clock_jumps(monkeypatch):
    # ORIGINAL BUG: _ready_to_probe() used time.time(), so an NTP correction (or
    # any wall-clock jump) could open the circuit for probing far too early.
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=30.0,
                             expected_exceptions=(ConnectionError,))
    _trip(breaker)

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 3600)  # jump 1 hour

    with pytest.raises(CircuitOpenError) as excinfo:
        breaker.call(_alive)
    assert excinfo.value.reason == "OPEN"


def test_hung_probe_is_reaped_instead_of_wedging_half_open():
    # ORIGINAL BUG: there was no probe slot at all. With a naive single-probe
    # flag a hung probe would wedge HALF_OPEN forever, so the reaper matters.
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.1,
                             success_threshold=1, probe_timeout_seconds=0.15,
                             expected_exceptions=(ConnectionError,))
    _trip(breaker)
    time.sleep(0.15)

    gate = threading.Event()

    def hangs():
        gate.wait(5.0)
        return "late"

    worker = threading.Thread(target=lambda: breaker.call(hangs), daemon=True)
    worker.start()
    time.sleep(0.05)
    assert breaker.snapshot()["probe_in_flight"] is True

    time.sleep(0.25)  # exceed probe_timeout_seconds
    assert breaker.state is CircuitState.OPEN  # reading state reaps the slot
    assert breaker.snapshot()["probe_in_flight"] is False

    gate.set()
    worker.join(5.0)


def test_fail_fast_does_not_inflate_failure_count():
    # ORIGINAL BUG RISK: if CircuitOpenError were raised inside the try that
    # catches expected_exceptions, the breaker would count its own fail-fast as
    # a downstream failure (default expected_exceptions is (Exception,)).
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10.0)
    _trip(breaker)
    before = breaker.snapshot()["failure_count"]

    for _ in range(5):
        with pytest.raises(CircuitOpenError):
            breaker.call(_alive)

    assert breaker.snapshot()["failure_count"] == before


def test_concurrent_closed_traffic_counts_correctly():
    # ORIGINAL BUG: failure_count += 1 was an unsynchronised read-modify-write,
    # so concurrent failures could be lost and the circuit would trip late.
    breaker = CircuitBreaker(failure_threshold=10_000, reset_timeout_seconds=10.0,
                             expected_exceptions=(ConnectionError,))
    n = 200

    def worker():
        try:
            breaker.call(_dead)
        except ConnectionError:
            pass

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10.0)

    assert breaker.snapshot()["failure_count"] == n
