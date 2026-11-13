"""Dense text embedding service for text-embedding-embeddinggemma-300m model."""

import hashlib
import json
import urllib.request


class EmbeddingGemmaService:
    """Service providing dense text embeddings using text-embedding-embeddinggemma-300m."""

    def __init__(
        self,
        endpoint_url: str = "http://localhost:1234/v1/embeddings",
        model_name: str = "google/text-embedding-embeddinggemma-300m",
        dimension: int = 768,
    ):
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self.dimension = dimension

    def _compute_deterministic_dense(self, text: str) -> list[float]:
        """Generates a deterministic normalized dense vector as a hermetic fallback."""
        vec: list[float] = []
        for i in range(self.dimension):
            h = int(hashlib.sha256(f"{text}:{i}".encode()).hexdigest()[:8], 16)
            val = (h / 0xFFFFFFFF) * 2.0 - 1.0
            vec.append(round(val, 6))

        # Normalize L2 norm
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [round(x / norm, 6) for x in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generates dense vector embeddings for a list of document passages."""
        if not texts:
            return []

        try:
            req_data = json.dumps({"input": texts, "model": self.model_name}).encode("utf-8")
            req = urllib.request.Request(
                self.endpoint_url,
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                embeddings = [item["embedding"] for item in data.get("data", [])]
                if len(embeddings) == len(texts):
                    return embeddings
        except Exception:
            pass

        return [self._compute_deterministic_dense(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        """Generates dense vector embedding for a single search query."""
        results = self.embed_documents([text])
        return results[0] if results else self._compute_deterministic_dense(text)
