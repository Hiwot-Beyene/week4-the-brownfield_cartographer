from __future__ import annotations

from pathlib import Path

import pytest


def test_startup_grammar_validation_lists_missing() -> None:
    from src.analyzers.tree_sitter_analyzer import GrammarValidationError, LanguageRouter, validate_required_grammars

    router = LanguageRouter.default()
    with pytest.raises(GrammarValidationError) as e:
        validate_required_grammars(router)

    # Must list missing grammars clearly (by language and/or extension).
    assert e.value.missing


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

