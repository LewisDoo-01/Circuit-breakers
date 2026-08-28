# Day 25 — Circuit Breakers & Reliability Patterns for LLM Systems

Bộ mã nguồn minh họa các design pattern bảo vệ hệ thống LLM/Agent trong production: Circuit Breaker, Semantic Cache, Fallback Ladder, Quality Guardrail, và Exponential Backoff with Jitter.

## Sơ đồ tổng quan

```
User Request
     │
     ▼
┌──────────────────┐    HIT     ┌────────────────────┐
│  Semantic Cache  │ ─────────> │  Trả kết quả cũ    │
│  (0 token, 0ms)  │            │  (miễn phí, nhanh) │
└────────┬─────────┘            └────────────────────┘
         │ MISS
         ▼
┌──────────────────┐   OPEN     ┌────────────────────┐
│ Circuit Breaker  │ ─────────> │  Fallback Ladder   │
│ (state machine)  │            │  (model dự phòng)  │
└────────┬─────────┘            └────────────────────┘
         │ CLOSED/HALF_OPEN
         ▼
┌──────────────────┐   Fail     ┌────────────────────┐
│  LLM Provider    │ ─────────> │  Retry + Jitter    │
│  (GPT/Claude/    │            │  (exponential      │
│   Gemini)        │            │   backoff)         │
└────────┬─────────┘            └────────────────────┘
         │ Success
         ▼
┌──────────────────┐  Vi phạm   ┌────────────────────┐
│ Quality Guardrail│ ─────────> │  Chặn + Fallback   │
│ (Faithfulness +  │   SLO      │  (không trả sai)   │
│  Relevancy)      │            └────────────────────┘
└────────┬─────────┘
         │ Đạt SLO
         ▼
    Response → User
```

## Cấu trúc file

| File | Nội dung |
|------|----------|
| `state_machine.py` | Circuit Breaker — state machine 3 trạng thái (CLOSED → OPEN → HALF_OPEN), thread-safe |
| `semantic_cache.py` | Semantic Cache dùng Gemini Embedding — cache theo nghĩa, không theo exact match |
| `cache.py` | Cache nâng cao — in-memory + Redis, có guardrail privacy & false-hit detection |
| `fallback_ladder.py` | Fallback Ladder — chuỗi provider dự phòng khi model chính sập, có timeout mỗi tầng |
| `jitter.py` | Exponential Backoff + Full Jitter — retry thông minh tránh thundering herd |
| `quality_guardrail.py` | Quality Guardrail — chặn hallucination dù HTTP 200 (Silent Degradation) |
| `gateway.py` | **Gateway hợp nhất** — nối cả 5 pattern trên thành một `handle_request()` duy nhất |
| `eval_deepeval.py` | Đánh giá Faithfulness bằng DeepEval + Gemini |
| `eval_ragas.py` | Đánh giá Faithfulness + Answer Relevancy bằng Ragas + Gemini |
| `tests/` | Bộ test hồi quy cho toàn bộ các file trên (`pytest`) |

## Yêu cầu

- Python 3.10+
- Google API Key — chỉ cần cho `semantic_cache.py`, `eval_ragas.py`, `eval_deepeval.py`
  (các file còn lại, kể cả `gateway.py`, chạy được mà không cần API key nào)
- Redis — chỉ cần nếu dùng `SharedRedisCache` trong `cache.py` (xem `docker-compose.yml`)

## Cài đặt

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # rồi điền GOOGLE_API_KEY vào .env
```

`requirements.txt` chia theo nhóm tính năng — đọc comment trong file để biết cài
gì là đủ cho nhu cầu của bạn (không phải mọi file trong repo cần mọi dependency).

## Chạy

```bash
export GOOGLE_API_KEY="your-key-here"   # chỉ cần cho 3 file có đánh dấu (*) dưới đây

# Không cần API key:
python state_machine.py        # Circuit Breaker
python fallback_ladder.py      # Fallback Ladder
python quality_guardrail.py    # Quality Guardrail
python jitter.py               # Exponential Backoff + Jitter
python gateway.py              # Gateway hợp nhất cả 5 pattern trên

# Cần GOOGLE_API_KEY (*):
python semantic_cache.py       # gọi Gemini Embedding API
python eval_deepeval.py        # Faithfulness qua DeepEval + Gemini
python eval_ragas.py           # Faithfulness + Answer Relevancy qua Ragas + Gemini
```

## Chạy test

```bash
pip install pytest
pytest tests/ -v
```

Test Redis (`tests/test_redis_cache.py`) tự động `skip` nếu không có Redis nào
đang chạy ở `localhost:6379` — không cần Redis vẫn chạy được toàn bộ phần còn lại.

## Khái niệm chính

### Circuit Breaker
Ngắt mạch khi downstream service lỗi liên tiếp, tránh đè thêm server đang quá tải. Tự phục hồi sau timeout.

### Semantic Cache
Dùng vector embedding so nghĩa câu hỏi. Câu hỏi đồng nghĩa nhưng khác chữ vẫn hit cache → tiết kiệm token + giảm latency.

### Fallback Ladder
Khi model chính sập, tự động chuyển xuống model rẻ hơn → semantic cache → static response. Đảm bảo luôn có câu trả lời.

### Quality Guardrail
HTTP 200 không có nghĩa câu trả lời đúng. Chấm faithfulness + relevancy online, chặn hallucination trước khi đến user.

### Exponential Backoff + Jitter
Retry với thời gian chờ tăng theo lũy thừa, thêm random (jitter) để nhiều client không retry đồng loạt. Chỉ retry lỗi TẠM THỜI (mất kết nối, timeout) — một API key sai thì có retry mấy lần cũng vẫn sai, chỉ tốn thời gian.

### Gateway hợp nhất (`gateway.py`)
5 pattern trên chỉ có giá trị đầy đủ khi phối hợp đúng cách với nhau — điều 5
demo độc lập không thể cho thấy. Ví dụ: **thứ tự ghép retry với circuit
breaker quyết định một sự cố lan rộng tới đâu**. Ghép sai (breaker bọc ngoài
retry), một request bị lỗi sẽ đấm vào server đang chết đủ `max_attempts` lần
trước khi breaker kịp nhận ra và ngắt mạch. Ghép đúng (retry bọc ngoài, breaker
ở trong — như `gateway.py` làm), ngay khi breaker mở, `CircuitOpenError` khiến
retry dừng lại tức khắc thay vì thử tiếp vào một mạch vừa báo "dừng". Đo được
trên cùng kịch bản: sai thứ tự = 10 lần gọi vào server chết, đúng thứ tự = 2
lần. Xem docstring đầu file `gateway.py` để biết chi tiết.
