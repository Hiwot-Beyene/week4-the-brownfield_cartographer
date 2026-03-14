from __future__ import annotations

from pathlib import Path

import pytest


def test_startup_grammar_validation_lists_missing() -> None:
    from src.analyzers.tree_sitter_analyzer import GrammarValidationError, LanguageRouter, validate_required_grammars

    router = LanguageRouter.default()
    try:
        validate_required_grammars(router)
        # If all grammars are installed (e.g. tree-sitter-* packages), validation passes.
    except GrammarValidationError as e:
        # When any grammar is missing, must list missing extensions clearly.
        assert e.missing


def test_missing_grammar_gracefully_skips_file() -> None:
    from src.analyzers.tree_sitter_analyzer import LanguageRouter, LanguageSpec, analyze_file_best_effort

    def _missing() -> object:
        raise RuntimeError("grammar missing")

    router = LanguageRouter(
        {
            ".py": LanguageSpec(language="python", load_grammar=_missing),
        }
    )

    result = analyze_file_best_effort(router=router, path=Path("a.py"))
    assert result is None

