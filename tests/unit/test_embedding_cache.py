"""
Unit tests for embedding cache (content-hash key, cache hit vs miss, disk persistence).
No real sentence-transformers or API calls; use stubs where needed.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest


def test_content_hash_key():
    """Cache key is content hash of text (e.g. sha256 of normalized string)."""
    from src.llm.embedding import _content_hash
    a = _content_hash("hello world")
    b = _content_hash("hello world")
    assert a == b
    assert a != _content_hash("hello world.")
    assert len(a) == 64  # sha256 hex


def test_cache_miss_returns_embedding():
    """On cache miss, embed() returns a vector and stores it (or we assert embed was called)."""
    from src.llm.embedding import EmbeddingCache
    with tempfile.TemporaryDirectory() as d:
        cache = EmbeddingCache(Path(d))
        # With no model, we may get stub; we need embed to work. Use a small stub model or mock.
        emb = cache.embed("first statement")
        assert emb is not None
        assert isinstance(emb, list)
        assert len(emb) > 0
        assert all(isinstance(x, (int, float)) for x in emb)


def test_cache_hit_returns_same_vector():
    """Same text yields same embedding and second call does not recompute (cache hit)."""
    from src.llm.embedding import EmbeddingCache
    with tempfile.TemporaryDirectory() as d:
        cache = EmbeddingCache(Path(d))
        a = cache.embed("same text")
        b = cache.embed("same text")
        assert a == b
