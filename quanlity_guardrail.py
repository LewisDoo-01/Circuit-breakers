import json
import logging
import random
import sys
import time
from dataclasses import asdict, dataclass
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
    evaluated: bool = True  # False nếu request này không được lấy mẫu chấm điểm


class ProductionAgentGateway:

    def __init__(
        self,
        quality_slo_threshold: float = 0.75,
        eval_sample_rate: float = 1.0,
        faithfulness_weight: float = 0.7,
        relevancy_weight: float = 0.3,
        rng: Optional[random.Random] = None,
    ):
        """
        eval_sample_rate: tỉ lệ request được chấm chất lượng online (0.0 -> 1.0).
            Mặc định 1.0 cho demo dễ quan sát. Production nên hạ xuống (0.05
            chẳng hạn) vì mỗi lần chấm là thêm một lời gọi LLM nữa.
        faithfulness_weight / relevancy_weight: trọng số hợp điểm, trước đây là
            hằng số 0.7/0.3 nằm cứng trong code.
        """
        if not 0.0 <= eval_sample_rate <= 1.0:
            raise ValueError(f"eval_sample_rate phải trong [0,1], nhận {eval_sample_rate}")
        total = faithfulness_weight + relevancy_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Tổng trọng số phải bằng 1.0, nhận {total}")

        self.slo_threshold = quality_slo_threshold
        self.eval_sample_rate = eval_sample_rate
        self.faithfulness_weight = faithfulness_weight
        self.relevancy_weight = relevancy_weight
        self._rng = rng or random.Random()

    def _should_evaluate(self) -> bool:
        if self.eval_sample_rate >= 1.0:
            return True
        if self.eval_sample_rate <= 0.0:
            return False
        return self._rng.random() < self.eval_sample_rate

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
        started = time.perf_counter()

        # 1. Gọi Agent chính
        response = self._call_primary_llm(query, retrieved_context)
        http_status = 200  # Về mặt hạ tầng: Hoàn toàn không có Exception / Lỗi 5xx

        # 2. Đánh giá chất lượng Online (Quality SLO Checking)
        #    Chấm điểm là một lời gọi LLM NỮA. Chấm 100% request nghĩa là nhân
        #    đôi (hoặc nhân ba) cả chi phí lẫn độ trễ của mọi câu trả lời. Hệ
        #    thống thật lấy mẫu một tỉ lệ nhỏ, hoặc chấm bất đồng bộ sau khi đã
        #    trả lời. Đánh đổi phải nói rõ: request KHÔNG được lấy mẫu sẽ không
        #    được bảo vệ — lấy mẫu dùng để phát hiện drift ở mức hệ thống, không
        #    phải để chặn từng câu trả lời hỏng.
        evaluated = self._should_evaluate()
        if evaluated:
            faithfulness = self._evaluate_faithfulness(
                query, retrieved_context, response
            )
            relevancy = self._evaluate_relevancy(query, response)
            quality_score = (
                faithfulness * self.faithfulness_weight
                + relevancy * self.relevancy_weight
            )
            is_violated = quality_score < self.slo_threshold
        else:
            faithfulness = relevancy = quality_score = float("nan")
            is_violated = False

        metrics = QualityMetrics(
            http_status=http_status,
            latency_seconds=time.perf_counter() - started,
            faithfulness_score=faithfulness,
            relevancy_score=relevancy,
            is_slo_violated=is_violated,
            evaluated=evaluated,
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
                "metrics": asdict(metrics),
            }

        return {
            "status": "success",
            "output": response,
            "metrics": asdict(metrics),
        }


# --- Thử nghiệm chạy thực tế ---


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
    gateway = ProductionAgentGateway(quality_slo_threshold=0.75)

    user_query = "Thời hạn hoàn tiền là bao lâu?"
    doc_context = "Quy định công ty: Thời hạn hoàn tiền tối đa là 30 ngày cho mọi đơn hàng hợp lệ."

    result = gateway.handle_request(user_query, doc_context)
    print("\nKết quả trả về cho Client:")
    print(json.dumps(result, indent=2, ensure_ascii=False))