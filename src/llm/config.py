"""
Semanticist LLM configuration from env (SEMANTIC_BULK_*, SEMANTIC_SYNTHESIS_*).
Defaults for Ollama-only: bulk = deepseek-coder:6.7b or codellama:7b, synthesis = deepseek-r1 or deepseek-coder:33b.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


DEFAULT_BULK_PROVIDER = "ollama"
DEFAULT_BULK_MODEL = "deepseek-coder:6.7b"
DEFAULT_SYNTHESIS_PROVIDER = "ollama"
DEFAULT_SYNTHESIS_MODEL = "deepseek-r1"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


@dataclass
class SemanticConfig:
    """Tiered LLM config: semantic_bulk (fast/cheap) and semantic_synthesis (stronger)."""
    bulk_provider: str
    bulk_model: str
    synthesis_provider: str
    synthesis_model: str
    ollama_base_url: str
    budget_cap_total: Optional[int] = None
    budget_cap_bulk: Optional[int] = None
    truncate_lines: int = 500

    @property
    def bulk_model_id(self) -> str:
        """Model id for bulk (strip provider prefix if present)."""
        return _parse_model_id(self.bulk_model, self.bulk_provider)

    @property
    def synthesis_model_id(self) -> str:
        """Model id for synthesis (strip provider prefix if present)."""
        return _parse_model_id(self.synthesis_model, self.synthesis_provider)


def _parse_model_id(raw: str, provider: str) -> str:
    """If raw is 'ollama:codellama:7b', return 'codellama:7b'; else return raw."""
    if not raw:
        return raw
    prefix = provider + ":"
    if raw.lower().startswith(prefix.lower()):
        return raw[len(prefix):].strip()
    return raw.strip()


def get_semantic_config() -> SemanticConfig:
    """Load config from os.environ (and .env via python-dotenv if available)."""
    bulk_provider = os.environ.get("SEMANTIC_BULK_PROVIDER") or DEFAULT_BULK_PROVIDER
    bulk_model = os.environ.get("SEMANTIC_BULK_MODEL") or DEFAULT_BULK_MODEL
    synthesis_provider = os.environ.get("SEMANTIC_SYNTHESIS_PROVIDER") or DEFAULT_SYNTHESIS_PROVIDER
    synthesis_model = os.environ.get("SEMANTIC_SYNTHESIS_MODEL") or DEFAULT_SYNTHESIS_MODEL
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL

    cap_total = None
    if os.environ.get("SEMANTIC_BUDGET_CAP_TOTAL"):
        try:
            cap_total = int(os.environ["SEMANTIC_BUDGET_CAP_TOTAL"])
        except ValueError:
            pass
    cap_bulk = None
    if os.environ.get("SEMANTIC_BUDGET_CAP_BULK"):
        try:
            cap_bulk = int(os.environ["SEMANTIC_BUDGET_CAP_BULK"])
        except ValueError:
            pass
    truncate_lines = 500
    if os.environ.get("SEMANTIC_TRUNCATE_LINES"):
        try:
            truncate_lines = int(os.environ["SEMANTIC_TRUNCATE_LINES"])
        except ValueError:
            pass

    return SemanticConfig(
        bulk_provider=bulk_provider,
        bulk_model=bulk_model,
        synthesis_provider=synthesis_provider,
        synthesis_model=synthesis_model,
        ollama_base_url=ollama_base_url.rstrip("/"),
        budget_cap_total=cap_total,
        budget_cap_bulk=cap_bulk,
        truncate_lines=truncate_lines,
    )
