"""Vector database and embedding management service using Qdrant in-memory mode."""

import contextlib
import uuid
from typing import Any

from app.coddy.graphrag.schemas.graphrag import SparseVector, VectorItem, VectorsExport
from app.coddy.utils.services.embeddinggemma_service import EmbeddingGemmaService
from app.coddy.utils.services.fastembed_service import FastEmbedService


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    k_constant: int = 60,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Merges multiple ranked lists of hits using Reciprocal Rank Fusion (RRF)."""
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for r_list in ranked_lists:
        for rank, item in enumerate(r_list, start=1):
            item_id = item.get("id") or str(item.get("properties", {}).get("id", ""))
            if not item_id:
                continue
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k_constant + rank))
            if item_id not in items:
                items[item_id] = item

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    fused = []
    for s_id in sorted_ids[:top_k]:
        entry = dict(items[s_id])
        entry["score"] = round(scores[s_id], 6)
        fused.append(entry)
    return fused


class VectorService:
    """Embedded in-memory Qdrant runtime with BM25 and BM42 sparse vector collections and dense vector support."""

    def __init__(
        self,
        fastembed_service: FastEmbedService | None = None,
        dense_service: EmbeddingGemmaService | None = None,
    ):
        self.fastembed = fastembed_service or FastEmbedService()
        self.dense_service = dense_service or EmbeddingGemmaService()
        self._client = None
        self._memory_store: dict[str, list[dict[str, Any]]] = {
            "DocChunk": [],
            "Fact": [],
        }
        self._init_qdrant()

    def _init_qdrant(self) -> None:
        try:
            from qdrant_client import QdrantClient, models

            self._client = QdrantClient(":memory:")
            for coll in ("DocChunk", "Fact"):
                self._client.create_collection(
                    collection_name=coll,
                    vectors_config={},
                    sparse_vectors_config={
                        "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF),
                        "bm42": models.SparseVectorParams(),
                    },
                )
        except Exception:
            self._client = None

    def upsert_chunk(
        self,
        chunk_id: str,
        properties: dict[str, Any],
        sparse_vectors: dict[str, Any],
    ) -> None:
        """Inserts or updates a document chunk with BM25/BM42 sparse vectors."""
        clean_sparse: dict[str, dict[str, list[Any]]] = {}
        for name, s_vec in sparse_vectors.items():
            if hasattr(s_vec, "indices") and hasattr(s_vec, "values"):
                clean_sparse[name] = {
                    "indices": [int(i) for i in s_vec.indices],
                    "values": [float(v) for v in s_vec.values],
                }
            elif isinstance(s_vec, dict):
                clean_sparse[name] = {
                    "indices": [int(i) for i in s_vec.get("indices", [])],
                    "values": [float(v) for v in s_vec.get("values", [])],
                }

        if self._client is not None:
            try:
                from qdrant_client import models

                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))
                clean_props = dict(properties)
                clean_props["id"] = chunk_id
                q_vectors = {
                    name: models.SparseVector(indices=vec["indices"], values=vec["values"])
                    for name, vec in clean_sparse.items()
                }
                self._client.upsert(
                    collection_name="DocChunk",
                    points=[models.PointStruct(id=point_id, vector=q_vectors, payload=clean_props)],
                )
            except Exception:
                pass

        item = {"id": chunk_id, "properties": properties, "sparse_vectors": clean_sparse}
        self._memory_store["DocChunk"] = [c for c in self._memory_store["DocChunk"] if c["id"] != chunk_id]
        self._memory_store["DocChunk"].append(item)

    def upsert_fact(
        self,
        fact_id: str,
        properties: dict[str, Any],
        sparse_vectors: dict[str, Any],
    ) -> None:
        """Inserts or updates a fact with BM25/BM42 sparse vectors."""
        clean_sparse: dict[str, dict[str, list[Any]]] = {}
        for name, s_vec in sparse_vectors.items():
            if hasattr(s_vec, "indices") and hasattr(s_vec, "values"):
                clean_sparse[name] = {
                    "indices": [int(i) for i in s_vec.indices],
                    "values": [float(v) for v in s_vec.values],
                }
            elif isinstance(s_vec, dict):
                clean_sparse[name] = {
                    "indices": [int(i) for i in s_vec.get("indices", [])],
                    "values": [float(v) for v in s_vec.get("values", [])],
                }

        if self._client is not None:
            try:
                from qdrant_client import models

                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, fact_id))
                clean_props = dict(properties)
                clean_props["id"] = fact_id
                q_vectors = {
                    name: models.SparseVector(indices=vec["indices"], values=vec["values"])
                    for name, vec in clean_sparse.items()
                }
                self._client.upsert(
                    collection_name="Fact",
                    points=[models.PointStruct(id=point_id, vector=q_vectors, payload=clean_props)],
                )
            except Exception:
                pass

        item = {"id": fact_id, "properties": properties, "sparse_vectors": clean_sparse}
        self._memory_store["Fact"] = [f for f in self._memory_store["Fact"] if f["id"] != fact_id]
        self._memory_store["Fact"].append(item)

    def search_chunks(self, sparse_query: dict[str, Any], using: str = "bm42", limit: int = 5) -> list[dict[str, Any]]:
        """Performs sparse similarity search (BM25 or BM42) on DocChunk collection."""
        if self._client is not None:
            try:
                from qdrant_client import models

                indices = sparse_query.get("indices", [])
                values = sparse_query.get("values", [])
                res = self._client.query_points(
                    collection_name="DocChunk",
                    query=models.SparseVector(indices=indices, values=values),
                    using=using,
                    limit=limit,
                )
                return [
                    {
                        "id": pt.payload.get("id", str(pt.id)),
                        "properties": pt.payload,
                        "score": float(pt.score),
                    }
                    for pt in res.points
                ]
            except Exception:
                pass

        return [
            {"id": item["id"], "properties": item["properties"], "score": 1.0}
            for item in self._memory_store["DocChunk"][:limit]
        ]

    def search_facts(
        self,
        sparse_query: dict[str, Any],
        using: str = "bm42",
        entity_type: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Performs sparse similarity search (BM25 or BM42) on Fact collection."""
        if self._client is not None:
            try:
                from qdrant_client import models

                indices = sparse_query.get("indices", [])
                values = sparse_query.get("values", [])
                query_filter = None
                if entity_type:
                    query_filter = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="fact_type",
                                match=models.MatchValue(value=entity_type),
                            )
                        ]
                    )
                res = self._client.query_points(
                    collection_name="Fact",
                    query=models.SparseVector(indices=indices, values=values),
                    using=using,
                    query_filter=query_filter,
                    limit=limit,
                )
                return [
                    {
                        "id": pt.payload.get("id", str(pt.id)),
                        "properties": pt.payload,
                        "score": float(pt.score),
                    }
                    for pt in res.points
                ]
            except Exception:
                pass

        results = []
        for item in self._memory_store["Fact"]:
            if entity_type:
                item_type = str(item["properties"].get("fact_type", "")).lower()
                if entity_type.lower() not in item_type:
                    continue
            results.append({"id": item["id"], "properties": item["properties"], "score": 1.0})
        return results[:limit]

    def export_vectors(self, commit_sha: str) -> VectorsExport:
        """Exports all collections and sparse vectors into VectorsExport schema."""
        collections_data: dict[str, list[VectorItem]] = {}
        for coll_name in ("DocChunk", "Fact"):
            items: list[VectorItem] = []
            if self._client is not None:
                try:
                    records, _ = self._client.scroll(
                        collection_name=coll_name,
                        with_vectors=True,
                        with_payload=True,
                        limit=10000,
                    )
                    for r in records:
                        p_id = str(r.payload.get("id", str(r.id))) if r.payload else str(r.id)
                        s_vecs: dict[str, SparseVector] = {}
                        if isinstance(r.vector, dict):
                            for k, v in r.vector.items():
                                s_vecs[k] = SparseVector(
                                    indices=[int(i) for i in getattr(v, "indices", [])],
                                    values=[float(val) for val in getattr(v, "values", [])],
                                )
                        items.append(VectorItem(id=p_id, properties=r.payload or {}, sparse_vectors=s_vecs))
                except Exception:
                    pass

            if not items:
                for it in self._memory_store.get(coll_name, []):
                    s_vecs = {
                        k: SparseVector(indices=v.get("indices", []), values=v.get("values", []))
                        for k, v in it.get("sparse_vectors", {}).items()
                    }
                    items.append(VectorItem(id=it["id"], properties=it["properties"], sparse_vectors=s_vecs))

            collections_data[coll_name] = items

        return VectorsExport(version="1.0", commit_sha=commit_sha, collections=collections_data)

    def import_vectors(self, export: VectorsExport) -> int:
        """Restores sparse vectors and collections from VectorsExport."""
        total = 0
        for coll_name, items in export.collections.items():
            for it in items:
                s_map = {k: {"indices": v.indices, "values": v.values} for k, v in it.sparse_vectors.items()}
                if coll_name == "DocChunk":
                    self.upsert_chunk(it.id, it.properties, s_map)
                elif coll_name == "Fact":
                    self.upsert_fact(it.id, it.properties, s_map)
                total += 1
        return total

    def get_stats(self) -> dict[str, int]:
        """Returns count of vectorized items in Qdrant collections."""
        chunks = 0
        facts = 0
        if self._client is not None:
            try:
                chunks = self._client.count(collection_name="DocChunk").count
                facts = self._client.count(collection_name="Fact").count
                return {"chunks": chunks, "facts": facts}
            except Exception:
                pass
        return {
            "chunks": len(self._memory_store.get("DocChunk", [])),
            "facts": len(self._memory_store.get("Fact", [])),
        }

    def close(self) -> None:
        """Shuts down the embedded Qdrant client."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None
