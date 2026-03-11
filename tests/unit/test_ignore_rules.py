from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "relpath,expected",
    [
        (".git/config", True),
        ("node_modules/react/index.js", True),
        (".env", True),
        (".env.local", True),
        (".envrc", True),
        ("secrets.pem", True),
        ("id_rsa", True),
        ("credentials.json", True),
        (".venv/lib/site-packages/x.py", True),
        ("venv/bin/activate", True),
        ("src/app.py", False),
        ("models/schema.yml", False),
    ],
)
def test_default_ignore_and_sensitive_rules(relpath: str, expected: bool) -> None:
    from src.analyzers.ignore_rules import IgnoreRules

    rules = IgnoreRules.default()
    assert rules.should_skip(Path(relpath)) is expected


def test_unignore_overrides_exclude() -> None:
    from src.analyzers.ignore_rules import IgnoreRules

    rules = IgnoreRules(
        exclude=["**/*.sql"],
        unignore=["models/allowed.sql"],
    )
    assert rules.should_skip(Path("models/blocked.sql")) is True
    assert rules.should_skip(Path("models/allowed.sql")) is False

