"""
SQLite store for versioned analyses: one DB holds all runs keyed by repo_id and run_at.
Enables querying across repos and runs without overwriting.
All .cartography JSON artifacts are also persisted in tables (file_hashes, git_velocity,
lineage_nodes, lineage_edges, sql_lineage_summary). Survey-style views (high impact, high velocity,
dead code) are derived via API getters from modules and git_velocity, not stored in separate tables.

Data directory: loaded from .env (CARTOGRAPHER_DATA_DIR) if set; otherwise defaults
to repo_root/.cartography when repo_root is provided (project storage), else ~/.brownfield-cartographer.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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


def _migrate_git_velocity_last_modified(conn: sqlite3.Connection) -> None:
    """Add last_modified to git_velocity if missing (replaces days column usage)."""
    cur = conn.execute("PRAGMA table_info(git_velocity)")
    existing = {row[1] for row in cur.fetchall()}
    if "last_modified" not in existing:
        conn.execute("ALTER TABLE git_velocity ADD COLUMN last_modified TEXT")


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

            CREATE TABLE IF NOT EXISTS file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_file_hashes_analysis_id ON file_hashes(analysis_id);

            CREATE TABLE IF NOT EXISTS git_velocity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                commit_count INTEGER NOT NULL DEFAULT 0,
                last_modified TEXT,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_git_velocity_analysis_id ON git_velocity(analysis_id);
            CREATE INDEX IF NOT EXISTS idx_git_velocity_commit_count ON git_velocity(analysis_id, commit_count);

            CREATE TABLE IF NOT EXISTS lineage_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                type TEXT NOT NULL,
                name TEXT,
                storage_type TEXT,
                extra TEXT,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_lineage_nodes_analysis_id ON lineage_nodes(analysis_id);

            CREATE TABLE IF NOT EXISTS lineage_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                transformation_type TEXT,
                source_file TEXT,
                line_start INTEGER,
                line_end INTEGER,
                is_write INTEGER,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_lineage_edges_analysis_id ON lineage_edges(analysis_id);
            CREATE INDEX IF NOT EXISTS idx_lineage_edges_source ON lineage_edges(analysis_id, source);
            CREATE INDEX IF NOT EXISTS idx_lineage_edges_target ON lineage_edges(analysis_id, target);

            CREATE TABLE IF NOT EXISTS sql_lineage_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                dialect_used TEXT,
                statement_count INTEGER NOT NULL DEFAULT 0,
                statement_types TEXT,
                tables_read INTEGER NOT NULL DEFAULT 0,
                tables_written INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_sql_lineage_summary_analysis_id ON sql_lineage_summary(analysis_id);
        """)
        _migrate_modules_columns(conn)
        _migrate_git_velocity_last_modified(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def insert_analysis(
    repo_root: Path,
    artifacts_dir: Path,
    modules: list[ModuleNode],
    pagerank_by_path: dict[str, float],
    edges: list[tuple[str, str] | tuple[str, str, int] | dict[str, Any]],
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
                    (lambda c: _safe_float(c) if c is not None and c != 0 else None)(getattr(m, "complexity_score", None)),
                    getattr(m, "change_velocity_30d", None),
                    1 if getattr(m, "is_dead_code_candidate", False) is True else 0,
                    getattr(m, "last_modified", None) or None,
                ),
            )
        for e in edges:
            src: str
            tgt: str
            weight: int = 1
            if isinstance(e, dict):
                src = str(e.get("source") or e.get("from") or "")
                tgt = str(e.get("target") or e.get("to") or "")
                try:
                    weight = int(e.get("weight") or 1)
                except (TypeError, ValueError):
                    weight = 1
            else:
                if len(e) >= 2:
                    src, tgt = str(e[0]), str(e[1])
                    if len(e) >= 3:
                        try:
                            weight = int(e[2] or 1)
                        except (TypeError, ValueError):
                            weight = 1
                else:
                    continue
            if not src or not tgt:
                continue
            conn.execute(
                "INSERT INTO import_edges (analysis_id, source_module, target_module, weight) VALUES (?, ?, ?, ?)",
                (analysis_id, src, tgt, max(1, weight)),
            )
        conn.commit()
        return analysis_id
    finally:
        conn.close()


def insert_analysis_run_only(
    repo_root: Path,
    artifacts_dir: Path,
    db_path: Optional[Path] = None,
) -> int:
    """
    Insert only an analyses row (no modules/edges). Used when Hydrologist runs standalone
    so lineage data has an analysis_id to attach to. Returns analysis_id.
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
            raise RuntimeError("insert_analysis_run_only: no lastrowid")
        conn.commit()
        return analysis_id
    finally:
        conn.close()


def insert_file_hashes(
    analysis_id: int,
    file_hashes: dict[str, str],
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """Persist file_hashes.json content into file_hashes table."""
    path = db_path or _get_db_path(repo_root)
    conn = sqlite3.connect(str(path))
    try:
        for file_path, content_hash in file_hashes.items():
            conn.execute(
                "INSERT INTO file_hashes (analysis_id, path, content_hash) VALUES (?, ?, ?)",
                (analysis_id, file_path, content_hash),
            )
        conn.commit()
    finally:
        conn.close()


def insert_git_velocity(
    analysis_id: int,
    per_file: dict[str, int],
    last_modified_by_path: dict[str, str],
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """Persist git velocity (commit counts and last modified date per file) into git_velocity table."""
    path = db_path or _get_db_path(repo_root)
    conn = sqlite3.connect(str(path))
    try:
        for file_path, commit_count in per_file.items():
            last_mod = last_modified_by_path.get(file_path)
            conn.execute(
                "INSERT INTO git_velocity (analysis_id, path, commit_count, last_modified) VALUES (?, ?, ?, ?)",
                (analysis_id, file_path, commit_count, last_mod),
            )
        conn.commit()
    finally:
        conn.close()


def insert_survey_summary(
    analysis_id: int,
    summary: dict[str, Any],
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """No-op: survey summary is not stored in DB. Use .cartography/survey_summary.json and API getters (get_high_impact, get_high_velocity, etc.) that derive from raw tables."""


# --- API-style getters: derive high-impact, high-velocity, etc. from raw tables ---

def get_high_impact(
    analysis_id: int,
    limit: int = 10,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[dict]:
    """Return high-impact (most connected) modules for an analysis from modules table (ORDER BY pagerank DESC)."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """SELECT path, pagerank FROM modules WHERE analysis_id = ?
               ORDER BY pagerank DESC NULLS LAST LIMIT ?""",
            (analysis_id, limit),
        )
        return [{"path": row["path"], "pagerank": row["pagerank"], "rank": i} for i, row in enumerate(cur.fetchall())]
    finally:
        conn.close()


def get_high_velocity(
    analysis_id: int,
    limit: int = 10,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[dict]:
    """Return high-velocity files for an analysis from git_velocity table (ORDER BY commit_count DESC)."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        # Detect whether last_modified column exists for backwards-compatible reads
        cur = conn.execute("PRAGMA table_info(git_velocity)")
        columns = {row[1] for row in cur.fetchall()}
        if "last_modified" in columns:
            cur = conn.execute(
                """SELECT path, commit_count, last_modified FROM git_velocity WHERE analysis_id = ?
                   ORDER BY commit_count DESC LIMIT ?""",
                (analysis_id, limit),
            )
            rows = [
                {
                    "path": row["path"],
                    "commit_count": row["commit_count"],
                    "last_modified": row["last_modified"],
                    "rank": i,
                }
                for i, row in enumerate(cur.fetchall())
            ]
        else:
            cur = conn.execute(
                """SELECT path, commit_count FROM git_velocity WHERE analysis_id = ?
                   ORDER BY commit_count DESC LIMIT ?""",
                (analysis_id, limit),
            )
            rows = [
                {
                    "path": row["path"],
                    "commit_count": row["commit_count"],
                    "last_modified": None,
                    "rank": i,
                }
                for i, row in enumerate(cur.fetchall())
            ]
        return rows
    finally:
        conn.close()


def get_dead_code_candidates(
    analysis_id: int,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[dict]:
    """Return dead-code candidates from modules table (is_dead_code_candidate = 1)."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT path FROM modules WHERE analysis_id = ? AND is_dead_code_candidate = 1",
            (analysis_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_survey_summary_json(
    analysis_id: int,
    limit: int = 10,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Optional[dict]:
    """Return full survey-summary shape for an analysis by deriving from raw tables (for API compatibility)."""
    high_impact = get_high_impact(analysis_id, limit=limit, db_path=db_path, repo_root=repo_root)
    high_velocity = get_high_velocity(analysis_id, limit=limit, db_path=db_path, repo_root=repo_root)
    dead = get_dead_code_candidates(analysis_id, db_path=db_path, repo_root=repo_root)
    return {
        "high_impact": [r["path"] for r in high_impact],
        "high_velocity": [r["path"] for r in high_velocity],
        "dead_code_candidates": [r["path"] for r in dead],
        "in_strongly_connected_components": [],  # would require computing from import_edges in API
        "risky": list(dict.fromkeys([r["path"] for r in dead])),  # risky = dead_code union scc; scc not stored
    }


def insert_lineage_graph(
    analysis_id: int,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """Persist lineage_graph.json nodes and edges into lineage_nodes and lineage_edges tables."""
    path = db_path or _get_db_path(repo_root)
    conn = sqlite3.connect(str(path))
    try:
        for n in nodes:
            node_id = n.get("id", "")
            ntype = n.get("type", "dataset")
            name = n.get("name")
            storage_type = n.get("storage_type")
            extra = n.get("extra")
            extra_str = json.dumps(extra) if extra is not None else None
            conn.execute(
                """INSERT INTO lineage_nodes (analysis_id, node_id, type, name, storage_type, extra)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (analysis_id, node_id, ntype, name, storage_type, extra_str),
            )
        for e in edges:
            line_range = e.get("line_range")
            line_start = line_range[0] if isinstance(line_range, (list, tuple)) and len(line_range) >= 1 else None
            line_end = line_range[1] if isinstance(line_range, (list, tuple)) and len(line_range) >= 2 else None
            is_write = e.get("is_write")
            conn.execute(
                """INSERT INTO lineage_edges (analysis_id, source, target, edge_type, transformation_type,
                   source_file, line_start, line_end, is_write) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    e.get("source", ""),
                    e.get("target", ""),
                    e.get("edge_type", "CONSUMES"),
                    e.get("transformation_type"),
                    e.get("source_file"),
                    line_start,
                    line_end,
                    1 if is_write is True else (0 if is_write is False else None),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def insert_sql_lineage_summary(
    analysis_id: int,
    files: list[dict[str, Any]],
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """Persist sql_lineage_summary.json (files array) into sql_lineage_summary table."""
    path = db_path or _get_db_path(repo_root)
    conn = sqlite3.connect(str(path))
    try:
        for f in files:
            stmt_types = f.get("statement_types")
            stmt_types_str = json.dumps(stmt_types) if stmt_types is not None else None
            err = f.get("error")
            err_str = str(err) if err is not None else None
            conn.execute(
                """INSERT INTO sql_lineage_summary (analysis_id, path, dialect_used, statement_count,
                   statement_types, tables_read, tables_written, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    f.get("path", ""),
                    f.get("dialect_used"),
                    f.get("statement_count", 0),
                    stmt_types_str,
                    f.get("tables_read", 0),
                    f.get("tables_written", 0),
                    err_str,
                ),
            )
        conn.commit()
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
        rows = [dict(row) for row in cur.fetchall()]
        for r in rows:
            if "is_dead_code_candidate" in r:
                r["is_dead_code_candidate"] = bool(r["is_dead_code_candidate"]) if r["is_dead_code_candidate"] is not None else False
        return rows
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


def get_module_graph_payload(
    analysis_id: int,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Build module graph for visualization from SQLite (modules + import_edges).

    Important: import_edges.target_module can be an import name (e.g. "json" or
    "ol_orchestrate.lib.utils"), not always a file path. For architecture graphing
    we resolve those names to *internal module file paths* when possible, then keep
    only internal module-to-module edges.

    Returns { nodes, edges, hubs } where nodes are repository modules and edges are
    resolved internal dependencies.
    """
    modules = get_modules(analysis_id, db_path=db_path, repo_root=repo_root)
    edges_raw = get_import_edges(analysis_id, db_path=db_path, repo_root=repo_root)

    module_by_path: dict[str, dict] = {m["path"]: m for m in modules if isinstance(m.get("path"), str)}
    module_paths = set(module_by_path)

    # Build lookup from import-like names -> module file path using all dotted suffixes.
    # This supports monorepo layouts where import roots vary by package.
    name_to_path: dict[str, str] = {}
    for raw_path in module_paths:
        path_norm = raw_path.replace("\\", "/")
        if not path_norm.endswith(".py"):
            continue

        no_ext = path_norm[:-3]
        segments = [s for s in no_ext.split("/") if s]
        if not segments:
            continue
        if segments[-1] == "__init__":
            segments = segments[:-1]
            if not segments:
                continue

        # Add all dotted suffixes so imports like "pkg.mod" can map even when
        # file path has extra leading monorepo/package segments.
        for i in range(len(segments)):
            dotted = ".".join(segments[i:])
            if dotted:
                name_to_path.setdefault(dotted, raw_path)
        # Also support basename-only imports.
        name_to_path.setdefault(segments[-1], raw_path)

    def _resolve_internal_module(ref: str) -> Optional[str]:
        """Resolve a source/target reference to an internal module path if possible."""
        value = (ref or "").strip()
        if not value:
            return None
        if value in module_paths:
            return value
        return name_to_path.get(value)

    # Keep only internal module-to-module edges for architecture connectivity.
    edges: list[dict[str, Any]] = []
    degree_by_path: dict[str, int] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for e in edges_raw:
        src = _resolve_internal_module(str(e.get("source_module") or ""))
        tgt = _resolve_internal_module(str(e.get("target_module") or ""))
        if not src or not tgt:
            continue
        # Drop self-import loops from visualization payload to reduce noise.
        if src == tgt:
            continue
        pair = (src, tgt)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edges.append({"from": src, "to": tgt, "weight": int(e.get("weight") or 1)})
        degree_by_path[src] = degree_by_path.get(src, 0) + 1
        degree_by_path[tgt] = degree_by_path.get(tgt, 0) + 1

    # Keep all modules from the database (including isolated ones).
    all_ids = set(module_by_path)
    nodes: list[dict[str, Any]] = []
    for path in sorted(all_ids):
        m = module_by_path.get(path)
        degree = degree_by_path.get(path, 0)
        pagerank = _safe_float(m.get("pagerank")) if m else 0.0
        pagerank = pagerank if pagerank is not None else 0.0
        dead_code = bool(m.get("is_dead_code_candidate")) if m else False
        base_size = 10
        size_from_degree = min(degree * 3, 24)
        size_from_pagerank = min(pagerank * 80, 30) if pagerank else 0
        size = base_size + size_from_degree + size_from_pagerank
        # Dead code candidates should never be marked "important" in visualization semantics.
        important = (not dead_code) and ((pagerank and pagerank >= 0.08) or degree >= 4)
        label = path.replace("\\", "/").split("/")[-1] if path else path
        nodes.append({
            "id": path,
            "label": label,
            "node_type": "module",
            "language": m.get("language", "unknown") if m else "unknown",
            "purpose_statement": m.get("purpose_statement") if m else None,
            "domain_cluster": m.get("domain_cluster") if m else None,
            "dead_code": dead_code,
            "last_modified": m.get("last_modified") if m else None,
            "degree": degree,
            "pagerank": pagerank,
            "size": size,
            "important": important,
        })

    # Hubs ("most connected"): rank by degree (connection count), excluding dead-code candidates.
    # Pagerank is kept only as a tie-breaker.
    live_nodes = [n for n in nodes if not n.get("dead_code")]
    sorted_nodes = sorted(live_nodes, key=lambda n: (-(n.get("degree") or 0), -(n.get("pagerank") or 0), n.get("id", "")))
    hubs = [n["id"] for n in sorted_nodes[:8]]

    return {
        "nodes": nodes,
        "edges": edges,
        "hubs": hubs,
        "filtered_isolated_regular_modules": 0,
    }


def get_lineage_nodes(
    analysis_id: int,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Return all lineage_nodes rows for an analysis."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """SELECT node_id, type, name, storage_type, extra
               FROM lineage_nodes WHERE analysis_id = ?""",
            (analysis_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_lineage_edges(
    analysis_id: int,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Return all lineage_edges rows for an analysis."""
    path = db_path or _get_db_path(repo_root)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """SELECT source, target, edge_type, transformation_type, source_file, line_start, line_end, is_write
               FROM lineage_edges WHERE analysis_id = ?""",
            (analysis_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_lineage_graph_payload(
    analysis_id: int,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Build lineage graph for visualization from SQLite (lineage_nodes + lineage_edges).
    Returns { nodes, edges } with node_type (dataset/transformation), so every edge source/target has a node.
    """
    raw_nodes = get_lineage_nodes(analysis_id, db_path=db_path, repo_root=repo_root)
    raw_edges = get_lineage_edges(analysis_id, db_path=db_path, repo_root=repo_root)

    node_by_id: dict[str, dict[str, Any]] = {}
    for r in raw_nodes:
        nid = (r.get("node_id") or "").strip()
        if not nid:
            continue
        ntype = (r.get("type") or "dataset").lower()
        name = r.get("name") or nid
        node_by_id[nid] = {
            "id": nid,
            "label": name if isinstance(name, str) else nid,
            "node_type": "dataset" if ntype == "dataset" else "transformation",
            "name": name,
            "storage_type": r.get("storage_type"),
            "extra": r.get("extra"),
        }

    # Ensure every edge endpoint has a node
    for e in raw_edges:
        src = (e.get("source") or "").strip()
        tgt = (e.get("target") or "").strip()
        if src and src not in node_by_id:
            node_by_id[src] = {"id": src, "label": src, "node_type": "dataset", "name": src}
        if tgt and tgt not in node_by_id:
            node_by_id[tgt] = {"id": tgt, "label": tgt, "node_type": "dataset", "name": tgt}

    nodes: list[dict[str, Any]] = []
    for nid, data in sorted(node_by_id.items()):
        ntype = data.get("node_type", "dataset")
        nodes.append({
            **data,
            "size": 12 if ntype == "transformation" else 10,
            "important": ntype == "transformation",
        })

    edges: list[dict[str, Any]] = []
    node_ids = set(node_by_id)
    for e in raw_edges:
        src = (e.get("source") or "").strip()
        tgt = (e.get("target") or "").strip()
        if src and tgt and src in node_ids and tgt in node_ids:
            edges.append({
                "from": src,
                "to": tgt,
                "edge_type": e.get("edge_type"),
                "transformation_type": e.get("transformation_type"),
                "source_file": e.get("source_file"),
                "is_write": bool(e.get("is_write")),
            })

    # Remove truly isolated nodes (degree=0) to reduce graph clutter.
    in_deg: dict[str, int] = {}
    out_deg: dict[str, int] = {}
    for n in nodes:
        nid = str(n.get("id") or "")
        if nid:
            in_deg[nid] = 0
            out_deg[nid] = 0
    for e in edges:
        src = str(e.get("from") or "")
        tgt = str(e.get("to") or "")
        if src in out_deg:
            out_deg[src] += 1
        if tgt in in_deg:
            in_deg[tgt] += 1

    kept_node_ids = set(in_deg)
    # Explicit lineage boundaries from full graph.
    sources = [
        nid for nid in kept_node_ids
        if in_deg.get(nid, 0) == 0 and out_deg.get(nid, 0) > 0
    ]
    sinks = [
        nid for nid in kept_node_ids
        if out_deg.get(nid, 0) == 0 and in_deg.get(nid, 0) > 0
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "sources": sorted(sources),
        "sinks": sorted(sinks),
        "filtered_isolated_nodes": 0,
    }


def get_lineage_upstream_dependencies(
    analysis_id: int,
    node_id: str,
    max_depth: int = 25,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[str]:
    """DB-backed upstream dependency query for a lineage node."""
    edges = get_lineage_edges(analysis_id, db_path=db_path, repo_root=repo_root)
    if not node_id:
        return []

    reverse_adj: dict[str, set[str]] = {}
    for e in edges:
        src = str(e.get("source") or "").strip()
        tgt = str(e.get("target") or "").strip()
        if not src or not tgt:
            continue
        reverse_adj.setdefault(tgt, set()).add(src)

    visited: set[str] = set()
    frontier: list[tuple[str, int]] = [(node_id, 0)]
    while frontier:
        cur, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for prev in sorted(reverse_adj.get(cur, set())):
            if prev in visited:
                continue
            visited.add(prev)
            frontier.append((prev, depth + 1))
    return sorted(visited)


def get_lineage_blast_radius(
    analysis_id: int,
    node_id: str,
    max_depth: int = 25,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> list[str]:
    """DB-backed downstream impact query (blast radius) for a lineage node."""
    edges = get_lineage_edges(analysis_id, db_path=db_path, repo_root=repo_root)
    if not node_id:
        return []

    forward_adj: dict[str, set[str]] = {}
    for e in edges:
        src = str(e.get("source") or "").strip()
        tgt = str(e.get("target") or "").strip()
        if not src or not tgt:
            continue
        forward_adj.setdefault(src, set()).add(tgt)

    visited: set[str] = set()
    frontier: list[tuple[str, int]] = [(node_id, 0)]
    while frontier:
        cur, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for nxt in sorted(forward_adj.get(cur, set())):
            if nxt in visited:
                continue
            visited.add(nxt)
            frontier.append((nxt, depth + 1))
    return sorted(visited)


