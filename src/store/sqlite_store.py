"""
SQLite store for versioned analyses: one DB holds all runs keyed by repo_id and run_at.
Enables querying across repos and runs without overwriting.

Data directory: loaded from .env (CARTOGRAPHER_DATA_DIR) if set; otherwise defaults
to repo_root/.cartography when repo_root is provided (project storage), else ~/.brownfield-cartographer.
"""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.models.module import ModuleNode


def _safe_float(x: Optional[float]) -> Optional[float]:
    """Convert to float for SQLite; None or NaN/Inf become None."""
    if x is None:
        return None
    try:
        f = float(x)
        if math.isfinite(f):
            return f
    except (TypeError, ValueError):
        pass
    return None


def _load_dotenv(repo_root: Optional[Path] = None) -> None:
    """Load .env from repo root or cwd so CARTOGRAPHER_DATA_DIR can override defaults."""
    try:
        from dotenv import load_dotenv
        root = (repo_root / ".env").resolve() if repo_root else (Path.cwd() / ".env")
        if root.exists():
            load_dotenv(root, override=False)
    except ImportError:
        pass


def get_data_dir(repo_root: Optional[Path] = None) -> Path:
    """
    Directory for SQLite DB and vector store. Created if missing.

    - If CARTOGRAPHER_DATA_DIR is set (env or .env), use that (resolved to absolute).
    - Else if repo_root is given, use repo_root/.cartography (project storage).
    - Else use ~/.brownfield-cartographer.

    Call with repo_root when running from the surveyor so storage is in the project by default.
    """
    _load_dotenv(repo_root)
    path = os.environ.get("CARTOGRAPHER_DATA_DIR")
    if path:
        p = Path(path).resolve()
    elif repo_root is not None:
        p = (Path(repo_root) if not isinstance(repo_root, Path) else repo_root).resolve() / ".cartography"
    else:
        p = Path.home() / ".brownfield-cartographer"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _repo_id(repo_root: Path) -> str:
    """Stable id for the repo (normalized path hash)."""
    s = str(repo_root.resolve())
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def get_repo_id(repo_root: Path) -> str:
    """Public stable id for the repo (for use by vector store and callers)."""
    return _repo_id(repo_root)


def _commit_sha(repo_root: Path) -> Optional[str]:
    """Current HEAD commit if repo is git, else None."""
    try:
        import subprocess
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()[:40]
    except Exception:
        pass
    return None


def _get_db_path(repo_root: Optional[Path] = None) -> Path:
    return get_data_dir(repo_root) / "cartographer.db"


def _migrate_modules_columns(conn: sqlite3.Connection) -> None:
    """Add Knowledge Graph ModuleNode columns if missing (for existing DBs)."""
    cur = conn.execute("PRAGMA table_info(modules)")
    existing = {row[1] for row in cur.fetchall()}
    columns = [
        ("purpose_statement", "TEXT"),
        ("domain_cluster", "TEXT"),
        ("complexity_score", "REAL"),
        ("change_velocity_30d", "REAL"),
        ("is_dead_code_candidate", "INTEGER"),
        ("last_modified", "TEXT"),
    ]
    for name, col_type in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE modules ADD COLUMN {name} {col_type}")


def init_db(db_path: Optional[Path] = None, repo_root: Optional[Path] = None) -> Path:
    """Create DB file and tables needed for Phase 1: analyses, modules, import_edges. Returns path used."""
    path = db_path or _get_db_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id TEXT NOT NULL,
                repo_path TEXT NOT NULL,
                commit_sha TEXT,
                run_at TEXT NOT NULL,
                artifacts_dir TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_analyses_repo_id ON analyses(repo_id);
            CREATE INDEX IF NOT EXISTS idx_analyses_run_at ON analyses(run_at);

            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                language TEXT NOT NULL,
                pagerank REAL,
                purpose_statement TEXT,
                domain_cluster TEXT,
                complexity_score REAL,
                change_velocity_30d REAL,
                is_dead_code_candidate INTEGER,
                last_modified TEXT,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_modules_analysis_id ON modules(analysis_id);

            CREATE TABLE IF NOT EXISTS import_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                source_module TEXT NOT NULL,
                target_module TEXT NOT NULL,
                weight INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_import_edges_analysis_id ON import_edges(analysis_id);
        """)
        _migrate_modules_columns(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def insert_analysis(
    repo_root: Path,
    artifacts_dir: Path,
    modules: list[ModuleNode],
    pagerank_by_path: dict[str, float],
    edges: list[tuple[str, str]],
    db_path: Optional[Path] = None,
) -> int:
    """
    Insert one analysis run. Persists analyses, modules (ModuleNode fields), and import_edges (IMPORTS).
    Returns analysis_id.
    """
    path = db_path or _get_db_path(repo_root)
    repo_id = _repo_id(repo_root)
    commit_sha = _commit_sha(repo_root)
    run_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            "INSERT INTO analyses (repo_id, repo_path, commit_sha, run_at, artifacts_dir) VALUES (?, ?, ?, ?, ?)",
            (repo_id, str(repo_root.resolve()), commit_sha, run_at, str(artifacts_dir.resolve())),
        )
        analysis_id = cur.lastrowid
        if analysis_id is None:
            raise RuntimeError("insert_analysis: no lastrowid")
        for m in modules:
            pr = _safe_float(pagerank_by_path.get(m.path))
            conn.execute(
                """INSERT INTO modules (analysis_id, path, language, pagerank,
                   purpose_statement, domain_cluster, complexity_score, change_velocity_30d,
                   is_dead_code_candidate, last_modified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    m.path,
                    m.language,
                    pr,
                    getattr(m, "purpose_statement", None) or None,
                    getattr(m, "domain_cluster", None) or None,
                    getattr(m, "complexity_score", None),
                    getattr(m, "change_velocity_30d", None),
                    1 if getattr(m, "is_dead_code_candidate", None) is True else (0 if getattr(m, "is_dead_code_candidate", None) is False else None),
                    getattr(m, "last_modified", None) or None,
                ),
            )
        for src, tgt in edges:
            conn.execute(
                "INSERT INTO import_edges (analysis_id, source_module, target_module, weight) VALUES (?, ?, ?, 1)",
                (analysis_id, src, tgt),
            )
        conn.commit()
        return analysis_id
    finally:
        conn.close()


def get_analyses(
    repo_id: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[dict]:
    """List analyses, optionally filtered by repo_id. Newest first."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        if repo_id:
            cur = conn.execute(
                "SELECT id, repo_id, repo_path, commit_sha, run_at, artifacts_dir FROM analyses WHERE repo_id = ? ORDER BY run_at DESC LIMIT ?",
                (repo_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT id, repo_id, repo_path, commit_sha, run_at, artifacts_dir FROM analyses ORDER BY run_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_modules(analysis_id: int, db_path: Optional[Path] = None, repo_root: Optional[Path] = None) -> list[dict]:
    """Return modules for an analysis (full Knowledge Graph ModuleNode schema columns)."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """SELECT id, analysis_id, path, language, pagerank,
               purpose_statement, domain_cluster, complexity_score, change_velocity_30d,
               is_dead_code_candidate, last_modified FROM modules WHERE analysis_id = ?""",
            (analysis_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_import_edges(analysis_id: int, db_path: Optional[Path] = None, repo_root: Optional[Path] = None) -> list[dict]:
    """Return IMPORTS edges for an analysis (source_module → target_module, weight)."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT id, analysis_id, source_module, target_module, weight FROM import_edges WHERE analysis_id = ?",
            (analysis_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


