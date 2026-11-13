"""Shared database and embedding utility services."""

from app.coddy.utils.services.duckdb_service import (
    DuckDbService,
    get_default_metrics_db_path,
    get_duckdb_service,
)
from app.coddy.utils.services.embeddinggemma_service import EmbeddingGemmaService
from app.coddy.utils.services.falkordb_service import FalkorDBService
from app.coddy.utils.services.fastembed_service import (
    FastEmbedService,
    get_query_sparse_embedding,
    get_query_sparse_embeddings,
    get_sparse_embeddings,
)
from app.coddy.utils.services.sqlite_service import (
    SqliteService,
    get_default_data_db_path,
    get_sqlite_service,
)
from app.coddy.utils.services.ui_service import (
    UIService,
    get_ui_service,
    ui_service,
)
from app.coddy.utils.services.user_service import (
    UserService,
    get_user_service,
)

__all__ = [
    "DuckDbService",
    "EmbeddingGemmaService",
    "FalkorDBService",
    "FastEmbedService",
    "SqliteService",
    "UIService",
    "UserService",
    "get_default_data_db_path",
    "get_default_metrics_db_path",
    "get_duckdb_service",
    "get_query_sparse_embedding",
    "get_query_sparse_embeddings",
    "get_sparse_embeddings",
    "get_sqlite_service",
    "get_ui_service",
    "get_user_service",
    "ui_service",
]
