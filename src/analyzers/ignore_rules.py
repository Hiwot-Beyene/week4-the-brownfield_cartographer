from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable


def _to_posix(path: Path) -> str:
    # Always match in repo-relative POSIX form.
    posix = path.as_posix()
    if posix.startswith("./"):
        return posix[2:]
    return posix


@dataclass(frozen=True)
class IgnoreRules:
    exclude: list[str]
    unignore: list[str] | None = None

    @staticmethod
    def default() -> "IgnoreRules":
        default_exclude = [
            # VCS / vendors / build outputs
            ".git",
            ".git/**",
            "**/.git/**",
            "node_modules",
            "node_modules/**",
            "**/node_modules/**",
            "dist/**",
            "build/**",
            "**/__pycache__/**",
            "*.pyc",
            # Virtual envs
            ".venv/**",
            "venv/**",
            "env/**",
            ".env/**",
            # Sensitive files
            ".env",
            ".env.*",
            ".envrc",
            ".secrets",
            "*.pem",
            "*.key",
            "id_rsa",
            "credentials.json",
        ]
        return IgnoreRules(exclude=default_exclude, unignore=[])

    def should_skip(self, relpath: Path) -> bool:
        posix = _to_posix(relpath)

        if self.unignore:
            for pat in self.unignore:
                if fnmatch(posix, pat):
                    return False

        for pat in self.exclude:
            if fnmatch(posix, pat):
                return True

        return False

    @staticmethod
    def from_patterns(exclude: Iterable[str], unignore: Iterable[str] | None = None) -> "IgnoreRules":
        return IgnoreRules(exclude=list(exclude), unignore=list(unignore) if unignore is not None else [])

