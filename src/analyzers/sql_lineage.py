"""
SQLLineageAnalyzer: extract table dependencies from SQL using sqlglot.
Parses .sql and dbt model files; FROM/JOIN/WITH/INSERT; supports PostgreSQL, BigQuery, Snowflake, DuckDB.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from src.models.knowledge_graph import DatasetNode

logger = logging.getLogger(__name__)

DIALECTS = {"postgres", "postgresql", "bigquery", "snowflake", "duckdb"}


def _table_name(table_exp: exp.Table) -> str:
    """Return fully qualified table name (catalog.schema.name or schema.name or name)."""
    parts = []
    if table_exp.catalog:
        parts.append(table_exp.catalog)
    if table_exp.db:
        parts.append(table_exp.db)
    if table_exp.name:
        parts.append(table_exp.name)
    return ".".join(parts) if parts else str(table_exp)


def analyze_sql_lineage(
    path: Path,
    dialect: str = "postgres",
) -> tuple[list[Any], list[Any]]:
    """
    Analyze a SQL file for table dependencies. Returns (nodes, edges).
    Nodes are DatasetNode (storage_type table); edges are CONSUMES (query -> input), PRODUCES (query -> output).
    On parse error returns ([], []) and does not raise.
    """
    path = Path(path).resolve()
    nodes: list[Any] = []
    edges: list[Any] = []
    try:
        sql = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("hydrologist_skip path=%s analyzer=SQLLineage error=%s", path, e)
        return [], []

    read_dialect = "postgres" if dialect in ("postgres", "postgresql") else dialect
    if read_dialect not in DIALECTS:
        read_dialect = "postgres"

    try:
        parsed = sqlglot.parse(sql, read=read_dialect)
    except Exception as e:
        logger.warning("hydrologist_skip path=%s analyzer=SQLLineage parse_error=%s", path, e)
        return [], []

    path_str = str(path)
    trans_id = f"sql:{path_str}"
    seen_tables: set[str] = set()
    all_edges: list[dict] = []

    for stmt in parsed:
        if stmt is None:
            continue
        out_table: str | None = None
        if isinstance(stmt, exp.Insert):
            if stmt.this and isinstance(stmt.this, exp.Table):
                out_table = _table_name(stmt.this)
        elif isinstance(stmt, exp.Merge):
            if stmt.this and isinstance(stmt.this, exp.Table):
                out_table = _table_name(stmt.this)

        for table_exp in stmt.find_all(exp.Table):
            name = _table_name(table_exp)
            if name not in seen_tables:
                seen_tables.add(name)
                nodes.append(DatasetNode(name=name, storage_type="table"))
            # CONSUMES: input table -> transformation (only for input tables, not output)
            if name != out_table:
                all_edges.append({"source": name, "target": trans_id})
            if out_table and name != out_table:
                if out_table not in seen_tables:
                    seen_tables.add(out_table)
                    nodes.append(DatasetNode(name=out_table, storage_type="table"))
                all_edges.append({"source": trans_id, "target": out_table})

        if out_table and out_table not in seen_tables:
            seen_tables.add(out_table)
            nodes.append(DatasetNode(name=out_table, storage_type="table"))
            all_edges.append({"source": trans_id, "target": out_table})

    if all_edges or nodes:
        nodes.append({"id": trans_id, "type": "transformation"})

    seen_edges: set[tuple[str, str]] = set()
    unique_edges: list[Any] = []
    for e in all_edges:
        src, tgt = e.get("source", ""), e.get("target", "")
        if (src, tgt) not in seen_edges:
            seen_edges.add((src, tgt))
            unique_edges.append(e)

    return nodes, unique_edges
