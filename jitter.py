import random
import time

def retry_with_exponential_backoff_and_jitter(func, max_attempts=5, base_delay=1.0, max_delay=32.0):
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise e
            
            # Tính Exponential Backoff có trần (max_delay)
            backoff = min(max_delay, base_delay * (2 ** attempt))
            
            # Áp dụng Full Jitter
            sleep_time = random.uniform(0, backoff)
            
            time.sleep(sleep_time)
