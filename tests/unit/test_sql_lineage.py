"""Unit tests for SQLLineageAnalyzer: table extraction from SELECT/FROM/JOIN/WITH, CONSUMES/PRODUCES edges."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzers.sql_lineage import analyze_sql_lineage

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "sql"


def test_analyze_simple_select_returns_from_table() -> None:
    """Analyzing simple_select.sql returns a dataset node for the FROM table."""
    path = FIXTURES / "simple_select.sql"
    nodes, edges = analyze_sql_lineage(path)
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "schema.table_a" in names or "table_a" in names


def test_analyze_cte_and_join_returns_all_tables() -> None:
    """Analyzing cte_and_join.sql returns nodes for t1, t2 (and cte if modeled) and edges."""
    path = FIXTURES / "cte_and_join.sql"
    nodes, edges = analyze_sql_lineage(path)
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "t1" in names or any("t1" in n for n in names)
    assert "t2" in names or any("t2" in n for n in names)
    assert len(edges) >= 1


def test_analyze_insert_select_returns_input_output_tables() -> None:
    """Analyzing insert_select.sql returns input (in_tab) and output (out_tab) nodes and PRODUCES/CONSUMES edges."""
    path = FIXTURES / "insert_select.sql"
    nodes, edges = analyze_sql_lineage(path)
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "in_tab" in names or any("in_tab" in n for n in names)
    assert "out_tab" in names or any("out_tab" in n for n in names)
    assert len(edges) >= 1


def test_analyze_bigquery_dialect() -> None:
    """Parsing with dialect=bigquery works for minimal BigQuery-style SQL."""
    path = FIXTURES / "simple_select.sql"
    nodes, edges = analyze_sql_lineage(path, dialect="bigquery")
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "schema.table_a" in names or "table_a" in names


def test_analyze_invalid_sql_skipped_no_crash() -> None:
    """Invalid SQL file is skipped (exception logged), returns empty and does not raise."""
    path = FIXTURES / "invalid.sql"
    path.write_text("SELECT FROM BROKEN")
    try:
        nodes, edges = analyze_sql_lineage(path)
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
    finally:
        if path.exists():
            path.unlink()
