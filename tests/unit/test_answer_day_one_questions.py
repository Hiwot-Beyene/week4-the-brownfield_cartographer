"""
Unit tests for answer_day_one_questions (mocked semantic_synthesis LLM).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.agents.semanticist import answer_day_one_questions


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@patch("src.agents.semanticist._call_llm_synthesis")
def test_answer_day_one_questions_parses_five_answers(mock_llm, tmp_path: Path) -> None:
    artifacts = tmp_path / ".cartography"
    artifacts.mkdir()
    # Minimal inputs; function only needs them present
    _write_json(artifacts / "module_graph.json", {"nodes": [], "edges": []})
    _write_json(artifacts / "lineage_graph.json", {"nodes": [], "edges": []})
    _write_json(
        artifacts / "survey_summary.json",
        {"high_impact": [], "high_velocity": [], "dead_code_candidates": []},
    )

    answers_payload = [
        {
            "question_id": f"q{i}",
            "answer": f"Answer {i}",
            "citations": [{"file": "src/app.py", "line": 10 + i}],
        }
        for i in range(1, 6)
    ]
    mock_llm.return_value = json.dumps(answers_payload)

    out = answer_day_one_questions(artifacts)

    assert isinstance(out, list)
    assert len(out) == 5
    ids = {a.question_id for a in out}
    assert ids == {"q1", "q2", "q3", "q4", "q5"}
    for a in out:
        assert a.citations
        assert a.citations[0].file == "src/app.py"


def test_answer_day_one_questions_heuristic_mode(tmp_path: Path) -> None:
    artifacts = tmp_path / ".cartography"
    artifacts.mkdir()
    _write_json(artifacts / "module_graph.json", {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "b"}]})
    _write_json(artifacts / "lineage_graph.json", {"nodes": [{"id": "raw.a"}], "edges": []})
    _write_json(artifacts / "survey_summary.json", {"high_impact": ["src/a.py"], "high_velocity": ["src/b.py"], "risky": []})

    out = answer_day_one_questions(artifacts, use_llm=False)
    assert len(out) == 5
    assert out[0].question_id.startswith("fde_")


@patch("src.agents.semanticist._call_llm_synthesis")
def test_answer_day_one_questions_falls_back_when_llm_output_invalid(mock_llm, tmp_path: Path) -> None:
    artifacts = tmp_path / ".cartography"
    artifacts.mkdir()
    _write_json(artifacts / "module_graph.json", {"nodes": [{"id": "a"}], "edges": []})
    _write_json(artifacts / "lineage_graph.json", {"nodes": [{"id": "raw.a"}], "edges": []})
    _write_json(artifacts / "survey_summary.json", {"high_impact": [], "high_velocity": [], "dead_code_candidates": []})
    mock_llm.return_value = "not-json"
    out = answer_day_one_questions(artifacts, use_llm=True)
    assert len(out) == 5
    assert out[0].question_id.startswith("fde_")

