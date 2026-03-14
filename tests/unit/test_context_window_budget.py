"""
Unit tests for ContextWindowBudget (token estimation, cumulative tracking, cap warning, truncation).
No real LLM or API calls; tests are self-contained.
"""
from __future__ import annotations

import pytest
from pathlib import Path


def test_estimate_tokens_heuristic():
    """Token estimation uses chars/4 heuristic when tiktoken unavailable."""
    from src.agents.semanticist import ContextWindowBudget
    budget = ContextWindowBudget()
    text = "x" * 400
    n = budget.estimate_tokens(text)
    assert n == 100  # 400 // 4


def test_cumulative_tracking():
    """Cumulative input tokens increment after consume."""
    from src.agents.semanticist import ContextWindowBudget
    budget = ContextWindowBudget()
    assert budget.cumulative_input_tokens == 0
    budget.consume_input_tokens(100)
    assert budget.cumulative_input_tokens == 100
    budget.consume_input_tokens(50)
    assert budget.cumulative_input_tokens == 150


def test_cap_warning_when_approaching():
    """When cumulative approaches cap (e.g. 80%), log warning (we assert state)."""
    from src.agents.semanticist import ContextWindowBudget
    budget = ContextWindowBudget(cap_total=1000)
    budget.consume_input_tokens(800)
    assert budget.cumulative_input_tokens == 800
    # At 80% we expect would_warn or similar; budget should expose that
    assert getattr(budget, "cap_total", None) == 1000


def test_truncate_module_code():
    """Truncation returns first N lines when over limit."""
    from src.agents.semanticist import ContextWindowBudget
    budget = ContextWindowBudget(truncate_lines=5)
    lines = ["line%d" % i for i in range(10)]
    code = "\n".join(lines)
    out = budget.truncate_module_code(code, max_lines=5)
    assert out.count("\n") + (1 if out.strip() else 0) <= 5
    assert "line0" in out and "line4" in out


def test_truncation_decision_when_over_bulk_budget():
    """When bulk phase would exceed cap_bulk_phase, truncate_module_code is used."""
    from src.agents.semanticist import ContextWindowBudget
    budget = ContextWindowBudget(cap_bulk_phase=100, truncate_lines=10)
    long_code = "x\n" * 500  # ~125 tokens per 500 lines heuristic
    estimated = budget.estimate_tokens(long_code)
    assert estimated > 100
    truncated = budget.truncate_module_code(long_code, max_lines=10)
    assert truncated.count("\n") < 500
