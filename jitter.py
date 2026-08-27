import logging
import random
import sys
import time

# Không print() trong code thư viện: hàm retry chạy trong đường đi của request,
# và print() ra console cp1252 (mặc định của Windows) sẽ ném UnicodeEncodeError
# đè lên chính exception mà caller đang chờ. logging nuốt lỗi encoding.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Mặc định an toàn: chỉ retry những lỗi mang tính TẠM THỜI.
# Không đưa Exception vào đây — xem giải thích trong docstring.
RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)


def retry_with_exponential_backoff_and_jitter(
    func,
    max_attempts=5,
    base_delay=1.0,
    max_delay=32.0,
    retryable_exceptions=RETRYABLE_EXCEPTIONS,
    is_retryable=None,
):
    """Retry với exponential backoff + full jitter.

    Chỉ retry những lỗi CÓ THỂ retry được. Bản cũ dùng `except Exception` nên
    retry mọi thứ, kể cả lỗi vĩnh viễn: một API key sai (401) được thử lại 5 lần
    thì vẫn sai 5 lần — chỉ tốn thời gian, tốn tiền, và làm chậm việc báo lỗi
    thật cho người dùng. Lỗi lập trình (TypeError, KeyError) cũng bị nuốt và
    retry y hệt, che mất bug.

    Tham số:
        retryable_exceptions: tuple các loại exception được phép retry.
        is_retryable: hàm tuỳ chọn nhận exception, trả True/False. Dùng khi
            provider gói mọi lỗi vào CÙNG một class và chỉ khác status code
            (ví dụ 429 nên retry, 401 thì không).

    Ném lại nguyên vẹn exception cuối cùng nếu hết lượt, hoặc ném ngay lập tức
    nếu lỗi không thuộc diện retry được.
    """
    if max_attempts < 1:
        # Bản cũ: vòng for không chạy lần nào, hàm rơi ra ngoài và trả None —
        # trông y hệt một kết quả hợp lệ. Lỗi cấu hình phải báo to, không im lặng.
        raise ValueError(f"max_attempts phải >= 1, nhận được {max_attempts}")

    for attempt in range(max_attempts):
        try:
            result = func()
            logger.info("[Attempt %d/%d] Thanh cong!", attempt + 1, max_attempts)
            return result
        except Exception as e:
            if is_retryable is not None:
                can_retry = is_retryable(e)
            else:
                can_retry = isinstance(e, retryable_exceptions)

            if not can_retry:
                logger.warning(
                    "[Attempt %d/%d] %s khong the retry — ném ngay, khong cho vo ich",
                    attempt + 1, max_attempts, type(e).__name__,
                )
                raise

            if attempt == max_attempts - 1:
                logger.warning(
                    "[Attempt %d/%d] That bai — het retry, raise exception",
                    attempt + 1, max_attempts,
                )
                raise  # `raise` trần giữ nguyên traceback gốc, khác với `raise e`

            backoff = min(max_delay, base_delay * (2 ** attempt))
            sleep_time = random.uniform(0, backoff)

            logger.info(
                "[Attempt %d/%d] That bai | backoff = min(%s, %s x 2^%d) = %.1fs"
                " | jitter = random(0, %.1f) = %.2fs | cho %.2fs roi retry...",
                attempt + 1, max_attempts, max_delay, base_delay, attempt,
                backoff, backoff, sleep_time, sleep_time,
            )
            time.sleep(sleep_time)

    # Không thể tới đây: max_attempts >= 1 nên lần lặp cuối luôn return hoặc raise.
    raise AssertionError("unreachable")


def _setup_demo_output():
    """Bật UTF-8 + hiện log cho console demo (chỉ trong khối __main__)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logging.basicConfig(level=logging.INFO, format="  %(message)s")


# --- Demo ---
if __name__ == "__main__":
    _setup_demo_output()

    print("=" * 60)
    print("  EXPONENTIAL BACKOFF + FULL JITTER DEMO")
    print("=" * 60)

    # Case 1: Luon that bai (mo phong service sap)
    print("\n--- Case 1: Service sap lien tuc ---")
    fail_count = 0

    def always_fail():
        global fail_count
        fail_count += 1
        raise ConnectionError(f"Connection refused (lan {fail_count})")

    try:
        retry_with_exponential_backoff_and_jitter(always_fail, max_attempts=4, base_delay=0.5, max_delay=4.0)
    except ConnectionError as e:
        print(f"  => Ket qua: {e}")

    # Case 2: That bai vai lan roi thanh cong (mo phong service phuc hoi)
    print("\n--- Case 2: Service phuc hoi sau 3 lan that bai ---")
    call_count = 0

    def recover_after_3():
        global call_count
        call_count += 1
        if call_count <= 3:
            raise ConnectionError(f"Connection refused (lan {call_count})")
        return {"status": "ok", "data": "Ket qua tu server"}

    result = retry_with_exponential_backoff_and_jitter(recover_after_3, max_attempts=5, base_delay=0.5, max_delay=4.0)
    print(f"  => Ket qua: {result}")

    # Case 3: Thanh cong ngay lan dau
    print("\n--- Case 3: Service hoat dong binh thuong ---")

    def always_ok():
        return {"status": "ok", "data": "Phan hoi nhanh"}

    result = retry_with_exponential_backoff_and_jitter(always_ok, max_attempts=5, base_delay=0.5, max_delay=4.0)
    print(f"  => Ket qua: {result}")

    # Case 4: Loi vinh vien - KHONG duoc retry
    print("\n--- Case 4: API key sai (401) - loi vinh vien, khong retry ---")
    auth_calls = 0

    class AuthError(Exception):
        pass

    def bad_api_key():
        global auth_calls
        auth_calls += 1
        raise AuthError("401 Invalid API key")

    try:
        retry_with_exponential_backoff_and_jitter(bad_api_key, max_attempts=5, base_delay=0.5)
    except AuthError as e:
        print(f"  => Ket qua: {e}")
        print(f"  => So lan goi thuc te: {auth_calls} (bản cũ sẽ gọi 5 lần vô ích)")

    # Case 5: Cung mot class exception, phan biet bang status code
    print("\n--- Case 5: Cung class exception, chi 429 moi duoc retry ---")

    class APIError(Exception):
        def __init__(self, status):
            super().__init__(f"HTTP {status}")
            self.status = status

    rate_limited = 0

    def rate_limit_then_ok():
        global rate_limited
        rate_limited += 1
        if rate_limited <= 2:
            raise APIError(429)
        return {"status": "ok"}

    result = retry_with_exponential_backoff_and_jitter(
        rate_limit_then_ok,
        max_attempts=5,
        base_delay=0.2,
        is_retryable=lambda e: isinstance(e, APIError) and e.status in (429, 500, 502, 503, 504),
    )
    print(f"  => Ket qua: {result} sau {rate_limited} lan goi")

    print("\n" + "=" * 60)
    print(" KET LUAN: retry dung cach = backoff + jitter + LOC LOI")
    print("   1. Exponential backoff -> giam tai server dang qua tai")
    print("   2. Full jitter         -> tranh thundering herd")
    print("   3. Loc loi retry duoc  -> khong phi 5 lan cho mot 401")
    print("=" * 60)
