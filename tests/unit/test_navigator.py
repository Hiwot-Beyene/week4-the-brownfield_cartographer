from __future__ import annotations

import json
from pathlib import Path

from src.agents.navigator import ask_navigator
from src.models.module import ModuleNode
from src.store import sqlite_store


def test_navigator_returns_evidence_citations(tmp_path: Path) -> None:
    repo_root = tmp_path
    artifacts = repo_root / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)
    sqlite_store.init_db(repo_root=repo_root)

    modules = [
        ModuleNode(
            path="src/revenue.py",
            language="python",
            purpose_statement="Computes revenue metrics from daily transactions.",
        ),
        ModuleNode(path="src/jobs.py", language="python"),
    ]
    analysis_id = sqlite_store.insert_analysis(
        repo_root=repo_root,
        artifacts_dir=artifacts,
        modules=modules,
        pagerank_by_path={"src/revenue.py": 0.7, "src/jobs.py": 0.2},
        edges=[("src/jobs.py", "src/revenue.py", 1)],
    )
    sqlite_store.insert_lineage_graph(
        analysis_id=analysis_id,
        nodes=[{"id": "raw.transactions", "type": "dataset"}, {"id": "mart.revenue", "type": "dataset"}],
        edges=[
            {
                "source": "raw.transactions",
                "target": "mart.revenue",
                "edge_type": "PRODUCES",
                "source_file": "models/revenue.sql",
                "line_range": [10, 40],
            }
        ],
        repo_root=repo_root,
    )

    (artifacts / "modules.json").write_text(
        json.dumps([m.model_dump(mode="json") for m in modules], indent=2),
        encoding="utf-8",
    )
    sem_dir = artifacts / "semantic_index"
    sem_dir.mkdir(parents=True, exist_ok=True)
    (sem_dir / "purpose_vectors.jsonl").write_text(
        json.dumps(
            {
                "path": "src/revenue.py",
                "purpose_statement": "Computes revenue metrics from daily transactions.",
                "vector": [1.0, 0.0],
                "method": "llm_inference",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    found = ask_navigator(
        analysis_id=analysis_id,
        query="Where is the revenue calculation logic?",
        repo_root=repo_root,
        artifacts_dir=artifacts,
    )
    assert "revenue.py" in (found.get("answer") or "")
    assert found.get("citations")
    assert {"source_file", "line_range", "method"} <= set(found["citations"][0].keys())

    lineage = ask_navigator(
        analysis_id=analysis_id,
        query="What produces mart.revenue dataset?",
        repo_root=repo_root,
        artifacts_dir=artifacts,
    )
    assert "lineage" in (lineage.get("answer") or "").lower()
    assert any(c.get("method") == "static" for c in lineage.get("citations") or [])

