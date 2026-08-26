import os
from dataclasses import dataclass
import time
from typing import List, Optional, Tuple

import numpy as np
from google import genai


@dataclass
class CacheEntry:
    query: str
    embedding: np.ndarray
    response: str
    created_at: float


class SemanticCache:

    def __init__(self, similarity_threshold: float = 0.88, ttl_seconds: float = 3600.0):
        self.threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.cache_store: List[CacheEntry] = []

        self._genai_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

        # Các chỉ số giám sát (Metrics)
        self.total_requests = 0
        self.hits = 0
        self.misses = 0

    def _get_embedding(self, text: str) -> np.ndarray:
        """Tạo vector embedding chuẩn hóa bằng Google Gemini Embedding API.

        Model: gemini-embedding-2 (hỗ trợ đa ngôn ngữ).
        Output đã L2-normalized nên cosine similarity = dot product.
        """
        result = self._genai_client.models.embed_content(
            model="gemini-embedding-2",
            contents=text,
        )
        vec = np.array(result.embeddings[0].values)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def _cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Tính Cosine Similarity giữa 2 vector đã chuẩn hóa."""
        return float(np.dot(vec_a, vec_b))

    def lookup(self, user_query: str) -> Tuple[Optional[str], float]:
        """Bước 1 & 2: Embed query và Vector Search tìm kiếm trong Cache."""
        self.total_requests += 1
        query_vec = self._get_embedding(user_query)
        current_time = time.time()

        best_match: Optional[CacheEntry] = None
        highest_sim = -1.0

        # Lọc các entry chưa hết hạn TTL
        valid_entries = [
            entry
            for entry in self.cache_store
            if (current_time - entry.created_at) < self.ttl_seconds
        ]
        self.cache_store = valid_entries

        for entry in self.cache_store:
            sim = self._cosine_similarity(query_vec, entry.embedding)
            if sim > highest_sim:
                highest_sim = sim
                best_match = entry

        # Bước 3: So khớp với Threshold (HIT hoặc MISS)
        if best_match and highest_sim >= self.threshold:
            self.hits += 1
            return best_match.response, highest_sim

        self.misses += 1
        return None, highest_sim

    def store(self, user_query: str, response: str):
        """Lưu câu trả lời mới vào Cache sau khi gọi LLM."""
        query_vec = self._get_embedding(user_query)
        self.cache_store.append(
            CacheEntry(
                query=user_query,
                embedding=query_vec,
                response=response,
                created_at=time.time(),
            )
        )

    def get_hit_rate(self) -> float:
        return (self.hits / self.total_requests) if self.total_requests > 0 else 0.0


# ---------------------------------------------------------
# Giả lập LLM Gateway tích hợp Semantic Cache
# ---------------------------------------------------------
def call_expensive_llm(prompt: str) -> str:
    print(f"   [LLM Provider] Đang tốn token để sinh câu trả lời cho: '{prompt}'...")
    return f"Hướng dẫn giải quyết: Bạn hãy vào Cài đặt -> Bảo mật để xử lý '{prompt}'."


def handle_user_request(cache: SemanticCache, user_query: str) -> str:
    print(f"\n>> Người dùng gửi query: '{user_query}'")

    # 1. Tra cứu trong Cache
    cached_reply, score = cache.lookup(user_query)

    if cached_reply:
        print(f"   [CACHE HIT] (Cosine Sim: {score:.3f} >= {cache.threshold}) -> Phản hồi tức thì 0ms, 0 token.")
        return cached_reply

    # 2. CACHE MISS: Gọi LLM và ghi đè vào cache
    print(f"   [CACHE MISS] (Cosine Sim: {score:.3f} < {cache.threshold}) -> Chuyển request lên LLM.")
    fresh_reply = call_expensive_llm(user_query)
    cache.store(user_query, fresh_reply)
    return fresh_reply


# --- Thử nghiệm chạy thực tế ---
if __name__ == "__main__":
    semantic_cache = SemanticCache(similarity_threshold=0.85, ttl_seconds=600)

    # Lần 1: Chưa có trong cache -> CACHE MISS (Gọi LLM)
    handle_user_request(
        semantic_cache, "Làm thế nào để quên mật khẩu và lấy lại tài khoản?"
    )

    # Lần 2: Query khác từ ngữ nhưng đồng nghĩa (Semantically equivalent) -> CACHE HIT
    handle_user_request(semantic_cache, "Quên password lấy lại tài khoản thế nào?")

    # Lần 3: Query hoàn toàn khác ý định -> CACHE MISS (Ngăn chặn False Hit)
    handle_user_request(semantic_cache, "Tôi muốn xóa tài khoản")

    print(f"\n--- Thống kê ---")
    print(f"Tổng requests: {semantic_cache.total_requests}")
    print(f"Cache Hit Rate: {semantic_cache.get_hit_rate() * 100:.1f}%")