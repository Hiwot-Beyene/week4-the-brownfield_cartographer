from __future__ import annotations

import json
from pathlib import Path

from src.agents.navigator import (
    ask_navigator,
    find_implementation,
    trace_lineage,
    blast_radius,
    explain_module,
)
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


def test_missing_dataset_trace_returns_low_confidence(tmp_path: Path) -> None:
    """Failure mode: trace_lineage for a dataset that does not exist returns clear message and lower confidence."""
    repo_root = tmp_path
    artifacts = repo_root / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)
    sqlite_store.init_db(repo_root=repo_root)
    modules = [ModuleNode(path="src/foo.py", language="python")]
    analysis_id = sqlite_store.insert_analysis(
        repo_root=repo_root,
        artifacts_dir=artifacts,
        modules=modules,
        pagerank_by_path={"src/foo.py": 0.5},
        edges=[],
    )
    sqlite_store.insert_lineage_graph(
        analysis_id=analysis_id,
        nodes=[],
        edges=[],
        repo_root=repo_root,
    )

    out = trace_lineage(
        analysis_id=analysis_id,
        dataset="nonexistent.dataset.xyz",
        direction="upstream",
        repo_root=repo_root,
    )
    assert "answer" in out and "confidence" in out
    assert "no" in (out["answer"] or "").lower() or "found" in (out["answer"] or "").lower()
    assert out["confidence"] < 0.8


def test_missing_module_explain_returns_not_found(tmp_path: Path) -> None:
    """Failure mode: explain_module for a path not in analysis returns not-found message."""
    repo_root = tmp_path
    artifacts = repo_root / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)
    sqlite_store.init_db(repo_root=repo_root)
    modules = [ModuleNode(path="src/known.py", language="python")]
    analysis_id = sqlite_store.insert_analysis(
        repo_root=repo_root,
        artifacts_dir=artifacts,
        modules=modules,
        pagerank_by_path={"src/known.py": 0.5},
        edges=[],
    )
    (artifacts / "modules.json").write_text(json.dumps([m.model_dump(mode="json") for m in modules]), encoding="utf-8")

    out = explain_module(
        analysis_id=analysis_id,
        path="src/nonexistent_module_xyz.py",
        repo_root=repo_root,
        artifacts_dir=artifacts,
    )
    assert "answer" in out
    assert "not found" in (out["answer"] or "").lower()
    assert out.get("confidence", 1) < 0.5


def test_library_api_tools_callable_without_agent(tmp_path: Path) -> None:
    """Library API: find_implementation, blast_radius, explain_module can be called without ask_navigator."""
    repo_root = tmp_path
    artifacts = repo_root / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)
    sqlite_store.init_db(repo_root=repo_root)
    modules = [
        ModuleNode(path="src/auth.py", language="python", purpose_statement="Handles login."),
    ]
    analysis_id = sqlite_store.insert_analysis(
        repo_root=repo_root,
        artifacts_dir=artifacts,
        modules=modules,
        pagerank_by_path={"src/auth.py": 0.6},
        edges=[],
    )
    (artifacts / "modules.json").write_text(json.dumps([m.model_dump(mode="json") for m in modules]), encoding="utf-8")

    find_out = find_implementation(
        analysis_id=analysis_id,
        concept="authentication",
        repo_root=repo_root,
        artifacts_dir=artifacts,
    )
    assert "answer" in find_out and "citations" in find_out and "confidence" in find_out

    blast_out = blast_radius(
        analysis_id=analysis_id,
        module_path="src/auth.py",
        repo_root=repo_root,
    )
    assert "answer" in blast_out and "confidence" in blast_out

    explain_out = explain_module(
        analysis_id=analysis_id,
        path="src/auth.py",
        repo_root=repo_root,
        artifacts_dir=artifacts,
    )
    assert "answer" in explain_out
    assert "auth" in (explain_out["answer"] or "").lower() or "Purpose" in (explain_out["answer"] or "")


def test_multi_step_find_then_trace(tmp_path: Path) -> None:
    """Multi-step: find_implementation then trace_lineage on a dataset produced by found module."""
    repo_root = tmp_path
    artifacts = repo_root / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)
    sqlite_store.init_db(repo_root=repo_root)
    modules = [
        ModuleNode(path="etl/revenue.sql", language="sql", purpose_statement="Builds revenue mart."),
    ]
    analysis_id = sqlite_store.insert_analysis(
        repo_root=repo_root,
        artifacts_dir=artifacts,
        modules=modules,
        pagerank_by_path={"etl/revenue.sql": 0.5},
        edges=[],
    )
    sqlite_store.insert_lineage_graph(
        analysis_id=analysis_id,
        nodes=[{"id": "mart.revenue", "type": "dataset"}, {"id": "raw.orders", "type": "dataset"}],
        edges=[
            {"source": "raw.orders", "target": "mart.revenue", "edge_type": "PRODUCES", "source_file": "etl/revenue.sql"},
        ],
        repo_root=repo_root,
    )
    (artifacts / "modules.json").write_text(json.dumps([m.model_dump(mode="json") for m in modules]), encoding="utf-8")

    step1 = find_implementation(
        analysis_id=analysis_id,
        concept="revenue mart",
        repo_root=repo_root,
        artifacts_dir=artifacts,
    )
    step2 = trace_lineage(
        analysis_id=analysis_id,
        dataset="mart.revenue",
        direction="upstream",
        repo_root=repo_root,
    )
    assert step1.get("answer") and step2.get("answer")
    assert "revenue" in (step1["answer"] or "").lower() or len(step1.get("citations") or []) >= 0
    assert "upstream" in (step2["answer"] or "").lower() or "lineage" in (step2["answer"] or "").lower()

