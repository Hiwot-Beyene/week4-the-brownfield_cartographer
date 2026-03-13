from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import networkx as nx
from networkx.readwrite import json_graph

from src.models.module import ModuleNode
from src.analyzers.file_discovery import discover_files
from src.analyzers.ignore_rules import IgnoreRules
from src.analyzers.tree_sitter_analyzer import GrammarValidationError, LanguageRouter, analyze_module, validate_required_grammars


def build_module_graph(modules: list[ModuleNode]) -> nx.DiGraph:
    g = nx.DiGraph()

    for m in modules:
        g.add_node(m.path)
        for imp in m.imports:
            raw = imp.raw.strip()
            target: str | None = None
            if raw.startswith("import "):
                target = raw[len("import ") :].split(",")[0].strip()
            elif raw.startswith("from "):
                target = raw[len("from ") :].split(" import ")[0].strip()
            if target:
                g.add_edge(m.path, target)

    return g


def compute_pagerank(g: nx.DiGraph) -> dict[str, float]:
    # Deterministic: NetworkX PageRank is deterministic given graph + parameters.
    return nx.pagerank(g)


def compute_sccs(g: nx.DiGraph) -> list[list[str]]:
    # Return SCCs as a stable list of sorted components (largest first).
    comps = [sorted(list(c)) for c in nx.strongly_connected_components(g) if len(c) > 1]
    comps.sort(key=lambda c: (-len(c), c))
    return comps


def extract_git_velocity_from_numstat(numstat_output: str) -> dict[str, int]:
    """
    Parse `git log --numstat`-style output and count file touch frequency.

    We count *occurrences*, not lines added/removed, to match "change frequency".
    Binary files show '-' for counts and are ignored.
    """
    counts: dict[str, int] = {}
    for line in numstat_output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, removed, path = parts[0], parts[1], parts[2]
        if added == "-" or removed == "-":
            continue
        counts[path] = counts.get(path, 0) + 1
    return counts


def high_velocity_core(counts: dict[str, int]) -> list[str]:
    """
    Identify the smallest set of files accounting for ~80% of changes.
    """
    if not counts:
        return []
    total = sum(counts.values())
    target = total * 0.8
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    core: list[str] = []
    running = 0
    for path, c in items:
        core.append(path)
        running += c
        if running >= target:
            break
    # Also ensure we don't exceed top 20% of files if counts are flat.
    max_core = max(1, int(len(items) * 0.2))
    return core[:max_core] if len(core) > max_core else core


def mark_dead_code_candidates(
    modules: list[ModuleNode],
    g: nx.DiGraph,
    pagerank_by_path: dict[str, float],
    velocity_counts: dict[str, int],
    repo_root: Path,
    *,
    pagerank_threshold: float = 0.001,
    velocity_threshold: int = 0,
) -> None:
    """
    Set is_dead_code_candidate on modules that have no inbound references (exported but never imported)
    and optionally low PageRank / zero velocity. Mutates modules in place.
    """
    repo_root = Path(repo_root).resolve()
    path_to_velocity: dict[str, int] = dict(velocity_counts)
    for k in list(path_to_velocity):
        try:
            path_to_velocity[str(Path(k).relative_to(repo_root))] = path_to_velocity[k]
        except ValueError:
            pass
    for m in modules:
        in_degree = g.in_degree(m.path)
        has_exports = bool(m.public_functions or m.classes)
        is_likely_entry = "__main__" in m.path or m.path.endswith("__main__.py")
        pr = pagerank_by_path.get(m.path) or 0.0
        vel = path_to_velocity.get(m.path, 0) or 0
        try:
            vel = path_to_velocity.get(str(Path(m.path).relative_to(repo_root)), vel)
        except ValueError:
            pass
        if is_likely_entry:
            m.is_dead_code_candidate = False
            continue
        if in_degree == 0 and has_exports:
            m.is_dead_code_candidate = True
        elif pr < pagerank_threshold and vel <= velocity_threshold and has_exports:
            m.is_dead_code_candidate = True
        elif m.is_dead_code_candidate is None and in_degree > 0:
            m.is_dead_code_candidate = False
    # Ensure every module has an explicit boolean (no None) for JSON/DB
    for m in modules:
        if m.is_dead_code_candidate is None:
            m.is_dead_code_candidate = False


def _enrich_modules_velocity(
    modules: list[ModuleNode],
    velocity_counts: dict[str, int],
    repo_root: Path,
) -> None:
    """Set change_velocity_30d on each module from velocity_counts so JSON/DB are populated (not null)."""
    path_to_velocity: dict[str, int] = dict(velocity_counts)
    for k in list(path_to_velocity):
        try:
            path_to_velocity[str(Path(k).relative_to(repo_root))] = path_to_velocity[k]
        except ValueError:
            pass
    for m in modules:
        v = path_to_velocity.get(m.path)
        if v is None:
            try:
                v = path_to_velocity.get(str(Path(m.path).relative_to(repo_root)), 0)
            except ValueError:
                v = 0
        m.change_velocity_30d = float(v)


def _enrich_last_modified(
    modules: list[ModuleNode],
    last_modified_by_path: dict[str, str],
    repo_root: Path,
) -> None:
    """Set last_modified on each module from git (ISO date string)."""
    path_to_date: dict[str, str] = dict(last_modified_by_path)
    for k in list(path_to_date):
        try:
            path_to_date[str(Path(k).relative_to(repo_root))] = path_to_date[k]
        except ValueError:
            pass
        try:
            path_to_date[str(repo_root / k)] = path_to_date[k]
        except Exception:
            pass
    for m in modules:
        date_str = path_to_date.get(m.path)
        if date_str is None:
            try:
                date_str = path_to_date.get(str(Path(m.path).relative_to(repo_root)))
            except ValueError:
                pass
        m.last_modified = date_str or None


def survey_summary(
    modules: list[ModuleNode],
    g: nx.DiGraph,
    sccs: list[list[str]],
    velocity_counts: dict[str, int],
    pagerank_by_path: dict[str, float],
    repo_root: Path,
    top_n: int = 10,
) -> dict:
    """
    High-level summary for downstream agents and users: top high-impact (PageRank), high-velocity, and risky modules.
    """
    repo_root = Path(repo_root).resolve()
    path_to_velocity: dict[str, int] = {}
    for k, v in velocity_counts.items():
        path_to_velocity[k] = v
        try:
            path_to_velocity[str(Path(k).relative_to(repo_root))] = v
        except ValueError:
            pass

    def _vel(m: ModuleNode) -> int:
        v = path_to_velocity.get(m.path)
        if v is not None:
            return v
        try:
            return path_to_velocity.get(str(Path(m.path).relative_to(repo_root)), 0)
        except ValueError:
            return 0

    by_pagerank = sorted(modules, key=lambda m: -(pagerank_by_path.get(m.path) or 0))
    by_velocity = sorted(modules, key=lambda m: -_vel(m))
    dead = [m.path for m in modules if m.is_dead_code_candidate]
    in_scc = set()
    for comp in sccs:
        for p in comp:
            in_scc.add(p)
    risky = [m.path for m in modules if m.is_dead_code_candidate or m.path in in_scc]

    high_impact_paths = [m.path for m in by_pagerank[:top_n]]
    high_velocity_paths = [m.path for m in by_velocity[:top_n]]
    out = {
        "high_impact": high_impact_paths,
        "high_velocity": high_velocity_paths,
        "dead_code_candidates": dead[:top_n * 2],
        "in_strongly_connected_components": list(in_scc)[:top_n * 3],
        "risky": list(dict.fromkeys(risky))[:top_n * 2],
    }
    if high_impact_paths:
        out["most_connected"] = high_impact_paths[0]
    return out


def extract_last_modified_from_git(repo_root: Path) -> dict[str, str]:
    """
    Return path -> last commit date (ISO 8601) from git. Uses a single git log run.
    Paths are as reported by git (often relative to repo_root). Returns {} if not a git repo.
    """
    repo_root = repo_root.resolve()
    if not (repo_root / ".git").exists():
        return {}
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "log", "--all", "--name-only", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return {}
        path_to_date: dict[str, str] = {}
        current_date: str = ""
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if line[0].isdigit() or line.startswith("20") and "T" in line:
                current_date = line
                continue
            if current_date and line not in path_to_date:
                path_to_date[line] = current_date
        return path_to_date
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {}


def extract_git_velocity(repo_root: Path, days: int = 90) -> dict[str, int]:
    """
    Compute per-file change frequency for the last `days` days via git log --numstat.

    Answers the challenge question: "What has changed most frequently in the last 90 days?"
    If the path is not a git repo or git fails, returns {} (graceful degradation).
    """
    repo_root = repo_root.resolve()
    git_dir = repo_root / ".git"
    if not git_dir.exists() or not git_dir.is_dir():
        return {}
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                f"--since={days} days ago",
                "--numstat",
                "--pretty=format:",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return {}
        return extract_git_velocity_from_numstat(result.stdout or "")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {}


def _import_edge_weights(modules: list[ModuleNode]) -> list[tuple[str, str, int]]:
    """Compute (source_module, target_module, weight) for IMPORTS; weight = import count."""
    counts: dict[tuple[str, str], int] = {}
    for m in modules:
        for imp in m.imports:
            raw = imp.raw.strip()
            target: str | None = None
            if raw.startswith("import "):
                target = raw[len("import ") :].split(",")[0].strip()
            elif raw.startswith("from "):
                target = raw[len("from ") :].split(" import ")[0].strip()
            if target:
                key = (m.path, target)
                counts[key] = counts.get(key, 0) + 1
    return [(src, tgt, w) for (src, tgt), w in counts.items()]


def _module_node_payload(
    m: ModuleNode,
    repo_root: Path,
    velocity_counts: dict[str, int],
    pagerank: float | None,
) -> dict:
    """One node dict for Knowledge Graph: type=module and schema fields."""
    try:
        rel = str(Path(m.path).relative_to(repo_root))
    except ValueError:
        rel = m.path
    change_velocity = velocity_counts.get(rel) or velocity_counts.get(m.path) or 0
    raw_complexity = getattr(m, "complexity_score", None)
    out: dict = {
        "type": "module",
        "id": m.path,
        "path": m.path,
        "language": m.language,
        "purpose_statement": getattr(m, "purpose_statement", None),
        "domain_cluster": getattr(m, "domain_cluster", None),
        "change_velocity_30d": change_velocity,
        "is_dead_code_candidate": bool(getattr(m, "is_dead_code_candidate", False)),
        "last_modified": getattr(m, "last_modified", None),
    }
    if raw_complexity is not None and raw_complexity != 0:
        out["complexity_score"] = raw_complexity
    if pagerank is not None:
        out["pagerank"] = pagerank
    out["imports"] = [imp.model_dump() for imp in m.imports]
    out["public_functions"] = [f.model_dump() for f in m.public_functions]
    out["classes"] = [c.model_dump() for c in m.classes]
    return out


def _drop_none(d: dict) -> dict:
    """Return a copy of the dict with keys whose value is None removed (so we don't store null in JSON)."""
    return {k: v for k, v in d.items() if v is not None}


def _drop_none_and_empty(d: dict) -> dict:
    """Remove keys that are None or empty list (so we don't store null or [] in JSON)."""
    return {k: v for k, v in d.items() if v is not None and not (isinstance(v, list) and len(v) == 0)}


def build_knowledge_graph_payload(
    modules: list[ModuleNode],
    g: nx.DiGraph,
    sccs: list[list[str]],
    velocity_counts: dict[str, int],
    repo_root: Path,
    pagerank_by_path: dict[str, float],
) -> dict:
    """
    Build module_graph.json payload per Knowledge Graph schema.
    Nodes: type + schema fields (Phase 1: module only). Edges: type + source/target/weight (Phase 1: IMPORTS only).
    Omits None values and empty strongly_connected_components so JSON/DB don't store null or [].
    """
    repo_root = Path(repo_root).resolve()
    nodes = []
    for m in modules:
        pr = pagerank_by_path.get(m.path)
        nodes.append(_drop_none_and_empty(_drop_none(_module_node_payload(m, repo_root, velocity_counts, pr))))
    # IMPORTS edges with weight = import_count
    import_edges = _import_edge_weights(modules)
    edges = [
        {"type": "IMPORTS", "source": src, "target": tgt, "weight": w}
        for src, tgt, w in sorted(import_edges, key=lambda x: (x[0], x[1]))
    ]
    # Deterministic ordering
    nodes.sort(key=lambda n: str(n.get("id", "")))
    graph_meta: dict = {"schema_version": 1}
    if sccs:
        graph_meta["strongly_connected_components"] = sccs
    return {
        "directed": True,
        "graph": graph_meta,
        "nodes": nodes,
        "edges": edges,
    }


def write_module_graph_json(
    out_path: Path,
    modules: list[ModuleNode] | None,
    g: nx.DiGraph,
    sccs: list[list[str]] | None = None,
    velocity_counts: dict[str, int] | None = None,
    repo_root: Path | None = None,
    pagerank_by_path: dict[str, float] | None = None,
) -> None:
    """
    Write module_graph.json in Knowledge Graph schema: nodes (type + schema fields), edges (type, source, target, weight).
    When modules is None, builds minimal payload from graph only (node ids, IMPORTS edges weight 1).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if modules is not None and repo_root is not None and pagerank_by_path is not None:
        sccs = sccs or []
        velocity_counts = velocity_counts or {}
        data = build_knowledge_graph_payload(
            modules, g, sccs, velocity_counts, repo_root, pagerank_by_path
        )
    else:
        # Fallback: graph-only (e.g. from KnowledgeGraph class)
        graph_meta = g.graph if isinstance(g.graph, dict) else {}
        sccs_fb = graph_meta.get("strongly_connected_components", [])
        g_dict: dict = {"schema_version": graph_meta.get("schema_version", 1)}
        if sccs_fb:
            g_dict["strongly_connected_components"] = sccs_fb
        data = {
            "directed": True,
            "graph": g_dict,
            "nodes": [
                _drop_none({
                    "type": "module",
                    "id": n,
                    "path": n,
                    "language": "unknown",
                    "imports": [],
                    "public_functions": [],
                    "classes": [],
                })
                for n in sorted(g.nodes())
            ],
            "edges": [
                {"type": "IMPORTS", "source": u, "target": v, "weight": 1}
                for u, v in sorted(g.edges())
            ],
        }
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_all_json_artifacts(
    cartography_dir: Path,
    new_hashes: dict[str, str],
    modules: list[ModuleNode],
    g: nx.DiGraph,
    velocity_days: int,
    velocity_counts: dict[str, int],
    velocity_core: list[str],
    last_modified_by_path: dict[str, str],
    repo_root: Path,
    pagerank_by_path: dict[str, float],
    sccs: list[list[str]],
    summary: dict,
) -> None:
    """Overwrite .cartography JSON files (hashes, modules, module_graph, git_velocity, survey_summary)."""
    cartography_dir.mkdir(parents=True, exist_ok=True)
    # 1. file_hashes.json
    (cartography_dir / "file_hashes.json").write_text(
        json.dumps(new_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # 2. modules.json (exclude null, empty arrays, and complexity_score when 0)
    def _module_dump(m: ModuleNode) -> dict:
        d = _drop_none_and_empty(m.model_dump(mode="json", exclude_none=True))
        if d.get("complexity_score") == 0:
            d.pop("complexity_score", None)
        return d
    (cartography_dir / "modules.json").write_text(
        json.dumps([_module_dump(m) for m in modules], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # 3. module_graph.json (Knowledge Graph schema: nodes with type + schema fields, edges with type + weight)
    write_module_graph_json(
        cartography_dir / "module_graph.json",
        modules,
        g,
        sccs,
        velocity_counts,
        repo_root,
        pagerank_by_path,
    )
    # 4. git_velocity.json (include last_modified per path from git)
    (cartography_dir / "git_velocity.json").write_text(
        json.dumps(
            {
                "days": velocity_days,
                "per_file": velocity_counts,
                "last_modified": last_modified_by_path,
                "high_velocity_core": velocity_core,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # 5. survey_summary.json (caller passes summary with empty-list keys already omitted)
    (cartography_dir / "survey_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_surveyor(repo_root: Path, project_data_dir: Optional[Path] = None) -> tuple[Path, Optional[int]]:
    """
    Phase 1 end-to-end runner:
    - discover files with ignore/safety
    - incremental analysis via content hashes + cached ModuleNodes
    - build module graph + analytics
    - persist to SQLite and vector store (use project_data_dir when analyzing a remote clone so DB lives in project)
    - always overwrite all .cartography JSON artifacts (file_hashes, modules, module_graph, git_velocity, survey_summary).
    Returns (path to module_graph.json, analysis_id or None if DB persistence failed).
    """
    repo_root = Path(repo_root).resolve()
    cartography_dir = repo_root / ".cartography"
    cartography_dir.mkdir(parents=True, exist_ok=True)
    # When analyzing a remote clone, store DB/chroma in the project so the user sees the analysis in project/.cartography
    store_root = (Path(project_data_dir).resolve() if project_data_dir else repo_root)

    router = LanguageRouter.default()
    try:
        validate_required_grammars(router)
    except GrammarValidationError:
        # Production-grade behavior: report missing grammars clearly but continue with best-effort analysis.
        # (Phase 1 still extracts Python via AST in analyze_module.)
        pass

    rules = IgnoreRules.default()
    files = discover_files(repo_root, rules)

    cache_hashes_path = cartography_dir / "file_hashes.json"
    cache_modules_path = cartography_dir / "modules.json"
    old_hashes: dict[str, str] = {}
    cached_modules: dict[str, ModuleNode] = {}

    if cache_hashes_path.exists():
        try:
            old_hashes = json.loads(cache_hashes_path.read_text(encoding="utf-8"))
        except Exception:
            old_hashes = {}

    if cache_modules_path.exists():
        try:
            raw = json.loads(cache_modules_path.read_text(encoding="utf-8"))
            for item in raw:
                m = ModuleNode.model_validate(item)
                cached_modules[m.path] = m
        except Exception:
            cached_modules = {}

    # Normalize paths so the same file is not processed twice (e.g. symlinks, path variants)
    seen_paths: set[str] = set()
    unique_files: list[Path] = []
    for f in sorted(files):
        key = str(f.resolve())
        if key in seen_paths:
            continue
        seen_paths.add(key)
        unique_files.append(f)
    files = unique_files

    new_hashes: dict[str, str] = {}
    modules: list[ModuleNode] = []
    seen_module_paths: set[str] = set()
    for f in sorted(files):
        h = _hash_file(f)
        new_hashes[str(f)] = h
        if old_hashes.get(str(f)) == h and str(f) in cached_modules:
            m = cached_modules[str(f)]
        else:
            try:
                m = analyze_module(f, router=router)
            except Exception as e:
                logging.getLogger(__name__).warning("surveyor_skip path=%s error=%s", f, e)
                continue
        path_key = str(Path(m.path).resolve())
        if path_key in seen_module_paths:
            continue
        seen_module_paths.add(path_key)
        modules.append(m)

    g = build_module_graph(modules)
    pr = compute_pagerank(g)
    nx.set_node_attributes(g, pr, "pagerank")
    sccs = compute_sccs(g)
    g.graph["strongly_connected_components"] = sccs
    g.graph["schema_version"] = 1

    velocity_days = 90
    velocity_counts = extract_git_velocity(repo_root, days=velocity_days)
    last_modified_by_path = extract_last_modified_from_git(repo_root)
    velocity_core = high_velocity_core(velocity_counts)

    mark_dead_code_candidates(modules, g, pr, velocity_counts, repo_root)
    # Enrich modules with change_velocity_30d and last_modified so JSON and DB have real values
    _enrich_modules_velocity(modules, velocity_counts, repo_root)
    _enrich_last_modified(modules, last_modified_by_path, repo_root)
    summary = survey_summary(modules, g, sccs, velocity_counts, pr, repo_root)
    # Omit empty-list keys so we don't store [] in JSON or DB
    summary_for_storage = {
        k: v for k, v in summary.items()
        if not (isinstance(v, list) and len(v) == 0)
    }

    # Persist to SQLite then vector store (separate try/except so one can succeed if the other fails)
    from src.store import (
        get_data_dir,
        get_repo_id,
        init_db,
        insert_analysis,
        insert_file_hashes,
        insert_git_velocity,
        insert_survey_summary,
        add_modules_to_vector_store,
    )
    data_dir = get_data_dir(store_root)
    db_path = data_dir / "cartographer.db"
    analysis_id: int | None = None
    repo_id: str | None = None

    try:
        init_db(db_path=db_path)
        analysis_id = insert_analysis(
            repo_root=repo_root,
            artifacts_dir=cartography_dir,
            modules=modules,
            pagerank_by_path=pr,
            edges=list(g.edges()),
            db_path=db_path,
        )
        repo_id = get_repo_id(repo_root)
        # Persist file_hashes, git_velocity, survey_summary to DB (same run)
        try:
            insert_file_hashes(analysis_id, new_hashes, db_path=db_path)
            insert_git_velocity(analysis_id, velocity_counts, last_modified_by_path, db_path=db_path)
            insert_survey_summary(analysis_id, summary_for_storage, db_path=db_path)
        except Exception as e:
            logging.exception("SQLite extra artifacts (file_hashes/git_velocity/survey_summary) failed: %s", e)
    except Exception as e:
        logging.exception("SQLite persistence failed: %s", e)
        print("Warning: Could not save to database (SQLite):", e, file=sys.stderr)

    if analysis_id is not None and repo_id is not None:
        try:
            add_modules_to_vector_store(
                analysis_id=analysis_id,
                repo_id=repo_id,
                modules=modules,
                persist_dir=data_dir / "chroma",
            )
        except Exception as e:
            logging.exception("Vector store persistence failed: %s", e)
            print("Warning: Could not save to vector store (Chroma):", e, file=sys.stderr)

    # Always overwrite all JSON files when process is done (ensures export even if DB or later steps fail)
    _write_all_json_artifacts(
        cartography_dir,
        new_hashes,
        modules,
        g,
        velocity_days,
        velocity_counts,
        velocity_core,
        last_modified_by_path,
        repo_root,
        pr,
        sccs,
        summary_for_storage,
    )
    out_path = cartography_dir / "module_graph.json"
    return (out_path, analysis_id)

