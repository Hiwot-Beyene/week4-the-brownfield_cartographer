"""FastAPI backend API for Brownfield Cartographer.

Exposes read-only endpoints over analyses, modules, survey summaries,
semantic domains, and Day-One answers stored in SQLite + .cartography.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.store import sqlite_store


REPO_ROOT = Path(os.environ.get("CARTOGRAPHER_REPO_ROOT", Path.cwd())).resolve()

app = FastAPI(title="Brownfield Cartographer API", version="0.1.0")

# CORS for local Next.js frontend (3000, 3001) and env override
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        os.environ.get("FRONTEND_ORIGIN", "*"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_db_path() -> Path:
    return sqlite_store._get_db_path(REPO_ROOT)  # type: ignore[attr-defined]


def _get_artifacts_dir(analysis: dict) -> Path:
    """Resolve artifacts_dir from analyses row, falling back to repo_root/.cartography."""
    raw = analysis.get("artifacts_dir")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = REPO_ROOT / raw
    else:
        p = REPO_ROOT / ".cartography"
    return p


@app.get("/health")
async def health() -> dict[str, Any]:
    """Basic health check with DB presence info."""
    db_path = _get_db_path()
    return {"status": "ok", "db_exists": db_path.exists(), "db_path": str(db_path)}


@app.get("/analyses")
async def list_analyses(limit: int = 50) -> list[dict[str, Any]]:
    """List recent analyses across repos (newest first)."""
    return sqlite_store.get_analyses(limit=limit, repo_root=REPO_ROOT)


@app.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: int) -> dict[str, Any]:
    """Return a single analysis row plus derived survey summary."""
    analyses = sqlite_store.get_analyses(limit=1000, repo_root=REPO_ROOT)
    analysis = next((a for a in analyses if a["id"] == analysis_id), None)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    summary = sqlite_store.get_survey_summary_json(analysis_id, repo_root=REPO_ROOT)
    return {"analysis": analysis, "survey_summary": summary}


@app.get("/analyses/{analysis_id}/modules")
async def get_modules(analysis_id: int) -> list[dict[str, Any]]:
    """Return modules for an analysis, including semantic fields when present."""
    return sqlite_store.get_modules(analysis_id, repo_root=REPO_ROOT)


@app.get("/analyses/{analysis_id}/survey-summary")
async def get_survey_summary(analysis_id: int) -> dict[str, Any]:
    summary = sqlite_store.get_survey_summary_json(analysis_id, repo_root=REPO_ROOT)
    if summary is None:
        raise HTTPException(status_code=404, detail="Survey summary not available")
    return summary


@app.get("/analyses/{analysis_id}/domains")
async def get_domain_architecture(analysis_id: int) -> dict[str, Any]:
    analyses = sqlite_store.get_analyses(limit=1000, repo_root=REPO_ROOT)
    analysis = next((a for a in analyses if a["id"] == analysis_id), None)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    artifacts_dir = _get_artifacts_dir(analysis)
    path = artifacts_dir / "domain_architecture_map.json"
    if not path.exists():
        # Graceful degradation: empty map
        return {"module_to_domain": {}, "cluster_to_domain": {}, "skipped_modules": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to read domain map: {e}")


@app.get("/analyses/{analysis_id}/day-one-answers")
async def get_day_one_answers(analysis_id: int) -> list[dict[str, Any]]:
    analyses = sqlite_store.get_analyses(limit=1000, repo_root=REPO_ROOT)
    analysis = next((a for a in analyses if a["id"] == analysis_id), None)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    artifacts_dir = _get_artifacts_dir(analysis)
    path = artifacts_dir / "day_one_answers.json"
    if not path.exists():
        # Graceful degradation: no answers yet
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Expecting a list; if wrapper dict present, unwrap
        if isinstance(data, dict) and "answers" in data:
            return list(data["answers"])
        if isinstance(data, list):
            return data
        return []
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to read day-one answers: {e}")


@app.get("/analyses/{analysis_id}/lineage-summary")
async def get_lineage_summary(analysis_id: int) -> dict[str, Any]:
    """Thin wrapper returning high-velocity, dead-code, and import edges for visualization."""
    survey = sqlite_store.get_survey_summary_json(analysis_id, repo_root=REPO_ROOT) or {}
    imports = sqlite_store.get_import_edges(analysis_id, repo_root=REPO_ROOT)
    return {"survey_summary": survey, "import_edges": imports}


@app.get("/analyses/{analysis_id}/module-graph")
async def get_module_graph(analysis_id: int) -> dict[str, Any]:
    """Module graph for the Surveyor view: nodes and edges from SQLite (modules + import_edges). No JSON files."""
    analyses = sqlite_store.get_analyses(limit=1000, repo_root=REPO_ROOT)
    if not any(a["id"] == analysis_id for a in analyses):
        raise HTTPException(status_code=404, detail="Analysis not found")
    return sqlite_store.get_module_graph_payload(analysis_id, repo_root=REPO_ROOT)


@app.get("/analyses/{analysis_id}/lineage-graph")
async def get_lineage_graph(analysis_id: int) -> dict[str, Any]:
    """Lineage graph for the Hydrologist view: nodes and edges from SQLite (lineage_nodes + lineage_edges)."""
    analyses = sqlite_store.get_analyses(limit=1000, repo_root=REPO_ROOT)
    if not any(a["id"] == analysis_id for a in analyses):
        raise HTTPException(status_code=404, detail="Analysis not found")
    return sqlite_store.get_lineage_graph_payload(analysis_id, repo_root=REPO_ROOT)


@app.get("/analyses/{analysis_id}/lineage/upstream/{node_id:path}")
async def get_lineage_upstream(analysis_id: int, node_id: str, max_depth: int = 25) -> dict[str, Any]:
    """Answer: Show me all upstream dependencies of dataset/table X (DB-backed)."""
    analyses = sqlite_store.get_analyses(limit=1000, repo_root=REPO_ROOT)
    if not any(a["id"] == analysis_id for a in analyses):
        raise HTTPException(status_code=404, detail="Analysis not found")
    upstream = sqlite_store.get_lineage_upstream_dependencies(
        analysis_id, node_id=node_id, max_depth=max_depth, repo_root=REPO_ROOT
    )
    return {"node_id": node_id, "upstream_dependencies": upstream, "count": len(upstream)}


@app.get("/analyses/{analysis_id}/lineage/blast-radius/{node_id:path}")
async def get_lineage_blast_radius(analysis_id: int, node_id: str, max_depth: int = 25) -> dict[str, Any]:
    """Answer: What would break if I change dataset/table Y (DB-backed downstream impact)."""
    analyses = sqlite_store.get_analyses(limit=1000, repo_root=REPO_ROOT)
    if not any(a["id"] == analysis_id for a in analyses):
        raise HTTPException(status_code=404, detail="Analysis not found")
    impacted = sqlite_store.get_lineage_blast_radius(
        analysis_id, node_id=node_id, max_depth=max_depth, repo_root=REPO_ROOT
    )
    return {"node_id": node_id, "downstream_dependents": impacted, "count": len(impacted)}


# To run locally:
#   uv run uvicorn src.api.server:app --reload --port 8000
