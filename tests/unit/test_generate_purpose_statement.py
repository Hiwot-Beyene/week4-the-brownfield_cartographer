"""
Unit tests for generate_purpose_statement (mocked LLM, code-only prompt, docstring comparison, drift flag, per-module try/except).
No real Ollama or API calls.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models.module import ModuleNode
from src.agents.semanticist import generate_purpose_statement, ContextWindowBudget


def _make_module(path: str = "src/foo.py", language: str = "python") -> ModuleNode:
    return ModuleNode(path=path, language=language)


@patch("src.agents.semanticist._call_llm_bulk")
def test_purpose_statement_from_code_only(mock_llm):
    """Prompt uses code only (not docstring); returns 2–3 sentence purpose."""
    mock_llm.return_value = "This module parses CSV files and validates rows."
    code = "def parse(path): ..."
    budget = ContextWindowBudget()
    result = generate_purpose_statement(_make_module(), code_slice=code, docstring=None, budget=budget)
    assert result is not None
    assert result.purpose_statement == "This module parses CSV files and validates rows."
    assert result.documentation_drift is False
    mock_llm.assert_called_once()
    (prompt,) = mock_llm.call_args[0]
    assert code in prompt
    assert "docstring" not in prompt.lower()


@patch("src.agents.semanticist._call_llm_bulk")
def test_documentation_drift_when_docstring_contradicts(mock_llm):
    """When docstring describes different behavior, documentation_drift is True and docstring_snippet stored."""
    mock_llm.return_value = "This module handles user authentication and session management."
    code = "def login(): ... def logout(): ..."
    docstring = "This module only formats dates and times."
    budget = ContextWindowBudget()
    result = generate_purpose_statement(
        _make_module(), code_slice=code, docstring=docstring, budget=budget
    )
    assert result.purpose_statement == "This module handles user authentication and session management."
    assert result.documentation_drift is True
    assert result.docstring_snippet == docstring or docstring in (result.docstring_snippet or "")


@patch("src.agents.semanticist._call_llm_bulk")
def test_no_drift_when_docstring_aligns(mock_llm):
    """When docstring aligns with purpose, documentation_drift is False."""
    same = "This module handles authentication."
    mock_llm.return_value = same
    budget = ContextWindowBudget()
    result = generate_purpose_statement(
        _make_module(), code_slice="def login(): pass", docstring=same, budget=budget
    )
    assert result.documentation_drift is False


@patch("src.agents.semanticist._call_llm_bulk")
def test_skip_module_on_llm_failure(mock_llm):
    """On LLM exception, return None (skip module) and do not crash."""
    mock_llm.side_effect = TimeoutError("ollama timeout")
    budget = ContextWindowBudget()
    result = generate_purpose_statement(
        _make_module(), code_slice="x", docstring=None, budget=budget
    )
    assert result is None
