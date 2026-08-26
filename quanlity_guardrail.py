import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_quality_monitor")


@dataclass
class QualityMetrics:
    http_status: int
    latency_seconds: float
    faithfulness_score: float  # Điểm bám sát context (0.0 -> 1.0)
    relevancy_score: float  # Điểm liên quan câu hỏi (0.0 -> 1.0)
    is_slo_violated: bool = False


class ProductionAgentGateway:

    def __init__(self, quality_slo_threshold: float = 0.75):
        self.slo_threshold = quality_slo_threshold

    def _call_primary_llm(self, query: str, context: str) -> str:
        """Giả lập Agent phản hồi HTTP 200 thành công nhưng nội dung bị Silent Degradation."""
        # Ví dụ: Model bị drift hoặc prompt lỗi, LLM bịa thông tin không có trong context
        return "Chính sách hoàn tiền của công ty hiện tại là trong vòng 90 ngày kể từ khi mua."

    def _evaluate_faithfulness(
        self, query: str, context: str, response: str
    ) -> float:
        """LLM-as-a-Judge hoặc Heuristic Checker kiểm tra độ trung thực (Faithfulness).

        Kiểm tra xem nội dung câu trả lời có được suy ra trực tiếp từ context
        hay không.
        """
        # Giả lập: Context quy định là 30 ngày, nhưng response trả lời là 90 ngày
        # Trong thực tế, bước này gọi model nhỏ (như Flash/Mini) hoặc thư viện (Ragas, DeepEval)
        if "90 ngày" in response and "30 ngày" in context:
            return 0.20  # Điểm rất thấp vì trả lời sai lệch tài liệu

        return 0.95

    def _evaluate_relevancy(self, query: str, response: str) -> float:
        """Đo lường mức độ trả lời đúng trọng tâm câu hỏi."""
        return 0.85

    def handle_request(
        self, query: str, retrieved_context: str
    ) -> Dict[str, Any]:
        # 1. Gọi Agent chính
        response = self._call_primary_llm(query, retrieved_context)
        http_status = 200  # Về mặt hạ tầng: Hoàn toàn không có Exception / Lỗi 5xx

        # 2. Đánh giá chất lượng Online (Quality SLO Checking)
        faithfulness = self._evaluate_faithfulness(
            query, retrieved_context, response
        )
        relevancy = self._evaluate_relevancy(query, response)

        # Tính điểm chất lượng tổng hợp
        quality_score = (faithfulness * 0.7) + (relevancy * 0.3)
        is_violated = quality_score < self.slo_threshold

        metrics = QualityMetrics(
            http_status=http_status,
            latency_seconds=1.2,
            faithfulness_score=faithfulness,
            relevancy_score=relevancy,
            is_slo_violated=is_violated,
        )

        # 3. Kích hoạt cảnh báo & Fallback khi phát hiện Silent Degradation
        if metrics.is_slo_violated:
            logger.warning(
                f"[ALERT: QUALITY SLO VIOLATION] "
                f"HTTP Status: {metrics.http_status} (OK) | "
                f"Quality Score: {quality_score:.2f} < Threshold: {self.slo_threshold} | "
                f"Faithfulness: {metrics.faithfulness_score}"
            )

            # Phục hồi: Trả về câu trả lời an toàn hoặc chuyển sang Fallback Model
            return {
                "status": "degraded_quality_detected",
                "output": "Xin lỗi, hiện tại tôi không thể đưa ra câu trả lời chính xác từ tài liệu. Vui lòng liên hệ nhân viên hỗ trợ.",
                "metrics": metrics.__dict__,
            }

        return {
            "status": "success",
            "output": response,
            "metrics": metrics.__dict__,
        }


# --- Thử nghiệm chạy thực tế ---
if __name__ == "__main__":
    gateway = ProductionAgentGateway(quality_slo_threshold=0.75)

    user_query = "Thời hạn hoàn tiền là bao lâu?"
    doc_context = "Quy định công ty: Thời hạn hoàn tiền tối đa là 30 ngày cho mọi đơn hàng hợp lệ."

    result = gateway.handle_request(user_query, doc_context)
    print("\nKết quả trả về cho Client:")
    print(json.dumps(result, indent=2, ensure_ascii=False))