"""Primary GraphRAG service orchestrating cache, graph, and vector subsystems."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.coddy.graphrag.schemas.graphrag import IngestionStats
from app.coddy.graphrag.services.cache_service import CacheService
from app.coddy.graphrag.services.graph_service import (
    STRUCTURAL_FACT_TYPES,
    DoclingChunker,
    GraphService,
    PythonASTExtractor,
    extract_deterministic_mentions,
    is_excluded_path,
    resolve_intent_direction,
    resolve_outbound_verb,
    synthesize_fact_content,
)
from app.coddy.graphrag.services.vector_service import VectorService
from app.coddy.utils.services.falkordb_service import FalkorDBService
from app.coddy.utils.services.fastembed_service import get_sparse_embeddings


class GraphRAGService:
    """Main GraphRAG service managing knowledge graph ingestion, vectorization, and caching."""

    def __init__(
        self,
        cache_service: CacheService | None = None,
        graph_service: GraphService | None = None,
        vector_service: VectorService | None = None,
    ):
        self.cache_service = cache_service or CacheService()
        self.graph_service = graph_service or GraphService()
        self.vector_service = vector_service or VectorService()

    @property
    def falkor(self) -> FalkorDBService:
        return self.graph_service.falkor

    @property
    def qdrant(self) -> VectorService:
        return self.vector_service

    def get_stats(self) -> IngestionStats:
        fstats = self.graph_service.get_stats()
        vstats = self.vector_service.get_stats()
        return IngestionStats(
            nodes=fstats.get("nodes", 0),
            edges=fstats.get("edges", 0),
            chunks=vstats.get("chunks", 0),
            facts=vstats.get("facts", 0),
        )

    def load_cache(self, commit_sha: str) -> bool:
        cache_data = self.cache_service.load_cache(commit_sha)
        if cache_data is None:
            return False
        g_exp, v_exp = cache_data
        self.graph_service.import_graph(g_exp)
        self.vector_service.import_vectors(v_exp)
        return True

    def save_cache(self, commit_sha: str) -> tuple[Path, Path]:
        g_exp = self.graph_service.export_graph(commit_sha)
        v_exp = self.vector_service.export_vectors(commit_sha)
        return self.cache_service.save_cache(g_exp, v_exp, commit_sha)

    def run_ingestion_pipeline(
        self,
        repo_dir: Path = Path("."),
        commit_sha: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> IngestionStats:
        """Executes the full GraphRAG ingestion pipeline without direct UI rendering."""

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        resolved_sha = commit_sha or self.cache_service.get_git_commit_sha(repo_dir)
        repo_name = repo_dir.resolve().name

        # Step 0: Repository Context
        log("Step 0/6: Preparing Repository Context & Cache Check...")

        # Step 1: Code Graph Ingestion
        log("Step 1/6: Extracting Code AST Facts (File, Class, Method, Function, Variable, Type)...")
        extractor = PythonASTExtractor(repo_dir)
        for py_file in repo_dir.rglob("*.py"):
            if is_excluded_path(py_file):
                continue
            extractor.extract_from_file(py_file)

        extractor.resolve_dangling_calls()

        node_payloads = [(n.id, n.label_str, n.properties) for n in extractor.nodes.values()]
        edge_payloads = [(e.src, e.tgt, e.relation, e.properties) for e in extractor.edges]

        self.graph_service.upsert_nodes(node_payloads)
        self.graph_service.upsert_edges(edge_payloads)

        facts_to_vectorize: list[dict[str, Any]] = []
        for node_id, label_str, props in node_payloads:
            node_type = str(props.get("type", "")).lower()
            if node_type in STRUCTURAL_FACT_TYPES:
                content_str = synthesize_fact_content(props)
                facts_to_vectorize.append(
                    {
                        "id": f"fact:{node_id}",
                        "repo": repo_name,
                        "commit_sha": resolved_sha,
                        "entity_name": str(props.get("name", node_id)),
                        "clean_name": str(props.get("clean_name", "")),
                        "qualified_name": str(props.get("qualified_name", "")),
                        "fact_type": node_type,
                        "file_path": str(props.get("file_path", "")),
                        "content": content_str,
                        "text": content_str,
                        "metadata": {"labels": label_str.split(":")},
                    }
                )

        if facts_to_vectorize:
            fact_texts = [f["content"] for f in facts_to_vectorize]
            sparse_facts = get_sparse_embeddings(fact_texts)
            for fact_item, s_vec in zip(facts_to_vectorize, sparse_facts):
                self.vector_service.upsert_fact(fact_id=fact_item["id"], properties=fact_item, sparse_vectors=s_vec)

        # Step 2: Convert Documentation
        log("Step 2/6: Parsing Documentation & Docling Chunks...")
        chunker = DoclingChunker(repo_dir)
        all_chunks: list[dict[str, Any]] = []
        converted_doc_paths: list[str] = []

        for md_file in repo_dir.rglob("*.md"):
            if is_excluded_path(md_file):
                continue
            chunks = chunker.extract_chunks(md_file)
            if chunks:
                all_chunks.extend(chunks)
                converted_doc_paths.append(str(md_file.relative_to(repo_dir)))

        # Step 3: Link Documentation to Code
        log("Step 3/6: Cross-Modal Code-to-Doc Linking...")
        doc_links: list[tuple[str, str, str, dict[str, Any]]] = []
        symbol_table = extractor.symbol_table

        for chunk in all_chunks:
            c_id = f"docchunk:{chunk['id']}"
            mentions = extract_deterministic_mentions(chunk["content"])
            for m in mentions:
                if m in symbol_table:
                    sym_id = symbol_table[m]
                    doc_links.append((c_id, sym_id, "REFERENCES_CODE", {"confidence": 1.0}))
                    doc_links.append((c_id, sym_id, "REFERS", {"confidence": 1.0}))
                    doc_links.append((sym_id, c_id, "DOCUMENTED_BY", {"confidence": 1.0}))

        # Step 4: Architectural Intent Discovery & Graph Enrichment
        log("Step 4/6: Architectural Intent Discovery, Reachability & Graph Enrichment...")
        doc_nodes: list[tuple[str, str, dict[str, Any]]] = []
        doc_edges: list[tuple[str, str, str, dict[str, Any]]] = []

        for doc_path in converted_doc_paths:
            doc_id = f"doc:{doc_path}"
            doc_nodes.append(
                (
                    doc_id,
                    "Document",
                    {
                        "repo": repo_name,
                        "commit_sha": resolved_sha,
                        "path": doc_path,
                        "type": "documentation",
                        "title": Path(doc_path).name,
                    },
                )
            )

        for chunk in all_chunks:
            sec_id = f"docchunk:{chunk['id']}"
            doc_id = f"doc:{chunk['doc_path']}"
            sec_props = {
                "id": sec_id,
                "repo": repo_name,
                "commit_sha": resolved_sha,
                "doc_path": chunk["doc_path"],
                "chunk_index": chunk["chunk_index"],
                "title": chunk["title"],
                "label": chunk["title"],
                "name": chunk["title"],
                "source": "DOCUMENTATION",
                "headings": " > ".join(chunk["headings"]) if chunk["headings"] else chunk["title"],
                "char_length": chunk["char_length"],
                "preview": chunk["preview"],
                "text": chunk["text"][:300],
                "type": "docchunk",
                "is_fact": False,
                "is_documentation": True,
            }
            doc_nodes.append((sec_id, "DocChunk:Documentation:DocSection", sec_props))
            doc_edges.append((doc_id, sec_id, "HAS_SECTION", {"chunk_index": chunk["chunk_index"]}))

        doc_edges.extend(doc_links)
        self.graph_service.upsert_nodes(doc_nodes)
        self.graph_service.upsert_edges(doc_edges)

        # Architectural Intents
        discovered_intents = [
            {
                "name": "CLI: coddy code",
                "category": "entrypoint_cli",
                "direction": "inbound",
                "trust_score": 0.98,
                "source": "CODE",
                "details": "Root CLI code entrypoint executing RTD workflow.",
                "file_path": "app/coddy/cli_code.py",
                "target_name": "code_cmd",
                "target_type": "Function",
            },
            {
                "name": "CLI: coddy graphrag ingest",
                "category": "entrypoint_cli",
                "direction": "inbound",
                "trust_score": 0.98,
                "source": "CODE",
                "details": "Forces re-ingestion of codebase AST, docs, and intents into cache.",
                "file_path": "app/coddy/cli_graphrag.py",
                "target_name": "graphrag_ingest_cmd",
                "target_type": "Function",
            },
            {
                "name": "CLI: coddy graphrag status",
                "category": "entrypoint_cli",
                "direction": "inbound",
                "trust_score": 0.98,
                "source": "CODE",
                "details": "Displays GraphRAG cache presence, git commit SHA, tree dirtiness.",
                "file_path": "app/coddy/cli_graphrag.py",
                "target_name": "graphrag_status_cmd",
                "target_type": "Function",
            },
            {
                "name": "Orchestrator: CodingOrchestrateAgent",
                "category": "bridge_orchestrator",
                "direction": "internal",
                "trust_score": 0.95,
                "source": "CODE",
                "details": "Workflow orchestrating sanitize -> research_plan.",
                "file_path": "app/coddy/agentic/workflows/coding_orchestrate.py",
                "caller_fn": "run_workflow",
                "target_name": "CodingOrchestrateAgent",
                "target_type": "Class",
            },
            {
                "name": "DB: FalkorDB In-Memory Graph Query & Store",
                "category": "outbound_db",
                "direction": "outbound",
                "trust_score": 0.95,
                "source": "CODE",
                "details": "In-memory FalkorDB Cypher queries and node/edge upserts.",
                "file_path": "app/coddy/utils/services/falkordb_service.py",
                "caller_fn": "query",
            },
            {
                "name": "DB: Qdrant In-Memory Sparse Vector Search",
                "category": "outbound_db",
                "direction": "outbound",
                "trust_score": 0.95,
                "source": "CODE",
                "details": "In-memory Qdrant BM25/BM42 sparse vector collections for DocChunk and Fact.",
                "file_path": "app/coddy/graphrag/services/vector_service.py",
                "caller_fn": "search_facts",
            },
            {
                "name": "Storage: GraphRAG Disk Cache Persistence",
                "category": "outbound_storage",
                "direction": "outbound",
                "trust_score": 0.95,
                "source": "CODE",
                "details": "Persists serialized graph.json and vectors.json into .cache/graphrag/<commit_sha>/.",
                "file_path": "app/coddy/graphrag/services/cache_service.py",
                "caller_fn": "save_cache",
            },
        ]

        intent_nodes: list[tuple[str, str, dict[str, Any]]] = []
        intent_edges: list[tuple[str, str, str, dict[str, Any]]] = []

        for item in discovered_intents:
            i_name = item["name"]
            cat = item["category"]
            direction = resolve_intent_direction(cat)
            trust = item["trust_score"]
            source = item.get("source", "CODE")
            details = item.get("details", "")

            intent_props = {
                "id": f"intent:{i_name}",
                "name": i_name,
                "label": i_name,
                "category": cat,
                "type": cat,
                "direction": direction,
                "trust_score": trust,
                "source": source,
                "details": details,
                "metadata": json.dumps({"source": source}),
                "is_intent": True,
                "kind": "intent",
            }
            intent_nodes.append((f"intent:{i_name}", "Intent:AI", intent_props))

            fp = item.get("file_path", "")
            if fp:
                intent_edges.append((fp, f"intent:{i_name}", "EXPOSES", {"is_intent": True, "kind": "intent"}))

            caller_fn = item.get("caller_fn")
            if caller_fn and caller_fn in symbol_table:
                c_sym = symbol_table[caller_fn]
                out_verb = resolve_outbound_verb(cat)
                intent_edges.append((c_sym, f"intent:{i_name}", out_verb, {"is_intent": True, "kind": "intent"}))
                intent_edges.append(
                    (c_sym, f"intent:{i_name}", "CALLS_OUTBOUND", {"is_intent": True, "kind": "intent"})
                )

            target_name = item.get("target_name")
            target_type = item.get("target_type", "Function")
            if target_name and target_name in symbol_table:
                t_sym = symbol_table[target_name]
                if target_type == "Class":
                    intent_edges.append((f"intent:{i_name}", t_sym, "INJECTS", {"is_intent": True, "kind": "intent"}))
                else:
                    intent_edges.append((f"intent:{i_name}", t_sym, "CALLS", {"is_intent": True, "kind": "intent"}))
                    intent_edges.append((f"intent:{i_name}", t_sym, "ROUTES_TO", {"is_intent": True, "kind": "intent"}))

        self.graph_service.upsert_nodes(intent_nodes)
        self.graph_service.upsert_edges(intent_edges)

        # Dead code analysis
        inbound_calls: dict[str, int] = {}
        for edge in extractor.edges:
            if edge.relation == "CALLS":
                inbound_calls[edge.tgt] = inbound_calls.get(edge.tgt, 0) + 1

        intent_target_names = {item.get("target_name") for item in discovered_intents if item.get("target_name")}
        dead_nodes: list[tuple[str, str, dict[str, Any]]] = []
        dead_edges: list[tuple[str, str, str, dict[str, Any]]] = []

        for nid, node in extractor.nodes.items():
            primary_label = node.label_str.split(":")[0]
            if primary_label in ("Function", "Method"):
                clean_name = node.clean_name
                if (
                    clean_name.startswith("__")
                    or clean_name in ("main", "main_entry", "run_workflow", "handle_acp")
                    or clean_name in intent_target_names
                    or "test" in node.source_file.lower()
                    or node.source_file.endswith("cli.py")
                ):
                    continue

                if inbound_calls.get(nid, 0) == 0:
                    updated_props = dict(node.properties)
                    updated_props["is_unknown"] = True
                    updated_props["dead_confidence"] = 0.85
                    updated_props["dead_reason"] = "Zero inbound calls and no registered inbound intent route"
                    dead_nodes.append((nid, f"{node.label_str}:DeadCode:Unknown", updated_props))
                    if node.source_file:
                        dead_edges.append((node.source_file, nid, "HAS_UNKNOWN", {"confidence": 0.85}))
                        dead_edges.append((node.source_file, nid, "HAS_DEAD_CODE", {"confidence": 0.85}))

        if dead_nodes:
            self.graph_service.upsert_nodes(dead_nodes)
            self.graph_service.upsert_edges(dead_edges)

        # Step 5: Perform RAG Ingestion into Vector Store
        log("Step 5/6: Vectorizing Documentation Chunks & Ingesting into Qdrant...")
        if all_chunks:
            chunk_texts = [c["content"] for c in all_chunks]
            sparse_chunks = get_sparse_embeddings(chunk_texts)
            for chunk, s_vec in zip(all_chunks, sparse_chunks):
                self.vector_service.upsert_chunk(chunk_id=chunk["id"], properties=chunk, sparse_vectors=s_vec)

        # Step 6: Persist Cache
        log("Step 6/6: Persisting Graph & Vectors Cache (.cache/graphrag/)...")
        self.save_cache(commit_sha=resolved_sha)

        return self.get_stats()

    def close(self) -> None:
        self.graph_service.close()
        self.vector_service.close()

    def __enter__(self) -> "GraphRAGService":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def run_ingestion_pipeline(
    repo_dir: Path = Path("."),
    runtime: Any | None = None,
    commit_sha: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Helper functional wrapper for ingestion pipeline returning stats dictionary."""
    service = (
        GraphRAGService()
        if runtime is None
        else GraphRAGService(
            graph_service=getattr(runtime, "graph_service", None) or GraphService(getattr(runtime, "falkor", None)),
            vector_service=getattr(runtime, "vector_service", None) or getattr(runtime, "qdrant", None),
        )
    )
    stats = service.run_ingestion_pipeline(
        repo_dir=repo_dir,
        commit_sha=commit_sha,
        progress_callback=progress_callback,
    )
    return {
        "nodes": stats.nodes,
        "edges": stats.edges,
        "chunks": stats.chunks,
        "facts": stats.facts,
    }
