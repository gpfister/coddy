"""In-memory embedded FalkorDB database service."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.coddy.graphrag.schemas.graphrag import GraphEdge, GraphExport, GraphNode


def sanitize_label(label: str) -> str:
    """Sanitizes Cypher label to alphanumeric and underscore, preserving colon for multiple labels."""
    parts = [re.sub(r"[^A-Za-z0-9_]", "", p) for p in label.split(":") if p]
    clean_parts = [p for p in parts if p]
    return ":".join(clean_parts) if clean_parts else "Entity"


def sanitize_rel(relation: str) -> str:
    """Sanitizes Cypher relationship type."""
    clean = re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_"))
    return clean if clean else "RELATED_TO"


class FalkorDBService:
    """Embedded FalkorDB runtime using redislite.falkordb_client in in-memory mode."""

    def __init__(self, dbpath: str | None = None, graph_name: str = "coddy_graph"):
        self.graph_name = graph_name
        self._db = None
        self._dbpath = dbpath
        self._init_db()

    def _init_db(self) -> None:
        try:
            from redislite.falkordb_client import FalkorDB

            # dbpath=None runs an in-memory embedded FalkorDB instance
            self._db = FalkorDB(self._dbpath)
            self._graph = self._db.select_graph(self.graph_name)
        except Exception:
            # Fallback mock for testing environments where redislite native binaries are unavailable
            self._db = None
            self._graph = None
            self._fallback_nodes: dict[str, tuple[list[str], dict[str, Any]]] = {}
            self._fallback_edges: list[tuple[str, str, str, dict[str, Any]]] = []

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        """Executes a Cypher query and returns the rows as a list of lists."""
        if self._graph is not None:
            try:
                res = self._graph.query(cypher, params or {})
                return res.result_set or []
            except Exception:
                return []
        return []

    def upsert_nodes(self, nodes: list[tuple[str, str, dict[str, Any]]]) -> int:
        """Upserts nodes: list of (node_id, label, properties)."""
        count = 0
        if self._graph is not None:
            for node_id, label, props in nodes:
                safe_lbl = sanitize_label(label)
                clean_props = {
                    k: v for k, v in props.items() if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
                }
                clean_props["id"] = node_id
                cypher = f"MERGE (n {{id: $id}}) SET n:{safe_lbl}, n += $props"
                self._graph.query(cypher, {"id": node_id, "props": clean_props})
                count += 1
        elif hasattr(self, "_fallback_nodes"):
            for node_id, label, props in nodes:
                labels = [part for part in label.split(":") if part]
                existing = self._fallback_nodes.get(node_id)
                if existing:
                    merged_labels = list(dict.fromkeys(existing[0] + labels))
                    merged_props = dict(existing[1])
                    merged_props.update(props)
                    merged_props["id"] = node_id
                    self._fallback_nodes[node_id] = (merged_labels, merged_props)
                else:
                    self._fallback_nodes[node_id] = (labels, dict(props, id=node_id))
                count += 1
        return count

    def upsert_edges(self, edges: list[tuple[str, str, str, dict[str, Any]]]) -> int:
        """Upserts directed edges: list of (src_id, tgt_id, relation, properties)."""
        count = 0
        if self._graph is not None:
            for src_id, tgt_id, rel, props in edges:
                safe_rel = sanitize_rel(rel)
                clean_props = {
                    k: v for k, v in props.items() if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
                }
                cypher = f"MATCH (s {{id: $src}}), (t {{id: $tgt}}) MERGE (s)-[r:{safe_rel}]->(t) SET r += $props"
                self._graph.query(cypher, {"src": src_id, "tgt": tgt_id, "props": clean_props})
                count += 1
        elif hasattr(self, "_fallback_edges"):
            for src_id, tgt_id, rel, props in edges:
                self._fallback_edges.append((src_id, tgt_id, rel, dict(props)))
                count += 1
        return count

    def export_graph(self, commit_sha: str) -> GraphExport:
        """Dumps all nodes and edges from the FalkorDB graph into GraphExport schema."""
        from app.coddy.graphrag.schemas.graphrag import GraphEdge, GraphExport, GraphNode

        nodes_export: list[GraphNode] = []
        edges_export: list[GraphEdge] = []

        if self._graph is not None:
            node_rows = self.query("MATCH (n) RETURN labels(n), properties(n)")
            for row in node_rows:
                if len(row) >= 2:
                    labels = row[0] or []
                    props = row[1] or {}
                    node_id = str(props.get("id", ""))
                    if node_id:
                        nodes_export.append(GraphNode(id=node_id, labels=labels, properties=props))

            edge_rows = self.query("MATCH (s)-[r]->(t) RETURN s.id, t.id, type(r), properties(r)")
            for row in edge_rows:
                if len(row) >= 4:
                    s_id = str(row[0] or "")
                    t_id = str(row[1] or "")
                    rel_type = str(row[2] or "RELATED_TO")
                    props = row[3] or {}
                    if s_id and t_id:
                        edges_export.append(GraphEdge(source=s_id, target=t_id, type=rel_type, properties=props))
        elif hasattr(self, "_fallback_nodes"):
            for n_id, (lbls, props) in self._fallback_nodes.items():
                nodes_export.append(GraphNode(id=n_id, labels=lbls, properties=props))
            for s_id, t_id, r_type, props in self._fallback_edges:
                edges_export.append(GraphEdge(source=s_id, target=t_id, type=r_type, properties=props))

        return GraphExport(version="1.0", commit_sha=commit_sha, nodes=nodes_export, edges=edges_export)

    def import_graph(self, export: GraphExport) -> tuple[int, int]:
        """Restores all nodes and edges into FalkorDB from GraphExport."""
        node_tuples: list[tuple[str, str, dict[str, Any]]] = []
        for n in export.nodes:
            lbl = ":".join(n.labels) if n.labels else "Entity"
            node_tuples.append((n.id, lbl, n.properties))

        edge_tuples: list[tuple[str, str, str, dict[str, Any]]] = []
        for e in export.edges:
            edge_tuples.append((e.source, e.target, e.type, e.properties))

        node_count = self.upsert_nodes(node_tuples)
        edge_count = self.upsert_edges(edge_tuples)
        return node_count, edge_count

    def get_stats(self) -> dict[str, int]:
        """Returns node and edge counts."""
        if self._graph is not None:
            n_res = self.query("MATCH (n) RETURN count(n)")
            e_res = self.query("MATCH ()-[r]->() RETURN count(r)")
            nodes = n_res[0][0] if n_res and n_res[0] else 0
            edges = e_res[0][0] if e_res and e_res[0] else 0
            return {"nodes": int(nodes), "edges": int(edges)}
        elif hasattr(self, "_fallback_nodes"):
            return {"nodes": len(self._fallback_nodes), "edges": len(self._fallback_edges)}
        return {"nodes": 0, "edges": 0}

    def close(self) -> None:
        """Cleans up any database connection."""
        self._graph = None
        self._db = None
