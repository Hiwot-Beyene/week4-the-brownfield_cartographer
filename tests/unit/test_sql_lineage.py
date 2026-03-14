"""Unit tests for SQLLineageAnalyzer: table extraction from SELECT/FROM/JOIN/WITH/CTAS, CONSUMES/PRODUCES edges, summary."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzers.sql_lineage import analyze_sql_lineage, dialect_from_path, DIALECTS

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "sql"


def test_analyze_simple_select_returns_from_table() -> None:
    """Analyzing simple_select.sql returns a dataset node for the FROM table."""
    path = FIXTURES / "simple_select.sql"
    nodes, edges, summary = analyze_sql_lineage(path)
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "schema.table_a" in names or "table_a" in names
    assert summary["dialect_used"] == "postgres"
    assert summary["statement_count"] >= 1


def test_analyze_cte_and_join_returns_all_tables() -> None:
    """Analyzing cte_and_join.sql returns nodes for t1, t2 (and cte if modeled) and edges."""
    path = FIXTURES / "cte_and_join.sql"
    nodes, edges, summary = analyze_sql_lineage(path)
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "t1" in names or any("t1" in n for n in names)
    assert "t2" in names or any("t2" in n for n in names)
    assert len(edges) >= 1


def test_analyze_insert_select_returns_input_output_tables() -> None:
    """Analyzing insert_select.sql returns input (in_tab) and output (out_tab) nodes and PRODUCES/CONSUMES edges."""
    path = FIXTURES / "insert_select.sql"
    nodes, edges, summary = analyze_sql_lineage(path)
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "in_tab" in names or any("in_tab" in n for n in names)
    assert "out_tab" in names or any("out_tab" in n for n in names)
    assert len(edges) >= 1


def test_analyze_bigquery_dialect() -> None:
    """Parsing with dialect=bigquery works for minimal BigQuery-style SQL."""
    path = FIXTURES / "simple_select.sql"
    nodes, edges, summary = analyze_sql_lineage(path, dialect="bigquery")
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "schema.table_a" in names or "table_a" in names
    assert summary["dialect_used"] == "bigquery"


def test_analyze_ctas_returns_output_and_input_tables(tmp_path: Path) -> None:
    """CREATE TABLE AS SELECT is parsed; output table and source table appear in nodes/edges."""
    sql = "CREATE TABLE foo AS SELECT * FROM bar"
    path = tmp_path / "ctas.sql"
    path.write_text(sql)
    nodes, edges, summary = analyze_sql_lineage(path)
    names = [n.name if hasattr(n, "name") else n.get("name", "") for n in nodes]
    assert "foo" in names
    assert "bar" in names
    assert "sql_ctas" in summary["statement_types"]


def test_dialect_from_path() -> None:
    """Path conventions (e.g. models/bigquery/) infer dialect."""
    assert dialect_from_path(Path("models/bigquery/foo.sql")) == "bigquery"
    assert dialect_from_path(Path("dbt/snowflake/models/x.sql")) == "snowflake"
    assert dialect_from_path(Path("plain/script.sql")) is None


def test_dialects_include_redshift_spark() -> None:
    """Supported dialects include redshift and spark."""
    assert "redshift" in DIALECTS
    assert "spark" in DIALECTS


def test_analyze_sql_returns_per_query_mapping_and_dbt_line_ranges(tmp_path: Path) -> None:
    """Summary includes queries (per-statement sources/targets with line ranges) and dbt_refs/dbt_sources."""
    sql = "SELECT * FROM t1;\nWITH cte AS (SELECT * FROM t2) SELECT * FROM cte"
    path = tmp_path / "with_cte.sql"
    path.write_text(sql)
    nodes, edges, summary = analyze_sql_lineage(path)
    assert "queries" in summary
    assert isinstance(summary["queries"], list)
    assert len(summary["queries"]) >= 1
    q = summary["queries"][0]
    assert "statement_type" in q
    assert "sources" in q
    assert "dbt_refs" in summary
    assert "dbt_sources" in summary


def test_analyze_invalid_sql_skipped_no_crash() -> None:
    """Unparseable SQL returns empty nodes/edges and summary with error; does not raise."""
    path = FIXTURES / "invalid.sql"
    path.write_text("{{{ NOT VALID SQL {{{")
    try:
        nodes, edges, summary = analyze_sql_lineage(path)
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        assert "path" in summary
        assert summary.get("error") is not None or (len(nodes) == 0 and len(edges) == 0)
    finally:
        if path.exists():
            path.write_text("")  # restore empty for other runs
