"""Embedding cache and embed(text) for Semanticist.

Uses sentence-transformers all-MiniLM-L6-v2 by default and a content-hash
cache stored under .cartography/embedding_cache/.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import List

import logging

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """Return SHA256 hex digest of normalized text."""
    normalized = (text or "").strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


class EmbeddingCache:
    """Disk-backed embedding cache keyed by content hash."""

    def __init__(
        self,
        cache_dir: Path,
        model_name: str = "all-MiniLM-L6-v2",
        provider: str | None = None,
        ollama_base_url: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.provider = (provider or os.environ.get("SEMANTIC_EMBED_PROVIDER") or "sentence_transformers").strip().lower()
        self.model_name = (model_name or os.environ.get("SEMANTIC_EMBED_MODEL") or "all-MiniLM-L6-v2").strip()
        self.ollama_base_url = (ollama_base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.model = None

    def _ensure_sentence_model(self) -> None:
        if self.model is not None:
            return
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(self.model_name)

    def _embed_with_ollama(self, text: str) -> List[float]:
        import httpx

        # Preferred endpoint.
        payload = {"model": self.model_name, "prompt": text}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{self.ollama_base_url}/api/embeddings", json=payload)
                resp.raise_for_status()
                data = resp.json()
                emb = data.get("embedding") or []
                if isinstance(emb, list) and emb:
                    return [float(x) for x in emb]
        except Exception:
            pass
        # Backward-compatible fallback endpoint.
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.ollama_base_url}/api/embed",
                    json={"model": self.model_name, "input": text},
                )
                resp.raise_for_status()
                data = resp.json()
                emb_list = data.get("embeddings") or []
                if isinstance(emb_list, list) and emb_list and isinstance(emb_list[0], list):
                    return [float(x) for x in emb_list[0]]
        except Exception as e:
            logger.warning("EmbeddingCache(ollama): embedding call failed: %s", e)
        return [0.0] * 8

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
            if self.provider == "ollama":
                data = self._embed_with_ollama(text)
            else:
                self._ensure_sentence_model()
                vec = self.model.encode([text])[0]
                data = [float(x) for x in vec]
            path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("EmbeddingCache: embedding failed for text hash %s: %s", key, e)
            # Graceful degradation: return a small zero vector so downstream k-means can still run,
            # even if it produces a trivial clustering.
            return [0.0] * 8
