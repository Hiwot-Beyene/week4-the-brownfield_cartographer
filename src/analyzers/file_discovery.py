from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.analyzers.ignore_rules import IgnoreRules


PHASE1_EXTS = {".py", ".sql", ".yml", ".yaml", ".js", ".ts", ".tsx"}


def discover_files(repo_root: Path, rules: IgnoreRules, exts: Iterable[str] = PHASE1_EXTS) -> list[Path]:
    exts_set = {e.lower() for e in exts}
    repo_root = repo_root.resolve()

    out: list[Path] = []
    for path in repo_root.rglob("*"):
        if path.is_dir():
            continue

        rel = path.relative_to(repo_root)
        if rules.should_skip(rel):
            continue

        if path.suffix.lower() not in exts_set:
            continue

        out.append(path)

    return out

