"""Unit tests for repo_resolver: local path and remote URL detection, resolve_repo for local paths."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.repo_resolver import is_remote_repo, resolve_repo


def test_is_remote_repo_github_https() -> None:
    assert is_remote_repo("https://github.com/owner/repo") is True
    assert is_remote_repo("https://github.com/owner/repo.git") is True
    assert is_remote_repo("http://github.com/foo/bar") is True


def test_is_remote_repo_github_ssh() -> None:
    assert is_remote_repo("git@github.com:owner/repo.git") is True
    assert is_remote_repo("git@github.com:owner/repo") is True


def test_is_remote_repo_generic_git() -> None:
    assert is_remote_repo("git@gitlab.com:group/project.git") is True
    assert is_remote_repo("https://gitlab.com/group/project") is True


def test_is_remote_repo_local_paths() -> None:
    assert is_remote_repo(".") is False
    assert is_remote_repo("/home/user/repo") is False
    assert is_remote_repo("relative/path") is False
    assert is_remote_repo("") is False


def test_resolve_repo_local_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp).resolve()
        out = resolve_repo(tmp)
        assert out == path
    with tempfile.TemporaryDirectory() as tmp:
        out = resolve_repo(str(Path(tmp).resolve()))
        assert out == Path(tmp).resolve()


def test_resolve_repo_local_path_cwd() -> None:
    out = resolve_repo(".")
    assert out.is_dir()
    assert out.resolve() == Path.cwd().resolve()


def test_resolve_repo_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        resolve_repo("")
    with pytest.raises(ValueError, match="empty"):
        resolve_repo("   ")


def test_resolve_repo_nonexistent_local_raises() -> None:
    with pytest.raises(ValueError, match="Not a local directory"):
        resolve_repo("/nonexistent/path/that/does/not/exist")
