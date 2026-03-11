from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import ast

from src.analyzers.grammars import get_language
from src.models.module import ClassRef, Evidence, FunctionRef, ImportRef, ModuleNode


def _load_grammar_or_raise(lang: str) -> object:
    """Load grammar for validation; raise if unavailable."""
    g = get_language(lang)
    if g is None:
        raise RuntimeError(f"grammar not available: {lang}")
    return g


def _sql_grammar_ok() -> object:
    """SQL uses sqlglot, not tree-sitter; satisfy validator."""
    return True


@dataclass(frozen=True)
class LanguageSpec:
    language: str
    # Grammar loader is intentionally abstracted so tests can validate routing
    # without requiring grammars to be present.
    load_grammar: Callable[[], object] | None = None
    queries: Mapping[str, str] | None = None


class LanguageRouter:
    def __init__(self, extension_map: Mapping[str, LanguageSpec]):
        # Single authoritative mapping: extension -> LanguageSpec
        self._ext = dict(extension_map)

    @staticmethod
    def default() -> "LanguageRouter":
        # Phase 1 supported scope; load_grammar wires tree-sitter (or no-op for SQL).
        ext = {
            ".py": LanguageSpec(language="python", load_grammar=lambda: _load_grammar_or_raise("python")),
            ".sql": LanguageSpec(language="sql", load_grammar=_sql_grammar_ok),
            ".yml": LanguageSpec(language="yaml", load_grammar=lambda: _load_grammar_or_raise("yaml")),
            ".yaml": LanguageSpec(language="yaml", load_grammar=lambda: _load_grammar_or_raise("yaml")),
            ".js": LanguageSpec(language="javascript", load_grammar=lambda: _load_grammar_or_raise("javascript")),
            ".ts": LanguageSpec(language="typescript", load_grammar=lambda: _load_grammar_or_raise("typescript")),
            ".tsx": LanguageSpec(language="typescript", load_grammar=lambda: _load_grammar_or_raise("typescript")),
        }
        return LanguageRouter(ext)

    def route(self, path: Path) -> LanguageSpec | None:
        # Unknown extensions are handled gracefully by returning None.
        return self._ext.get(path.suffix.lower())


@dataclass(frozen=True)
class GrammarValidationError(Exception):
    missing: list[str]

    def __str__(self) -> str:  # pragma: no cover
        return f"Missing grammars: {', '.join(self.missing)}"


def validate_required_grammars(router: LanguageRouter) -> None:
    """
    Validate that Phase 1 required grammars are available.

    In this simplified implementation, a grammar is considered missing if:
    - the LanguageSpec has no load_grammar function, or
    - the load_grammar call raises.
    """
    required_exts = [".py", ".sql", ".yml", ".yaml", ".js", ".ts", ".tsx"]
    missing: list[str] = []
    for ext in required_exts:
        spec = router._ext.get(ext)
        if spec is None or spec.load_grammar is None:
            missing.append(ext)
            continue
        try:
            spec.load_grammar()
        except Exception:
            missing.append(ext)
    if missing:
        raise GrammarValidationError(missing=missing)


def analyze_file_best_effort(router: LanguageRouter, path: Path) -> object | None:
    """
    Best-effort entry point used by unit tests.

    If grammar is missing/unavailable, return None to indicate 'skip' and never raise.
    """
    spec = router.route(path)
    if spec is None:
        return None
    if spec.load_grammar is None:
        return None
    try:
        spec.load_grammar()
    except Exception:
        return None
    return object()


def _sql_tables_referenced(path: Path) -> list[str]:
    """Extract table/reference names from a SQL file via reusable AST service."""
    from src.analyzers.multilang_ast import extract_structural

    ext = extract_structural(path, "sql")
    return ext.tables_referenced if not ext.error else []


def _yaml_structural_keys(path: Path) -> list[str]:
    """Extract top-level config keys from YAML via reusable AST service (tree-sitter or PyYAML fallback)."""
    from src.analyzers.multilang_ast import extract_structural

    ext = extract_structural(path, "yaml")
    return ext.structural_keys if not ext.error else []


def _js_ts_imports(path: Path, language: str) -> list[ImportRef]:
    """Extract import declarations from JS/TS via reusable AST service (tree-sitter)."""
    from src.analyzers.multilang_ast import extract_structural

    path_str = str(path)
    ext = extract_structural(path, language)
    if ext.error:
        return []
    return [
        ImportRef(
            raw=raw,
            evidence=Evidence(source_file=path_str, start_line=start_line, end_line=end_line, method="static"),
        )
        for raw, start_line, end_line in ext.imports_raw
    ]


def analyze_module(path: Path, router: LanguageRouter | None = None) -> ModuleNode:
    """
    Phase 1 best-effort module analyzer.

    Uses LanguageRouter to set language from file extension (.py, .sql, .yml, .yaml, .js, .ts, .tsx).
    Full extraction (imports, functions, classes) for Python; SQL -> tables_referenced;
    YAML -> structural_keys; JS/TS -> imports via tree-sitter.
    """
    path = path.resolve()
    suffix = path.suffix.lower()
    router = router or LanguageRouter.default()
    spec = router.route(path)
    language = spec.language if spec else "unknown"

    if suffix == ".sql":
        tables = _sql_tables_referenced(path)
        return ModuleNode(path=str(path), language=language, tables_referenced=tables)

    if suffix in (".yml", ".yaml"):
        keys = _yaml_structural_keys(path)
        return ModuleNode(path=str(path), language=language, structural_keys=keys)

    if suffix in (".js", ".ts", ".tsx"):
        try:
            imp = _js_ts_imports(path, "typescript" if suffix != ".js" else "javascript")
            return ModuleNode(path=str(path), language=language, imports=imp)
        except Exception:
            return ModuleNode(path=str(path), language=language)

    if suffix != ".py":
        return ModuleNode(path=str(path), language=language)

    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)

    imports: list[ImportRef] = []
    public_functions: list[FunctionRef] = []
    classes: list[ClassRef] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            raw = "import " + ", ".join(alias.name for alias in node.names)
            imports.append(
                ImportRef(
                    raw=raw,
                    evidence=Evidence(
                        source_file=str(path),
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        method="static",
                    ),
                )
            )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            raw = f"from {mod} import " + ", ".join(alias.name for alias in node.names)
            imports.append(
                ImportRef(
                    raw=raw,
                    evidence=Evidence(
                        source_file=str(path),
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        method="static",
                    ),
                )
            )
        elif isinstance(node, ast.FunctionDef):
            if node.name.startswith("_"):
                continue
            public_functions.append(
                FunctionRef(
                    name=node.name,
                    evidence=Evidence(
                        source_file=str(path),
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        method="static",
                    ),
                )
            )
        elif isinstance(node, ast.ClassDef):
            bases: list[str] = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(base.attr)
            classes.append(
                ClassRef(
                    name=node.name,
                    bases=bases,
                    evidence=Evidence(
                        source_file=str(path),
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        method="static",
                    ),
                )
            )

    return ModuleNode(
        path=str(path),
        language=language,
        imports=imports,
        public_functions=public_functions,
        classes=classes,
    )

