"""
Orchestrator: wires Surveyor + Hydrologist in sequence and serializes all outputs to .cartography/.
Entry point for full analysis (module graph + lineage) from CLI.
"""

from __future__ import annotations

import logging
import subprocess
import shutil
import time
from pathlib import Path

from src.agents.archivist import run_archivist
from src.agents.surveyor import run_surveyor
from src.agents.hydrologist import run_hydrologist
from src.agents.semanticist import run_semanticist
from src.repo_resolver import resolve_repo
from src.store import sqlite_store

logger = logging.getLogger(__name__)

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


def _changed_files_since_last_analysis(repo_path: Path, project_dir: Path) -> list[str]:
    """
    Return files changed since the last stored commit for this repo.
    If no baseline run exists, return [] to indicate full run.
    """
    try:
        repo_id = sqlite_store.get_repo_id(repo_path)
        analyses = sqlite_store.get_analyses(repo_id=repo_id, limit=1, repo_root=project_dir)
        if not analyses:
            return []
        last_sha = (analyses[0].get("commit_sha") or "").strip()
        if not last_sha:
            return []
        r = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--name-only", f"{last_sha}..HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 0:
            return []
        return [line.strip() for line in (r.stdout or "").splitlines() if line.strip()]
    except Exception:
        return []


def analyze(
    repo_input: str,
    branch: str | None = None,
    clone_depth: int | None = 1,
    output_dir: Path | None = None,
    skip_lineage: bool = False,
    incremental: bool = True,
) -> str:
    """
    Run Surveyor, Hydrologist, then Semanticist in sequence on a local path or remote repository.
    All outputs are serialized to output_dir/.cartography/ (default: cwd), including:
    - module_graph.json, modules.json (Surveyor)
    - lineage_graph.json (Hydrologist; at least SQL lineage via sqlglot)
    - domain_architecture_map.json, day_one_answers.json (Semanticist).

    skip_lineage: if True, run only Surveyor+Semanticist (no lineage).
    """
    t0 = time.perf_counter()
    logger.info("analyze: resolving repo input=%s", repo_input)
    repo_path = resolve_repo(repo_input, branch=branch, depth=clone_depth)
    project_dir = Path(output_dir).resolve() if output_dir else Path.cwd().resolve()
    logger.info("analyze: repo=%s output_dir=%s", repo_path, project_dir)
    changed_files = _changed_files_since_last_analysis(repo_path, project_dir) if incremental else []
    if incremental:
        if changed_files:
            logger.info("analyze: incremental mode enabled (%d changed files)", len(changed_files))
        else:
            logger.info("analyze: incremental mode enabled (no baseline changes found; running full scan)")

    # 1. Surveyor: module graph, PageRank, git velocity, dead-code candidates
    s0 = time.perf_counter()
    logger.info("analyze: [1/4] starting Surveyor")
    out, analysis_id = run_surveyor(repo_path, project_data_dir=project_dir)
    logger.info("analyze: [1/4] Surveyor complete in %.1fs", time.perf_counter() - s0)
    _copy_json_artifacts(repo_path, project_dir)
    # 2. Hydrologist: DataLineageGraph, blast_radius, find_sources/find_sinks (unless skipped)
    if not skip_lineage:
        h0 = time.perf_counter()
        logger.info("analyze: [2/4] starting Hydrologist")
        run_hydrologist(
            repo_path,
            project_data_dir=project_dir,
            analysis_id=analysis_id,
            changed_files=changed_files if incremental else None,
        )
        logger.info("analyze: [2/4] Hydrologist complete in %.1fs", time.perf_counter() - h0)
    else:
        logger.info("analyze: [2/4] Hydrologist skipped (--skip-lineage)")
    # 3. Semanticist: purpose statements, domains, Day-One answers
    m0 = time.perf_counter()
    logger.info("analyze: [3/4] starting Semanticist")
    sem_modules, sem_domain_map, sem_day_one = run_semanticist(
        repo_path,
        artifacts_dir=project_dir / ".cartography",
        changed_files=changed_files if incremental else None,
    )
    logger.info(
        "analyze: [3/4] Semanticist complete in %.1fs (modules=%d, day_one_answers=%d)",
        time.perf_counter() - m0,
        len(sem_modules),
        len(sem_day_one),
    )

    # Persist Semanticist outputs into SQLite for API/frontend DB-backed reads.
    if analysis_id is not None:
        db_path = sqlite_store.get_data_dir(project_dir) / "cartographer.db"
        sqlite_store.init_db(db_path=db_path)
        sqlite_store.upsert_modules_semantic_fields(
            analysis_id,
            [m.model_dump(mode="json") for m in sem_modules],
            db_path=db_path,
        )
        sqlite_store.insert_domain_architecture_map(
            analysis_id, sem_domain_map, db_path=db_path
        )
        sqlite_store.insert_day_one_answers(
            analysis_id, sem_day_one, db_path=db_path
        )
    # 4. Archivist: living context + trace + semantic index
    a0 = time.perf_counter()
    logger.info("analyze: [4/4] starting Archivist")
    run_archivist(
        repo_root=repo_path,
        artifacts_dir=project_dir / ".cartography",
        changed_files=changed_files if incremental else None,
    )
    logger.info("analyze: [4/4] Archivist complete in %.1fs", time.perf_counter() - a0)
    logger.info("analyze: finished in %.1fs", time.perf_counter() - t0)
    return str(out)

