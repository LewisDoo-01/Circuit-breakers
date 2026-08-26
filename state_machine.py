from enum import Enum
import time
from typing import Callable, Any, Tuple, Type


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Ngoại lệ ném ra khi mạch đang OPEN (Fail-fast)."""

    pass


class CircuitBreaker:

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout_seconds: float = 5.0,
        success_threshold: int = 2,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.success_threshold = success_threshold
        self.expected_exceptions = expected_exceptions

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.time()

    def _ready_to_probe(self) -> bool:
        """Kiểm tra xem đã hết thời gian reset_timeout để thăm dò chưa."""
        return (time.time() - self.last_state_change) >= self.reset_timeout_seconds

    def record_success(self):
        """Ghi nhận lượt gọi thành công và cập nhật trạng thái."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            # Đạt đủ số lần probe thành công -> Đóng mạch trở lại
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_state_change = time.time()
                print("[CIRCUIT] Phục hồi thành công -> Chuyển về CLOSED")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        """Ghi nhận lượt gọi thất bại và cập nhật trạng thái."""
        self.failure_count += 1
        self.last_state_change = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Probe thất bại -> Lập tức quay lại OPEN
            self.state = CircuitState.OPEN
            self.success_count = 0
            print("[CIRCUIT] Probe thất bại -> Quay lại OPEN")
        elif (
            self.state == CircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            # Vượt ngưỡng lỗi -> Ngắt mạch
            self.state = CircuitState.OPEN
            print(
                f"[CIRCUIT] Vượt ngưỡng {self.failure_threshold} lỗi -> Chuyển sang OPEN"
            )

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        # 1. Kiểm tra trạng thái OPEN
        if self.state == CircuitState.OPEN:
            if not self._ready_to_probe():
                raise CircuitOpenError(
                    "Circuit is OPEN - Fast fail để bảo vệ downstream service."
                )
            # Đã hết thời gian chờ -> Chuyển sang HALF_OPEN để thăm dò
            self.state = CircuitState.HALF_OPEN
            self.success_count = 0
            print("[CIRCUIT] Hết timeout -> Chuyển sang HALF_OPEN để thăm dò")

        # 2. Thực thi hàm gọi API/Tool
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except self.expected_exceptions as e:
            self.record_failure()
            raise e


# ============================================================
# Demo: Giả lập LLM Gateway có Circuit Breaker + Fallback
# ============================================================
#
#   Kịch bản:
#     - LLM provider (GPT, Claude, Gemini...) bị sập 503
#     - Gateway phát hiện lỗi liên tiếp -> ngắt mạch
#     - Chờ timeout -> thăm dò lại -> phục hồi
#
#   Sơ đồ trạng thái:
#
#     CLOSED ──(lỗi >= threshold)──> OPEN ──(hết timeout)──> HALF_OPEN
#       ^                                                        |
#       └──────────(probe thành công)────────────────────────────┘
#                  (probe thất bại) ──> quay lại OPEN
#
# ============================================================

is_server_down = True


def mock_call_llm(prompt: str) -> str:
    """Giả lập LLM API: ném lỗi khi server sập, trả kết quả khi sống."""
    if is_server_down:
        raise ConnectionError("503 Service Unavailable")
    return f"LLM Response: '{prompt}'"


breaker = CircuitBreaker(
    failure_threshold=2,       # 2 lỗi liên tiếp -> ngắt mạch
    reset_timeout_seconds=2.0, # Chờ 2s rồi thăm dò lại
    success_threshold=1,       # 1 probe thành công -> đóng mạch
    expected_exceptions=(ConnectionError, TimeoutError),
)


def robust_llm_gateway(prompt: str) -> str:
    """Gateway bọc Circuit Breaker + Fallback."""
    try:
        return breaker.call(mock_call_llm, prompt)
    except CircuitOpenError:
        return "[FALLBACK] Mạch đang ngắt - trả lời từ cache/model dự phòng."
    except ConnectionError:
        return "[FALLBACK] Lỗi kết nối - kích hoạt fallback chain."


def print_status():
    """In trạng thái hiện tại của circuit breaker."""
    state_icons = {
        CircuitState.CLOSED: "CLOSED    (cho request đi qua bình thường)",
        CircuitState.OPEN: "OPEN      (chặn mọi request - fail fast)",
        CircuitState.HALF_OPEN: "HALF_OPEN (cho 1 request thăm dò)",
    }
    print(f"    State: {state_icons[breaker.state]}")
    print(f"    Failures: {breaker.failure_count}/{breaker.failure_threshold}")


if __name__ == "__main__":
    print("=" * 60)
    print(" CIRCUIT BREAKER DEMO - LLM Gateway")
    print("=" * 60)
    print(f" Config: failure_threshold={breaker.failure_threshold}, "
          f"reset_timeout={breaker.reset_timeout_seconds}s, "
          f"success_threshold={breaker.success_threshold}")
    print()

    # ── Bước 1: LLM đang sập, gọi liên tiếp ──
    print("[Bước 1] LLM đang sập - gọi 2 lần để trigger ngắt mạch")
    print("-" * 60)
    print_status()
    print()
    for i in range(1, 3):
        result = robust_llm_gateway(f"Xin chào lần {i}")
        print(f"  Request #{i}: {result}")
        print_status()
        print()

    # ── Bước 2: Mạch đã OPEN, request bị chặn ngay ──
    print("[Bước 2] Mạch đã OPEN - request mới bị chặn ngay (Fail Fast)")
    print("-" * 60)
    result = robust_llm_gateway("Câu hỏi mới")
    print(f"  Request #3: {result}")
    print(f"    --> Không gọi LLM, bảo vệ server đang quá tải")
    print_status()
    print()

    # ── Bước 3: Chờ timeout rồi thăm dò ──
    wait = breaker.reset_timeout_seconds + 0.1
    print(f"[Bước 3] Chờ {wait:.1f}s cho reset timeout hết hạn...")
    print("-" * 60)
    time.sleep(wait)
    is_server_down = False  # Server đã phục hồi
    print(f"  (Server đã phục hồi)")
    print()

    # ── Bước 4: Probe call ──
    print("[Bước 4] Gửi probe request ở trạng thái HALF_OPEN")
    print("-" * 60)
    result = robust_llm_gateway("Probe: bạn phục hồi chưa?")
    print(f"  Probe:   {result}")
    print_status()
    print()

    # ── Bước 5: Mạch phục hồi, hoạt động bình thường ──
    print("[Bước 5] Mạch phục hồi - gọi bình thường")
    print("-" * 60)
    result = robust_llm_gateway("Câu hỏi bình thường")
    print(f"  Request: {result}")
    print_status()
    print()

    print("=" * 60)
    print(" KẾT LUẬN: Circuit Breaker bảo vệ hệ thống qua 3 pha:")
    print("   1. Phát hiện lỗi liên tiếp  -> Ngắt mạch (OPEN)")
    print("   2. Fail-fast trong timeout   -> Không đè thêm server")
    print("   3. Thăm dò + tự phục hồi    -> HALF_OPEN -> CLOSED")
    print("=" * 60)