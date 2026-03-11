"""
PythonDataFlowAnalyzer: extract dataset read/write from Python code.
Uses AST (stdlib ast) to find pandas read_csv/read_sql, SQLAlchemy execute(), PySpark read/write.
Literal string args only; non-literals log "dynamic reference, cannot resolve" and no edge.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from src.models.knowledge_graph import DatasetNode

logger = logging.getLogger(__name__)

# Call patterns: (module/attr names to look for, arg index for path/table, storage_type)
_PANDAS_READ = [("read_csv", 0, "file"), ("read_sql", 0, "table"), ("read_parquet", 0, "file")]
_SQLALCHEMY = [("execute", 0, "table")]
_PYSPARK_READ = [("csv", 0, "file"), ("parquet", 0, "file")]
_PYSPARK_WRITE = [("saveAsTable", 0, "table")]


def _resolve_literal(node: ast.AST) -> str | None:
    """Return string value if node is a literal string, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    return None


def _get_call_name(node: ast.Call) -> str | None:
    """Return qualified name for call (e.g. 'read_csv' or 'execute')."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_pandas_read(call_name: str) -> bool:
    return call_name in ("read_csv", "read_sql", "read_parquet", "read_excel")


def _is_sqlalchemy_execute(call_name: str) -> bool:
    return call_name == "execute"


def _is_pyspark_read_write(call_name: str) -> bool:
    return call_name in ("csv", "parquet", "saveAsTable", "save")


def _collect_data_flow_calls(tree: ast.AST, path: Path) -> list[tuple[str, str, int]]:
    """Collect (dataset_name_or_path, storage_type, line) for literal args only."""
    result: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _get_call_name(node)
        if not name:
            continue
        args = node.args
        if not args:
            continue
        if _is_pandas_read(name) or name in ("csv", "parquet"):
            lit = _resolve_literal(args[0])
            if lit is not None:
                st = "file" if name in ("read_csv", "read_parquet", "csv", "parquet") else "table"
                result.append((lit, st, node.lineno))
            else:
                logger.info("dynamic reference, cannot resolve (file=%s line=%s)", path, node.lineno)
        elif _is_sqlalchemy_execute(name):
            lit = _resolve_literal(args[0])
            if lit is not None:
                result.append((lit, "table", node.lineno))
            else:
                logger.info("dynamic reference, cannot resolve (file=%s line=%s)", path, node.lineno)
        elif _is_pyspark_read_write(name):
            lit = _resolve_literal(args[0])
            if lit is not None:
                st = "table" if name == "saveAsTable" else "file"
                result.append((lit, st, node.lineno))
            else:
                logger.info("dynamic reference, cannot resolve (file=%s line=%s)", path, node.lineno)
    return result


def analyze_python_data_flow(path: Path) -> tuple[list[Any], list[Any]]:
    """
    Analyze a Python file for data flow (read/write). Returns (nodes, edges).
    Nodes are DatasetNode or dict; edges are (source_id, target_id) or dict with source/target.
    On parse error returns ([], []) and does not raise.
    """
    path = Path(path).resolve()
    nodes: list[Any] = []
    edges: list[Any] = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.warning("hydrologist_skip path=%s analyzer=PythonDataFlow error=%s", path, e)
        return [], []

    path_str = str(path)
    for name_or_path, storage_type, line in _collect_data_flow_calls(tree, path):
        nodes.append(DatasetNode(name=name_or_path, storage_type=storage_type))
        trans_id = f"transformation:{path_str}:{line}"
        nodes.append({"id": trans_id, "type": "transformation"})
        edges.append({"source": trans_id, "target": name_or_path})
    return nodes, edges
