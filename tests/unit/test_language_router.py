from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "path,expected",
    [
        ("a.py", "python"),
        ("a.sql", "sql"),
        ("a.yml", "yaml"),
        ("a.yaml", "yaml"),
        ("a.js", "javascript"),
        ("a.ts", "typescript"),
        ("a.tsx", "typescript"),
        ("a.unknown", None),
        ("Makefile", None),
    ],
)
def test_language_router_routes_by_extension(path: str, expected: str | None) -> None:
    from src.analyzers.tree_sitter_analyzer import LanguageRouter

    router = LanguageRouter.default()
    spec = router.route(Path(path))

    if expected is None:
        assert spec is None
    else:
        assert spec.language == expected

