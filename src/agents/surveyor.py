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
    out: dict = {
        "type": "module",
        "id": m.path,
        "path": m.path,
        "language": m.language,
        "purpose_statement": getattr(m, "purpose_statement", None),
        "domain_cluster": getattr(m, "domain_cluster", None),
        "complexity_score": getattr(m, "complexity_score", None),
        "change_velocity_30d": change_velocity,
        "is_dead_code_candidate": getattr(m, "is_dead_code_candidate", None),
        "last_modified": getattr(m, "last_modified", None),
    }
    if pagerank is not None:
        out["pagerank"] = pagerank
    out["imports"] = [imp.model_dump() for imp in m.imports]
    out["public_functions"] = [f.model_dump() for f in m.public_functions]
    out["classes"] = [c.model_dump() for c in m.classes]
    return out


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
    """
    repo_root = Path(repo_root).resolve()
    nodes = []
    for m in modules:
        pr = pagerank_by_path.get(m.path)
        nodes.append(_module_node_payload(m, repo_root, velocity_counts, pr))
    # IMPORTS edges with weight = import_count
    import_edges = _import_edge_weights(modules)
    edges = [
        {"type": "IMPORTS", "source": src, "target": tgt, "weight": w}
        for src, tgt, w in sorted(import_edges, key=lambda x: (x[0], x[1]))
    ]
    # Deterministic ordering
    nodes.sort(key=lambda n: str(n.get("id", "")))
    return {
        "directed": True,
        "graph": {
            "schema_version": 1,
            "strongly_connected_components": sccs,
        },
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
        data = {
            "directed": True,
            "graph": {
                "schema_version": graph_meta.get("schema_version", 1),
                "strongly_connected_components": graph_meta.get("strongly_connected_components", []),
            },
            "nodes": [
                {
                    "type": "module",
                    "id": n,
                    "path": n,
                    "language": "unknown",
                    "purpose_statement": None,
                    "domain_cluster": None,
                    "complexity_score": None,
                    "change_velocity_30d": None,
                    "is_dead_code_candidate": None,
                    "last_modified": None,
                    "imports": [],
                    "public_functions": [],
                    "classes": [],
                }
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
    repo_root: Path,
    pagerank_by_path: dict[str, float],
    sccs: list[list[str]],
) -> None:
    """Overwrite all four .cartography JSON files. Call at end of run to guarantee they are updated."""
    cartography_dir.mkdir(parents=True, exist_ok=True)
    # 1. file_hashes.json
    (cartography_dir / "file_hashes.json").write_text(
        json.dumps(new_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # 2. modules.json
    (cartography_dir / "modules.json").write_text(
        json.dumps([m.model_dump() for m in modules], indent=2, sort_keys=True) + "\n",
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
    # 4. git_velocity.json
    (cartography_dir / "git_velocity.json").write_text(
        json.dumps(
            {"days": velocity_days, "per_file": velocity_counts, "high_velocity_core": velocity_core},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_surveyor(repo_root: Path, project_data_dir: Optional[Path] = None) -> Path:
    """
    Phase 1 end-to-end runner:
    - discover files with ignore/safety
    - incremental analysis via content hashes + cached ModuleNodes
    - build module graph + analytics
    - persist to SQLite and vector store (use project_data_dir when analyzing a remote clone so DB lives in project)
    - always overwrite all four .cartography JSON artifacts: file_hashes.json, modules.json, module_graph.json, git_velocity.json
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
            m = analyze_module(f, router=router)
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
    velocity_core = high_velocity_core(velocity_counts)

    # Persist to SQLite then vector store (separate try/except so one can succeed if the other fails)
    from src.store import (
        get_data_dir,
        get_repo_id,
        init_db,
        insert_analysis,
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

    # Always overwrite all four JSON files when process is done (ensures export even if DB or later steps fail)
    _write_all_json_artifacts(
        cartography_dir,
        new_hashes,
        modules,
        g,
        velocity_days,
        velocity_counts,
        velocity_core,
        repo_root,
        pr,
        sccs,
    )
    out_path = cartography_dir / "module_graph.json"
    return out_path

