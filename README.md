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
| `state_machine.py` | Circuit Breaker — state machine 3 trạng thái (CLOSED → OPEN → HALF_OPEN) |
| `semantic_cache.py` | Semantic Cache dùng Gemini Embedding — cache theo nghĩa, không theo exact match |
| `cache.py` | Cache nâng cao — in-memory + Redis, có guardrail privacy & false hit detection |
| `fallback_ladder.py` | Fallback Ladder — chuỗi provider dự phòng khi model chính sập |
| `jitter.py` | Exponential Backoff + Full Jitter — retry thông minh tránh thundering herd |
| `quanlity_guardrail.py` | Quality Guardrail — chặn hallucination dù HTTP 200 (Silent Degradation) |
| `eval_deepeval.py` | Đánh giá Faithfulness bằng DeepEval + Gemini |
| `eval_ragas.py` | Đánh giá Faithfulness + Answer Relevancy bằng Ragas + Gemini |

## Yêu cầu

- Python 3.10+
- Google API Key (cho embedding & LLM evaluation)

## Cài đặt

```bash
python -m venv venv
source venv/bin/activate
pip install numpy google-genai deepeval ragas datasets pandas openai
```

## Chạy

```bash
export GOOGLE_API_KEY="your-key-here"

# Circuit Breaker demo
python state_machine.py

# Semantic Cache (gọi Gemini Embedding API)
python semantic_cache.py

# Fallback Ladder
python fallback_ladder.py

# Quality Guardrail (giả lập, không cần API)
python quanlity_guardrail.py

# Exponential Backoff + Jitter (không cần API)
python jitter.py

# Evaluation với Gemini (cần GOOGLE_API_KEY)
python eval_deepeval.py
python eval_ragas.py
```

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
Retry với thời gian chờ tăng theo lũy thừa, thêm random (jitter) để nhiều client không retry đồng loạt.
