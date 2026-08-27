import asyncio
import os
import sys

import pandas as pd
from google import genai
from openai import AsyncOpenAI
from ragas.embeddings import GoogleEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, Faithfulness
from tqdm import tqdm

# Số mẫu chấm song song. Bản cũ `await` tuần tự trong vòng lặp nên N mẫu = N lần
# chờ nối tiếp; với một bộ dữ liệu thật thì đó là hàng chục phút chờ vô ích, vì
# phần lớn thời gian chỉ là đợi mạng. Đặt trần để không đâm vào rate limit.
MAX_CONCURRENCY = 4

# Chuẩn bị dữ liệu mẫu theo format của Ragas
data_samples = {
    "question": [
        "Thời hạn hoàn tiền của tôi là bao lâu?",
        "Công ty có hỗ trợ giao hàng hỏa tốc không?",
    ],
    "answer": [
        "Chính sách hoàn tiền là trong vòng 90 ngày kể từ khi mua.",  # Sai thực tế (Hallucination)
        "Có, chúng tôi hỗ trợ giao hàng hỏa tốc nội thành trong 2 giờ.",  # Đúng thực tế
    ],
    "contexts": [
        ["Quy định công ty: Thời hạn hoàn tiền tối đa là 30 ngày."],
        ["Dịch vụ vận chuyển: Giao hàng hỏa tốc nội thành nhận hàng trong 2 giờ."],
    ],
}


def build_metrics():
    """Khởi tạo LLM judge + embeddings.

    Tách khỏi cấp module để việc `import eval_ragas` không tự tạo client và gọi
    API — bản cũ chạy toàn bộ đánh giá ngay khi import.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            'Thiếu biến môi trường GOOGLE_API_KEY. '
            'Đặt bằng: export GOOGLE_API_KEY="your-key-here"'
        )

    # Collections.ascore() cần async client. Gemini native (genai.Client) là sync,
    # nên LLM đi qua OpenAI-compatible endpoint; embeddings vẫn dùng google-genai.
    llm_client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    llm = llm_factory("gemini-2.5-flash", client=llm_client, max_tokens=4096)
    embeddings = GoogleEmbeddings(client=genai.Client(api_key=api_key))

    return Faithfulness(llm=llm), AnswerRelevancy(llm=llm, embeddings=embeddings)


async def _score_one(faithfulness_metric, relevancy_metric,
                     question, answer, contexts, sem, pbar):
    """Chấm một mẫu. Một mẫu lỗi không được làm hỏng cả lượt chạy."""
    async with sem:
        row = {
            "user_input": question,
            "faithfulness": None,
            "answer_relevancy": None,
            "error": None,
        }
        try:
            faith, rel = await asyncio.gather(
                faithfulness_metric.ascore(
                    user_input=question,
                    response=answer,
                    retrieved_contexts=contexts,
                ),
                relevancy_metric.ascore(user_input=question, response=answer),
            )
            row["faithfulness"] = faith.value
            row["answer_relevancy"] = rel.value
        except Exception as e:
            # Bản cũ không bắt lỗi: một mẫu hỏng là mất trắng toàn bộ kết quả.
            row["error"] = f"{type(e).__name__}: {e}"
        finally:
            pbar.update(2)
        return row


async def evaluate_samples(faithfulness_metric, relevancy_metric) -> list[dict]:
    samples = list(
        zip(
            data_samples["question"],
            data_samples["answer"],
            data_samples["contexts"],
        )
    )
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    with tqdm(total=len(samples) * 2, desc="Evaluating") as pbar:
        return await asyncio.gather(
            *(
                _score_one(faithfulness_metric, relevancy_metric,
                           question, answer, contexts, sem, pbar)
                for question, answer, contexts in samples
            )
        )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    faithfulness_metric, relevancy_metric = build_metrics()
    rows = asyncio.run(evaluate_samples(faithfulness_metric, relevancy_metric))
    frame = pd.DataFrame(rows)
    print(frame)

    failed = frame["error"].notna().sum()
    if failed:
        print(f"\n{failed}/{len(frame)} mẫu chấm lỗi.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
