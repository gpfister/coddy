"""Cache management service for GraphRAG: git commit resolution, dirty check, and JSON serialization."""

import json
import subprocess
from pathlib import Path
from typing import Any

from app.coddy.graphrag.schemas.graphrag import GraphExport, VectorsExport

DEFAULT_CACHE_BASE = Path(".cache/graphrag")


class CacheService:
    """Service managing GraphRAG commit hashes, dirty status, and cache serialization."""

    def __init__(self, base_dir: Path = DEFAULT_CACHE_BASE):
        self.base_dir = base_dir

    def get_git_commit_sha(self, repo_dir: Path = Path(".")) -> str:
        """Retrieves current HEAD commit SHA via git rev-parse HEAD."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            sha = res.stdout.strip()
            if sha:
                return sha
        except Exception:
            pass
        return "0000000000000000000000000000000000000000"

    def is_git_dirty(self, repo_dir: Path = Path(".")) -> bool:
        """Checks if git working tree has uncommitted modifications."""
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(res.stdout.strip())
        except Exception:
            return False

    def get_cache_dir(self, commit_sha: str) -> Path:
        """Returns the cache directory path for a specific commit SHA."""
        return self.base_dir / commit_sha

    def has_cached_graphrag(self, commit_sha: str) -> bool:
        """Returns True if both graph.json and vectors.json exist for this commit."""
        cdir = self.get_cache_dir(commit_sha)
        return (cdir / "graph.json").is_file() and (cdir / "vectors.json").is_file()

    def save_cache(
        self,
        graph_export: GraphExport,
        vectors_export: VectorsExport,
        commit_sha: str,
    ) -> tuple[Path, Path]:
        """Serializes GraphExport and VectorsExport to graph.json and vectors.json."""
        cdir = self.get_cache_dir(commit_sha)
        cdir.mkdir(parents=True, exist_ok=True)

        graph_file = cdir / "graph.json"
        vectors_file = cdir / "vectors.json"

        graph_file.write_text(graph_export.model_dump_json(indent=2), encoding="utf-8")
        vectors_file.write_text(vectors_export.model_dump_json(indent=2), encoding="utf-8")

        return graph_file, vectors_file

    def load_cache(self, commit_sha: str) -> tuple[GraphExport, VectorsExport] | None:
        """Loads graph.json and vectors.json from cache as Pydantic models."""
        cdir = self.get_cache_dir(commit_sha)
        graph_file = cdir / "graph.json"
        vectors_file = cdir / "vectors.json"

        if not graph_file.is_file() or not vectors_file.is_file():
            return None

        graph_data = json.loads(graph_file.read_text(encoding="utf-8"))
        vectors_data = json.loads(vectors_file.read_text(encoding="utf-8"))

        graph_export = GraphExport.model_validate(graph_data)
        vectors_export = VectorsExport.model_validate(vectors_data)
        return graph_export, vectors_export


_default_cache_service = CacheService()


def get_git_commit_sha(repo_dir: Path = Path(".")) -> str:
    return _default_cache_service.get_git_commit_sha(repo_dir)


def is_git_dirty(repo_dir: Path = Path(".")) -> bool:
    return _default_cache_service.is_git_dirty(repo_dir)


def get_cache_dir(commit_sha: str, base_dir: Path = DEFAULT_CACHE_BASE) -> Path:
    return base_dir / commit_sha


def has_cached_graphrag(commit_sha: str, base_dir: Path = DEFAULT_CACHE_BASE) -> bool:
    return CacheService(base_dir).has_cached_graphrag(commit_sha)


def save_graphrag_cache(
    runtime_or_exports: Any,
    commit_sha: str,
    base_dir: Path = DEFAULT_CACHE_BASE,
) -> tuple[Path, Path]:
    svc = CacheService(base_dir)
    if hasattr(runtime_or_exports, "falkor") and hasattr(runtime_or_exports, "qdrant"):
        g_exp = runtime_or_exports.falkor.export_graph(commit_sha=commit_sha)
        v_exp = runtime_or_exports.qdrant.export_vectors(commit_sha=commit_sha)
    elif hasattr(runtime_or_exports, "graph_service") and hasattr(runtime_or_exports, "vector_service"):
        g_exp = runtime_or_exports.graph_service.export_graph(commit_sha=commit_sha)
        v_exp = runtime_or_exports.vector_service.export_vectors(commit_sha=commit_sha)
    else:
        raise ValueError("Invalid runtime object for save_graphrag_cache")
    return svc.save_cache(g_exp, v_exp, commit_sha)


def load_graphrag_cache(
    runtime: Any,
    commit_sha: str,
    base_dir: Path = DEFAULT_CACHE_BASE,
) -> bool:
    svc = CacheService(base_dir)
    res = svc.load_cache(commit_sha)
    if res is None:
        return False
    g_exp, v_exp = res
    if hasattr(runtime, "falkor") and hasattr(runtime, "qdrant"):
        runtime.falkor.import_graph(g_exp)
        runtime.qdrant.import_vectors(v_exp)
    elif hasattr(runtime, "graph_service") and hasattr(runtime, "vector_service"):
        runtime.graph_service.import_graph(g_exp)
        runtime.vector_service.import_vectors(v_exp)
    return True
