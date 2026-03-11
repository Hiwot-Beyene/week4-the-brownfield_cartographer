import os
from pathlib import Path

from . import sibling  # type: ignore
from ..parent import thing  # type: ignore


def _private():
    return 1


def public_fn(x: int) -> int:
    return x + 1


class Base:
    pass


class Child(Base):
    def method(self):
        return os.getenv("X")

