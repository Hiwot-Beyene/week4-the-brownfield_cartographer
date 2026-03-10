"""
Tree-sitter grammar loading for multi-language AST extraction.

Uses optional grammar packages: tree-sitter-python, tree-sitter-javascript,
tree-sitter-yaml, tree-sitter-typescript. Missing packages are skipped without raising.
SQL structural extraction uses sqlglot (no tree-sitter).
"""

from __future__ import annotations

import logging
from typing import Any

from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)

_parser_cache: dict[str, Parser] = {}
_language_cache: dict[str, Any] = {}


def _load_python() -> Any | None:
    try:
        import tree_sitter_python as tsp

        return Language(tsp.language())
    except Exception as e:
        logger.debug("grammar python: %s", e)
        return None


def _load_javascript() -> Any | None:
    try:
        import tree_sitter_javascript as tsj

        return Language(tsj.language())
    except Exception as e:
        logger.debug("grammar javascript: %s", e)
        return None


def _load_typescript() -> Any | None:
    try:
        import tree_sitter_typescript as tst

        return Language(tst.language_typescript)
    except Exception as e:
        logger.debug("grammar typescript: %s", e)
        return None


def _load_yaml() -> Any | None:
    try:
        import tree_sitter_yaml as tsy

        return Language(tsy.language())
    except Exception as e:
        logger.debug("grammar yaml: %s", e)
        return None


# language key -> loader (returns Language or None)
_LOADERS: dict[str, Any] = {
    "python": _load_python,
    "javascript": _load_javascript,
    "typescript": _load_typescript,
    "yaml": _load_yaml,
}


def get_language(language: str) -> Any | None:
    """
    Return the tree-sitter Language for the given language, or None if unavailable.

    Supported: python, javascript, typescript, yaml.
    SQL is not loaded via tree-sitter (use sqlglot for SQL).
    """
    if language in _language_cache:
        return _language_cache[language]
    loader = _LOADERS.get(language)
    if loader is None:
        return None
    lang = loader()
    if lang is not None:
        _language_cache[language] = lang
    return lang


def get_parser(language: str) -> Parser | None:
    """
    Return a tree-sitter Parser for the given language, or None if unavailable.
    """
    if language in _parser_cache:
        return _parser_cache[language]
    lang = get_language(language)
    if lang is None:
        return None
    p = Parser(lang)
    _parser_cache[language] = p
    return p


def parse_source(source: bytes, language: str) -> Any | None:
    """
    Parse source bytes with the appropriate grammar. Returns the tree root node or None.
    """
    parser = get_parser(language)
    if parser is None:
        return None
    try:
        tree = parser.parse(source)
        return tree.root_node if tree else None
    except Exception as e:
        logger.debug("parse_source failed language=%s error=%s", language, e)
        return None
