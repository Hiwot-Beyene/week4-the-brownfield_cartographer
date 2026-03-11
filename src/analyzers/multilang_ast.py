"""
Reusable multi-language AST parsing service.

Single entry point for parsing and structural extraction across SQL, YAML, JS/TS, Python.
Graceful parse failure: returns structured result with success/error, never raises.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.analyzers.grammars import get_parser, parse_source

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of a parse attempt; parse failures set success=False and error message."""

    success: bool
    language: str
    source_path: Path | None = None
    root: Any = None  # tree-sitter root node, or sqlglot statements list for SQL
    error: str | None = None
    dialect: str | None = None  # SQL only


@dataclass
class StructuralExtract:
    """Structural extraction result: keys, table refs, imports, etc."""

    tables_referenced: list[str] = field(default_factory=list)
    structural_keys: list[str] = field(default_factory=list)
    imports_raw: list[tuple[str, int, int]] = field(default_factory=list)  # (raw_import, start_line, end_line)
    error: str | None = None


def _line_range_from_node(node: Any) -> tuple[int, int] | None:
    """Get (start_line, end_line) from a tree-sitter or similar node."""
    if hasattr(node, "start_point") and hasattr(node, "end_point"):
        return (getattr(node, "start_point", (0, 0))[0] + 1, getattr(node, "end_point", (0, 0))[0] + 1)
    if hasattr(node, "line") and hasattr(node, "end_line"):
        return (node.line, node.end_line)
    if hasattr(node, "line"):
        return (node.line, node.line)
    return None


def parse(path: Path, language: str | None = None) -> ParseResult:
    """
    Parse a file into an AST. Reusable entry point with graceful failure.

    For .sql we use sqlglot (not tree-sitter); language is ignored and dialect inferred from path.
    For .py we use stdlib ast (not tree-sitter) and return a minimal wrapper.
    """
    path = Path(path).resolve()
    suffix = path.suffix.lower()
    lang = language or (
        "yaml" if suffix in (".yml", ".yaml") else "javascript" if suffix == ".js" else "typescript" if suffix in (".ts", ".tsx") else "python" if suffix == ".py" else "sql"
    )

    if suffix == ".sql":
        return _parse_sql(path)
    if suffix == ".py":
        return _parse_python(path)
    # tree-sitter for yaml, js, ts
    try:
        source = path.read_bytes()
    except OSError as e:
        return ParseResult(success=False, language=lang, source_path=path, error=str(e))

    root = parse_source(source, lang)
    if root is None:
        return ParseResult(success=False, language=lang, source_path=path, error="parse_source returned None")
    return ParseResult(success=True, language=lang, source_path=path, root=root)


def _parse_sql(path: Path) -> ParseResult:
    """Parse SQL with sqlglot; dialect from path or default."""
    try:
        from src.analyzers.sql_lineage import dialect_from_path, DIALECTS, DEFAULT_DIALECT

        sql = path.read_text(encoding="utf-8", errors="replace")
        dialect = dialect_from_path(path) or DEFAULT_DIALECT
        dialect = "postgres" if dialect in ("postgres", "postgresql") else dialect
        if dialect not in DIALECTS:
            dialect = DEFAULT_DIALECT
        import sqlglot

        parsed = sqlglot.parse(sql, read=dialect)
        return ParseResult(success=True, language="sql", source_path=path, root=parsed, dialect=dialect)
    except Exception as e:
        logger.debug("sql parse failed path=%s error=%s", path, e)
        return ParseResult(success=False, language="sql", source_path=path, error=str(e), dialect=None)


def _parse_python(path: Path) -> ParseResult:
    """Parse Python with stdlib ast."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        import ast

        tree = ast.parse(source)
        return ParseResult(success=True, language="python", source_path=path, root=tree)
    except SyntaxError as e:
        return ParseResult(success=False, language="python", source_path=path, error=f"SyntaxError: {e}")
    except Exception as e:
        return ParseResult(success=False, language="python", source_path=path, error=str(e))


def extract_structural(path: Path, language: str | None = None) -> StructuralExtract:
    """
    Extract structural elements (table refs, config keys, imports) from a file.
    Reusable; on parse failure returns empty lists and sets error.
    """
    path = Path(path).resolve()
    suffix = path.suffix.lower()
    lang = language or ("yaml" if suffix in (".yml", ".yaml") else "javascript" if suffix == ".js" else "typescript" if suffix in (".ts", ".tsx") else "python" if suffix == ".py" else "sql")

    if suffix == ".sql":
        return _extract_sql_structural(path)
    if suffix in (".yml", ".yaml"):
        return _extract_yaml_structural(path)
    if suffix in (".js", ".ts", ".tsx"):
        return _extract_js_ts_structural(path, lang)
    if suffix == ".py":
        return _extract_python_structural(path)
    return StructuralExtract(error="unsupported_extension")


def _extract_sql_structural(path: Path) -> StructuralExtract:
    """SQL: table refs via sqlglot AST + dbt ref/source from text (with line ranges)."""
    result = parse(path, "sql")
    if not result.success or result.root is None:
        return StructuralExtract(error=result.error or "parse failed")
    tables: list[str] = []
    seen: set[str] = set()
    try:
        from sqlglot import exp

        for stmt in result.root or []:
            if stmt is None:
                continue
            for table in stmt.find_all(exp.Table):
                parts = []
                if getattr(table, "catalog", None):
                    parts.append(table.catalog)
                if getattr(table, "db", None):
                    parts.append(table.db)
                if getattr(table, "name", None):
                    parts.append(table.name)
                name = ".".join(parts) if parts else ""
                if name and name not in seen:
                    seen.add(name)
                    tables.append(name)
        # dbt ref/source from raw text (with line numbers)
        sql = path.read_text(encoding="utf-8", errors="replace")
        import re

        for m in re.finditer(r"\bref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", sql, re.I):
            name = m.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                tables.append(name)
        for m in re.finditer(r"\bsource\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", sql, re.I):
            name = f"source:{m.group(1).strip()}.{m.group(2).strip()}"
            if name not in seen:
                seen.add(name)
                tables.append(name)
        return StructuralExtract(tables_referenced=tables)
    except Exception as e:
        logger.debug("sql structural extract failed path=%s error=%s", path, e)
        return StructuralExtract(error=str(e))


def _extract_yaml_structural(path: Path) -> StructuralExtract:
    """YAML: top-level config keys via tree-sitter AST (block_mapping_pair key) or PyYAML fallback."""
    source = path.read_bytes()
    root = parse_source(source, "yaml")
    keys: list[str] = []
    if root is not None:
        try:
            # tree-sitter-yaml: stream(0) -> document -> block_node -> block_mapping -> block_mapping_pair(depth 4). Top-level keys only.
            def collect_keys(n: Any, depth: int = 0) -> None:
                if not hasattr(n, "type"):
                    return
                t = getattr(n, "type", "")
                if t == "block_mapping_pair" and 3 <= depth <= 5:
                    key_node = n.child(0) if getattr(n, "child_count", 0) else None
                    if key_node is not None and hasattr(key_node, "start_byte"):
                        key_text = source[key_node.start_byte : key_node.end_byte].decode("utf-8", errors="replace").strip().strip("'\"")
                        if key_text and key_text not in keys:
                            keys.append(key_text)
                for i in range(getattr(n, "child_count", 0) or 0):
                    if hasattr(n, "child"):
                        collect_keys(n.child(i), depth + 1)

            collect_keys(root)
        except Exception:
            pass
    if not keys:
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                keys = list(data.keys())
        except Exception:
            pass
    return StructuralExtract(structural_keys=keys)


def _extract_js_ts_structural(path: Path, lang: str) -> StructuralExtract:
    """JS/TS: import statements via tree-sitter."""
    try:
        source = path.read_bytes()
    except OSError as e:
        return StructuralExtract(error=str(e))
    root = parse_source(source, lang)
    if root is None:
        return StructuralExtract(error="parse failed")
    imports: list[tuple[str, int, int]] = []

    def node_text(n: Any) -> str:
        if not hasattr(n, "start_byte"):
            return ""
        return source[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

    def walk(n: Any) -> None:
        if not hasattr(n, "type"):
            return
        t = getattr(n, "type", "")
        if t in ("import_statement", "import_declaration"):
            raw = node_text(n).strip()
            if raw:
                start_line = getattr(n, "start_point", (0, 0))[0] + 1
                end_line = getattr(n, "end_point", (0, 0))[0] + 1
                imports.append((raw, start_line, end_line))
            return
        for i in range(getattr(n, "child_count", 0) or 0):
            if hasattr(n, "child"):
                walk(n.child(i))

    walk(root)
    return StructuralExtract(imports_raw=imports)


def _extract_python_structural(path: Path) -> StructuralExtract:
    """Python: imports from stdlib ast (evidence lines)."""
    result = parse(path, "python")
    if not result.success or result.root is None:
        return StructuralExtract(error=result.error or "parse failed")
    imports: list[tuple[str, int, int]] = []
    try:
        import ast

        for node in ast.walk(result.root):
            if isinstance(node, ast.Import):
                raw = "import " + ", ".join(a.name for a in node.names)
                line = getattr(node, "lineno", 0)
                end = getattr(node, "end_lineno", line)
                imports.append((raw, line, end))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                raw = f"from {mod} import " + ", ".join(a.name for a in node.names)
                line = getattr(node, "lineno", 0)
                end = getattr(node, "end_lineno", line)
                imports.append((raw, line, end))
        return StructuralExtract(imports_raw=imports)
    except Exception as e:
        return StructuralExtract(error=str(e))
