"""
Resolve repository input to a local path: local directory or clone of a remote (e.g. GitHub) URL.

Supports the challenge requirement: "system that ingests any GitHub repository (or local path)
and produces a living, queryable knowledge graph".
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

# GitHub URL patterns: https://github.com/owner/repo, https://github.com/owner/repo.git, git@github.com:owner/repo.git
_GITHUB_HTTPS = re.compile(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", re.IGNORECASE)
_GITHUB_SSH = re.compile(r"^git@github\.com:([^/]+)/([^/#?]+?)(?:\.git)?/?$", re.IGNORECASE)


def is_remote_repo(input_str: str) -> bool:
    """Return True if input looks like a remote Git URL (GitHub or generic git)."""
    s = (input_str or "").strip()
    if not s:
        return False
    if _GITHUB_HTTPS.match(s) or _GITHUB_SSH.match(s):
        return True
    if s.startswith("git@") or s.startswith("https://") or s.startswith("http://"):
        return True
    return False


def _slug_from_github_url(url: str) -> Optional[str]:
    """Return owner_repo slug from GitHub URL, or None."""
    m = _GITHUB_HTTPS.match(url.strip()) or _GITHUB_SSH.match(url.strip())
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return None


def _slug_from_git_url(url: str) -> str:
    """Best-effort slug from any git URL (e.g. last path component without .git)."""
    s = url.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    parts = s.replace(":", "/").split("/")
    if len(parts) >= 2:
        return "_".join(parts[-2:])
    return parts[-1] if parts else "repo"


def clone_or_update_remote(
    url: str,
    dest: Path,
    *,
    branch: Optional[str] = None,
    depth: Optional[int] = 1,
) -> Path:
    """
    Clone the remote URL into dest, or pull if dest already exists and is a git repo.
    Returns dest (path to repo root).
    """
    dest = Path(dest).resolve()
    if dest.exists() and (dest / ".git").is_dir():
        try:
            subprocess.run(
                ["git", "-C", str(dest), "pull", "--rebase"],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass  # use existing clone
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    args = ["git", "clone"]
    if depth is not None:
        args.extend(["--depth", str(depth)])
    if branch:
        args.extend(["--branch", branch])
    args.extend([url.strip(), str(dest)])
    subprocess.run(args, capture_output=True, text=True, timeout=300, check=True)
    return dest


def resolve_repo(
    repo_input: str,
    clone_root: Optional[Path] = None,
    *,
    branch: Optional[str] = None,
    depth: Optional[int] = 1,
) -> Path:
    """
    Resolve repo_input to a local Path.

    - If repo_input is a local path (existing directory), return its resolved Path.
    - If repo_input is a remote Git URL (e.g. https://github.com/owner/repo), clone (or update)
      into clone_root / <slug> and return that path.

    clone_root: where to put cloned repos. Defaults to get_data_dir(cwd) / "cloned".
    """
    s = (repo_input or "").strip()
    if not s:
        raise ValueError("repo_input is empty")

    # Local path: must exist and be a directory
    p = Path(s).expanduser().resolve()
    if p.exists() and p.is_dir():
        return p

    if not is_remote_repo(s):
        raise ValueError(f"Not a local directory and not a recognized remote URL: {s!r}")

    # Remote: resolve clone root and slug
    if clone_root is None:
        from src.store.sqlite_store import get_data_dir
        clone_root = get_data_dir(Path.cwd()) / "cloned"
    clone_root = Path(clone_root).resolve()
    slug = _slug_from_github_url(s) or _slug_from_git_url(s)
    # Safe filename: replace characters that might be problematic
    slug = re.sub(r"[^\w\-.]", "_", slug)
    dest = clone_root / slug
    return clone_or_update_remote(s, dest, branch=branch, depth=depth)
