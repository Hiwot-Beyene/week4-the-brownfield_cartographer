from __future__ import annotations

from pathlib import Path


def test_analyze_module_extracts_imports_functions_classes(tmp_path: Path) -> None:
    from src.analyzers.tree_sitter_analyzer import analyze_module

    # Copy fixture into a temp location so line numbers are stable.
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "sample_module.py"
    target = tmp_path / "sample_module.py"
    target.write_text(fixture.read_text())

    node = analyze_module(target)
    assert node.path.endswith("sample_module.py")
    assert node.language == "python"

    # Imports
    imported = {imp.raw for imp in node.imports}
    assert "import os" in imported
    assert "from pathlib import Path" in imported

    # Public functions (private excluded)
    fn_names = {fn.name for fn in node.public_functions}
    assert "public_fn" in fn_names
    assert "_private" not in fn_names

    # Classes + inheritance
    class_map = {c.name: c for c in node.classes}
    assert "Base" in class_map
    assert "Child" in class_map
    assert "Base" in class_map["Child"].bases


def test_analyze_module_sets_language_from_extension(tmp_path: Path) -> None:
    """Non-Python files get correct language from LanguageRouter, not 'unknown'."""
    from src.analyzers.tree_sitter_analyzer import analyze_module

    (tmp_path / "script.sql").write_text("SELECT 1")
    (tmp_path / "config.yml").write_text("key: value")
    (tmp_path / "app.js").write_text("const x = 1;")
    (tmp_path / "file.ts").write_text("const x: number = 1;")

    assert analyze_module(tmp_path / "script.sql").language == "sql"
    assert analyze_module(tmp_path / "config.yml").language == "yaml"
    assert analyze_module(tmp_path / "app.js").language == "javascript"
    assert analyze_module(tmp_path / "file.ts").language == "typescript"

