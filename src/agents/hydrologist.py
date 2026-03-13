"""
Phase 2 Hydrologist Agent: data lineage from Python/SQL/YAML.
Orchestrates PythonDataFlowAnalyzer, SQLLineageAnalyzer, DAGConfigAnalyzer,
merges into DataLineageGraph, writes .cartography/lineage_graph.json and
sql_lineage_summary.json, and persists lineage + summary to SQLite.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.file_discovery import discover_files
from src.analyzers.ignore_rules import IgnoreRules
from src.analyzers.python_data_flow import analyze_python_data_flow
from src.analyzers.sql_lineage import analyze_sql_lineage
from src.analyzers.dag_config_parser import analyze_dag_config

if TYPE_CHECKING:
    from src.graph.lineage_graph import DataLineageGraph

HYDROLOGIST_EXTS = {".py", ".sql", ".yml", ".yaml"}
logger = logging.getLogger(__name__)


def run_hydrologist(
    repo_root: Path,
    project_data_dir: Path | None = None,
    analysis_id: int | None = None,
) -> "DataLineageGraph":
    """
    Run all lineage analyzers on repo_root using Phase 1 file discovery.
    Returns DataLineageGraph (merge + blast_radius, find_sources, find_sinks).
    Writes lineage_graph.json and sql_lineage_summary.json to .cartography/;
    persists nodes/edges and SQL summary to SQLite when analysis_id is set or created.
    When analysis_id is None (e.g. lineage-only CLI), creates an analysis row for this run.
    """
    repo_root = Path(repo_root).resolve()
    project_data_dir = Path(project_data_dir).resolve() if project_data_dir else None
    rules = IgnoreRules.default()
    files = discover_files(repo_root, rules, exts=HYDROLOGIST_EXTS)
    # Filter to Hydrologist-relevant extensions only (discover_files already applied ignore/sensitive)
    hydrologist_files = [f for f in files if f.suffix.lower() in HYDROLOGIST_EXTS]
    logger.info("lineage: discovered %d files to analyze", len(hydrologist_files))

    all_nodes: list = []
    all_edges: list = []
    sql_summaries: list = []
    skipped = 0

    for path in hydrologist_files:
        if path.suffix.lower() == ".py":
            try:
                nodes, edges = analyze_python_data_flow(path)
                all_nodes.extend(nodes)
                all_edges.extend(edges)
            except Exception as e:
                skipped += 1
                logger.warning(
                    "hydrologist_skip path=%s analyzer=PythonDataFlow error=%s",
                    path,
                    e,
                    exc_info=False,
                )
        elif path.suffix.lower() == ".sql":
            try:
                nodes, edges, summary = analyze_sql_lineage(path)
                all_nodes.extend(nodes)
                all_edges.extend(edges)
                sql_summaries.append(summary)
            except Exception as e:
                skipped += 1
                logger.warning(
                    "hydrologist_skip path=%s analyzer=SQLLineage error=%s",
                    path,
                    e,
                    exc_info=False,
                )
        elif path.suffix.lower() in (".yml", ".yaml"):
            try:
                nodes, edges = analyze_dag_config(path)
                all_nodes.extend(nodes)
                all_edges.extend(edges)
            except Exception as e:
                skipped += 1
                logger.warning(
                    "hydrologist_skip path=%s analyzer=DAGConfig error=%s",
                    path,
                    e,
                    exc_info=False,
                )

    if skipped:
        logger.info("lineage: skipped %d file(s) due to errors", skipped)

    # Lazy import to avoid circular dependency until graph exists
    from src.graph.lineage_graph import DataLineageGraph

    graph = DataLineageGraph()
    graph.merge(all_nodes, all_edges)
    # Write to project .cartography when set (keep latest analysis there); else repo-local
    if project_data_dir is not None:
        out_path = project_data_dir / ".cartography" / "lineage_graph.json"
        store_root = project_data_dir
    else:
        out_path = repo_root / ".cartography" / "lineage_graph.json"
        store_root = repo_root
    out_path.parent.mkdir(parents=True, exist_ok=True)
    graph.write_json(out_path)
    # Write SQL lineage summary JSON: only include files with successful parse (statement_count > 0)
    # so we don't store thousands of null/error-only rows; add summary counts for transparency
    if sql_summaries:
        files_with_lineage = [s for s in sql_summaries if (s.get("statement_count") or 0) > 0]
        total = len(sql_summaries)
        with_lineage = len(files_with_lineage)
        # Omit null, empty list, and zero for numeric fields so we don't store null/[]/0
        def _clean_entry(e: dict) -> dict:
            out = {}
            for k, v in e.items():
                if v is None:
                    continue
                if isinstance(v, list) and len(v) == 0:
                    continue
                if k in ("statement_count", "tables_read", "tables_written") and v == 0:
                    continue
                out[k] = v
            return out
        files_clean = [_clean_entry(s) for s in files_with_lineage]
        summary_dict = {"total_files_analyzed": total, "files_with_lineage": with_lineage}
        if total - with_lineage != 0:
            summary_dict["files_parse_error_or_empty"] = total - with_lineage
        summary_payload = {"summary": summary_dict, "files": files_clean}
        summary_path = out_path.parent / "sql_lineage_summary.json"
        try:
            summary_path.write_text(
                json.dumps(summary_payload, indent=2),
                encoding="utf-8",
            )
        except OSError as err:
            logger.warning("could not write sql_lineage_summary.json: %s", err)

    # Persist lineage graph and SQL summary to SQLite (same run as Surveyor when analysis_id passed)
    _analysis_id = analysis_id
    if _analysis_id is None:
        from src.store.sqlite_store import (
            get_data_dir,
            init_db,
            insert_analysis_run_only,
        )
        data_dir = get_data_dir(store_root)
        db_path = data_dir / "cartographer.db"
        artifacts_dir = store_root / ".cartography"
        try:
            init_db(db_path=db_path)
            _analysis_id = insert_analysis_run_only(repo_root, artifacts_dir, db_path=db_path)
        except Exception as e:
            logger.warning("could not create analysis row for lineage run: %s", e)
    if _analysis_id is not None:
        from src.store.sqlite_store import (
            get_data_dir,
            init_db,
            insert_lineage_graph,
            insert_sql_lineage_summary,
        )
        data_dir = get_data_dir(store_root)
        db_path = data_dir / "cartographer.db"
        try:
            init_db(db_path=db_path)
            nodes, edges = graph.get_nodes_and_edges()
            insert_lineage_graph(_analysis_id, nodes, edges, db_path=db_path)
            if sql_summaries:
                files_with_lineage = [s for s in sql_summaries if (s.get("statement_count") or 0) > 0]
                if files_with_lineage:
                    insert_sql_lineage_summary(_analysis_id, files_with_lineage, db_path=db_path)
        except Exception as e:
            logger.warning("could not persist lineage to SQLite: %s", e)

    return graph


