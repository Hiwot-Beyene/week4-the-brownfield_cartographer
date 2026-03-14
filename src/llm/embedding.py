"""Embedding cache and embed(text) for Semanticist.

Uses sentence-transformers all-MiniLM-L6-v2 by default and a content-hash
cache stored under .cartography/embedding_cache/.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List

import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """Return SHA256 hex digest of normalized text."""
    normalized = (text or "").strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


class EmbeddingCache:
    """Disk-backed embedding cache keyed by content hash."""

    def __init__(self, cache_dir: Path, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as e:  # pragma: no cover - defensive
            # If the embedding model cannot be loaded, log and re-raise so callers can decide how to degrade.
            logger.error("Failed to load embedding model %s: %s", model_name, e)
            raise

    def _path_for_key(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def embed(self, text: str) -> List[float]:
        key = _content_hash(text)
        path = self._path_for_key(key)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("EmbeddingCache: failed to read cached vector at %s; regenerating", path)
                path.unlink(missing_ok=True)
        try:
            vec = self.model.encode([text])[0]
            data = [float(x) for x in vec]
            path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("EmbeddingCache: embedding failed for text hash %s: %s", key, e)
            # Graceful degradation: return a small zero vector so downstream k-means can still run,
            # even if it produces a trivial clustering.
            return [0.0] * 8
