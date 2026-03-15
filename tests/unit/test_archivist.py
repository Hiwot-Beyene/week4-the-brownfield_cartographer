from __future__ import annotations

import json
from pathlib import Path

from src.agents.archivist import (
    run_archivist,
    CODEBASE_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_run_archivist_generates_living_artifacts(tmp_path: Path) -> None:
    artifacts = tmp_path / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)

    _write_json(
        artifacts / "modules.json",
        [
            {
                "path": "src/core.py",
                "language": "python",
                "pagerank": 0.8,
                "purpose_statement": "Coordinates core application behavior.",
                "documentation_drift": True,
            },
            {
                "path": "src/helpers.py",
                "language": "python",
                "pagerank": 0.2,
                "purpose_statement": "Provides helper utilities.",
            },
        ],
    )
    _write_json(
        artifacts / "module_graph.json",
        {"graph": {"strongly_connected_components": [["src/core.py", "src/helpers.py"]]}},
    )
    _write_json(
        artifacts / "lineage_graph.json",
        {
            "nodes": [{"id": "raw.users"}, {"id": "mart.active_users"}],
            "edges": [{"source": "raw.users", "target": "mart.active_users"}],
        },
    )
    _write_json(
        artifacts / "git_velocity.json",
        {"days": 30, "per_file": {"src/core.py": 6, "src/helpers.py": 3}},
    )
    _write_json(
        artifacts / "day_one_answers.json",
        {
            "answers": [
                {
                    "question_id": "fde_q1_business_capability",
                    "answer": "Core capability answer.",
                    "citations": [{"file": "src/core.py", "line": 12}],
                }
            ]
        },
    )

    out = run_archivist(repo_root=tmp_path, artifacts_dir=artifacts, changed_files=["src/core.py"])

    assert (artifacts / "CODEBASE.md").exists()
    assert (artifacts / "onboarding_brief.md").exists()
    assert (artifacts / "semantic_index" / "manifest.json").exists()
    assert (artifacts / "cartography_trace.jsonl").exists()
    trace_line = (artifacts / "cartography_trace.jsonl").read_text(encoding="utf-8").strip().split("\n")[0]
    trace_obj = json.loads(trace_line)
    assert trace_obj.get("schema_version") == TRACE_SCHEMA_VERSION
    assert "codebase" in out and out["codebase"].endswith("CODEBASE.md")

    codebase = (artifacts / "CODEBASE.md").read_text(encoding="utf-8")
    assert f"cartography_codebase_schema={CODEBASE_SCHEMA_VERSION}" in codebase
    assert "## Architecture Overview" in codebase
    assert "## Critical Path" in codebase
    assert "## Data Sources & Sinks" in codebase
    assert "## Known Debt" in codebase
    assert "## High-Velocity Files" in codebase
    assert "## Module Purpose Index" in codebase

    brief = (artifacts / "onboarding_brief.md").read_text(encoding="utf-8")
    assert "## The Five FDE Day-One Questions" in brief
    assert "What is the primary data ingestion path?" in brief


def test_onboarding_brief_reads_semantic_index_day_one_answers(tmp_path: Path) -> None:
    """Brief is always built from artifacts (evidence-based); stored day_one_answers are not used for brief content."""
    artifacts = tmp_path / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "semantic_index").mkdir(parents=True, exist_ok=True)
    _write_json(artifacts / "modules.json", [])
    _write_json(artifacts / "module_graph.json", {"graph": {}, "nodes": [], "edges": []})
    _write_json(artifacts / "lineage_graph.json", {"nodes": [], "edges": []})
    _write_json(artifacts / "survey_summary.json", {"high_impact": [], "high_velocity": [], "risky": []})
    _write_json(artifacts / "git_velocity.json", {"days": 30, "per_file": {}})
    _write_json(
        artifacts / "semantic_index" / "day_one_answers.json",
        {
            "answers": [
                {
                    "question_id": "fde_q1_business_capability",
                    "answer": "Ingestion comes from upstream raw sources.",
                    "citations": [{"file": "lineage_graph.json", "line": 1}],
                }
            ]
        },
    )

    run_archivist(repo_root=tmp_path, artifacts_dir=artifacts)
    brief = (artifacts / "onboarding_brief.md").read_text(encoding="utf-8")
    # Brief is artifact-derived: contains evidence-based wording and provenance
    assert "Data ingestion" in brief or "lineage" in brief
    assert "Evidence (provenance)" in brief
    assert "The Five FDE Day-One Questions" in brief


def test_onboarding_brief_replaces_placeholder_answers_with_heuristics(tmp_path: Path) -> None:
    artifacts = tmp_path / ".cartography"
    artifacts.mkdir(parents=True, exist_ok=True)
    _write_json(artifacts / "module_graph.json", {"nodes": [], "edges": []})
    _write_json(artifacts / "lineage_graph.json", {"nodes": [], "edges": [{"source": "raw.a", "target": "int.a"}]})
    _write_json(artifacts / "survey_summary.json", {"high_impact": ["src/a.py"], "high_velocity": ["src/b.py"]})
    _write_json(
        artifacts / "day_one_answers.json",
        {
            "answers": [
                {
                    "question_id": "fde_q1_business_capability",
                    "answer": "Insufficient evidence in this run to produce a high-confidence answer.",
                    "citations": [],
                }
            ]
        },
    )
    run_archivist(repo_root=tmp_path, artifacts_dir=artifacts)
    brief = (artifacts / "onboarding_brief.md").read_text(encoding="utf-8")
    assert "Insufficient evidence in this run to produce a high-confidence answer." not in brief

