from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class _Key:
    path: str
    content_hash: str


class ParseCache(Generic[T]):
    def __init__(self, max_entries: int = 128):
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max = max_entries
        self._data: OrderedDict[_Key, T] = OrderedDict()

    def get(self, path: Path, content_hash: str) -> T | None:
        key = _Key(path=path.as_posix(), content_hash=content_hash)
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value  # move to MRU
        return value

    def put(self, path: Path, content_hash: str, tree: T) -> None:
        key = _Key(path=path.as_posix(), content_hash=content_hash)
        if key in self._data:
            self._data.pop(key)
        self._data[key] = tree
        while len(self._data) > self._max:
            self._data.popitem(last=False)  # evict LRU

