"""
SQLLineageAnalyzer: extract table dependencies from SQL using sqlglot.
Parses .sql and dbt model files; FROM/JOIN/WITH/INSERT; dbt ref()/source(); clear parse diagnostics.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from src.models.knowledge_graph import DatasetNode

logger = logging.getLogger(__name__)

DIALECTS = {"postgres", "postgresql", "bigquery", "snowflake", "duckdb"}

# dbt-style ref('model_name') and source('source_name','table_name') for logical model mapping
_DBT_REF = re.compile(r"\bref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", re.IGNORECASE)
_DBT_SOURCE = re.compile(r"\bsource\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", re.IGNORECASE)


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
        err_msg = str(e)
        if hasattr(e, "errors") and e.errors:
            err_msg = "; ".join(str(x) for x in e.errors[:3])
        logger.warning(
            "SQLLineage unparseable path=%s dialect=%s diagnostic=%s (file skipped)",
            path, read_dialect, err_msg,
        )
        return [], []

    path_str = str(path)
    trans_id = f"sql:{path_str}"
    seen_tables: set[str] = set()
    all_edges: list[dict] = []

    # dbt ref()/source(): logical model names as dataset nodes (map to underlying tables)
    for m in _DBT_REF.finditer(sql):
        model_name = m.group(1).strip()
        if model_name and model_name not in seen_tables:
            seen_tables.add(model_name)
            nodes.append(DatasetNode(name=model_name, storage_type="table"))
    for m in _DBT_SOURCE.finditer(sql):
        source_name, table_name = m.group(1).strip(), m.group(2).strip()
        logical = f"source:{source_name}.{table_name}"
        if logical not in seen_tables:
            seen_tables.add(logical)
            nodes.append(DatasetNode(name=logical, storage_type="table"))

    for stmt in parsed:
        if stmt is None:
            continue
        out_table: str | None = None
        stmt_type = "sql_select"
        if isinstance(stmt, exp.Insert):
            stmt_type = "sql_insert"
            if stmt.this and isinstance(stmt.this, exp.Table):
                out_table = _table_name(stmt.this)
        elif isinstance(stmt, exp.Merge):
            stmt_type = "sql_merge"
            if stmt.this and isinstance(stmt.this, exp.Table):
                out_table = _table_name(stmt.this)

        line_start = getattr(stmt, "line", None)
        if line_start is None and stmt.expressions:
            line_start = getattr(stmt.expressions[0], "line", None)
        line_end = getattr(stmt, "end_line", None) or line_start
        line_range = (line_start, line_end) if line_start is not None and line_end is not None else None

        def _edge(src: str, tgt: str, edge_type: str, is_write: bool) -> dict:
            e = {"source": src, "target": tgt, "edge_type": edge_type, "is_write": is_write}
            e["transformation_type"] = stmt_type
            e["source_file"] = path_str
            if line_range:
                e["line_range"] = line_range
            return e

        for table_exp in stmt.find_all(exp.Table):
            name = _table_name(table_exp)
            if name not in seen_tables:
                seen_tables.add(name)
                nodes.append(DatasetNode(name=name, storage_type="table"))
            if name != out_table:
                all_edges.append(_edge(name, trans_id, "CONSUMES", False))
            if out_table and name != out_table:
                if out_table not in seen_tables:
                    seen_tables.add(out_table)
                    nodes.append(DatasetNode(name=out_table, storage_type="table"))
                all_edges.append(_edge(trans_id, out_table, "PRODUCES", True))

        if out_table and out_table not in seen_tables:
            seen_tables.add(out_table)
            nodes.append(DatasetNode(name=out_table, storage_type="table"))
            all_edges.append(_edge(trans_id, out_table, "PRODUCES", True))

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
