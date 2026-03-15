"""Domain clustering for Semanticist: embed purpose statements and run k-means.

Separated from main semanticist entrypoint for clarity.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

import numpy as np
from sklearn.cluster import KMeans

from src.llm.embedding import EmbeddingCache
from src.llm.config import get_semantic_config
from src.models.module import ModuleNode
from src.models.semanticist import DomainArchitectureMap


_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ingestion": ("ingest", "extract", "fetch", "collect", "source", "raw", "import"),
    "transformation": ("transform", "clean", "normalize", "feature", "model", "dbt", "sql"),
    "serving": ("serve", "api", "endpoint", "query", "dashboard", "report", "view"),
    "monitoring": ("monitor", "alert", "metric", "health", "observability", "log"),
    "orchestration": ("dag", "schedule", "task", "workflow", "orchestrate", "pipeline"),
    "storage": ("warehouse", "table", "dataset", "persist", "store", "sink"),
}


def _normalize_tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9_]+", (text or "").lower()) if t]


def _infer_domain_name(samples: list[str], cluster_idx: int) -> str:
    """Name clusters deterministically from keyword hits (no LLM call)."""
    if not samples:
        return f"domain_{cluster_idx}"
    tokens: list[str] = []
    for s in samples[:25]:
        tokens.extend(_normalize_tokens(s))
    if not tokens:
        return f"domain_{cluster_idx}"
    score: dict[str, int] = {k: 0 for k in _DOMAIN_KEYWORDS}
    for domain, kws in _DOMAIN_KEYWORDS.items():
        for kw in kws:
            score[domain] += sum(1 for t in tokens if kw in t)
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
    best, best_score = ranked[0]
    return best if best_score > 0 else f"domain_{cluster_idx}"


def cluster_into_domains(modules: List[ModuleNode], k: Optional[int] = None) -> DomainArchitectureMap:
    """Embed all purpose statements, run k-means, and name clusters heuristically.

    Modules without a purpose_statement are skipped and listed in skipped_modules.
    """
    cfg = get_semantic_config()
    cache_dir = Path(".cartography") / "embedding_cache"
    cache = EmbeddingCache(
        cache_dir,
        provider=os.environ.get("SEMANTIC_EMBED_PROVIDER", "ollama"),
        model_name=os.environ.get("SEMANTIC_EMBED_MODEL", "nomic-embed-text"),
        ollama_base_url=cfg.ollama_base_url,
    )

    texts: List[str] = []
    kept_modules: List[ModuleNode] = []
    skipped: List[str] = []
    for m in modules:
        if not m.purpose_statement:
            skipped.append(m.path)
            continue
        kept_modules.append(m)
        texts.append(m.purpose_statement)

    if not kept_modules:
        return DomainArchitectureMap()

    vectors = [cache.embed(t) for t in texts]
    X = np.array(vectors)

    # Per Phase 3 guidance: prefer k in [5, 8], adapt for small repos.
    requested_k = k if k is not None else 6
    requested_k = max(5, min(8, requested_k))
    k_eff = min(requested_k, len(kept_modules)) or 1

    kmeans = KMeans(n_clusters=k_eff, n_init=10, random_state=42)
    labels = kmeans.fit_predict(X)

    cluster_to_domain: dict[int, str] = {}
    module_to_domain: dict[str, str] = {}

    for cluster_idx in range(k_eff):
        sample = [kept_modules[i].purpose_statement for i in range(len(kept_modules)) if labels[i] == cluster_idx]
        if not sample:
            cluster_to_domain[cluster_idx] = f"domain_{cluster_idx}"
            continue
        name = _infer_domain_name([s or "" for s in sample], cluster_idx)
        cluster_to_domain[cluster_idx] = name

    for mod, label in zip(kept_modules, labels):
        domain = cluster_to_domain.get(int(label), f"domain_{int(label)}")
        mod.domain_cluster = domain
        module_to_domain[mod.path] = domain

    return DomainArchitectureMap(
        module_to_domain=module_to_domain,
        cluster_to_domain=cluster_to_domain,
        skipped_modules=skipped,
    )
