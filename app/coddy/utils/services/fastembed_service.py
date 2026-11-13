"""Fastembed in-memory service for BM25 and BM42 sparse representations."""

import hashlib
import re
from typing import Any

BM25_MODEL_NAME = "Qdrant/bm25"
BM42_MODEL_NAME = "Qdrant/bm42-all-minilm-l6-v2-attentions"


class FastEmbedService:
    """Service managing Fastembed sparse embedding models and vector generation."""

    def __init__(self):
        self._bm25_model: Any = None
        self._bm42_model: Any = None

    def get_bm25_model(self) -> Any:
        """Lazily initializes and caches the Fastembed BM25 sparse model."""
        if self._bm25_model is None:
            try:
                from fastembed import SparseTextEmbedding

                self._bm25_model = SparseTextEmbedding(model_name=BM25_MODEL_NAME)
            except Exception:
                self._bm25_model = None
        return self._bm25_model

    def get_bm42_model(self) -> Any:
        """Lazily initializes and caches the Fastembed BM42 sparse model."""
        if self._bm42_model is None:
            try:
                from fastembed import SparseTextEmbedding

                self._bm42_model = SparseTextEmbedding(model_name=BM42_MODEL_NAME)
            except Exception:
                self._bm42_model = None
        return self._bm42_model

    @staticmethod
    def compute_deterministic_sparse(text: str) -> dict[str, Any]:
        """Generates a deterministic bag-of-words sparse vector used if fastembed is offline."""
        words = re.findall(r"\w+", text.lower())
        if not words:
            return {"indices": [0], "values": [0.0]}
        freqs: dict[int, float] = {}
        for w in words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16) % 1_000_000
            freqs[h] = freqs.get(h, 0.0) + 1.0
        sorted_items = sorted(freqs.items(), key=lambda x: x[0])
        return {
            "indices": [int(k) for k, _ in sorted_items],
            "values": [float(v) for _, v in sorted_items],
        }

    def get_sparse_embeddings(self, texts: list[str]) -> list[dict[str, dict[str, list[Any]]]]:
        """Generates BM25 and BM42 passage sparse embeddings for a list of document texts."""
        if not texts:
            return []

        bm25 = self.get_bm25_model()
        bm42 = self.get_bm42_model()

        results: list[dict[str, dict[str, list[Any]]]] = []

        bm25_embeds = None
        bm42_embeds = None

        if bm25 is not None:
            try:
                bm25_embeds = list(bm25.passage_embed(texts))
            except Exception:
                bm25_embeds = None

        if bm42 is not None:
            try:
                bm42_embeds = list(bm42.passage_embed(texts))
            except Exception:
                bm42_embeds = None

        for idx, text in enumerate(texts):
            entry: dict[str, dict[str, list[Any]]] = {}

            if bm25_embeds and idx < len(bm25_embeds):
                emb = bm25_embeds[idx]
                entry["bm25"] = {
                    "indices": [int(i) for i in emb.indices],
                    "values": [float(v) for v in emb.values],
                }
            else:
                entry["bm25"] = self.compute_deterministic_sparse(text)

            if bm42_embeds and idx < len(bm42_embeds):
                emb = bm42_embeds[idx]
                entry["bm42"] = {
                    "indices": [int(i) for i in emb.indices],
                    "values": [float(v) for v in emb.values],
                }
            else:
                entry["bm42"] = self.compute_deterministic_sparse(text)

            results.append(entry)

        return results

    def get_query_sparse_embedding(self, query: str, model_type: str = "bm42") -> dict[str, list[Any]]:
        """Generates query sparse vector for BM25 or BM42."""
        clean_type = model_type.lower().strip()
        model = self.get_bm25_model() if clean_type == "bm25" else self.get_bm42_model()

        if model is not None:
            try:
                q_emb = list(model.query_embed(query))[0]
                return {
                    "indices": [int(i) for i in q_emb.indices],
                    "values": [float(v) for v in q_emb.values],
                }
            except Exception:
                pass

        return self.compute_deterministic_sparse(query)

    def get_query_sparse_embeddings(self, query: str) -> dict[str, dict[str, list[Any]]]:
        """Generates both BM25 and BM42 query sparse vectors."""
        return {
            "bm25": self.get_query_sparse_embedding(query, model_type="bm25"),
            "bm42": self.get_query_sparse_embedding(query, model_type="bm42"),
        }


# Global singleton instance and function wrappers
_default_fastembed_service = FastEmbedService()


def get_sparse_embeddings(texts: list[str]) -> list[dict[str, dict[str, list[Any]]]]:
    return _default_fastembed_service.get_sparse_embeddings(texts)


def get_query_sparse_embedding(query: str, model_type: str = "bm42") -> dict[str, list[Any]]:
    return _default_fastembed_service.get_query_sparse_embedding(query, model_type=model_type)


def get_query_sparse_embeddings(query: str) -> dict[str, dict[str, list[Any]]]:
    return _default_fastembed_service.get_query_sparse_embeddings(query)
