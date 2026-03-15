"""
Navigator query agent with four tools:
- find_implementation(concept)
- trace_lineage(dataset, direction)
- blast_radius(module_path)
- explain_module(path)
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, TypedDict

from src.agents.archivist import CartographyTraceLogger
from src.store import sqlite_store


class NavigatorState(TypedDict, total=False):
    analysis_id: int
    query: str
    tool_name: str
    tool_args: dict[str, Any]
    answer: str
    citations: list[dict[str, Any]]
    confidence: float


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _line_range(start: Any, end: Any) -> list[int]:
    try:
        s = int(start) if start is not None else 1
        e = int(end) if end is not None else s
        if e < s:
            e = s
        return [max(1, s), max(1, e)]
    except Exception:
        return [1, 1]


def _route_query(query: str) -> tuple[str, dict[str, Any]]:
    q = (query or "").strip()
    ql = q.lower()
    path_match = re.search(r"(src/[A-Za-z0-9_./-]+)", q)
    if "lineage" in ql or "upstream" in ql or "downstream" in ql or "produces" in ql or "dataset" in ql:
        direction = "upstream" if "upstream" in ql or "produces" in ql else "downstream"
        dataset = q
        quoted = re.findall(r"[\"']([^\"']+)[\"']", q)
        if quoted:
            dataset = quoted[0]
        else:
            dotted = re.findall(r"([A-Za-z0-9_]+\.[A-Za-z0-9_]+)", q)
            if dotted:
                dataset = dotted[-1]
        return "trace_lineage", {"dataset": dataset, "direction": direction}
    if "break" in ql or "blast radius" in ql:
        module_path = path_match.group(1) if path_match else q
        return "blast_radius", {"module_path": module_path}
    if "explain" in ql or "what does" in ql:
        module_path = path_match.group(1) if path_match else q.replace("explain", "").strip()
        return "explain_module", {"path": module_path}
    return "find_implementation", {"concept": q}


def _find_implementation(
    analysis_id: int,
    concept: str,
    artifacts_dir: Path,
    repo_root: Path,
) -> tuple[str, list[dict[str, Any]], float]:
    try:
        from src.llm.embedding import EmbeddingCache
    except Exception:
        EmbeddingCache = None  # type: ignore[assignment]

    modules = sqlite_store.get_modules(analysis_id, repo_root=repo_root)
    purpose_vectors_file = artifacts_dir / "semantic_index" / "purpose_vectors.jsonl"
    cache = EmbeddingCache(cache_dir=artifacts_dir / "embedding_cache") if EmbeddingCache else None
    query_vec = cache.embed(concept) if cache is not None else []
    scored: list[tuple[float, dict[str, Any]]] = []
    if cache is not None and purpose_vectors_file.exists():
        for line in purpose_vectors_file.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            path = str(row.get("path") or "")
            vec = row.get("vector") or []
            if not path or not isinstance(vec, list):
                continue
            score = _cosine(query_vec, [float(v) for v in vec])
            scored.append((score, {"path": path, "purpose_statement": row.get("purpose_statement") or ""}))
    else:
        tokens = [t for t in re.split(r"[^a-z0-9_]+", concept.lower()) if len(t) >= 3]
        for m in modules:
            text = f"{m.get('path', '')} {m.get('purpose_statement', '')}".lower()
            score = float(sum(1 for t in tokens if t in text))
            if score > 0:
                scored.append((score, m))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("path") or "")))
    top = scored[:5]
    if not top:
        return (
            f"No likely implementation found for '{concept}'.",
            [],
            0.35,
        )
    bullets = []
    cits: list[dict[str, Any]] = []
    for score, row in top:
        path = str(row.get("path") or "")
        purpose = str(row.get("purpose_statement") or "")
        bullets.append(f"- `{path}` (semantic score={score:.3f}) {purpose}".strip())
        cits.append({"source_file": path, "line_range": [1, 1], "method": "llm_inference"})
    return (
        f"Likely implementation modules for '{concept}':\n" + "\n".join(bullets),
        cits,
        0.82,
    )


def _trace_lineage(
    analysis_id: int,
    dataset: str,
    direction: str,
    repo_root: Path,
) -> tuple[str, list[dict[str, Any]], float]:
    direction_norm = "upstream" if direction.lower().startswith("up") else "downstream"
    if direction_norm == "upstream":
        nodes = sqlite_store.get_lineage_upstream_dependencies(analysis_id, dataset, repo_root=repo_root)
    else:
        nodes = sqlite_store.get_lineage_blast_radius(analysis_id, dataset, repo_root=repo_root)
    edges = sqlite_store.get_lineage_edges(analysis_id, repo_root=repo_root)
    touched = set(nodes)
    touched.add(dataset)
    cits: list[dict[str, Any]] = []
    for e in edges:
        src = str(e.get("source") or "")
        tgt = str(e.get("target") or "")
        if src in touched and tgt in touched and str(e.get("source_file") or "").strip():
            cits.append(
                {
                    "source_file": str(e.get("source_file")),
                    "line_range": _line_range(e.get("line_start"), e.get("line_end")),
                    "method": "static",
                }
            )
    cits = cits[:12]
    if not nodes:
        return (
            f"No {direction_norm} lineage nodes found for '{dataset}'.",
            cits,
            0.55,
        )
    listing = "\n".join(f"- `{n}`" for n in nodes[:25])
    return (
        f"{direction_norm.title()} lineage for `{dataset}` ({len(nodes)} nodes):\n{listing}",
        cits,
        0.9,
    )


def _blast_radius(
    analysis_id: int,
    module_path: str,
    repo_root: Path,
) -> tuple[str, list[dict[str, Any]], float]:
    edges = sqlite_store.get_import_edges(analysis_id, repo_root=repo_root)
    reverse_adj: dict[str, set[str]] = {}
    for e in edges:
        src = str(e.get("source_module") or "").strip()
        tgt = str(e.get("target_module") or "").strip()
        if not src or not tgt:
            continue
        reverse_adj.setdefault(tgt, set()).add(src)

    visited: set[str] = set()
    queue = [module_path]
    while queue:
        cur = queue.pop(0)
        for dep in sorted(reverse_adj.get(cur, set())):
            if dep in visited:
                continue
            visited.add(dep)
            queue.append(dep)

    impacted = sorted(visited)
    cits = [
        {"source_file": p, "line_range": [1, 1], "method": "static"}
        for p in impacted[:10]
    ]
    if not impacted:
        return (f"No downstream import blast radius found for `{module_path}`.", cits, 0.58)
    listing = "\n".join(f"- `{p}`" for p in impacted[:25])
    return (
        f"Changing `{module_path}` may impact {len(impacted)} importing modules:\n{listing}",
        cits,
        0.84,
    )


def _explain_module(
    analysis_id: int,
    path: str,
    artifacts_dir: Path,
    repo_root: Path,
) -> tuple[str, list[dict[str, Any]], float]:
    modules = sqlite_store.get_modules(analysis_id, repo_root=repo_root)
    target = next((m for m in modules if str(m.get("path")) == path), None)
    if target is None:
        return (f"Module `{path}` not found in analysis {analysis_id}.", [], 0.2)
    module_blob = _read_json(artifacts_dir / "modules.json") or []
    full = next((m for m in module_blob if str((m or {}).get("path") or "") == path), {})
    imports = full.get("imports") or []
    funcs = full.get("public_functions") or []
    classes = full.get("classes") or []
    purpose = str(target.get("purpose_statement") or "No purpose statement available.")
    answer = (
        f"`{path}` ({target.get('language', 'unknown')})\n"
        f"- Purpose: {purpose}\n"
        f"- Imports: {len(imports)}\n"
        f"- Public functions: {len(funcs)}\n"
        f"- Classes: {len(classes)}"
    )
    cits: list[dict[str, Any]] = [{"source_file": path, "line_range": [1, 1], "method": "llm_inference"}]
    for imp in imports[:4]:
        ev = (imp or {}).get("evidence") or {}
        cits.append(
            {
                "source_file": str(ev.get("source_file") or path),
                "line_range": _line_range(ev.get("start_line"), ev.get("end_line")),
                "method": str(ev.get("method") or "static"),
            }
        )
    return answer, cits[:10], 0.88


def _execute_tool(state: NavigatorState, repo_root: Path, artifacts_dir: Path) -> NavigatorState:
    analysis_id = int(state["analysis_id"])
    tool = state.get("tool_name", "")
    args = state.get("tool_args", {}) or {}
    if tool == "find_implementation":
        answer, citations, confidence = _find_implementation(
            analysis_id=analysis_id,
            concept=str(args.get("concept") or ""),
            artifacts_dir=artifacts_dir,
            repo_root=repo_root,
        )
    elif tool == "trace_lineage":
        answer, citations, confidence = _trace_lineage(
            analysis_id=analysis_id,
            dataset=str(args.get("dataset") or ""),
            direction=str(args.get("direction") or "upstream"),
            repo_root=repo_root,
        )
    elif tool == "blast_radius":
        answer, citations, confidence = _blast_radius(
            analysis_id=analysis_id,
            module_path=str(args.get("module_path") or ""),
            repo_root=repo_root,
        )
    else:
        answer, citations, confidence = _explain_module(
            analysis_id=analysis_id,
            path=str(args.get("path") or ""),
            artifacts_dir=artifacts_dir,
            repo_root=repo_root,
        )
    return {
        **state,
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
    }


def find_implementation(
    analysis_id: int,
    concept: str,
    *,
    repo_root: Path,
    artifacts_dir: Path,
) -> dict[str, Any]:
    """
    Library API: find modules implementing a concept (semantic or token match).
    Returns dict with keys: answer, citations, confidence.
    """
    repo_root = Path(repo_root).resolve()
    artifacts_dir = Path(artifacts_dir).resolve()
    answer, citations, confidence = _find_implementation(
        analysis_id=analysis_id,
        concept=concept,
        artifacts_dir=artifacts_dir,
        repo_root=repo_root,
    )
    return {"answer": answer, "citations": citations, "confidence": confidence}


def trace_lineage(
    analysis_id: int,
    dataset: str,
    direction: str,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """
    Library API: trace lineage upstream or downstream for a dataset.
    Returns dict with keys: answer, citations, confidence.
    """
    repo_root = Path(repo_root).resolve()
    answer, citations, confidence = _trace_lineage(
        analysis_id=analysis_id,
        dataset=dataset,
        direction=direction,
        repo_root=repo_root,
    )
    return {"answer": answer, "citations": citations, "confidence": confidence}


def blast_radius(
    analysis_id: int,
    module_path: str,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """
    Library API: compute downstream import blast radius for a module.
    Returns dict with keys: answer, citations, confidence.
    """
    repo_root = Path(repo_root).resolve()
    answer, citations, confidence = _blast_radius(
        analysis_id=analysis_id,
        module_path=module_path,
        repo_root=repo_root,
    )
    return {"answer": answer, "citations": citations, "confidence": confidence}


def explain_module(
    analysis_id: int,
    path: str,
    *,
    repo_root: Path,
    artifacts_dir: Path,
) -> dict[str, Any]:
    """
    Library API: explain a module (purpose, imports, functions, classes).
    Returns dict with keys: answer, citations, confidence.
    """
    repo_root = Path(repo_root).resolve()
    artifacts_dir = Path(artifacts_dir).resolve()
    answer, citations, confidence = _explain_module(
        analysis_id=analysis_id,
        path=path,
        artifacts_dir=artifacts_dir,
        repo_root=repo_root,
    )
    return {"answer": answer, "citations": citations, "confidence": confidence}


def ask_navigator(
    analysis_id: int,
    query: str,
    *,
    repo_root: Path,
    artifacts_dir: Path,
) -> dict[str, Any]:
    """
    Invoke Navigator with a LangGraph workflow when available, else deterministic fallback.
    """
    repo_root = Path(repo_root).resolve()
    artifacts_dir = Path(artifacts_dir).resolve()
    tool_name, tool_args = _route_query(query)
    state: NavigatorState = {
        "analysis_id": int(analysis_id),
        "query": query,
        "tool_name": tool_name,
        "tool_args": tool_args,
    }

    # Try LangGraph runtime, but keep deterministic fallback for environments where it is unavailable.
    try:
        from langgraph.graph import END, StateGraph  # type: ignore

        graph = StateGraph(NavigatorState)

        def route_node(s: NavigatorState) -> NavigatorState:
            tool, args = _route_query(str(s.get("query") or ""))
            return {**s, "tool_name": tool, "tool_args": args}

        def tool_node(s: NavigatorState) -> NavigatorState:
            return _execute_tool(s, repo_root=repo_root, artifacts_dir=artifacts_dir)

        graph.add_node("route", route_node)
        graph.add_node("tool", tool_node)
        graph.set_entry_point("route")
        graph.add_edge("route", "tool")
        graph.add_edge("tool", END)
        app = graph.compile()
        out = app.invoke(state)
    except Exception:
        out = _execute_tool(state, repo_root=repo_root, artifacts_dir=artifacts_dir)

    trace = CartographyTraceLogger(trace_path=artifacts_dir / "cartography_trace.jsonl", agent="navigator")
    trace.log(
        "query",
        confidence=float(out.get("confidence") or 0.5),
        method="static+llm",
        evidence=out.get("citations") or [],
        details={"analysis_id": analysis_id, "query": query, "tool": out.get("tool_name")},
    )

    return {
        "query": query,
        "tool_used": out.get("tool_name"),
        "answer": out.get("answer"),
        "citations": out.get("citations") or [],
        "confidence": float(out.get("confidence") or 0.5),
    }

