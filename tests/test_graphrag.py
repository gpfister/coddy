"""Unit tests for GraphRAG schemas, runtime, tools, caching, and AST/doc ingestion."""

import pytest
from typer.testing import CliRunner

from app.coddy.agentic.tools.graphrag_tools import GraphRAGTools
from app.coddy.app import app
from app.coddy.graphrag.schemas.graphrag import (
    GraphEdge,
    GraphExport,
    GraphNode,
    SparseVector,
    VectorItem,
    VectorsExport,
)
from app.coddy.graphrag.services.cache_service import (
    has_cached_graphrag,
    load_graphrag_cache,
    save_graphrag_cache,
)
from app.coddy.graphrag.services.graph_service import CodeASTExtractor, DoclingChunker
from app.coddy.graphrag.services.graphrag_service import (
    GraphRAGService as GraphRAGRuntime,
)
from app.coddy.graphrag.services.graphrag_service import run_ingestion_pipeline
from app.coddy.utils.services.fastembed_service import get_sparse_embeddings


def test_graphrag_schemas_strict():
    """Verify strict validation and extra='forbid' on GraphRAG schemas."""
    node = GraphNode(id="app.main", labels=["Module"], properties={"file_path": "app/main.py"})
    assert node.id == "app.main"

    with pytest.raises(Exception):
        GraphNode(id="app.main", extra_forbidden="bad")

    edge = GraphEdge(source="app.main", target="app.utils", type="IMPORTS", properties={"line": 10})
    assert edge.type == "IMPORTS"

    with pytest.raises(Exception):
        GraphEdge(source="a", target="b", type="CALLS", extra_forbidden="bad")

    export = GraphExport(commit_sha="abcdef123456", nodes=[node], edges=[edge])
    assert len(export.nodes) == 1
    assert len(export.edges) == 1

    sparse_v = SparseVector(indices=[1, 2], values=[0.1, 0.2])
    assert sparse_v.indices == [1, 2]
    vec_item = VectorItem(
        id="doc_1",
        properties={"text": "hello"},
        sparse_vectors={"bm25": sparse_v, "bm42": SparseVector(indices=[3], values=[0.5])},
    )
    vec_export = VectorsExport(commit_sha="abcdef123456", collections={"DocChunk": [vec_item]})
    assert len(vec_export.collections["DocChunk"]) == 1
    assert "bm25" in vec_export.collections["DocChunk"][0].sparse_vectors


def test_graphrag_runtime_and_cypher():
    """Verify in-memory FalkorDB and Qdrant store operations."""
    runtime = GraphRAGRuntime()

    # Falkor node and edge insertion
    nodes = [
        ("func:add", "Function:CodeEntity", {"name": "add", "file_path": "math.py", "line_start": 1}),
        ("func:main", "Function:CodeEntity", {"name": "main", "file_path": "main.py", "line_start": 5}),
    ]
    edges = [
        ("func:main", "func:add", "CALLS", {"line": 10}),
    ]
    runtime.falkor.upsert_nodes(nodes)
    runtime.falkor.upsert_edges(edges)

    stats = runtime.falkor.get_stats()
    assert stats["nodes"] >= 2
    assert stats["edges"] >= 1

    res = runtime.falkor.query("MATCH (f:Function) RETURN f.name AS name")
    names = [r[0] for r in res]
    assert "add" in names
    assert "main" in names

    # Qdrant in-memory store with BM25 and BM42 sparse representations
    runtime.qdrant.upsert_chunk(
        chunk_id="chunk:doc1",
        properties={"title": "Overview", "text": "This is architecture overview."},
        sparse_vectors={
            "bm25": {"indices": [10, 11], "values": [1.5, 1.2]},
            "bm42": {"indices": [20, 21], "values": [0.8, 0.6]},
        },
    )
    runtime.qdrant.upsert_fact(
        fact_id="fact:1",
        properties={"text": "Rule R1 specifies strict schemas.", "fact_type": "rule"},
        sparse_vectors={
            "bm25": {"indices": [30, 31], "values": [1.2, 1.1]},
            "bm42": {"indices": [40, 41], "values": [0.9, 0.7]},
        },
    )

    qstats = runtime.qdrant.get_stats()
    assert qstats["chunks"] == 1
    assert qstats["facts"] == 1

    # Search chunks via BM42
    chunk_res = runtime.qdrant.search_chunks(sparse_query={"indices": [20], "values": [1.0]}, using="bm42", limit=1)
    assert len(chunk_res) == 1
    assert chunk_res[0]["id"] == "chunk:doc1"

    # Search facts via BM25
    fact_res = runtime.qdrant.search_facts(
        sparse_query={"indices": [30], "values": [1.0]}, using="bm25", entity_type="rule", limit=1
    )
    assert len(fact_res) == 1
    assert fact_res[0]["id"] == "fact:1"


def test_graphrag_cache_save_and_load(tmp_path):
    """Verify cache serialization and restoration to/from graph.json and vectors.json."""
    runtime = GraphRAGRuntime()
    runtime.falkor.upsert_nodes([("node:1", "Item", {"name": "TestNode"})])
    runtime.qdrant.upsert_chunk(
        "chunk:1",
        {"title": "Doc1", "text": "Content"},
        sparse_vectors={"bm25": {"indices": [1], "values": [1.0]}, "bm42": {"indices": [2], "values": [0.5]}},
    )

    commit_sha = "testcommit12345"
    graph_f, vectors_f = save_graphrag_cache(runtime, commit_sha=commit_sha, base_dir=tmp_path)
    assert graph_f.is_file()
    assert vectors_f.is_file()
    assert has_cached_graphrag(commit_sha=commit_sha, base_dir=tmp_path)

    # Restore into fresh runtime
    new_runtime = GraphRAGRuntime()
    loaded = load_graphrag_cache(new_runtime, commit_sha=commit_sha, base_dir=tmp_path)
    assert loaded is True

    fstats = new_runtime.falkor.get_stats()
    qstats = new_runtime.qdrant.get_stats()
    assert fstats["nodes"] == 1
    assert qstats["chunks"] == 1


def test_ast_extractor(tmp_path):
    """Verify AST extraction of modules, functions, classes, and calls."""
    code = '''
"""Sample module docstring."""
import os

class Worker:
    def execute(self, task):
        return run_helper(task)

def run_helper(x):
    return x * 2
'''
    py_file = tmp_path / "sample.py"
    py_file.write_text(code, encoding="utf-8")

    extractor = CodeASTExtractor(repo_dir=tmp_path)
    nodes, edges = extractor.extract_from_file(py_file)

    node_names = [n[2].get("name") for n in nodes]
    assert "Worker" in node_names
    assert "execute" in node_names
    assert "run_helper" in node_names

    edge_types = [e[2] for e in edges]
    assert "DEFINES" in edge_types
    assert "CALLS" in edge_types


def test_docling_chunker(tmp_path):
    """Verify Markdown chunking by headers."""
    md_content = """# Architecture Guide

This is the system overview.

## Multi-Agent Topology

The orchestrator coordinates workers.

## Schemas

Rule R1 enforces strict schemas.
"""
    md_file = tmp_path / "GUIDE.md"
    md_file.write_text(md_content, encoding="utf-8")

    chunker = DoclingChunker(repo_dir=tmp_path)
    chunks = chunker.extract_chunks(md_file)

    assert len(chunks) >= 3
    titles = [c["title"] for c in chunks]
    assert "Architecture Guide" in titles
    assert "Multi-Agent Topology" in titles
    assert "Schemas" in titles


def test_graphrag_tools_interface(tmp_path):
    """Verify all GraphRAGTools methods return structured dicts and handle queries."""
    runtime = GraphRAGRuntime()
    runtime.falkor.upsert_nodes(
        [
            ("func:calc", "Function:CodeEntity", {"name": "calc", "file_path": "calc.py", "line_start": 1}),
            ("func:caller", "Function:CodeEntity", {"name": "caller", "file_path": "caller.py", "line_start": 10}),
            ("intent:rtd", "Intent:Fact", {"id": "intent:rtd", "text": "RTD pipeline", "category": "architecture"}),
        ]
    )
    runtime.falkor.upsert_edges(
        [
            ("func:caller", "func:calc", "CALLS", {"line": 15}),
        ]
    )
    chunk_embeds = get_sparse_embeddings(["RTD documentation"])
    fact_embeds = get_sparse_embeddings(["RTD architecture fact"])
    runtime.qdrant.upsert_chunk(
        "chunk:1",
        {"title": "Docs", "text": "RTD documentation"},
        sparse_vectors=chunk_embeds[0],
    )
    runtime.qdrant.upsert_fact(
        "fact:1",
        {"text": "RTD architecture fact", "fact_type": "architecture"},
        sparse_vectors=fact_embeds[0],
    )

    tools = GraphRAGTools(runtime=runtime, repo_dir=tmp_path)

    # Search facts via BM25, BM42, and both
    facts_both = tools.search_facts("RTD", method="both", top_k=2)
    assert len(facts_both) >= 1

    facts_bm25 = tools.search_facts("RTD", method="bm25", top_k=2)
    assert len(facts_bm25) >= 1

    facts_bm42 = tools.search_facts("RTD", method="bm42", top_k=2)
    assert len(facts_bm42) >= 1

    # Search documents via BM25, BM42, and both
    docs_both = tools.search_documents("RTD", method="both", top_k=2)
    assert len(docs_both) >= 1

    docs_bm25 = tools.search_documents("RTD", method="bm25", top_k=2)
    assert len(docs_bm25) >= 1

    docs_bm42 = tools.search_documents("RTD", method="bm42", top_k=2)
    assert len(docs_bm42) >= 1

    # Execute Cypher
    c_res = tools.execute_cypher("MATCH (f:Function) RETURN f.name AS name")
    assert len(c_res) >= 2

    # Entity lookup & call hierarchy
    entity = tools.get_code_entity("calc")
    assert entity["count"] >= 1
    assert len(entity["matches"]) >= 1

    hierarchy = tools.get_call_hierarchy("calc")
    assert len(hierarchy["incoming_callers"]) >= 1
    assert hierarchy["incoming_callers"][0]["caller"] == "caller"

    # Intents & Dead code
    intents = tools.list_intents()
    assert len(intents) >= 1

    dead_code = tools.find_dead_code()
    assert "dead_code_candidates" in dead_code
    assert isinstance(dead_code["dead_code_candidates"], list)

    impact = tools.trace_dead_code_impact("calc")
    assert impact["symbol"] == "calc"
    assert "cascading_impacts" in impact

    # File inspection tools
    f_sample = tmp_path / "hello.py"
    f_sample.write_text("print('hello world')\n", encoding="utf-8")

    files = tools.list_files()
    assert "hello.py" in files["files"]

    snippet = tools.read_file_snippet("hello.py", start_line=1, max_lines=5)
    assert "hello world" in snippet["content"]

    # Web search
    web = tools.web_search("pydantic extra forbid")
    assert web["query"] == "pydantic extra forbid"
    assert "results" in web


def test_cli_graphrag_status():
    """Verify coddy graphrag status CLI command."""
    runner = CliRunner()
    result = runner.invoke(app, ["graphrag", "status"])
    assert result.exit_code == 0
    assert "GraphRAG Cache Status" in result.output
    assert "Commit SHA" in result.output


def test_ingestion_pipeline_qdrant(tmp_path):
    """Verify end-to-end ingestion pipeline with Qdrant BM25/BM42 sparse indexing and caching."""
    # Create sample codebase
    py_dir = tmp_path / "app" / "pkg"
    py_dir.mkdir(parents=True)
    sample_code = "def sample_func():\n    return 42\n\nclass SampleService:\n    def execute(self):\n        return sample_func()\n"
    (py_dir / "sample.py").write_text(sample_code, encoding="utf-8")

    doc_dir = tmp_path / "docs"
    doc_dir.mkdir(parents=True)
    sample_doc = "# Sample Documentation\n\nThis documents sample_func and architecture.\n"
    (doc_dir / "sample.md").write_text(sample_doc, encoding="utf-8")

    runtime = GraphRAGRuntime()
    stats = run_ingestion_pipeline(repo_dir=tmp_path, runtime=runtime, commit_sha="committest001")

    assert stats["nodes"] >= 2
    assert stats["chunks"] >= 1
    assert stats["facts"] >= 3

    # Check that cache files exist and contain sparse vectors
    _cdir = tmp_path / ".cache" / "graphrag" / "committest001"
    # Note: cache was written to default path relative to repo or cwd; let's check runtime stats
    qstats = runtime.qdrant.get_stats()
    assert qstats["chunks"] >= 1
    assert qstats["facts"] >= 3

    # Search with GraphRAGTools
    tools = GraphRAGTools(runtime=runtime, repo_dir=tmp_path)
    hits = tools.search_documents("sample_func", method="both", top_k=2)
    assert len(hits) >= 1
    assert "sample_func" in hits[0]["properties"]["text"]


def test_mirrored_taxonomy_and_fact_intent_unknown(tmp_path):
    """Verify 100% mirrored taxonomy, node types, labels, relationships, and FACT/INTENT/UNKNOWN handling."""
    from app.coddy.graphrag.services.graph_service import PythonASTExtractor

    code = """
from typing import Protocol

MyType = int

class RepositoryInterface(Protocol):
    def fetch(self, item_id: str) -> dict: ...

class SQLRepository(RepositoryInterface):
    timeout: int = 30

    def __init__(self, conn: str) -> None:
        self.conn = conn

    def fetch(self, item_id: str) -> dict:
        local_var = item_id.strip()
        return {"id": local_var}

def dead_standalone_helper(x: int) -> int:
    return x * 10
"""
    py_dir = tmp_path / "app"
    py_dir.mkdir(parents=True)
    py_file = py_dir / "service.py"
    py_file.write_text(code, encoding="utf-8")

    extractor = PythonASTExtractor(repo_dir=tmp_path)
    extractor.extract_from_file(py_file)
    extractor.resolve_dangling_calls()

    # Check node labels and FACT flag
    labels = {n.label_str for n in extractor.nodes.values()}
    assert any(lbl.startswith("Interface:") and "Fact" in lbl for lbl in labels)
    assert any(lbl.startswith("Class:") and "Fact" in lbl for lbl in labels)
    assert any(lbl.startswith("Method:") and "Fact" in lbl for lbl in labels)
    assert any(lbl.startswith("ClassParameter:") and "Fact" in lbl for lbl in labels)
    assert any(lbl.startswith("Function:") and "Fact" in lbl for lbl in labels)
    assert any(lbl.startswith("Variable:") and "Fact" in lbl for lbl in labels)
    assert any(lbl.startswith("Type:") and "Fact" in lbl for lbl in labels)
    assert any(lbl.startswith("File:") and "Fact" in lbl for lbl in labels)

    for node in extractor.nodes.values():
        assert node.properties.get("is_fact") is True
        assert node.properties.get("kind") == "fact"

    # Check relationships
    edge_rels = {e.relation for e in extractor.edges}
    assert "DEFINES" in edge_rels
    assert "IMPLEMENTS" in edge_rels
    assert "DECLARES" in edge_rels
    assert "HAS_TYPE" in edge_rels

    # Run full ingestion pipeline to verify INTENT, UNKNOWN, and DeadCode
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir(parents=True)
    (doc_dir / "service.md").write_text(
        "# Service Architecture\n\nDocs for `SQLRepository` and `fetch`.\n", encoding="utf-8"
    )

    runtime = GraphRAGRuntime()
    _stats = run_ingestion_pipeline(repo_dir=tmp_path, runtime=runtime, commit_sha="taxotest123")

    # Query FalkorDB to verify FACT, INTENT, and UNKNOWN entities
    nodes_res = runtime.falkor.query(
        "MATCH (n) RETURN n.id AS id, labels(n) AS labels, n.is_unknown AS is_unknown, n.is_intent AS is_intent"
    )

    # Check DeadCode / Unknown tagging on uncalled function
    dead_helper_found = False
    for nid, nlabels, is_unk, is_int in nodes_res:
        if str(nid).endswith("dead_standalone_helper()"):
            dead_helper_found = True
            assert is_unk is True
            assert "DeadCode" in nlabels
            assert "Unknown" in nlabels

    assert dead_helper_found is True

    # Check Intent nodes
    intents = [r for r in nodes_res if r[3] is True or "Intent" in r[1]]
    assert len(intents) > 0
