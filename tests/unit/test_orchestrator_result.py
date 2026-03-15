"""Tests for orchestrator AnalysisResult and partial failure handling."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.orchestrator import analyze, AnalysisResult, _collect_artifact_names


def test_analyze_returns_analysis_result_on_resolve_failure() -> None:
    """When resolve_repo raises, analyze returns AnalysisResult with failed_stage=resolve."""
    with patch("src.orchestrator.resolve_repo") as m:
        m.side_effect = ValueError("Invalid repo URL")
        result = analyze("https://invalid.example.com/nonexistent")
    assert isinstance(result, AnalysisResult)
    assert result.success is False
    assert result.failed_stage == "resolve"
    assert result.error is not None


def test_collect_artifact_names_empty_when_no_cartography_dir(tmp_path: Path) -> None:
    """_collect_artifact_names returns [] when .cartography does not exist."""
    assert _collect_artifact_names(tmp_path) == []


def test_collect_artifact_names_lists_existing_files(tmp_path: Path) -> None:
    """_collect_artifact_names lists existing artifact files."""
    cart = tmp_path / ".cartography"
    cart.mkdir(parents=True)
    (cart / "module_graph.json").write_text("{}", encoding="utf-8")
    (cart / "survey_summary.json").write_text("{}", encoding="utf-8")
    names = _collect_artifact_names(tmp_path)
    assert "module_graph.json" in names
    assert "survey_summary.json" in names
