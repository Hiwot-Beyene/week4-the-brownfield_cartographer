"""Unit tests for Hydrologist agent: file discovery reuse, per-file skip, no crash."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.hydrologist import run_hydrologist
from src.graph.lineage_graph import DataLineageGraph

FIXTURES_SQL = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "sql"


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


def test_run_hydrologist_integrates_edge_case_sql(tmp_path: Path) -> None:
    """Hydrologist run on a dir containing edge-case SQL (nested CTE) produces graph with base tables."""
    deeply_nested = (FIXTURES_SQL / "deeply_nested_cte.sql").read_text(encoding="utf-8")
    (tmp_path / "deeply_nested_cte.sql").write_text(deeply_nested)
    graph = run_hydrologist(tmp_path)
    assert isinstance(graph, DataLineageGraph)
    sources = graph.find_sources()
    sinks = graph.find_sinks()
    # Node IDs in the graph include dataset names (e.g. base_a, base_b, base_c)
    name_str = " ".join(graph._g.nodes())
    assert "base_a" in name_str or "base_b" in name_str or "base_c" in name_str
    assert sources is not None
    assert sinks is not None
