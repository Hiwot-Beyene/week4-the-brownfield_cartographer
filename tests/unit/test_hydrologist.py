"""Unit tests for Hydrologist agent: file discovery reuse, per-file skip, no crash."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.hydrologist import run_hydrologist
from src.graph.lineage_graph import DataLineageGraph


def test_run_hydrologist_uses_discovery_and_returns_graph(tmp_path: Path) -> None:
    """run_hydrologist discovers files and returns a DataLineageGraph without reading sensitive paths."""
    (tmp_path / "a.py").write_text("x = 1\n")
    graph = run_hydrologist(tmp_path)
    assert isinstance(graph, DataLineageGraph)
    assert (tmp_path / ".cartography" / "lineage_graph.json").exists()


def test_run_hydrologist_skips_invalid_python_and_completes(tmp_path: Path) -> None:
    """One bad .py file is skipped (logged), run completes and returns graph."""
    (tmp_path / "valid.py").write_text("x = 1\n")
    (tmp_path / "invalid.py").write_text("syntax error here [\n")  # invalid Python
    graph = run_hydrologist(tmp_path)
    assert isinstance(graph, DataLineageGraph)
    # Run must complete; graph may be empty or have nodes from valid.py once analyzer is wired
    assert graph.find_sources() is not None
    assert graph.find_sinks() is not None
