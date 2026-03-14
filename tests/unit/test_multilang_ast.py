"""Tests for the reusable multi-language AST parsing service (parse + extract_structural + graceful failure)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzers.multilang_ast import ParseResult, StructuralExtract, parse, extract_structural

FIXTURES_SQL = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "sql"
FIXTURES_YAML = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "dbt_airflow"


def test_parse_sql_returns_result_with_dialect() -> None:
    """parse() for .sql returns success and sqlglot AST (root is list of statements)."""
    path = FIXTURES_SQL / "simple_select.sql"
    if not path.exists():
        pytest.skip("fixture missing")
    r = parse(path)
    assert isinstance(r, ParseResult)
    assert r.success is True
    assert r.language == "sql"
    assert r.root is not None
    assert r.dialect is not None


def test_parse_nonexistent_file_returns_failure() -> None:
    """parse() for missing file returns success=False and error message."""
    r = parse(Path("/nonexistent/file.sql"))
    assert r.success is False
    assert r.error is not None


def test_extract_structural_sql_returns_tables() -> None:
    """extract_structural() for SQL returns tables_referenced and no error when parse succeeds."""
    path = FIXTURES_SQL / "simple_select.sql"
    if not path.exists():
        pytest.skip("fixture missing")
    ext = extract_structural(path, "sql")
    assert isinstance(ext, StructuralExtract)
    assert ext.error is None
    assert "schema.table_a" in ext.tables_referenced or "table_a" in ext.tables_referenced


def test_extract_structural_yaml_returns_keys() -> None:
    """extract_structural() for YAML returns structural_keys (top-level config keys)."""
    path = FIXTURES_YAML / "schema.yml"
    if not path.exists():
        pytest.skip("fixture missing")
    ext = extract_structural(path, "yaml")
    assert ext.error is None
    assert "version" in ext.structural_keys or "sources" in ext.structural_keys or "models" in ext.structural_keys


def test_extract_structural_graceful_failure() -> None:
    """extract_structural() on unparseable content sets error and returns empty lists."""
    path = Path("/nonexistent/x.sql")
    ext = extract_structural(path, "sql")
    assert ext.error is not None
    assert ext.tables_referenced == []
