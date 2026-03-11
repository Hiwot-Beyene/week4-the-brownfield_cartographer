from __future__ import annotations

from pathlib import Path


def test_extract_git_velocity_returns_empty_when_not_a_git_repo(tmp_path: Path) -> None:
    """When path is not a git repo, extract_git_velocity returns {} (graceful degradation)."""
    from src.agents.surveyor import extract_git_velocity

    counts = extract_git_velocity(tmp_path, days=90)
    assert counts == {}


def test_extract_git_velocity_parses_numstat() -> None:
    from src.agents.surveyor import extract_git_velocity_from_numstat

    sample = "\n".join(
        [
            "1\t0\tsrc/a.py",
            "2\t1\tsrc/b.py",
            "5\t0\tsrc/a.py",
            "-\t-\tdata/binary.parquet",
            "",
        ]
    )
    counts = extract_git_velocity_from_numstat(sample)
    assert counts["src/a.py"] == 2
    assert counts["src/b.py"] == 1
    assert "data/binary.parquet" not in counts


def test_high_velocity_core_80_20() -> None:
    from src.agents.surveyor import high_velocity_core

    counts = {
        "a": 80,
        "b": 10,
        "c": 5,
        "d": 5,
    }
    core = high_velocity_core(counts)
    # Top file alone accounts for 80% of changes -> should be core.
    assert core == ["a"]

