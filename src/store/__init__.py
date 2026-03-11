"""
Persistence layer: SQLite for structured graph/analyses, Chroma for vector search.

Central data dir defaults to ~/.brownfield-cartographer (override with
CARTOGRAPHER_DATA_DIR). Each analysis run is stored so multiple repos/runs
do not overwrite each other.
"""

from src.store.sqlite_store import (
    get_data_dir,
    get_repo_id,
    init_db,
    insert_analysis,
    get_analyses,
    get_modules,
    get_import_edges,
)
from src.store.vector_store import (
    init_vector_store,
    add_modules_to_vector_store,
    search_modules,
)

__all__ = [
    "get_data_dir",
    "get_repo_id",
    "init_db",
    "insert_analysis",
    "get_analyses",
    "get_modules",
    "get_import_edges",
    "init_vector_store",
    "add_modules_to_vector_store",
    "search_modules",
]
