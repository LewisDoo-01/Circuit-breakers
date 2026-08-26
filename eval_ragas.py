import asyncio
import os

import pandas as pd
from google import genai
from openai import AsyncOpenAI
from ragas.embeddings import GoogleEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, Faithfulness
from tqdm import tqdm

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

# Collections.ascore() cần async client. Gemini native (genai.Client) là sync,
# nên LLM đi qua OpenAI-compatible endpoint; embeddings vẫn dùng google-genai.
api_key = os.environ["GOOGLE_API_KEY"]
llm_client = AsyncOpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)
llm = llm_factory("gemini-2.5-flash", client=llm_client, max_tokens=4096)
embeddings = GoogleEmbeddings(client=genai.Client(api_key=api_key))

faithfulness_metric = Faithfulness(llm=llm)
relevancy_metric = AnswerRelevancy(llm=llm, embeddings=embeddings)


async def evaluate_samples() -> list[dict]:
    samples = list(
        zip(
            data_samples["question"],
            data_samples["answer"],
            data_samples["contexts"],
        )
    )
    total_evals = len(samples) * 2
    rows = []
    with tqdm(total=total_evals, desc="Evaluating") as pbar:
        for question, answer, contexts in samples:
            faith = await faithfulness_metric.ascore(
                user_input=question,
                response=answer,
                retrieved_contexts=contexts,
            )
            pbar.update(1)
            rel = await relevancy_metric.ascore(user_input=question, response=answer)
            pbar.update(1)
            rows.append(
                {
                    "user_input": question,
                    "faithfulness": faith.value,
                    "answer_relevancy": rel.value,
                }
            )
    return rows


print(pd.DataFrame(asyncio.run(evaluate_samples())))