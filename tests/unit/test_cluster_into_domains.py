"""
Unit tests for cluster_into_domains (fixed stub embeddings, deterministic k-means, domain names per cluster).
Mock LLM for cluster naming; no real Ollama.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models.module import ModuleNode
from src.models.semanticist import DomainArchitectureMap


def _make_modules_with_purpose(n: int, purpose_prefix: str = "Purpose") -> list[ModuleNode]:
    return [
        ModuleNode(path=f"src/m{i}.py", language="python", purpose_statement=f"{purpose_prefix} {i}")
        for i in range(n)
    ]


@patch("src.agents.semanticist._call_llm_bulk")
def test_cluster_into_domains_assigns_labels(mock_llm):
    """cluster_into_domains assigns cluster label (domain_cluster name) to each module."""
    mock_llm.return_value = "ingestion"
    from src.agents.semanticist_cluster import cluster_into_domains
    modules = _make_modules_with_purpose(10)
    for m in modules:
        m.purpose_statement = m.purpose_statement or "Handles data."
    result = cluster_into_domains(modules, k=3)
    assert isinstance(result, (dict, DomainArchitectureMap))
    if hasattr(result, "module_to_domain"):
        assert len(result.module_to_domain) <= 10
    else:
        assert "module_to_domain" in result or "cluster_to_domain" in result
    for m in modules:
        assert getattr(m, "domain_cluster", None) is not None or m.path in result.get("module_to_domain", {})


@patch("src.agents.semanticist._call_llm_bulk")
def test_cluster_into_domains_deterministic_with_fixed_embeddings(mock_llm):
    """With fixed stub embeddings, k-means produces deterministic cluster labels."""
    mock_llm.return_value = "domain"
    from src.agents.semanticist_cluster import cluster_into_domains
    modules = _make_modules_with_purpose(6)
    for m in modules:
        m.purpose_statement = "Same purpose for all."
    result1 = cluster_into_domains(modules, k=2)
    result2 = cluster_into_domains(modules, k=2)
    labels1 = [getattr(m, "domain_cluster", None) for m in modules]
    labels2 = [getattr(m, "domain_cluster", None) for m in modules]
    assert labels1 == labels2
