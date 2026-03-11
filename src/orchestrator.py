"""
Orchestrator: wires Surveyor + Hydrologist in sequence and serializes all outputs to .cartography/.
Entry point for full analysis (module graph + lineage) from CLI.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from src.agents.surveyor import run_surveyor
from src.agents.hydrologist import run_hydrologist
from src.repo_resolver import resolve_repo

_CARTOGRAPHY_JSON_ARTIFACTS = (
    "file_hashes.json",
    "git_velocity.json",
    "modules.json",
    "module_graph.json",
    "survey_summary.json",
    "lineage_graph.json",
    "sql_lineage_summary.json",
)


def _copy_json_artifacts(repo_path: Path, dest_root: Path) -> None:
    """Copy .cartography JSON artifacts from the analyzed repo into dest_root/.cartography."""
    source_dir = Path(repo_path).resolve() / ".cartography"
    dest_dir = Path(dest_root).resolve() / ".cartography"
    if source_dir == dest_dir or not source_dir.is_dir():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in _CARTOGRAPHY_JSON_ARTIFACTS:
        src = source_dir / name
        if src.is_file():
            shutil.copy2(src, dest_dir / name)


def analyze(
    repo_input: str,
    branch: str | None = None,
    clone_depth: int | None = 1,
    output_dir: Path | None = None,
    skip_lineage: bool = False,
) -> str:
    """
    Run Surveyor then Hydrologist in sequence on a local path or remote repository (e.g. GitHub URL).
    All outputs are serialized to output_dir/.cartography/ (default: cwd), including:
    - module_graph.json (Surveyor)
    - lineage_graph.json (Hydrologist; at least SQL lineage via sqlglot).
    skip_lineage: if True, run only Surveyor (no lineage).
    """
    repo_path = resolve_repo(repo_input, branch=branch, depth=clone_depth)
    project_dir = Path(output_dir).resolve() if output_dir else Path.cwd().resolve()
    # 1. Surveyor: module graph, PageRank, git velocity, dead-code candidates
    out = run_surveyor(repo_path, project_data_dir=project_dir)
    _copy_json_artifacts(repo_path, project_dir)
    # 2. Hydrologist: DataLineageGraph, blast_radius, find_sources/find_sinks (unless skipped)
    if not skip_lineage:
        run_hydrologist(repo_path, project_data_dir=project_dir)
    return str(out)

