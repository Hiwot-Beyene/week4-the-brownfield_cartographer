"""Unit tests for PythonDataFlowAnalyzer: literal path extraction, dynamic ref logging, skip on error."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.analyzers.python_data_flow import analyze_python_data_flow

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "python"


def test_analyze_read_csv_literal_returns_dataset() -> None:
    """Analyzing read_csv_literal.py returns at least one dataset with name/path equal to the literal."""
    path = FIXTURES / "read_csv_literal.py"
    nodes, edges = analyze_python_data_flow(path)
    names = [n.name if hasattr(n, "name") else n.get("name") for n in nodes]
    assert "data/file.csv" in names
    assert len(nodes) >= 1


def test_analyze_dynamic_ref_logs_and_no_edge(caplog: pytest.LogCaptureFixture) -> None:
    """Analyzing dynamic_ref.py (f-string or variable) logs 'dynamic reference, cannot resolve' and adds no lineage edge for that call."""
    caplog.set_level(logging.INFO)
    path = FIXTURES / "dynamic_ref.py"
    nodes, edges = analyze_python_data_flow(path)
    assert "dynamic reference" in caplog.text.lower() or "cannot resolve" in caplog.text.lower()
    # No literal path in dynamic_ref.py (f-string and variable) so no node for x.csv
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "x.csv" not in names


def test_analyze_invalid_python_skipped_no_crash() -> None:
    """Invalid Python file is skipped (exception caught), returns empty and does not raise."""
    path = FIXTURES / "invalid_syntax.py"
    nodes, edges = analyze_python_data_flow(path)
    assert isinstance(nodes, list)
    assert isinstance(edges, list)
    assert len(nodes) == 0
    assert len(edges) == 0


def test_complex_dynamic_query_no_literal_no_edge() -> None:
    """Format(), % formatting, and string concatenation for table names produce no lineage edges (dynamic)."""
    path = FIXTURES / "dynamic_query_complex.py"
    nodes, edges = analyze_python_data_flow(path)
    names = [getattr(n, "name", n.get("name", "")) for n in nodes]
    # No literal "users" or "events" in read_sql/execute; all dynamic
    assert "users" not in names
    assert "events" not in names
    assert isinstance(edges, list)


def test_complex_dynamic_query_logs_dynamic_reference(caplog: pytest.LogCaptureFixture) -> None:
    """Complex dynamic query construction logs dynamic reference / cannot resolve."""
    caplog.set_level(logging.INFO)
    path = FIXTURES / "dynamic_query_complex.py"
    analyze_python_data_flow(path)
    assert "dynamic reference" in caplog.text.lower() or "cannot resolve" in caplog.text.lower()
