"""Domain clustering for Semanticist: embed purpose statements, run k-means, name clusters.

Separated from main semanticist entrypoint for clarity.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
from sklearn.cluster import KMeans

from src.llm.embedding import EmbeddingCache
from src.llm.config import get_semantic_config
from src.models.module import ModuleNode
from src.models.semanticist import DomainArchitectureMap
from src.agents.semanticist import _call_llm_bulk


def cluster_into_domains(modules: List[ModuleNode], k: Optional[int] = None) -> DomainArchitectureMap:
    """Embed all purpose statements, run k-means, and name clusters via LLM.

    Modules without a purpose_statement are skipped and listed in skipped_modules.
    """
    cfg = get_semantic_config()
    cache_dir = Path(".cartography") / "embedding_cache"
    cache = EmbeddingCache(cache_dir)

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
            cluster_to_domain[cluster_idx] = f"cluster_{cluster_idx}"
            continue
        prompt = "Infer a short business domain name (one or two words) for these modules:\n" + "\n".join(
            f"- {s}" for s in sample[:10]
        )
        try:
            name = _call_llm_bulk(prompt) or f"cluster_{cluster_idx}"
        except Exception:
            name = f"cluster_{cluster_idx}"
        name = name.strip().splitlines()[0]
        cluster_to_domain[cluster_idx] = name

    for mod, label in zip(kept_modules, labels):
        domain = cluster_to_domain.get(int(label), f"cluster_{int(label)}")
        mod.domain_cluster = domain
        module_to_domain[mod.path] = domain

    return DomainArchitectureMap(
        module_to_domain=module_to_domain,
        cluster_to_domain=cluster_to_domain,
        skipped_modules=skipped,
    )
