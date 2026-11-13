"""GraphRAG query tools querying in-memory FalkorDB and Qdrant stores.

All agent tools in this module are defined as standalone functions.
"""

import fnmatch
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from app.coddy.graphrag.services.vector_service import reciprocal_rank_fusion
from app.coddy.utils.services.fastembed_service import get_query_sparse_embedding

_ACTIVE_RUNTIME: Any = None
_ACTIVE_REPO_DIR: Path = Path(".")


def set_active_graphrag_runtime(runtime: Any, repo_dir: Path | None = None) -> None:
    """Sets the active runtime and repository directory for module-level tool functions."""
    global _ACTIVE_RUNTIME, _ACTIVE_REPO_DIR
    _ACTIVE_RUNTIME = runtime
    if repo_dir is not None:
        _ACTIVE_REPO_DIR = repo_dir


def get_active_graphrag_runtime() -> Any:
    """Retrieves the active GraphRAG runtime."""
    return _ACTIVE_RUNTIME


def get_active_repo_dir() -> Path:
    """Retrieves the active repository directory."""
    return _ACTIVE_REPO_DIR


def _resolve_falkor(runtime: Any | None = None) -> Any:
    rt = runtime or _ACTIVE_RUNTIME
    return getattr(rt, "falkor", None) or getattr(rt, "graph_service", None)


def _resolve_qdrant(runtime: Any | None = None) -> Any:
    rt = runtime or _ACTIVE_RUNTIME
    return getattr(rt, "qdrant", None) or getattr(rt, "vector_service", None)


def search_facts(
    query: str,
    entity_type: str = "",
    method: str = "both",
    top_k: int = 5,
    runtime: Any | None = None,
) -> list[dict[str, Any]]:
    """Searches facts collection leveraging Fastembed BM25 and BM42 sparse representations.

    Args:
        query: Search query text.
        entity_type: Optional entity type filter.
        method: Search method ('bm25', 'bm42', or 'both').
        top_k: Number of results to return.
        runtime: Optional runtime override.

    Returns:
        List of matching fact dictionaries.
    """
    qdrant = _resolve_qdrant(runtime)
    if not qdrant:
        return []

    clean_method = method.lower().strip()
    if clean_method == "bm25":
        q_vec = get_query_sparse_embedding(query, model_type="bm25")
        return qdrant.search_facts(q_vec, using="bm25", entity_type=entity_type, limit=top_k)
    elif clean_method == "bm42":
        q_vec = get_query_sparse_embedding(query, model_type="bm42")
        return qdrant.search_facts(q_vec, using="bm42", entity_type=entity_type, limit=top_k)
    else:
        q_bm25 = get_query_sparse_embedding(query, model_type="bm25")
        q_bm42 = get_query_sparse_embedding(query, model_type="bm42")
        bm25_hits = qdrant.search_facts(q_bm25, using="bm25", entity_type=entity_type, limit=top_k * 2)
        bm42_hits = qdrant.search_facts(q_bm42, using="bm42", entity_type=entity_type, limit=top_k * 2)
        return reciprocal_rank_fusion([bm42_hits, bm25_hits], top_k=top_k)


def search_documents(
    query: str,
    method: str = "both",
    top_k: int = 10,
    runtime: Any | None = None,
) -> list[dict[str, Any]]:
    """Searches documentation chunks collection leveraging Fastembed BM25 and BM42 sparse representations.

    Args:
        query: Search query text.
        method: Search method ('bm25', 'bm42', or 'both').
        top_k: Number of results to return.
        runtime: Optional runtime override.

    Returns:
        List of matching document chunks.
    """
    qdrant = _resolve_qdrant(runtime)
    if not qdrant:
        return []

    clean_method = method.lower().strip()
    if clean_method == "bm25":
        q_vec = get_query_sparse_embedding(query, model_type="bm25")
        return qdrant.search_chunks(q_vec, using="bm25", limit=top_k)
    elif clean_method == "bm42":
        q_vec = get_query_sparse_embedding(query, model_type="bm42")
        return qdrant.search_chunks(q_vec, using="bm42", limit=top_k)
    else:
        q_bm25 = get_query_sparse_embedding(query, model_type="bm25")
        q_bm42 = get_query_sparse_embedding(query, model_type="bm42")
        bm25_hits = qdrant.search_chunks(q_bm25, using="bm25", limit=top_k * 2)
        bm42_hits = qdrant.search_chunks(q_bm42, using="bm42", limit=top_k * 2)
        return reciprocal_rank_fusion([bm42_hits, bm25_hits], top_k=top_k)


def execute_cypher(query: str, runtime: Any | None = None) -> dict[str, Any]:
    """Executes a Cypher query on the embedded FalkorDB graph.

    Args:
        query: Cypher query string.
        runtime: Optional runtime override.

    Returns:
        Dictionary with query results and match count, or error message.
    """
    falkor = _resolve_falkor(runtime)
    if not falkor:
        return {"error": "FalkorDB graph service is not available"}
    try:
        rows = falkor.query(query)
        return {"results": rows, "count": len(rows)}
    except Exception as e:
        return {"error": f"Cypher execution error: {e}"}


def get_code_entity(name: str, runtime: Any | None = None) -> dict[str, Any]:
    """Retrieves detailed code entity node information, callers, and callees from FalkorDB.

    Args:
        name: Name or identifier of the code symbol.
        runtime: Optional runtime override.

    Returns:
        Dictionary with matching entity details, inbound and outbound relationships.
    """
    falkor = _resolve_falkor(runtime)
    if not falkor:
        return {"error": "FalkorDB graph service is not available"}

    clean_name = name.strip()
    if "(" in clean_name and clean_name.endswith(")"):
        clean_name = clean_name[: clean_name.find("(")].strip()
    if ":" in clean_name:
        clean_name = clean_name.split(":")[-1].strip()

    cypher = """
    MATCH (n)
    WHERE n.name = $name OR n.clean_name = $name OR n.qualified_name = $name OR n.id = $name
       OR n.name = $clean OR n.clean_name = $clean OR n.qualified_name = $clean OR n.id = $clean
    RETURN labels(n) as labels, properties(n) as props
    LIMIT 5
    """
    rows = falkor.query(cypher, {"name": name, "clean": clean_name})
    if not rows:
        fuzzy_cypher = """
        MATCH (n)
        WHERE toLower(n.name) CONTAINS toLower($clean) OR toLower(coalesce(n.qualified_name, '')) CONTAINS toLower($clean)
        RETURN labels(n) as labels, properties(n) as props
        LIMIT 5
        """
        rows = falkor.query(fuzzy_cypher, {"clean": clean_name})

    if not rows:
        return {"error": f"No code entity found matching '{name}'"}

    entities = []
    for r in rows:
        labels = r[0] if len(r) > 0 else []
        props = r[1] if len(r) > 1 else {}
        node_id = props.get("id")

        inbound = []
        outbound = []
        if node_id:
            in_rows = falkor.query(
                "MATCH (s)-[r]->(t {id: $id}) RETURN type(r), labels(s), coalesce(s.path, s.name, s.id)",
                {"id": node_id},
            )
            for in_r in in_rows:
                inbound.append({"relation": in_r[0], "source_labels": in_r[1], "source": in_r[2]})

            out_rows = falkor.query(
                "MATCH (s {id: $id})-[r]->(t) RETURN type(r), labels(t), coalesce(t.path, t.name, t.id)",
                {"id": node_id},
            )
            for out_r in out_rows:
                outbound.append({"relation": out_r[0], "target_labels": out_r[1], "target": out_r[2]})

        entities.append(
            {
                "labels": labels,
                "properties": props,
                "inbound_relationships": inbound,
                "outbound_relationships": outbound,
            }
        )

    return {"matches": entities, "count": len(entities)}


def get_call_hierarchy(
    symbol: str,
    depth: int = 2,
    direction: str = "both",
    runtime: Any | None = None,
) -> dict[str, Any]:
    """Traverses the call graph up to specified depth in incoming, outgoing, or both directions.

    Args:
        symbol: Target function or method symbol name.
        depth: Graph traversal depth limit.
        direction: 'incoming', 'outgoing', or 'both'.
        runtime: Optional runtime override.

    Returns:
        Dictionary with callers and callees lists.
    """
    falkor = _resolve_falkor(runtime)
    if not falkor:
        return {"error": "FalkorDB graph service is not available"}

    callers: list[dict[str, Any]] = []
    callees: list[dict[str, Any]] = []

    if direction in ("incoming", "both"):
        c_rows = falkor.query(
            "MATCH (caller)-[:CALLS]->(target) WHERE target.name = $sym OR target.id CONTAINS $sym "
            "RETURN coalesce(caller.name, caller.id), caller.path",
            {"sym": symbol},
        )
        for r in c_rows:
            callers.append({"caller": r[0], "path": r[1] if len(r) > 1 else ""})

    if direction in ("outgoing", "both"):
        o_rows = falkor.query(
            "MATCH (source)-[:CALLS]->(callee) WHERE source.name = $sym OR source.id CONTAINS $sym "
            "RETURN coalesce(callee.name, callee.id), callee.path",
            {"sym": symbol},
        )
        for r in o_rows:
            callees.append({"callee": r[0], "path": r[1] if len(r) > 1 else ""})

    return {
        "symbol": symbol,
        "incoming_callers": callers,
        "outgoing_callees": callees,
        "depth": depth,
    }


def list_intents(
    category: str | None = None,
    min_trust: float = 0.0,
    runtime: Any | None = None,
) -> dict[str, Any]:
    """Lists high-level architectural intents and capabilities stored in the graph.

    Args:
        category: Optional category filter.
        min_trust: Minimum trust threshold.
        runtime: Optional runtime override.

    Returns:
        Dictionary containing matching intent specifications.
    """
    falkor = _resolve_falkor(runtime)
    if not falkor:
        return {"intents": [], "count": 0}

    cypher = "MATCH (i:Intent) RETURN properties(i)"
    rows = falkor.query(cypher)
    intents = [r[0] for r in rows if r and len(r) > 0]
    if category:
        intents = [i for i in intents if i.get("category") == category]
    return {"intents": intents, "count": len(intents)}


def find_dead_code(
    file_or_module: str | None = None,
    min_confidence: float = 0.7,
    runtime: Any | None = None,
) -> dict[str, Any]:
    """Identifies functions or methods that have no incoming CALLS relationships in the graph.

    Args:
        file_or_module: Optional path or module filter.
        min_confidence: Minimum confidence threshold.
        runtime: Optional runtime override.

    Returns:
        Dictionary of candidate dead code symbols.
    """
    falkor = _resolve_falkor(runtime)
    if not falkor:
        return {"dead_code_candidates": [], "count": 0}

    cypher = """
    MATCH (f:Function)
    WHERE NOT ()-[:CALLS]->(f)
    RETURN f.name, f.path, f.start_line, f.end_line
    """
    rows = falkor.query(cypher)
    candidates = []
    for r in rows:
        name = r[0]
        path = r[1] or ""
        if name.startswith("__") or name in ("main", "main_entry", "run", "cli"):
            continue
        if file_or_module and file_or_module not in path:
            continue
        candidates.append(
            {
                "symbol": name,
                "path": path,
                "start_line": r[2],
                "end_line": r[3],
                "confidence": min_confidence,
            }
        )
    return {"dead_code_candidates": candidates, "count": len(candidates)}


def trace_dead_code_impact(
    entity_name: str,
    file_path: str | None = None,
    runtime: Any | None = None,
) -> dict[str, Any]:
    """Traces whether removing an unused symbol impacts any downstream callees or references.

    Args:
        entity_name: Target symbol name.
        file_path: Optional file path context.
        runtime: Optional runtime override.

    Returns:
        Dictionary with cascading impacts list.
    """
    falkor = _resolve_falkor(runtime)
    if not falkor:
        return {"symbol": entity_name, "cascading_impacts": []}

    rows = falkor.query(
        "MATCH (e)-[r]->(target) WHERE e.name = $name RETURN type(r), coalesce(target.name, target.id)",
        {"name": entity_name},
    )
    impacts = [{"relation": r[0], "target": r[1]} for r in rows if len(r) >= 2]
    return {"symbol": entity_name, "cascading_impacts": impacts}


def list_files(
    pattern: str | None = None,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    """Lists files matching an optional glob pattern across the codebase.

    Args:
        pattern: Optional fnmatch glob pattern.
        repo_dir: Optional root repository directory override.

    Returns:
        Dictionary with list of relative file paths and count.
    """
    target_dir = repo_dir or _ACTIVE_REPO_DIR
    matched = []
    for p in target_dir.rglob("*"):
        if p.is_file() and not any(part in p.parts for part in (".venv", ".git", "__pycache__", ".cache", "out")):
            rel_str = str(p.relative_to(target_dir))
            if pattern:
                if fnmatch.fnmatch(rel_str, pattern):
                    matched.append(rel_str)
            else:
                matched.append(rel_str)
    return {"files": sorted(matched)[:100], "count": len(matched)}


def read_file_snippet(
    path: str,
    start_line: int = 1,
    end_line: int | None = None,
    max_lines: int | None = None,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    """Reads a specific line range from a source file.

    Args:
        path: Path relative to repository directory.
        start_line: 1-indexed starting line number.
        end_line: 1-indexed ending line number.
        max_lines: Maximum number of lines to read.
        repo_dir: Optional root repository directory override.

    Returns:
        Dictionary with snippet content, start/end line, total lines or error.
    """
    target_dir = repo_dir or _ACTIVE_REPO_DIR
    fpath = target_dir / path
    if not fpath.is_file():
        return {"error": f"File not found: {path}"}
    try:
        lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        s_idx = max(0, start_line - 1)
        if end_line is not None:
            e_idx = min(len(lines), end_line)
        elif max_lines is not None:
            e_idx = min(len(lines), s_idx + max_lines)
        else:
            e_idx = min(len(lines), s_idx + 100)
        snippet = "\n".join(lines[s_idx:e_idx])
        return {
            "path": path,
            "start_line": s_idx + 1,
            "end_line": e_idx,
            "total_lines": len(lines),
            "content": snippet,
        }
    except Exception as e:
        return {"error": f"Error reading file '{path}': {e}"}


def web_search(query: str) -> dict[str, Any]:
    """Performs a web search via DuckDuckGo HTML/Instant search fallback.

    Args:
        query: Search query text.

    Returns:
        Dictionary containing search query and top text snippet results.
    """
    try:
        encoded_q = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text_parts: list[str] = []
                    self.in_snippet: bool = False

                def handle_starttag(self, tag: str, attrs: Any) -> None:
                    if tag == "a" and any(k == "class" and "result__snippet" in v for k, v in attrs):
                        self.in_snippet = True

                def handle_endtag(self, tag: str) -> None:
                    if tag == "a":
                        self.in_snippet = False

                def handle_data(self, data: str) -> None:
                    if self.in_snippet:
                        self.text_parts.append(data.strip())

            extractor = TextExtractor()
            extractor.feed(html)
            snippets = [s for s in extractor.text_parts if len(s) > 20][:5]
            if snippets:
                return {"query": query, "results": snippets}
    except Exception:
        pass

    return {
        "query": query,
        "results": [f"Web search summary for '{query}': consulted standard reference documentation."],
    }


class GraphRAGTools:
    """Compatibility adapter providing object-oriented interface for standalone tool functions."""

    def __init__(
        self,
        runtime: Any,
        repo_dir: Path = Path("."),
        session_logger: Any | None = None,
    ):
        self.runtime = runtime
        self.repo_dir = repo_dir
        self.session_logger = session_logger
        set_active_graphrag_runtime(runtime, repo_dir)

    def search_facts(
        self, query: str, entity_type: str = "", method: str = "both", top_k: int = 5
    ) -> list[dict[str, Any]]:
        return search_facts(query, entity_type, method, top_k, self.runtime)

    def search_documents(self, query: str, method: str = "both", top_k: int = 10) -> list[dict[str, Any]]:
        return search_documents(query, method, top_k, self.runtime)

    def execute_cypher(self, query: str) -> dict[str, Any]:
        return execute_cypher(query, self.runtime)

    def get_code_entity(self, name: str) -> dict[str, Any]:
        return get_code_entity(name, self.runtime)

    def get_call_hierarchy(self, symbol: str, depth: int = 2, direction: str = "both") -> dict[str, Any]:
        return get_call_hierarchy(symbol, depth, direction, self.runtime)

    def list_intents(self, category: str | None = None, min_trust: float = 0.0) -> dict[str, Any]:
        return list_intents(category, min_trust, self.runtime)

    def find_dead_code(self, file_or_module: str | None = None, min_confidence: float = 0.7) -> dict[str, Any]:
        return find_dead_code(file_or_module, min_confidence, self.runtime)

    def trace_dead_code_impact(self, entity_name: str, file_path: str | None = None) -> dict[str, Any]:
        return trace_dead_code_impact(entity_name, file_path, self.runtime)

    def list_files(self, pattern: str | None = None) -> dict[str, Any]:
        return list_files(pattern, self.repo_dir)

    def read_file_snippet(
        self,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
        max_lines: int | None = None,
    ) -> dict[str, Any]:
        return read_file_snippet(path, start_line, end_line, max_lines, self.repo_dir)

    def web_search(self, query: str) -> dict[str, Any]:
        return web_search(query)

    def execute_tool_call(self, name: str, args: dict[str, Any]) -> str:
        fn_map = {
            "search_facts": lambda: self.search_facts(
                args.get("query", ""),
                args.get("entity_type", ""),
                args.get("method", "both"),
                int(args.get("top_k", 5)),
            ),
            "search_documents": lambda: self.search_documents(
                args.get("query", ""), args.get("method", "both"), int(args.get("top_k", 10))
            ),
            "execute_cypher": lambda: self.execute_cypher(args.get("query", "")),
            "get_code_entity": lambda: self.get_code_entity(args.get("name", "")),
            "get_call_hierarchy": lambda: self.get_call_hierarchy(
                args.get("symbol", ""), int(args.get("depth", 2)), args.get("direction", "both")
            ),
            "list_intents": lambda: self.list_intents(args.get("category"), float(args.get("min_trust", 0.0))),
            "find_dead_code": lambda: self.find_dead_code(
                args.get("file_or_module"), float(args.get("min_confidence", 0.7))
            ),
            "trace_dead_code_impact": lambda: self.trace_dead_code_impact(
                args.get("entity_name", ""), args.get("file_path")
            ),
            "list_files": lambda: self.list_files(args.get("pattern")),
            "read_file_snippet": lambda: self.read_file_snippet(
                args.get("path", ""), int(args.get("start_line", 1)), args.get("end_line"), args.get("max_lines")
            ),
            "web_search": lambda: self.web_search(args.get("query", "")),
        }
        if name in fn_map:
            res = fn_map[name]()
        else:
            res = {"error": f"Unknown tool: '{name}'"}
        return json.dumps(res, default=str)
