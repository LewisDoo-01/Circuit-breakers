"""LLM Gateway — hợp nhất 5 pattern rời rạc trong repo thành MỘT pipeline.

Đúng sơ đồ trong README:

    User Request
        -> Semantic Cache      HIT  -> trả kết quả cũ (0 token, 0ms)
        -> MISS -> Circuit Breaker + Retry/Jitter bọc lời gọi model chính
                OPEN/hết retry -> Fallback Ladder (backup -> model nhỏ -> cache -> tĩnh)
        -> Quality Guardrail   vi phạm SLO -> chặn, KHÔNG cache câu trả lời sai
        -> lưu cache, trả lời

Trước file này, cả 5 pattern chỉ tồn tại như 5 demo độc lập — không file nào gọi
file nào. Ghép chúng lại lộ ra một tương tác mà không demo đơn lẻ nào cho thấy:

    THỨ TỰ GHÉP retry() VÀ breaker.call() QUYẾT ĐỊNH BLAST RADIUS CỦA MỘT SỰ CỐ.

        SAI:  breaker.call(lambda: retry(fn))     — breaker Ở NGOÀI
        ĐÚNG: retry(lambda: breaker.call(fn))     — breaker Ở TRONG

    Đo được trên 2 request liên tiếp, ngưỡng lỗi = 2, retry tối đa 5 lần:

        SAI : breaker chỉ thấy MỖI REQUEST là 1 lần thử (retry() nuốt hết 5 lần
              retry rồi mới trả kết quả cuối cho breaker). Server nhận đủ
              2 request x 5 retry = 10 lần gọi TRƯỚC KHI breaker kịp mở.

        ĐÚNG: mỗi lần retry đi qua breaker RIÊNG. Ngay khi breaker mở ở lần
              gọi thứ 2, retry() nhận về CircuitOpenError — mà CircuitOpenError
              KHÔNG nằm trong RETRYABLE_EXCEPTIONS=(ConnectionError, TimeoutError)
              của jitter.py — nên retry() dừng NGAY, không dùng nốt 3 lần còn lại.
              Server chỉ bị gọi 2 lần, không phải 10.

    Đây không phải trùng hợp: đó là lý do jitter.py lọc theo exception type thay
    vì `except Exception`, và lý do CircuitOpenError không kế thừa từ
    ConnectionError/TimeoutError. Hai bản vá độc lập (P1-5 lọc lỗi retry được,
    và thiết kế exception riêng cho circuit breaker) cộng lại giải quyết đúng vấn
    đề mà không cần thêm code nào — NẾU ghép đúng thứ tự.
"""
import logging
import random
import re
import sys
import threading
import time
from dataclasses import asdict
from typing import Any, Callable, Optional, Protocol, Tuple

from cache import ResponseCache, false_hit_reason
from jitter import RETRYABLE_EXCEPTIONS, retry_with_exponential_backoff_and_jitter
from quanlity_guardrail import QualityMetrics
from state_machine import CircuitBreaker, CircuitOpenError

# Không print() trong code thư viện — xem lý do ở state_machine.py (P0-1).
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class Cache(Protocol):
    """Kiểu cấu trúc (duck type) mà cả ResponseCache và SharedRedisCache đều
    thoả mãn sẵn — gateway không quan tâm cache nằm trong tiến trình hay trên
    Redis dùng chung."""

    def get(self, query: str) -> Tuple[Optional[str], float]: ...
    def set(self, query: str, value: str, metadata: Optional[dict] = None) -> None: ...


# "Cuộc gọi không thành công, xuống Fallback Ladder" chỉ nên áp dụng cho lỗi
# TẠM THỜI + tín hiệu "mạch đang mở" — KHÔNG phải mọi Exception. Một bug lập
# trình trong primary_llm_fn/backup_llm_fn (KeyError, TypeError do code của
# caller viết sai) không phải downstream đang quá tải; bắt nó ở đây rồi lặng lẽ
# chuyển sang Fallback Ladder sẽ biến một bug thành "hard_degraded" trong log —
# đúng loại chẩn đoán sai mà cả repo này tồn tại để dạy cách tránh (P1-5 ở
# jitter.py lọc lỗi retry được; #12 ở fallback_ladder.py đòi log nêu rõ lý do).
# Để bug thật nổ ra ngay tại đây thay vì bị nguỵ trang thành một sự cố hạ tầng.
DEGRADABLE_EXCEPTIONS = RETRYABLE_EXCEPTIONS + (CircuitOpenError,)

STATIC_FALLBACK_MESSAGE = (
    "Hệ thống tư vấn tự động đang quá tải. Yêu cầu của bạn đã được ghi nhận "
    "và gửi tới nhân viên hỗ trợ."
)
SAFE_REFUSAL_MESSAGE = (
    "Xin lỗi, hiện tại tôi không thể đưa ra câu trả lời chính xác từ tài liệu. "
    "Vui lòng liên hệ nhân viên hỗ trợ."
)

_WORD_RE = re.compile(r"[a-zA-Z0-9À-ỹ]+")


def _tokens(text: str) -> set:
    return set(_WORD_RE.findall(text.lower()))


# Ngưỡng overlap quan sát được trên các câu trả lời TRUNG THỰC thật (diễn đạt
# lại bằng từ khác) trong bộ ví dụ đo thử: 0.30-0.36 với ngưỡng độ dài token >=3
# ký tự. Overlap của câu lạc đề chỉ ~0.09-0.10. Hallucination CÙNG chủ đề lại có
# overlap gần bằng câu trung thực (~0.31-0.33) — overlap KHÔNG phân biệt được 2
# ca này, đó là lý do bước 1 phải dùng false_hit_reason() (tín hiệu nhị phân,
# đáng tin) thay vì chỉ dựa vào overlap (tín hiệu liên tục, nhiều nhiễu).
_OVERLAP_FULL_SCORE = 0.30
_MIN_TOKEN_LEN = 3


def _content_overlap(a: str, b: str) -> float:
    """Tỉ lệ token "nội dung" (>= 3 ký tự) của a cũng xuất hiện trong b.

    Lọc token ngắn để giảm nhiễu từ hư từ (là, có, từ, ty...) — không phải xử lý
    ngôn ngữ học chính xác, chỉ là một bộ lọc thô đủ dùng cho một heuristic không
    cần model.
    """
    content = {t for t in _tokens(a) if len(t) >= _MIN_TOKEN_LEN}
    if not content:
        return 0.0
    return len(content & _tokens(b)) / len(content)


def default_faithfulness(query: str, context: str, response: str) -> float:
    """Heuristic không cần model, dùng làm mặc định khi caller chưa gắn LLM-judge.

    Hai bước, đo bằng ví dụ thật (xem chú thích các hằng số ở trên):

    1. Tái dùng CHÍNH guardrail chống false-hit của cache.py (P0-3): "response
       có mâu thuẫn số liệu/phủ định/đối nghĩa với context không" chính là câu
       hỏi "response có bịa/lệch context không" — cùng một phép kiểm tra, khác
       chỗ áp dụng. Đã kiểm chứng bắt đúng ca số liệu (30 ngày -> 90 ngày) và
       ca phủ định (can cancel -> cannot cancel), điểm 0.1.
    2. Khi KHÔNG phát hiện mâu thuẫn, overlap nội dung giữa response và context
       phân biệt được câu trung thực (overlap cao, vì số liệu/thực thể cụ thể
       thường lặp lại nguyên văn dù diễn đạt khác) khỏi câu lạc đề hoàn toàn
       (overlap gần 0) — điều mà false_hit_reason() một mình không bắt được vì
       nó chỉ tìm MÂU THUẪN, không tìm "không liên quan".

    Đây vẫn là placeholder — production nên thay bằng LLM-as-judge hoặc thư
    viện (Ragas, DeepEval); xem eval_ragas.py / eval_deepeval.py trong repo.
    """
    if not context.strip():
        return 0.5  # không có context để đối chiếu — không thể khẳng định trung thực

    if false_hit_reason(response, context) is not None:
        return 0.1  # mâu thuẫn trực tiếp: số liệu/phủ định/đối nghĩa lệch context

    overlap = _content_overlap(response, context)
    return min(overlap / _OVERLAP_FULL_SCORE, 1.0) * 0.9


def default_relevancy(query: str, response: str) -> float:
    """Heuristic không cần model: overlap nội dung giữa câu hỏi và câu trả lời."""
    overlap = _content_overlap(query, response)
    return min(overlap / _OVERLAP_FULL_SCORE, 1.0) * 0.9


def _run_with_timeout(fn: Callable[[], Any], timeout: float, *, thread_name: str) -> Any:
    """Chạy fn() với trần thời gian; ném TimeoutError nếu quá hạn.

    Cùng mẫu daemon-thread-per-call như fallback_ladder._run_with_timeout (xem
    đó để biết vì sao KHÔNG dùng thread pool dùng chung: pool bị các lời gọi
    treo chiếm hết worker sẽ chặn luôn tầng tiếp theo dù nó hoàn toàn khoẻ mạnh).
    Lặp lại thay vì import trực tiếp để gateway.py không phụ thuộc vào một
    phương thức riêng (`_`-prefixed) của FallbackLadderAgent.
    """
    box: dict = {}

    def runner():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - chuyển nguyên vẹn cho caller
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True, name=thread_name)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise TimeoutError(f"vượt quá {timeout:.1f}s (đã bỏ chờ; luồng vẫn chạy nền)")
    if "error" in box:
        raise box["error"]
    return box["value"]


class LLMGateway:
    """Gateway hợp nhất cache, circuit breaker, retry+jitter, fallback ladder,
    và quality guardrail thành một `handle_request()` duy nhất.

    `primary_llm_fn` là bắt buộc; `backup_llm_fn`/`smaller_llm_fn` tuỳ chọn (bỏ
    trống thì fallback ladder chỉ còn cache + thông báo tĩnh). Mỗi hàm nhận
    `(query, context)` và trả về một chuỗi câu trả lời.
    """

    def __init__(
        self,
        primary_llm_fn: Callable[[str, str], str],
        *,
        backup_llm_fn: Optional[Callable[[str, str], str]] = None,
        smaller_llm_fn: Optional[Callable[[str, str], str]] = None,
        cache: Optional[Cache] = None,
        breaker: Optional[CircuitBreaker] = None,
        max_attempts: int = 3,
        base_delay: float = 0.2,
        max_delay: float = 2.0,
        attempt_timeout_seconds: Optional[float] = None,
        tier_timeout_seconds: float = 5.0,
        total_deadline_seconds: float = 15.0,
        quality_slo_threshold: float = 0.75,
        eval_sample_rate: float = 1.0,
        faithfulness_weight: float = 0.7,
        relevancy_weight: float = 0.3,
        faithfulness_fn: Callable[[str, str, str], float] = default_faithfulness,
        relevancy_fn: Callable[[str, str], float] = default_relevancy,
        rng: Optional[random.Random] = None,
    ):
        if not 0.0 <= eval_sample_rate <= 1.0:
            raise ValueError(f"eval_sample_rate phải trong [0,1], nhận {eval_sample_rate}")
        total_weight = faithfulness_weight + relevancy_weight
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError(f"Tổng trọng số phải bằng 1.0, nhận {total_weight}")

        self.primary_llm_fn = primary_llm_fn
        self.backup_llm_fn = backup_llm_fn
        self.smaller_llm_fn = smaller_llm_fn
        self.cache = cache if cache is not None else ResponseCache(
            ttl_seconds=3600, similarity_threshold=0.85
        )

        # expected_exceptions=RETRYABLE_EXCEPTIONS (không phải Exception mặc định
        # của CircuitBreaker): một bug lập trình trong primary_llm_fn (TypeError,
        # KeyError...) không phải là "downstream đang quá tải" — nó không nên vừa
        # bị breaker tính là lỗi mạch, vừa bị retry() thử lại như một trục trặc
        # tạm thời. Nó phải nổ ra ngay, giống lý do jitter.py lọc exception ở P1-5.
        self.breaker = breaker if breaker is not None else CircuitBreaker(
            failure_threshold=3,
            reset_timeout_seconds=5.0,
            success_threshold=2,
            expected_exceptions=RETRYABLE_EXCEPTIONS,
        )

        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.attempt_timeout_seconds = attempt_timeout_seconds
        self.tier_timeout_seconds = tier_timeout_seconds
        self.total_deadline_seconds = total_deadline_seconds

        self.quality_slo_threshold = quality_slo_threshold
        self.eval_sample_rate = eval_sample_rate
        self.faithfulness_weight = faithfulness_weight
        self.relevancy_weight = relevancy_weight
        self.faithfulness_fn = faithfulness_fn
        self.relevancy_fn = relevancy_fn
        self._rng = rng or random.Random()

        self._abandoned_lock = threading.Lock()
        self.abandoned_calls = 0  # lời gọi đã bỏ chờ nhưng luồng nền còn chạy

    # ------------------------------------------------------------------
    def _call_with_timeout(self, fn: Callable[[], Any], timeout: float) -> Any:
        try:
            return _run_with_timeout(fn, timeout, thread_name="gateway-call")
        except TimeoutError:
            with self._abandoned_lock:
                self.abandoned_calls += 1
            raise

    def _call_primary(self, query: str, context: str) -> str:
        """retry() BỌC NGOÀI breaker.call() — xem docstring module về thứ tự.

        Nếu `attempt_timeout_seconds` được đặt, mỗi lần thử còn được bọc thêm
        một trần thời gian bằng daemon thread. Điều này AN TOÀN cộng dồn với cơ
        chế generation-counter của CircuitBreaker (P0-2): nếu gateway bỏ chờ một
        lần thử đã treo, luồng nền của nó vẫn chạy tới khi xong và tự gọi
        breaker._on_result() — nhưng generation lúc đó đã lệch (mạch đã sang
        OPEN/HALF_OPEN khác) nên kết quả trễ bị coi là stale và bị bỏ qua, đúng
        như bất biến mà P0-2 đã chứng minh, không phải giả định mới.
        """

        def attempt():
            call = lambda: self.breaker.call(self.primary_llm_fn, query, context)
            if self.attempt_timeout_seconds is not None:
                return self._call_with_timeout(call, self.attempt_timeout_seconds)
            return call()

        return retry_with_exponential_backoff_and_jitter(
            attempt,
            max_attempts=self.max_attempts,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            retryable_exceptions=RETRYABLE_EXCEPTIONS,
        )

    def _run_fallback_ladder(
        self, query: str, context: str, started: float
    ) -> Tuple[Optional[str], Optional[str]]:
        """Tier 2 (backup) -> Tier 3 (model nhỏ) -> Tier 4 (cache) -> None.

        Mỗi tier có trần thời gian riêng VÀ chia sẻ một ngân sách thời gian tổng
        (xem fallback_ladder.py #11): một tier treo không được phép ngốn hết
        thời gian mà các tier lành mạnh phía sau đáng lẽ còn được thử.
        """
        tiers = []
        if self.backup_llm_fn is not None:
            tiers.append(("backup_provider", lambda: self.backup_llm_fn(query, context)))
        if self.smaller_llm_fn is not None:
            tiers.append(("smaller_model", lambda: self.smaller_llm_fn(query, context)))

        for name, fn in tiers:
            remaining = self.total_deadline_seconds - (time.monotonic() - started)
            if remaining <= 0:
                logger.warning(
                    "Hết ngân sách %.1fs cho cả thang. Bỏ qua các tầng còn lại.",
                    self.total_deadline_seconds,
                )
                break
            budget = min(self.tier_timeout_seconds, remaining)
            try:
                return self._call_with_timeout(fn, budget), name
            except Exception as e:
                logger.warning("%s thất bại (%s). Xuống bậc tiếp theo.", name, e)

        # Tier 4: kiểm lại chính cache đó. Vô ích nếu chỉ một request — nhưng
        # khi nhiều request trùng câu hỏi tới cùng lúc lúc cache còn lạnh
        # (cache stampede), request đi trước có thể đã ghi xong cache trong lúc
        # request này còn đang loay hoay ở Tier 1-3.
        cached, score = self.cache.get(query)
        if cached is not None:
            logger.info("Tier 4: Cache (stampede) hit, score=%.3f", score)
            return cached, "cache_stampede"

        return None, None

    def _should_evaluate(self) -> bool:
        if self.eval_sample_rate >= 1.0:
            return True
        if self.eval_sample_rate <= 0.0:
            return False
        return self._rng.random() < self.eval_sample_rate

    def _evaluate_quality(self, query: str, context: str, response: str) -> QualityMetrics:
        started = time.perf_counter()
        evaluated = self._should_evaluate()
        if evaluated:
            faithfulness = self.faithfulness_fn(query, context, response)
            relevancy = self.relevancy_fn(query, response)
            quality_score = (
                faithfulness * self.faithfulness_weight
                + relevancy * self.relevancy_weight
            )
            is_violated = quality_score < self.quality_slo_threshold
        else:
            faithfulness = relevancy = float("nan")
            is_violated = False

        return QualityMetrics(
            http_status=200,
            latency_seconds=time.perf_counter() - started,
            faithfulness_score=faithfulness,
            relevancy_score=relevancy,
            is_slo_violated=is_violated,
            evaluated=evaluated,
        )

    # ------------------------------------------------------------------
    def handle_request(self, query: str, context: str = "") -> dict:
        started = time.monotonic()

        # 1. CACHE — hit thì trả ngay, không chạm breaker/retry/guardrail.
        cached, score = self.cache.get(query)
        if cached is not None:
            return {
                "status": "cache_hit",
                "output": cached,
                "source": "cache",
                "cache_score": score,
            }

        # 2. CIRCUIT BREAKER + RETRY (retry Ở NGOÀI, breaker Ở TRONG — xem đầu file)
        source = "primary"
        response: Optional[str]
        try:
            response = self._call_primary(query, context)
        except DEGRADABLE_EXCEPTIONS as primary_error:
            logger.warning(
                "Primary LLM thất bại (%s). Chuyển sang Fallback Ladder.", primary_error
            )
            response, source = self._run_fallback_ladder(query, context, started)
            if response is None:
                return {
                    "status": "hard_degraded",
                    "output": STATIC_FALLBACK_MESSAGE,
                    "source": "static_fallback",
                }

        # 3. QUALITY GUARDRAIL — HTTP/luồng gọi có thể hoàn toàn "thành công"
        #    trong khi nội dung bịa đặt (Silent Degradation). Vi phạm SLO thì
        #    chặn và KHÔNG cache — cache một câu trả lời sai là nhân bản cái sai.
        metrics = self._evaluate_quality(query, context, response)
        if metrics.is_slo_violated:
            logger.warning(
                "[ALERT: QUALITY SLO VIOLATION] score < %.2f | nguồn=%s | "
                "faithfulness=%.2f — chặn, không cache.",
                self.quality_slo_threshold, source, metrics.faithfulness_score,
            )
            return {
                "status": "degraded_quality_detected",
                "output": SAFE_REFUSAL_MESSAGE,
                "source": source,
                "metrics": asdict(metrics),
            }

        # 4. Đạt SLO -> lưu cache rồi trả lời
        self.cache.set(query, response)
        return {
            "status": "success",
            "output": response,
            "source": source,
            "metrics": asdict(metrics),
        }


# ============================================================
# Demo: mô phỏng một sự cố toàn diện đi qua cả 5 pattern
# ============================================================
def _setup_demo_output():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logging.basicConfig(level=logging.INFO, format="  %(message)s")


if __name__ == "__main__":
    _setup_demo_output()

    print("=" * 68)
    print(" LLM GATEWAY DEMO - hợp nhất Cache + Breaker + Retry + Ladder + Guardrail")
    print("=" * 68)

    server_state = {"primary_down": True, "hallucinate": False}

    def primary_llm(query: str, context: str) -> str:
        if server_state["primary_down"]:
            raise ConnectionError("503 Service Unavailable")
        if server_state["hallucinate"]:
            return "Chính sách hoàn tiền của công ty là trong vòng 90 ngày kể từ khi mua."
        return "Chính sách hoàn tiền của công ty là trong vòng 30 ngày kể từ khi mua."

    def backup_llm(query: str, context: str) -> str:
        return "Theo nhà cung cấp dự phòng: hoàn tiền trong vòng 30 ngày."

    gateway = LLMGateway(
        primary_llm_fn=primary_llm,
        backup_llm_fn=backup_llm,
        max_attempts=3,
        base_delay=0.05,
        max_delay=0.1,
    )
    gateway.breaker.reset_timeout_seconds = 0.3
    gateway.breaker.success_threshold = 1  # 1 probe thành công là đủ đóng mạch (rõ ràng cho demo)

    context = "Quy định công ty: Thời hạn hoàn tiền tối đa là 30 ngày cho mọi đơn hàng hợp lệ."
    query_a = "Thời hạn hoàn tiền là bao lâu?"
    # Cố ý khác chủ đề diễn đạt với query_a (similarity đo được chỉ 0.20, dưới
    # ngưỡng cache 0.85) để Bước 2 chắc chắn là cache MISS thật, không phải
    # trúng cache của Bước 1 — nhưng vẫn đủ liên quan để không bị Guardrail
    # chặn vì lạc đề (relevancy đo được 0.90 với câu trả lời đúng).
    query_b = "Công ty có chính sách hoàn tiền khi khách hàng đổi ý không?"

    print("\n[Bước 1] Primary LLM đang sập -> Circuit Breaker mở -> Fallback Ladder")
    print("-" * 68)
    result = gateway.handle_request(query_a, context)
    print(f"  Request #1 (query_a, MISS): status={result['status']} source={result.get('source')}")
    print(f"    output: {result['output']}")

    result = gateway.handle_request(query_a, context)
    print(f"  Request #2 (query_a lần 2): status={result['status']} source={result.get('source')}")
    print(f"    output: {result['output']}")
    print(f"    -> phải là 'cache_hit': cache đứng TRƯỚC breaker, không quan tâm")
    print(f"       breaker đang OPEN hay không.")

    print(f"\n  Circuit breaker state: {gateway.breaker.snapshot()['state'].value}")

    print("\n[Bước 2] Server hồi phục, chờ reset_timeout, hỏi CÂU KHÁC (cache miss thật)")
    print("-" * 68)
    time.sleep(gateway.breaker.reset_timeout_seconds + 0.1)
    server_state["primary_down"] = False
    result = gateway.handle_request(query_b, context)
    print(f"  Request #3 (query_b, MISS): status={result['status']} source={result.get('source')}")
    print(f"    output: {result['output']}")
    print(f"    -> source phải là 'primary': breaker đã thăm dò (HALF_OPEN) và")
    print(f"       đóng lại thành công (CLOSED).")
    print(f"  Circuit breaker state: {gateway.breaker.snapshot()['state'].value}")

    print("\n[Bước 3] Hỏi lại query_b -> phải trúng cache, không gọi LLM")
    print("-" * 68)
    result = gateway.handle_request(query_b, context)
    print(f"  Request #4: status={result['status']} source={result.get('source')}")
    print(f"    output: {result['output']}")

    print("\n[Bước 4] Model bắt đầu 'bịa' (Silent Degradation, vẫn HTTP 200)")
    print("-" * 68)
    server_state["hallucinate"] = True
    other_query = "Công ty hoàn tiền trong thời hạn nào?"
    result = gateway.handle_request(other_query, context)
    print(f"  Request #5: status={result['status']} source={result.get('source')}")
    print(f"    output: {result['output']}")
    print(f"    metrics: {result.get('metrics')}")
    cached_after_bad, _ = gateway.cache.get(other_query)
    print(f"    -> câu trả lời bịa đặt CÓ bị cache không? {cached_after_bad is not None}")

    print("\n" + "=" * 68)
    print(" KẾT LUẬN: 5 pattern phối hợp qua MỘT request duy nhất")
    print("   Cache -> Breaker(+Retry đúng thứ tự) -> Fallback Ladder -> Guardrail")
    print("=" * 68)
