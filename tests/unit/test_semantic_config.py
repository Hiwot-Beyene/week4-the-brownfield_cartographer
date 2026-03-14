"""
Unit tests for Semanticist LLM config (env parsing, defaults, ollama:model style).
No real API calls.
"""
from __future__ import annotations

import os
import pytest


def test_defaults_when_env_unset(monkeypatch):
    """When env vars are unset, defaults are Ollama bulk and synthesis."""
    from src.llm.config import get_semantic_config
    for k in ("SEMANTIC_BULK_PROVIDER", "SEMANTIC_BULK_MODEL", "SEMANTIC_SYNTHESIS_PROVIDER",
              "SEMANTIC_SYNTHESIS_MODEL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = get_semantic_config()
    assert cfg.bulk_provider == "ollama"
    assert cfg.synthesis_provider == "ollama"
    assert "deepseek" in cfg.bulk_model.lower() or "codellama" in cfg.bulk_model.lower()
    assert cfg.ollama_base_url == "http://localhost:11434"


def test_parse_ollama_prefix():
    """SEMANTIC_BULK_MODEL=ollama:codellama:7b yields model_id codellama:7b."""
    from src.llm.config import SemanticConfig, _parse_model_id
    assert _parse_model_id("ollama:codellama:7b", "ollama") == "codellama:7b"
    assert _parse_model_id("codellama:7b", "ollama") == "codellama:7b"


def test_config_override_via_env(monkeypatch):
    """Override via SEMANTIC_BULK_MODEL and SEMANTIC_SYNTHESIS_MODEL."""
    from src.llm.config import get_semantic_config
    monkeypatch.setenv("SEMANTIC_BULK_MODEL", "ollama:codellama:7b")
    monkeypatch.setenv("SEMANTIC_SYNTHESIS_MODEL", "ollama:deepseek-r1")
    cfg = get_semantic_config()
    assert cfg.bulk_model == "ollama:codellama:7b"
    assert cfg.bulk_model_id == "codellama:7b"
    assert cfg.synthesis_model_id == "deepseek-r1"
