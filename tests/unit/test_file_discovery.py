from __future__ import annotations

from pathlib import Path


def test_file_discovery_respects_ignore_rules(tmp_path: Path) -> None:
    from src.analyzers.file_discovery import discover_files
    from src.analyzers.ignore_rules import IgnoreRules

    # Create a tiny repo layout.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("print('ok')\n")
    (tmp_path / ".env").write_text("SECRET=1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("console.log('x')\n")

    rules = IgnoreRules.default()
    found = discover_files(tmp_path, rules)
    rel = sorted([p.relative_to(tmp_path).as_posix() for p in found])

    assert "src/ok.py" in rel
    assert ".env" not in rel
    assert "node_modules/x.js" not in rel

