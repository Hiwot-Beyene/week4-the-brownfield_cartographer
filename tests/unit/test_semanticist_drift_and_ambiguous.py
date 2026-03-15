"""
Regression tests for Semanticist: drift-rate handling, ambiguous modules, and summary stats.
Ensures subtle drift cases and ambiguous purpose statements are counted and reported.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.models.module import ModuleNode
from src.agents.semanticist import _compute_semantic_summary_stats


def _make_module(
    path: str = "src/foo.py",
    purpose_statement: str | None = "Handles auth.",
    documentation_drift: bool | None = False,
    domain_cluster: str | None = "ingestion",
) -> ModuleNode:
    return ModuleNode(
        path=path,
        language="python",
        purpose_statement=purpose_statement,
        documentation_drift=documentation_drift,
        domain_cluster=domain_cluster,
    )


def test_summary_stats_drift_rate() -> None:
    """Drift rate is computed from modules with documentation_drift=True."""
    modules = [
        _make_module("a.py", documentation_drift=False),
        _make_module("b.py", documentation_drift=True),
        _make_module("c.py", documentation_drift=True),
    ]
    domains = {"module_to_domain": {"a.py": "x", "b.py": "x", "c.py": "y"}}
    stats = _compute_semantic_summary_stats(modules, domains)
    assert stats["total_modules"] == 3
    assert stats["drift_count"] == 2
    assert stats["drift_rate"] == pytest.approx(2 / 3, rel=1e-3)


def test_summary_stats_ambiguous_count() -> None:
    """Ambiguous count includes empty purpose and known placeholder phrases."""
    modules = [
        _make_module("a.py", purpose_statement="Real purpose here."),
        _make_module("b.py", purpose_statement=""),
        _make_module("c.py", purpose_statement="No determinable purpose."),
        _make_module("d.py", purpose_statement="No purpose statement yet."),
    ]
    domains = {"module_to_domain": {m.path: "x" for m in modules}}
    stats = _compute_semantic_summary_stats(modules, domains)
    assert stats["ambiguous_count"] >= 2  # empty + "no determinable purpose" / "no purpose statement yet"
    assert stats["total_modules"] == 4


def test_summary_stats_cluster_coherence() -> None:
    """Cluster sizes and coherence variance are reported."""
    modules = [
        _make_module("a.py", domain_cluster="ingestion"),
        _make_module("b.py", domain_cluster="ingestion"),
        _make_module("c.py", domain_cluster="serving"),
    ]
    domains = {
        "module_to_domain": {"a.py": "ingestion", "b.py": "ingestion", "c.py": "serving"},
        "cluster_to_domain": {},
    }
    stats = _compute_semantic_summary_stats(modules, domains)
    assert stats["cluster_count"] == 2
    assert stats["cluster_sizes"] == {"ingestion": 2, "serving": 1}
    assert stats["cluster_coherence_avg_size"] == 1.5
    assert "cluster_coherence_variance" in stats


def test_summary_stats_empty_modules() -> None:
    """Empty module list yields zero drift and zero clusters."""
    stats = _compute_semantic_summary_stats([], {"module_to_domain": {}})
    assert stats["total_modules"] == 0
    assert stats["drift_rate"] == 0.0
    assert stats["cluster_count"] == 0
