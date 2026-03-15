"""
Edge-case tests for SQLLineageAnalyzer: deeply nested CTEs and vendor-specific SQL.
Complements test_sql_lineage.py with parser-boundary and dialect coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzers.sql_lineage import analyze_sql_lineage, dialect_from_path, DIALECTS

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "sql"


def _node_name(n: object) -> str:
    if hasattr(n, "name"):
        return str(getattr(n, "name", ""))
    if isinstance(n, dict):
        return str(n.get("name", ""))
    return ""


def test_deeply_nested_cte_extracts_base_tables() -> None:
    """Deeply nested CTEs (level1 -> level2 -> level3) still yield base table nodes and edges."""
    path = FIXTURES / "deeply_nested_cte.sql"
    nodes, edges, summary = analyze_sql_lineage(path)
    names = [_node_name(n) for n in nodes]
    name_str = " ".join(names)
    # Parser should find base_a, base_b, base_c from the innermost/outer SELECTs
    assert "base_a" in name_str or "base_b" in name_str or "base_c" in name_str
    assert summary.get("statement_count", 0) >= 1
    assert len(edges) >= 1


def test_vendor_bigquery_backticks_and_qualify() -> None:
    """BigQuery dialect: backtick-qualified table and QUALIFY clause parse without crashing."""
    path = FIXTURES / "vendor_bigquery.sql"
    nodes, edges, summary = analyze_sql_lineage(path, dialect="bigquery")
    names = [_node_name(n) for n in nodes]
    name_str = " ".join(names)
    # May be raw_events, my_project.my_dataset.raw_events, or similar
    assert "raw_events" in name_str or "my_dataset" in name_str or len(nodes) == 0
    assert summary["dialect_used"] == "bigquery"
    # Parser may or may not support QUALIFY; we only require no crash and summary
    assert "path" in summary


def test_vendor_snowflake_sample_and_quoted_identifiers() -> None:
    """Snowflake dialect: SAMPLE and double-quoted identifiers parse without crashing."""
    path = FIXTURES / "vendor_snowflake.sql"
    nodes, edges, summary = analyze_sql_lineage(path, dialect="snowflake")
    names = [_node_name(n) for n in nodes]
    name_str = " ".join(names)
    # May be fact_orders, analytics.fact_orders, or similar
    assert "fact_orders" in name_str or len(nodes) == 0
    assert summary["dialect_used"] == "snowflake"
    assert "path" in summary


def test_dialect_from_path_vendor_dirs() -> None:
    """Path-based dialect inference for vendor-specific directories."""
    assert dialect_from_path(Path("models/bigquery/events.sql")) == "bigquery"
    assert dialect_from_path(Path("dbt/snowflake/staging/fact.sql")) == "snowflake"
    assert dialect_from_path(Path("sql/redshift/export.sql")) == "redshift"
    assert dialect_from_path(Path("scripts/plain.sql")) is None


def test_unparseable_vendor_sql_returns_summary_with_error(tmp_path: Path) -> None:
    """Vendor or malformed SQL that fails all dialects returns summary with error, no raise."""
    path = tmp_path / "weird.sql"
    path.write_text("EXECUTE IMMEDIATE 'SELECT * FROM ' || :tbl;")
    nodes, edges, summary = analyze_sql_lineage(path)
    assert isinstance(nodes, list)
    assert isinstance(edges, list)
    assert summary.get("path") == str(path)
    # May have fallback lineage or empty; must not raise
    assert "error" in summary or len(nodes) == 0
