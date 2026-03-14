from __future__ import annotations

from pathlib import Path


def test_parse_cache_hits_by_path_and_hash() -> None:
    from src.analyzers.parse_cache import ParseCache

    cache = ParseCache(max_entries=2)
    p = Path("a.py")
    assert cache.get(p, "h1") is None
    cache.put(p, "h1", "TREE1")
    assert cache.get(p, "h1") == "TREE1"
    assert cache.get(p, "h2") is None


def test_parse_cache_eviction_lru() -> None:
    from src.analyzers.parse_cache import ParseCache

    cache = ParseCache(max_entries=2)
    cache.put(Path("a.py"), "h1", "A1")
    cache.put(Path("b.py"), "h1", "B1")
    # Touch a.py to make b.py the LRU
    assert cache.get(Path("a.py"), "h1") == "A1"
    cache.put(Path("c.py"), "h1", "C1")
    assert cache.get(Path("b.py"), "h1") is None
    assert cache.get(Path("a.py"), "h1") == "A1"
    assert cache.get(Path("c.py"), "h1") == "C1"

