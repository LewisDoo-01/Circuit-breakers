import json
import logging
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fallback_ladder")

# Schema đầu ra mong muốn — nguồn sự thật DUY NHẤT về tên trường và kiểu.
EXPECTED_SCHEMA = {"intent": str, "confidence": float, "reply": str}

# Ràng buộc miền giá trị, khai báo tách khỏi logic kiểm tra.
# confidence = 42.0 đúng kiểu float nhưng không phải một độ tin cậy.
NUMERIC_RANGES = {"confidence": (0.0, 1.0)}


# ---------------------------------------------------------
# Giả lập các tầng dịch vụ (Providers / Cache)
# ---------------------------------------------------------
def call_primary_model(prompt: str) -> Dict[str, Any]:
    """Bậc 1: Best Model (GPT-4o / Claude 3.5 Sonnet)."""
    # Giả lập nhà cung cấp chính bị sập / timeout
    raise TimeoutError("OpenAI API 504 Gateway Timeout")


def call_backup_provider(prompt: str) -> Dict[str, Any]:
    """Bậc 2: Backup Provider có năng lực tương đương (Gemini 1.5 Pro)."""
    # Giả lập provider backup cũng bị rate limit hoặc trả sai schema
    raise ConnectionError("Google Vertex AI 429 Rate Limit Exceeded")


def call_smaller_model(prompt: str) -> Dict[str, Any]:
    """Bậc 3: Model nhỏ/nhanh/rẻ hơn (GPT-4o-mini / Gemini Flash)."""
    # Model nhỏ hoạt động bình thường và hỗ trợ JSON output
    return {
        "intent": "refund_request",
        "confidence": 0.82,
        "reply": "Tôi có thể hỗ trợ bạn xử lý yêu cầu hoàn tiền ngay bây giờ.",
    }


_CACHE_STORE = {
    "hoan_tien": {
        "intent": "refund_request",
        "confidence": 0.70,
        "reply": "Chính sách hoàn tiền của chúng tôi áp dụng trong 30 ngày.",
    }
}

# Từ khoá -> mục cache. Đứng thay cho một vector index thật.
_CACHE_KEYWORDS = {
    "hoan_tien": ("hoàn tiền", "hoan tien", "refund", "trả lại tiền"),
}


def get_from_cache(prompt: str) -> Optional[Dict[str, Any]]:
    """Bậc 4: Tầng Semantic / Exact Cache.

    Bản cũ bỏ qua hoàn toàn tham số `prompt` và luôn trả về mục "hoan_tien".
    Nghĩa là MỌI câu hỏi — kể cả "phí giao hàng bao nhiêu?" — đều nhận được câu
    trả lời về chính sách hoàn tiền. Một cache trả nhầm còn tệ hơn không có cache:
    nó biến một sự cố thành một câu trả lời sai trông rất tự tin.
    """
    normalized = prompt.lower()
    for entry_id, keywords in _CACHE_KEYWORDS.items():
        if any(kw in normalized for kw in keywords):
            return _CACHE_STORE[entry_id]
    return None


# ---------------------------------------------------------
# Bộ điều phối Fallback Ladder (Graceful Degradation)
# ---------------------------------------------------------
class FallbackLadderAgent:
    """Thang dự phòng có chặn thời gian.

    Ladder chỉ có ý nghĩa nếu tầng hỏng *báo lỗi nhanh*. Không có timeout, một
    Tier 1 bị treo 60 giây sẽ giữ người dùng chờ đủ 60 giây TRƯỚC KHI thang bắt
    đầu thử Tier 2 — và tổng thời gian xấu nhất là tổng timeout của mọi tầng
    cộng lại. Vì vậy cần hai mức chặn:
        tier_timeout_seconds   - trần cho MỖI tầng
        total_deadline_seconds - trần cho CẢ thang

    Giới hạn cần nói rõ: Python không huỷ được một thread đang chạy. Timeout ở
    đây nghĩa là "ngừng chờ", không phải "ngừng chạy" — lời gọi bị bỏ rơi vẫn
    tiếp tục ở luồng nền cho tới khi tự kết thúc. Đếm chúng qua `abandoned_calls`.
    """

    def __init__(
        self,
        tier_timeout_seconds: float = 5.0,
        total_deadline_seconds: float = 15.0,
    ):
        self.tier_timeout_seconds = tier_timeout_seconds
        self.total_deadline_seconds = total_deadline_seconds
        self._abandoned_lock = threading.Lock()
        self.abandoned_calls = 0  # số lời gọi đã bỏ rơi nhưng luồng còn chạy nền

    def close(self) -> None:
        """Giữ cho tương thích API. Không còn pool để đóng."""
        return None

    def _run_with_timeout(self, fn: Callable[[], Any], timeout: float) -> Any:
        """Chạy fn() với trần thời gian; ném TimeoutError nếu quá hạn.

        Dùng MỘT luồng daemon riêng cho mỗi lời gọi, cố ý KHÔNG dùng thread pool
        dùng chung. Với pool có N worker, các lời gọi bị bỏ rơi vẫn chiếm worker
        cho tới khi chúng tự kết thúc; chỉ cần N lời gọi treo là hàng đợi đầy, và
        tầng tiếp theo — dù hoàn toàn khoẻ mạnh — không bao giờ được chạy. Nó chỉ
        nằm xếp hàng rồi "hết giờ", và log sẽ báo "tầng X thất bại" trong khi tầng
        X chưa từng được gọi. Một chẩn đoán sai còn tệ hơn không có chẩn đoán.

        Luồng daemon không chặn tiến trình thoát. Đổi lại, số luồng có thể tăng
        khi provider treo kéo dài, nên `abandoned_calls` được đếm để giám sát.
        """
        box: Dict[str, Any] = {}

        def runner():
            try:
                box["value"] = fn()
            except BaseException as exc:  # noqa: BLE001 - chuyển nguyên vẹn cho caller
                box["error"] = exc

        thread = threading.Thread(target=runner, daemon=True, name="ladder-tier")
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            with self._abandoned_lock:
                self.abandoned_calls += 1
            raise TimeoutError(
                f"vượt quá {timeout:.1f}s (đã bỏ chờ; luồng vẫn chạy nền)"
            )

        if "error" in box:
            raise box["error"]
        return box["value"]

    def _schema_violation(self, data: Any) -> Optional[str]:
        """Trả về mô tả vi phạm schema đầu tiên, hoặc None nếu hợp lệ.

        Chỉ kiểm tra sự tồn tại của key là chưa đủ: cả điểm của fallback ladder
        là bắt được output méo mó từ model rẻ hơn. Một model nhỏ trả
        confidence="high" thay vì 0.82 sẽ lọt qua phép kiểm tra "key in data"
        rồi nổ ở tầng dưới, đúng nơi khó debug nhất.
        """
        if not isinstance(data, dict):
            return f"không phải dict (nhận được {type(data).__name__})"

        for field, expected in EXPECTED_SCHEMA.items():
            if field not in data:
                return f"thiếu trường '{field}'"
            value = data[field]

            # bool là subclass của int trong Python, nên True sẽ lọt qua phép
            # kiểm tra kiểu số nếu không loại nó ra trước.
            if isinstance(value, bool) and expected is not bool:
                return f"'{field}' là bool, cần {expected.__name__}"

            if expected is float:
                # Chấp nhận int thật (confidence=1 là JSON hợp lệ), không chấp nhận bool.
                if not isinstance(value, (int, float)):
                    return (
                        f"'{field}' sai kiểu: cần số, nhận được "
                        f"{type(value).__name__} ({value!r})"
                    )
            elif not isinstance(value, expected):
                return (
                    f"'{field}' sai kiểu: cần {expected.__name__}, nhận được "
                    f"{type(value).__name__} ({value!r})"
                )

            # Chuỗi rỗng đúng kiểu str nhưng vô dụng với người dùng.
            if expected is str and not value.strip():
                return f"'{field}' rỗng hoặc chỉ có khoảng trắng"

            low, high = NUMERIC_RANGES.get(field, (None, None))
            if low is not None and not (low <= value <= high):
                return f"'{field}'={value!r} ngoài khoảng [{low}, {high}]"

        return None

    def _validate_schema(self, data: Any) -> bool:
        """Dạng boolean của _schema_violation() (giữ tương thích API cũ)."""
        return self._schema_violation(data) is None

    def execute(self, user_prompt: str) -> Dict[str, Any]:
        ladder_steps = [
            ("Tier 1: Primary Best Model", lambda: call_primary_model(user_prompt)),
            ("Tier 2: Backup Provider", lambda: call_backup_provider(user_prompt)),
            ("Tier 3: Smaller/Cheaper Model", lambda: call_smaller_model(user_prompt)),
        ]

        # 1. Thử lần lượt các tầng Model, trong ngân sách thời gian tổng
        started = time.monotonic()
        for tier_name, run_func in ladder_steps:
            remaining = self.total_deadline_seconds - (time.monotonic() - started)
            if remaining <= 0:
                logger.warning(
                    "Hết ngân sách %.1fs cho cả thang. Bỏ qua các tầng model còn lại.",
                    self.total_deadline_seconds,
                )
                break
            budget = min(self.tier_timeout_seconds, remaining)
            try:
                logger.info(f"Đang thử: {tier_name} (trần {budget:.1f}s)...")
                result = self._run_with_timeout(run_func, budget)
                violation = self._schema_violation(result)
                if violation is None:
                    return {"source": tier_name, "status": "success", "data": result}
                # Nói RÕ trường nào sai và sai thế nào — đó là khác biệt giữa một
                # ladder debug được và một ladder không debug được.
                logger.warning(
                    f"{tier_name} trả về sai Schema: {violation}. Xuống bậc tiếp theo."
                )
            except Exception as e:
                logger.warning(f"{tier_name} thất bại ({e}). Xuống bậc tiếp theo.")

        # 2. Bậc 4: Thử lấy từ Cached Response
        logger.info("Đang thử: Tier 4: Cached Response...")
        cached_data = get_from_cache(user_prompt)
        if cached_data is not None:
            violation = self._schema_violation(cached_data)
            if violation is None:
                return {
                    "source": "Tier 4: Cache",
                    "status": "degraded_cached",
                    "data": cached_data,
                }
            logger.warning(f"Tier 4: Cache trả về sai Schema: {violation}.")

        # 3. Bậc 5: Static Fallback Message (Phương án an toàn cuối cùng)
        logger.error("Mọi tầng model & cache đều thất bại. Kích hoạt Static Fallback.")
        return {
            "source": "Tier 5: Static Fallback",
            "status": "hard_degraded",
            "data": {
                "intent": "unknown",
                "confidence": 0.0,
                "reply": "Hệ thống tư vấn tự động đang quá tải. Yêu cầu của bạn đã được ghi nhận và gửi tới nhân viên hỗ trợ.",
            },
        }


# --- Chạy thử nghiệm ---


def _setup_demo_output():
    """Bật UTF-8 cho console demo.

    Console Windows mặc định là cp1252, không encode nổi tiếng Việt có dấu ->
    print() sẽ ném UnicodeEncodeError và giết luôn demo. Chỉ làm ở khối demo,
    không làm lúc import, để không giành quyền cấu hình I/O của ứng dụng khác.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # nỗ lực tối đa; demo vẫn chạy dù không đổi được encoding


if __name__ == "__main__":
    _setup_demo_output()
    agent = FallbackLadderAgent()
    response = agent.execute("Tôi muốn hoàn tiền đơn hàng")
    print("\n--- Kết quả trả về cuối cùng ---")
    print(json.dumps(response, indent=2, ensure_ascii=False))