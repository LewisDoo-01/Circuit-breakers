import logging
import math
import sys
import threading
import time
from enum import Enum
from typing import Any, Callable, NamedTuple, Optional, Tuple, Type

# Logger cấp module. KHÔNG dùng print() trong code thư viện: print() ghi thẳng ra
# stdout và sẽ ném UnicodeEncodeError trên console cp1252 (mặc định của Windows).
# Ngoại lệ đó xảy ra NGAY TRONG đường đi của request, sau khi state đã đổi, và nó
# thay thế luôn exception gốc (ConnectionError) mà caller đang chờ đợi.
# logging thì nuốt lỗi encoding trong Handler.handleError() -> không bao giờ làm
# hỏng luồng xử lý. NullHandler để thư viện im lặng nếu ứng dụng chưa cấu hình log.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Ngoại lệ ném ra khi mạch không cho request đi qua (Fail-fast).

    Thuộc tính `reason` cho biết vì sao bị chặn:
        "OPEN"            - mạch đang ngắt, chưa hết reset_timeout.
        "HALF_OPEN_BUSY"  - đang có 1 probe chạy, các request còn lại fail nhanh.
    """

    def __init__(self, message: str, reason: str = "OPEN"):
        super().__init__(message)
        self.reason = reason


class _Admission(NamedTuple):
    """Vé vào cửa do critical section #1 cấp, mang theo generation lúc được nhận."""

    generation: int
    is_probe: bool


# Sentinel cho chế độ thủ công của record_success()/record_failure():
# "bỏ qua kiểm tra stale, tự suy ra is_probe từ trạng thái hiện tại".
_MANUAL = object()


class CircuitBreaker:
    """Circuit Breaker an toàn đa luồng (thread-safe).

    Bất biến quan trọng:
      * Lock KHÔNG BAO GIỜ được giữ trong lúc fn() chạy -> N request ở trạng thái
        CLOSED vẫn chạy song song N chiều, không bị tuần tự hoá.
      * Ở HALF_OPEN chỉ đúng MỘT probe được đi qua; phần còn lại fail nhanh.
      * Kết quả của một "thế hệ" (generation) mạch đã bị thay thế sẽ bị bỏ qua,
        nên một response cũ về muộn không thể đóng nhầm mạch.

    Lưu ý: breaker KHÔNG thể huỷ một probe bị treo. Nó chỉ ngừng chờ và ngừng để
    probe đó đại diện cho mạch (xem probe_timeout_seconds). Caller vẫn phải tự
    đặt timeout I/O cho fn.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout_seconds: float = 5.0,
        success_threshold: int = 2,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        *,
        probe_timeout_seconds: Optional[float] = None,
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.success_threshold = success_threshold
        self.expected_exceptions = expected_exceptions
        # Mặc định: probe không được giữ chỗ lâu hơn chính khoảng chờ giữa 2 lần
        # probe, nếu không nó lại thành một dạng "đói tài nguyên" khác.
        self.probe_timeout_seconds = (
            reset_timeout_seconds if probe_timeout_seconds is None else probe_timeout_seconds
        )

        # RLock bảo vệ TOÀN BỘ state bên dưới.
        self._lock = threading.RLock()
        self._monotonic = time.monotonic
        self._wall = time.time

        self._state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self._generation = 0  # epoch, chỉ tăng, không bao giờ dùng lại
        self._probe_in_flight = False
        self._probe_deadline = math.inf

        # Hai mốc thời gian TÁCH BIỆT:
        #   _opened_at        - đồng hồ ĐƠN ĐIỆU, dùng để tính reset_timeout.
        #                       time.time() bị NTP chỉnh giật lùi có thể khiến mạch
        #                       mở vĩnh viễn hoặc probe quá sớm.
        #   last_state_change - giờ treo tường, chỉ để hiển thị/log (giữ tương thích).
        self._opened_at = self._monotonic()
        self.last_state_change = self._wall()

    # ------------------------------------------------------------------
    # Đọc trạng thái
    # ------------------------------------------------------------------
    @property
    def state(self) -> CircuitState:
        """Trạng thái hiện tại (chỉ đọc). Có thu hồi luôn probe treo quá hạn."""
        logs = []
        with self._lock:
            msg = self._locked_expire_probe_if_needed(self._monotonic())
            if msg:
                logs.append(msg)
            current = self._state
        for m in logs:
            logger.info(m)
        return current

    def snapshot(self) -> dict:
        """Chụp toàn bộ state trong MỘT critical section (dùng cho test/giám sát).

        Đọc rời từng thuộc tính công khai có thể thấy trạng thái không nhất quán
        vì thread khác đang sửa dở.
        """
        with self._lock:
            return {
                "state": self._state,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "generation": self._generation,
                "probe_in_flight": self._probe_in_flight,
                "last_state_change": self.last_state_change,
            }

    def _ready_to_probe(self) -> bool:
        """Đã hết reset_timeout để thăm dò chưa (tính trên đồng hồ đơn điệu)."""
        with self._lock:
            return (self._monotonic() - self._opened_at) >= self.reset_timeout_seconds

    # ------------------------------------------------------------------
    # Chuyển trạng thái — caller PHẢI đang giữ _lock
    # ------------------------------------------------------------------
    def _locked_enter_open(self, now: float) -> None:
        self._generation += 1  # mọi công việc đang bay đều bị thay thế
        self._state = CircuitState.OPEN
        self.success_count = 0
        self._probe_in_flight = False
        self._probe_deadline = math.inf
        self._opened_at = now
        self.last_state_change = self._wall()
        # KHÔNG reset failure_count: giữ đúng hành vi cũ (demo in "2/2").

    def _locked_enter_closed(self, now: float) -> None:
        self._generation += 1
        self._state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self._probe_in_flight = False
        self._probe_deadline = math.inf
        self.last_state_change = self._wall()

    def _locked_enter_half_open(self, now: float) -> None:
        # KHÔNG tăng generation: ở OPEN không có request nào được nhận, nên không
        # có việc đang bay để vô hiệu hoá. Đây là phần tiếp nối của cùng thế hệ.
        self._state = CircuitState.HALF_OPEN
        self.success_count = 0
        self._probe_in_flight = False
        self._probe_deadline = math.inf
        self.last_state_change = self._wall()

    def _locked_expire_probe_if_needed(self, now: float) -> Optional[str]:
        """Thu hồi vé của probe treo quá hạn, coi như probe thất bại.

        Không có thread nền, không timer: dọn lười ngay tại các điểm vào critical
        section. Nếu thiếu bước này, một probe treo sẽ khoá HALF_OPEN vĩnh viễn.
        """
        if (
            self._state is CircuitState.HALF_OPEN
            and self._probe_in_flight
            and now >= self._probe_deadline
        ):
            self.failure_count += 1
            self._locked_enter_open(now)
            return "[CIRCUIT] Probe treo quá hạn -> Quay lại OPEN"
        return None

    # ------------------------------------------------------------------
    # Ghi nhận kết quả
    # ------------------------------------------------------------------
    def _on_result(self, generation: Any, is_probe: Optional[bool], ok: bool) -> None:
        logs = []
        with self._lock:
            now = self._monotonic()
            msg = self._locked_expire_probe_if_needed(now)
            if msg:
                logs.append(msg)

            manual = generation is _MANUAL
            if not manual and generation != self._generation:
                # KẾT QUẢ CŨ (stale): bỏ qua hoàn toàn. Không đụng counters, không
                # đụng state, không trả vé probe (vé đó thuộc thế hệ khác).
                pass
            else:
                if manual:
                    is_probe = self._state is CircuitState.HALF_OPEN
                if ok:
                    logs.extend(self._locked_record_success(now, bool(is_probe), manual))
                else:
                    logs.extend(self._locked_record_failure(now, bool(is_probe), manual))

        for m in logs:
            logger.info(m)

    def _locked_record_success(self, now: float, is_probe: bool, manual: bool):
        logs = []
        if self._state is CircuitState.HALF_OPEN:
            self.success_count += 1
            if not manual:
                self._probe_in_flight = False
                self._probe_deadline = math.inf
            if self.success_count >= self.success_threshold:
                self._locked_enter_closed(now)
                logs.append("[CIRCUIT] Phục hồi thành công -> Chuyển về CLOSED")
        elif self._state is CircuitState.CLOSED:
            self.failure_count = 0
        return logs

    def _locked_record_failure(self, now: float, is_probe: bool, manual: bool):
        logs = []
        self.failure_count += 1
        if self._state is CircuitState.HALF_OPEN:
            # Probe thất bại -> lập tức quay lại OPEN (enter_open tự trả vé probe).
            self._locked_enter_open(now)
            logs.append("[CIRCUIT] Probe thất bại -> Quay lại OPEN")
        elif (
            self._state is CircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            self._locked_enter_open(now)
            logs.append(
                f"[CIRCUIT] Vượt ngưỡng {self.failure_threshold} lỗi -> Chuyển sang OPEN"
            )
        return logs

    def _abandon_probe(self, adm: _Admission) -> None:
        """Trả vé probe mà KHÔNG đụng counters/state (ngoại lệ ngoài dự kiến)."""
        with self._lock:
            if (
                adm.generation == self._generation
                and self._state is CircuitState.HALF_OPEN
                and self._probe_in_flight
            ):
                self._probe_in_flight = False
                self._probe_deadline = math.inf

    def record_success(self):
        """Ghi nhận thành công theo trạng thái hiện tại (chế độ thủ công).

        Dành cho demo/bài tập. Đường đi được hỗ trợ khi chạy đa luồng là call().
        """
        self._on_result(_MANUAL, None, ok=True)

    def record_failure(self):
        """Ghi nhận thất bại theo trạng thái hiện tại (chế độ thủ công)."""
        self._on_result(_MANUAL, None, ok=False)

    # ------------------------------------------------------------------
    # Đường đi chính
    # ------------------------------------------------------------------
    def call(self, fn: Callable, *args, **kwargs) -> Any:
        # --- Critical section #1: xét vé vào cửa ---
        # Việc kiểm tra OPEN và chiếm vé probe nằm TRONG CÙNG một critical section.
        # Đó chính là điều dập tắt cảnh 20 thread cùng lao vào downstream đã chết.
        logs = []
        deny: Optional[CircuitOpenError] = None
        adm: Optional[_Admission] = None

        with self._lock:
            now = self._monotonic()
            msg = self._locked_expire_probe_if_needed(now)
            if msg:
                logs.append(msg)

            if self._state is CircuitState.OPEN:
                if (now - self._opened_at) < self.reset_timeout_seconds:
                    deny = CircuitOpenError(
                        "Circuit is OPEN - Fast fail để bảo vệ downstream service.",
                        reason="OPEN",
                    )
                else:
                    self._locked_enter_half_open(now)
                    logs.append("[CIRCUIT] Hết timeout -> Chuyển sang HALF_OPEN để thăm dò")

            if deny is None:
                if self._state is CircuitState.HALF_OPEN:
                    if self._probe_in_flight:
                        deny = CircuitOpenError(
                            "Circuit is HALF_OPEN - đã có 1 probe đang chạy, "
                            "fail-fast các request còn lại.",
                            reason="HALF_OPEN_BUSY",
                        )
                    else:
                        self._probe_in_flight = True
                        self._probe_deadline = now + self.probe_timeout_seconds
                        adm = _Admission(self._generation, True)
                else:
                    adm = _Admission(self._generation, False)

        # --- Ngoài lock: đẩy log, rồi fail nhanh nếu bị từ chối ---
        for m in logs:
            logger.info(m)
        if deny is not None:
            # Ném NGOÀI khối try bên dưới. Nếu ném bên trong, với mặc định
            # expected_exceptions=(Exception,) mạch sẽ tự tính cú fail-fast của
            # chính nó thành một lỗi downstream, và 19 request bị chặn sẽ thổi
            # phồng failure_count.
            raise deny

        assert adm is not None

        # --- Phase B: chạy fn() KHÔNG giữ lock ---
        settled = False
        try:
            result = fn(*args, **kwargs)
        except self.expected_exceptions as e:
            settled = True
            self._on_result(adm.generation, adm.is_probe, ok=False)
            raise e
        else:
            settled = True
            self._on_result(adm.generation, adm.is_probe, ok=True)
            return result
        finally:
            # Ngoại lệ NGOÀI expected_exceptions (kể cả BaseException như
            # KeyboardInterrupt) không tính là lỗi mạch — giữ đúng ngữ nghĩa cũ —
            # nhưng vẫn phải trả lại vé probe, nếu không HALF_OPEN kẹt vĩnh viễn.
            if adm.is_probe and not settled:
                self._abandon_probe(adm)


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
    except (ConnectionError, TimeoutError):
        return "[FALLBACK] Lỗi kết nối - kích hoạt fallback chain."


def print_status():
    """In trạng thái hiện tại của circuit breaker."""
    snap = breaker.snapshot()
    state_icons = {
        CircuitState.CLOSED: "CLOSED    (cho request đi qua bình thường)",
        CircuitState.OPEN: "OPEN      (chặn mọi request - fail fast)",
        CircuitState.HALF_OPEN: "HALF_OPEN (cho 1 request thăm dò)",
    }
    print(f"    State: {state_icons[snap['state']]}")
    print(f"    Failures: {snap['failure_count']}/{breaker.failure_threshold}")


def _setup_demo_output():
    """Bật UTF-8 cho console demo.

    Console Windows mặc định là cp1252, không encode nổi tiếng Việt có dấu ->
    print() sẽ ném UnicodeEncodeError. Chỉ làm ở khối demo, không làm lúc import,
    để không giành quyền cấu hình I/O của ứng dụng dùng module này.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # nỗ lực tối đa; demo vẫn chạy dù không đổi được encoding
    logging.basicConfig(level=logging.INFO, format="%(message)s")


if __name__ == "__main__":
    _setup_demo_output()

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
