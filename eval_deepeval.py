from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
from deepeval.models import GeminiModel
from deepeval.test_case import LLMTestCase

# Dữ liệu thực tế cần đánh giá
input_query = "Thời hạn hoàn tiền của tôi là bao lâu?"
actual_output = "Chính sách hoàn tiền của công ty là trong vòng 90 ngày."
retrieval_context = ["Quy định công ty: Thời hạn hoàn tiền tối đa là 30 ngày cho mọi đơn hàng."]

# 1. Khởi tạo TestCase
test_case = LLMTestCase(
    input=input_query,
    actual_output=actual_output,
    retrieval_context=retrieval_context
)

# 2. Khởi tạo metric với Gemini làm LLM-as-a-Judge (cần GOOGLE_API_KEY)
eval_model = GeminiModel(model="gemini-2.5-flash")
faithfulness_metric = FaithfulnessMetric(threshold=0.7, model=eval_model)

# 3. Đo lường
faithfulness_metric.measure(test_case)

print(f"Faithfulness Score: {faithfulness_metric.score}")  # Sẽ trả về ~ 0.0 hoặc rất thấp
print(f"Đạt SLO không: {faithfulness_metric.is_successful()}")
print(f"Lý do vi phạm: {faithfulness_metric.reason}")
