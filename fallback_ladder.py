import json
import logging
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fallback_ladder")

# Schema đầu ra mong muốn
EXPECTED_SCHEMA = {"intent": str, "confidence": float, "reply": str}


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


def get_from_cache(prompt: str) -> Optional[Dict[str, Any]]:
    """Bậc 4: Tầng Semantic / Exact Cache."""
    cache_store = {
        "hoan_tien": {
            "intent": "refund_request",
            "confidence": 0.70,
            "reply": "Chính sách hoàn tiền của chúng tôi áp dụng trong 30 ngày.",
        }
    }
    return cache_store.get("hoan_tien")


# ---------------------------------------------------------
# Bộ điều phối Fallback Ladder (Graceful Degradation)
# ---------------------------------------------------------
class FallbackLadderAgent:

    def _validate_schema(self, data: Any) -> bool:
        """Kiểm tra tính tương thích tính năng (Feature Compatibility) của output."""
        if not isinstance(data, dict):
            return False
        return all(key in data for key in EXPECTED_SCHEMA)

    def execute(self, user_prompt: str) -> Dict[str, Any]:
        ladder_steps = [
            ("Tier 1: Primary Best Model", lambda: call_primary_model(user_prompt)),
            ("Tier 2: Backup Provider", lambda: call_backup_provider(user_prompt)),
            ("Tier 3: Smaller/Cheaper Model", lambda: call_smaller_model(user_prompt)),
        ]

        # 1. Thử lần lượt các tầng Model
        for tier_name, run_func in ladder_steps:
            try:
                logger.info(f"Đang thử: {tier_name}...")
                result = run_func()
                if self._validate_schema(result):
                    return {"source": tier_name, "status": "success", "data": result}
                logger.warning(f"{tier_name} trả về sai Schema. Xuống bậc tiếp theo.")
            except Exception as e:
                logger.warning(f"{tier_name} thất bại ({e}). Xuống bậc tiếp theo.")

        # 2. Bậc 4: Thử lấy từ Cached Response
        logger.info("Đang thử: Tier 4: Cached Response...")
        cached_data = get_from_cache(user_prompt)
        if cached_data and self._validate_schema(cached_data):
            return {
                "source": "Tier 4: Cache",
                "status": "degraded_cached",
                "data": cached_data,
            }

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
if __name__ == "__main__":
    agent = FallbackLadderAgent()
    response = agent.execute("Tôi muốn hoàn tiền đơn hàng")
    print("\n--- Kết quả trả về cuối cùng ---")
    print(json.dumps(response, indent=2, ensure_ascii=False))