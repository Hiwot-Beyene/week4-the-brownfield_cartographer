"""
Phase 2 Hydrologist Agent: data lineage from Python/SQL/YAML.
Orchestrates PythonDataFlowAnalyzer, SQLLineageAnalyzer, DAGConfigAnalyzer,
merges into DataLineageGraph, and writes .cartography/lineage_graph.json.
"""

from __future__ import annotations

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


def run_hydrologist(repo_root: Path, project_data_dir: Path | None = None) -> "DataLineageGraph":
    """
    Run all lineage analyzers on repo_root using Phase 1 file discovery.
    Returns DataLineageGraph (merge + blast_radius, find_sources, find_sinks).
    Writes lineage_graph.json to project_data_dir/.cartography/ when set (so latest analysis
    is kept in the project .cartography); otherwise writes to repo_root/.cartography/.
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
                nodes, edges = analyze_sql_lineage(path)
                all_nodes.extend(nodes)
                all_edges.extend(edges)
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
    else:
        out_path = repo_root / ".cartography" / "lineage_graph.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    graph.write_json(out_path)
    return graph


