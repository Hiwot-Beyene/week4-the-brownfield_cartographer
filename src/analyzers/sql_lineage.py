"""
SQLLineageAnalyzer: extract table dependencies from SQL using sqlglot.
Explicit traversal of FROM, JOIN, WITH/CTEs, subqueries; multi-dialect support;
dbt ref()/source() resolution with structured per-query source/target mappings and line ranges.
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

DIALECTS = {"postgres", "postgresql", "bigquery", "snowflake", "duckdb", "redshift", "spark"}
DEFAULT_DIALECT = "postgres"

# dbt-style ref('model_name') and source('source_name','table_name') for logical model mapping
_DBT_REF = re.compile(r"\bref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", re.IGNORECASE)
_DBT_SOURCE = re.compile(r"\bsource\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", re.IGNORECASE)


def _offset_to_line(sql: str, offset: int) -> int:
    """Return 1-based line number for character offset in sql."""
    if offset <= 0:
        return 1
    return sql[:offset].count("\n") + 1


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


def _line_range_for_expr(node: exp.Expression) -> tuple[int, int] | None:
    """Return (start_line, end_line) for a sqlglot expression if available."""
    start = getattr(node, "line", None)
    end = getattr(node, "end_line", None) or start
    if start is not None and end is not None:
        return (start, end)
    return None


def _extract_dbt_refs_sources_with_lines(sql: str) -> tuple[list[dict], list[dict]]:
    """
    Extract dbt ref() and source() calls with line ranges (for structured per-query mapping).
    Returns (refs, sources) where each ref is {model, line_start, line_end}, each source is {source_name, table_name, line_start, line_end}.
    """
    refs: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for m in _DBT_REF.finditer(sql):
        model = m.group(1).strip()
        line_start = _offset_to_line(sql, m.start())
        line_end = _offset_to_line(sql, m.end())
        refs.append({"model": model, "line_start": line_start, "line_end": line_end})
    for m in _DBT_SOURCE.finditer(sql):
        src_name = m.group(1).strip()
        tbl_name = m.group(2).strip()
        line_start = _offset_to_line(sql, m.start())
        line_end = _offset_to_line(sql, m.end())
        sources.append({"source_name": src_name, "table_name": tbl_name, "line_start": line_start, "line_end": line_end})
    return refs, sources


def _tables_from_from_join_with_subqueries(stmt: exp.Expression) -> list[tuple[str, int, int]]:
    """
    Explicitly traverse sqlglot AST for FROM, JOIN, WITH (CTE), and subqueries; return (table_name, line_start, line_end).
    Handles: exp.From.this, exp.Join.this, exp.With.expressions (CTE), exp.Subquery.
    """
    result: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()

    def add_table(table_exp: exp.Table) -> None:
        name = _table_name(table_exp)
        rng = _line_range_for_expr(table_exp) or (0, 0)
        key = (name, rng[0], rng[1])
        if key not in seen:
            seen.add(key)
            result.append((name, rng[0], rng[1]))

    def walk(e: exp.Expression) -> None:
        if e is None:
            return
        if isinstance(e, exp.Table):
            add_table(e)
            return
        if isinstance(e, exp.From):
            walk(e.this)
            return
        if isinstance(e, exp.Join):
            walk(e.this)
            return
        if isinstance(e, exp.With):
            for cte in (e.expressions or []):
                if isinstance(cte, exp.CTE):
                    # CTE definition: cte.this is the subquery, alias is the CTE name (we want tables inside the subquery)
                    walk(cte.this)
            return
        if isinstance(e, exp.CTE):
            walk(e.this)
            return
        if isinstance(e, exp.Subquery):
            walk(e.this)
            return
        if isinstance(e, exp.Select):
            from_ = e.args.get("from_") or e.args.get("from")
            if from_:
                walk(from_[0] if isinstance(from_, list) else from_)
            for join in (e.args.get("joins") or []):
                walk(join)
            with_ = e.args.get("with")
            if with_:
                walk(with_[0] if isinstance(with_, list) else with_)
            return
        if isinstance(e, exp.Insert):
            if e.this and isinstance(e.this, exp.Table):
                add_table(e.this)
            walk(e.expression)
            return
        if isinstance(e, exp.Create):
            if e.this and isinstance(e.this, exp.Table):
                add_table(e.this)
            if getattr(e, "expression", None):
                walk(e.expression)
            return
        if isinstance(e, exp.Merge):
            if e.this and isinstance(e.this, exp.Table):
                add_table(e.this)
            return
        # Recurse into children
        for k, v in e.args.items():
            if isinstance(v, (list, tuple)):
                for item in v:
                    if isinstance(item, exp.Expression):
                        walk(item)
            elif isinstance(v, exp.Expression):
                walk(v)

    walk(stmt)
    return result


def dialect_from_path(path: Path) -> str | None:
    """
    Infer SQL dialect from path conventions (e.g. models/bigquery/ -> bigquery).
    Returns None if no convention matches; caller should use default.
    """
    path_str = str(path).replace("\\", "/").lower()
    for d in ("bigquery", "snowflake", "duckdb", "redshift", "spark", "postgres", "postgresql"):
        if f"/{d}/" in path_str or path_str.startswith(f"{d}/"):
            return d if d != "postgresql" else "postgres"
    return None


def analyze_sql_lineage(
    path: Path,
    dialect: str | None = None,
) -> tuple[list[Any], list[Any], dict[str, Any]]:
    """
    Analyze a SQL file for table dependencies. Returns (nodes, edges, summary).
    Nodes are DatasetNode (storage_type table); edges are CONSUMES/PRODUCES.
    summary: dialect_used, statement_count, statement_types, tables_read, tables_written.
    On parse error returns ([], [], summary_with_error) and does not raise.
    """
    path = Path(path).resolve()
    empty_summary: dict[str, Any] = {"path": str(path), "dialect_used": None, "statement_count": 0, "statement_types": [], "tables_read": 0, "tables_written": 0, "error": None}
    nodes: list[Any] = []
    edges: list[Any] = []
    try:
        sql = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("hydrologist_skip path=%s analyzer=SQLLineage error=%s", path, e)
        empty_summary["error"] = str(e)
        return [], [], empty_summary

    read_dialect = dialect or dialect_from_path(path) or DEFAULT_DIALECT
    read_dialect = "postgres" if read_dialect in ("postgres", "postgresql") else read_dialect
    if read_dialect not in DIALECTS:
        read_dialect = DEFAULT_DIALECT

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
        empty_summary["dialect_used"] = read_dialect
        empty_summary["error"] = err_msg
        return [], [], empty_summary

    path_str = str(path)
    trans_id = f"sql:{path_str}"
    seen_tables: set[str] = set()
    all_edges: list[dict] = []
    statement_types: list[str] = []
    tables_written_set: set[str] = set()
    tables_read_set: set[str] = set()
    queries_mapping: list[dict[str, Any]] = []  # per-query source/target with line ranges

    # dbt ref()/source() with line ranges (structured resolution)
    dbt_refs_all, dbt_sources_all = _extract_dbt_refs_sources_with_lines(sql)
    for r in dbt_refs_all:
        model_name = r["model"]
        if model_name and model_name not in seen_tables:
            seen_tables.add(model_name)
            nodes.append(DatasetNode(name=model_name, storage_type="table"))
    for s in dbt_sources_all:
        logical = f"source:{s['source_name']}.{s['table_name']}"
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
        elif isinstance(stmt, exp.Create):
            # CREATE TABLE AS SELECT
            stmt_type = "sql_ctas"
            if stmt.this and isinstance(stmt.this, exp.Table):
                out_table = _table_name(stmt.this)
            # Tables from the SELECT part
            if getattr(stmt, "expression", None) is not None:
                for t in stmt.expression.find_all(exp.Table):
                    tables_read_set.add(_table_name(t))
        statement_types.append(stmt_type)

        line_start = getattr(stmt, "line", None)
        if line_start is None and getattr(stmt, "expressions", None):
            line_start = getattr(stmt.expressions[0], "line", None)
        line_end = getattr(stmt, "end_line", None) or line_start
        line_range = (line_start, line_end) if line_start is not None and line_end is not None else None

        # Per-query source/target mapping (explicit FROM/JOIN/WITH/subquery traversal)
        sources_with_lines = _tables_from_from_join_with_subqueries(stmt)
        stmt_line_start = line_start or 0
        stmt_line_end = line_end or 0
        refs_in_stmt = [r for r in dbt_refs_all if stmt_line_start <= r["line_start"] <= stmt_line_end]
        sources_in_stmt = [s for s in dbt_sources_all if stmt_line_start <= s["line_start"] <= stmt_line_end]
        targets_with_lines: list[dict[str, Any]] = []
        if out_table:
            targets_with_lines.append({"table": out_table, "line_start": stmt_line_start, "line_end": stmt_line_end})
        queries_mapping.append({
            "statement_type": stmt_type,
            "line_range": line_range,
            "sources": [{"table": t[0], "line_start": t[1], "line_end": t[2]} for t in sources_with_lines],
            "targets": targets_with_lines,
            "dbt_refs": refs_in_stmt,
            "dbt_sources": sources_in_stmt,
        })

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
                tables_read_set.add(name)
                all_edges.append(_edge(name, trans_id, "CONSUMES", False))
            if out_table and name != out_table:
                if out_table not in seen_tables:
                    seen_tables.add(out_table)
                    nodes.append(DatasetNode(name=out_table, storage_type="table"))
                tables_written_set.add(out_table)
                all_edges.append(_edge(trans_id, out_table, "PRODUCES", True))

        if out_table and out_table not in seen_tables:
            seen_tables.add(out_table)
            nodes.append(DatasetNode(name=out_table, storage_type="table"))
            tables_written_set.add(out_table)
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

    summary: dict[str, Any] = {
        "path": path_str,
        "dialect_used": read_dialect,
        "statement_count": len(statement_types),
        "statement_types": statement_types,
        "tables_read": len(tables_read_set),
        "tables_written": len(tables_written_set),
        "queries": queries_mapping,
        "dbt_refs": dbt_refs_all,
        "dbt_sources": dbt_sources_all,
    }
    return nodes, unique_edges, summary
