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
    insert_analysis_run_only,
    insert_file_hashes,
    insert_git_velocity,
    insert_lineage_graph,
    insert_sql_lineage_summary,
    insert_survey_summary,
    get_analyses,
    get_modules,
    get_import_edges,
    get_high_impact,
    get_high_velocity,
    get_dead_code_candidates,
    get_survey_summary_json,
    get_domain_architecture_map,
    get_day_one_answers,
    insert_domain_architecture_map,
    insert_day_one_answers,
    upsert_modules_semantic_fields,
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
    "insert_analysis_run_only",
    "insert_file_hashes",
    "insert_git_velocity",
    "insert_lineage_graph",
    "insert_sql_lineage_summary",
    "insert_survey_summary",
    "get_high_impact",
    "get_high_velocity",
    "get_dead_code_candidates",
    "get_survey_summary_json",
    "get_domain_architecture_map",
    "get_day_one_answers",
    "insert_domain_architecture_map",
    "insert_day_one_answers",
    "upsert_modules_semantic_fields",
    "get_analyses",
    "get_modules",
    "get_import_edges",
    "init_vector_store",
    "add_modules_to_vector_store",
    "search_modules",
]
