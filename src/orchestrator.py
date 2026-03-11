from __future__ import annotations

import shutil
from pathlib import Path

from src.agents.surveyor import run_surveyor
from src.repo_resolver import resolve_repo

_CARTOGRAPHY_JSON_ARTIFACTS = (
    "file_hashes.json",
    "git_velocity.json",
    "modules.json",
    "module_graph.json",
)


def _copy_json_artifacts_to_cwd(repo_path: Path) -> None:
    """Copy the four .cartography JSON files from the analyzed repo into cwd/.cartography so they are always updated."""
    source_dir = Path(repo_path).resolve() / ".cartography"
    dest_dir = Path.cwd().resolve() / ".cartography"
    if source_dir == dest_dir or not source_dir.is_dir():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in _CARTOGRAPHY_JSON_ARTIFACTS:
        src = source_dir / name
        if src.is_file():
            shutil.copy2(src, dest_dir / name)


def analyze(repo_input: str, branch: str | None = None, clone_depth: int | None = 1) -> str:
    """
    Run Surveyor analysis on a local path or remote repository (e.g. GitHub URL).
    DB and vector store are always written to the project (cwd) .cartography so analyses are recorded there.
    All four JSON files are overwritten in the analyzed repo's .cartography, then copied to cwd/.cartography.
    """
    repo_path = resolve_repo(repo_input, branch=branch, depth=clone_depth)
    # Use cwd as project data dir so DB/chroma and exported JSONs live in the project for both local and remote
    out = run_surveyor(repo_path, project_data_dir=Path.cwd())
    _copy_json_artifacts_to_cwd(repo_path)
    return str(out)

