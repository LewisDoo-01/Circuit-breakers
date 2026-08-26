import random
import time


def retry_with_exponential_backoff_and_jitter(func, max_attempts=5, base_delay=1.0, max_delay=32.0):
    for attempt in range(max_attempts):
        try:
            result = func()
            print(f"  [Attempt {attempt + 1}/{max_attempts}] Thanh cong!")
            return result
        except Exception as e:
            if attempt == max_attempts - 1:
                print(f"  [Attempt {attempt + 1}/{max_attempts}] That bai — het retry, raise exception")
                raise e

            backoff = min(max_delay, base_delay * (2 ** attempt))
            sleep_time = random.uniform(0, backoff)

            print(
                f"  [Attempt {attempt + 1}/{max_attempts}] That bai"
                f" | backoff = min({max_delay}, {base_delay} x 2^{attempt}) = {backoff:.1f}s"
                f" | jitter = random(0, {backoff:.1f}) = {sleep_time:.2f}s"
                f" | cho {sleep_time:.2f}s roi retry..."
            )
            time.sleep(sleep_time)


# --- Demo ---
if __name__ == "__main__":
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
