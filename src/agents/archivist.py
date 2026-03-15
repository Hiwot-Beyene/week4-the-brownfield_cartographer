"""
Phase 4 Archivist: maintain living artifacts and analysis trace.

Artifacts:
- CODEBASE.md
- onboarding_brief.md
- lineage_graph.json (already produced by Hydrologist; archived as context source)
- semantic_index/ (purpose-statement vector index)
- cartography_trace.jsonl
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Schema versions for programmatic detection and backward compatibility.
CODEBASE_SCHEMA_VERSION = 1
TRACE_SCHEMA_VERSION = 1

# Stable section order for CODEBASE.md; do not reorder so tools can rely on headings.
CODEBASE_SECTION_ORDER = (
    "Architecture Overview",
    "Critical Path",
    "Data Sources & Sinks",
    "Known Debt",
    "High-Velocity Files",
    "Recent Change Velocity",
    "Module Purpose Index",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


_FDE_QUESTION_TEXT: dict[str, str] = {
    "fde_q1_business_capability": "What is the primary data ingestion path?",
    "fde_q2_key_data_flow": "What are the 3-5 most critical output datasets/endpoints?",
    "fde_q3_change_risk": "What is the blast radius if the most critical module fails?",
    "fde_q4_operational_hotspots": "Where is the business logic concentrated vs. distributed?",
    "fde_q5_first_90_days": "What has changed most frequently in the last 90 days (git velocity map)?",
}


def _normalize_day_one_answers(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        answers = raw.get("answers")
        if isinstance(answers, list):
            raw = answers
        else:
            raw = []
    if not isinstance(raw, list):
        raw = []
    by_qid: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("question_id") or "").strip()
        if not qid:
            continue
        by_qid[qid] = item
    out: list[dict[str, Any]] = []
    for qid in _FDE_QUESTION_TEXT:
        out.append(
            by_qid.get(
                qid,
                {
                    "question_id": qid,
                    "answer": "Insufficient evidence in this run to produce a high-confidence answer.",
                    "citations": [],
                },
            )
        )
    return out


def _lineage_ingestion_citations(lineage_graph: dict[str, Any], max_citations: int = 5) -> list[dict[str, Any]]:
    """Collect file:line evidence for ingestion path from CONSUMES edges that have source_file. Each citation has method for provenance."""
    edges = lineage_graph.get("edges") or []
    seen: set[tuple[str, int]] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        if str(e.get("edge_type")) != "CONSUMES":
            continue
        path = (e.get("source_file") or "").strip()
        if not path:
            continue
        line = 1
        if isinstance(e.get("line_range"), (list, tuple)) and len(e["line_range"]) >= 1:
            line = int(e["line_range"][0]) if e["line_range"] else 1
        key = (path, line)
        if key in seen or len(out) >= max_citations:
            continue
        seen.add(key)
        out.append({"file": path, "line": line, "method": "lineage (CONSUMES edge)"})
    return out


def _lineage_sink_citations(lineage_graph: dict[str, Any], sinks: list[str], max_citations: int = 5) -> list[dict[str, Any]]:
    """Collect file evidence for sink/output datasets from PRODUCES edges. Each citation has method for provenance."""
    edges = lineage_graph.get("edges") or []
    sink_set = set(sinks)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in edges:
        if not isinstance(e, dict) or str(e.get("edge_type")) != "PRODUCES":
            continue
        tgt = str((e.get("target") or "")).strip()
        if tgt not in sink_set:
            continue
        src = str(e.get("source") or e.get("transformation") or "").strip()
        if not src:
            continue
        path = src
        if ":" in src:
            parts = src.split(":", 2)
            if len(parts) >= 2 and ("/" in parts[1] or "\\" in parts[1]):
                path = parts[1]
            elif len(parts) >= 2:
                path = parts[-1] if "/" in parts[-1] or "\\" in parts[-1] else src
        if path in seen or len(out) >= max_citations:
            continue
        seen.add(path)
        out.append({"file": path, "line": 1, "method": "lineage (PRODUCES edge)"})
    return out


def _heuristic_onboarding_answers(
    artifacts_dir: Path,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    module_graph = _read_json(artifacts_dir / "module_graph.json") or {}
    lineage_graph = _read_json(artifacts_dir / "lineage_graph.json") or {}
    survey_summary = _read_json(artifacts_dir / "survey_summary.json") or {}
    sources, sinks = _data_sources_and_sinks(lineage_graph)
    high_impact = survey_summary.get("high_impact") or []
    high_velocity = survey_summary.get("high_velocity") or []
    most_connected = survey_summary.get("most_connected")
    risky = survey_summary.get("risky") or []
    n_edges = len(lineage_graph.get("edges") or [])
    n_nodes = len(lineage_graph.get("nodes") or [])

    ingestion_citations = _lineage_ingestion_citations(lineage_graph, max_citations=5)
    sink_citations = _lineage_sink_citations(lineage_graph, sinks, max_citations=5)

    short = lambda p: _short_path(p, repo_root) if repo_root and p else p
    high_impact_short = [short(p) for p in high_impact[:5]]
    high_velocity_short = [short(p) for p in high_velocity[:5]]
    risky_short = [short(p) for p in risky[:3]]

    # One clear sentence per answer; optional second sentence only when needed.
    sources_list = ", ".join(sources[:8]) if sources else "none detected"
    sinks_list = ", ".join(sinks[:5]) if sinks else "none detected"
    q1_answer = (
        f"Data ingestion starts from these lineage sources: {sources_list}. "
        f"The first transformations that consume them are in the staging SQL and dbt model files (see Evidence for exact file:line)."
    )
    q2_answer = (
        f"The critical output datasets are: {sinks_list}. "
        f"Each is produced by a dbt model or SQL file; Evidence lists the defining file for each."
    )
    q3_answer = (
        f"The most critical modules by PageRank (highest blast radius if they fail) are: {', '.join(high_impact_short[:3]) or 'none'}. "
        f"Use Navigator blast_radius on a module path for the full downstream dependency list."
    )
    q4_answer = (
        f"Business logic is concentrated in: {', '.join(high_impact_short[:3]) or 'see survey'}. "
        + (f"Risky/dead-code candidates (review first): {', '.join(risky_short)}." if risky_short else "No risky/dead-code candidates flagged.")
    )
    q5_answer = (
        f"High-velocity files (most changed, from structural analysis) are: {', '.join(high_velocity_short[:5]) or 'no git history (shallow clone)'}. "
        f"Evidence lists each file; re-run with full clone for commit counts."
    )

    def citations_for_paths(paths: list[str], line: int = 1, method: str = "survey (high_impact)") -> list[dict[str, Any]]:
        return [{"file": p, "line": line, "method": method} for p in (paths or [])[:5]]

    answers = [
        {
            "question_id": "fde_q1_business_capability",
            "answer": q1_answer,
            "citations": ingestion_citations if ingestion_citations else citations_for_paths(high_impact[:2], method="survey (high_impact)"),
        },
        {
            "question_id": "fde_q2_key_data_flow",
            "answer": q2_answer,
            "citations": sink_citations if sink_citations else citations_for_paths(high_impact[:2], method="survey (high_impact)"),
        },
        {
            "question_id": "fde_q3_change_risk",
            "answer": q3_answer,
            "citations": citations_for_paths(high_impact[:5], method="survey (PageRank / most_connected)") or ([{"file": most_connected, "line": 1, "method": "survey (most_connected)"}] if most_connected else []),
        },
        {
            "question_id": "fde_q4_operational_hotspots",
            "answer": q4_answer,
            "citations": citations_for_paths(risky[:3], method="survey (risky/dead-code)") or citations_for_paths(high_impact[:5], method="survey (high_impact)"),
        },
        {
            "question_id": "fde_q5_first_90_days",
            "answer": q5_answer,
            "citations": citations_for_paths(high_velocity[:5], method="survey (high_velocity)"),
        },
    ]
    return answers


def _modules_from_artifacts(artifacts_dir: Path) -> list[dict[str, Any]]:
    """Primary source: module_graph.json module nodes; fallback: modules.json."""
    module_graph = _read_json(artifacts_dir / "module_graph.json") or {}
    nodes = module_graph.get("nodes") or []
    graph_modules = [
        n for n in nodes if isinstance(n, dict) and str((n or {}).get("type") or "").lower() == "module"
    ]
    if graph_modules:
        return graph_modules
    return _read_json(artifacts_dir / "modules.json") or []


def _purpose_map_from_semantic_index(artifacts_dir: Path) -> dict[str, str]:
    """Load path -> purpose_statement from semantic_index/modules.json (from Semanticist)."""
    path_to_purpose: dict[str, str] = {}
    semantic_modules = _read_json(artifacts_dir / "semantic_index" / "modules.json")
    if not isinstance(semantic_modules, list):
        return path_to_purpose
    for entry in semantic_modules:
        if not isinstance(entry, dict):
            continue
        path = str((entry.get("module_name") or entry.get("path")) or "").strip()
        purpose = str((entry.get("purpose_statement") or entry.get("purpose")) or "").strip()
        if path and purpose:
            path_to_purpose[path] = purpose
    return path_to_purpose


def _repo_display_name(repo_root: Path) -> str:
    """Derive a short display name for the analyzed repository."""
    name = (repo_root or Path()).name
    if name in (".", ""):
        try:
            name = (repo_root or Path()).resolve().name
        except Exception:
            name = "repository"
    return name or "repository"


def _short_path(path_str: str, repo_root: Path | None) -> str:
    """
    Return path suitable for display: repo_name/relative_path when path is under repo_root,
    otherwise the original path. Uses forward slashes.
    """
    if not path_str:
        return path_str
    path_str = path_str.replace("\\", "/").strip()
    if not repo_root:
        return path_str
    repo_resolved = Path(repo_root).resolve()
    try:
        path_resolved = Path(path_str).resolve()
        rel = path_resolved.relative_to(repo_resolved)
        return f"{repo_resolved.name}/{rel.as_posix()}"
    except ValueError:
        pass
    except Exception:
        pass
    if repo_resolved.name in path_str:
        idx = path_str.find(repo_resolved.name)
        suffix = path_str[idx + len(repo_resolved.name) :].lstrip("/")
        if suffix:
            return f"{repo_resolved.name}/{suffix}"
    return path_str


def _shorten_lineage_id(node_id: str, repo_root: Path | None) -> str:
    """
    Shorten path inside lineage node ids like 'dbt_model:/full/path:name', 'sql:/full/path', 'dbt_source:/full/path:name'.
    """
    if not node_id or not repo_root:
        return node_id
    for prefix in ("dbt_model:", "sql:", "dbt_source:"):
        if node_id.startswith(prefix):
            rest = node_id[len(prefix) :]
            if ":" in rest:
                path_part, suffix = rest.split(":", 1)
                short_path = _short_path(path_part.strip(), repo_root)
                return f"{prefix}{short_path}:{suffix}"
            short_path = _short_path(rest.strip(), repo_root)
            return f"{prefix}{short_path}"
    if "/" in node_id or "\\" in node_id:
        return _short_path(node_id, repo_root)
    return node_id


def _synthesize_architecture_overview(
    repo_root: Path,
    survey_summary: dict[str, Any],
    top_module_paths: list[str],
    sources: list[str],
    sinks: list[str],
    module_count: int,
) -> str:
    """Build one paragraph describing the analyzed repository (not the Cartographer)."""
    repo_name = _repo_display_name(repo_root)
    parts = [
        f"This repository ({repo_name}) contains {module_count} analyzed modules."
    ]
    if top_module_paths:
        short = [p.split("/")[-1] if "/" in p else p for p in top_module_paths[:5]]
        parts.append(f"Structurally central or high-impact modules include: {', '.join(short)}.")
    if sources or sinks:
        if sources:
            parts.append(f"Data sources include {min(3, len(sources))} entry points.")
        if sinks:
            parts.append(f"Outputs or sinks include {min(3, len(sinks))} endpoints or datasets.")
    high_impact = (survey_summary.get("high_impact") or [])[:3]
    if high_impact:
        parts.append("High-impact and velocity signals point to key workflow and transformation paths.")
    return " ".join(parts).strip() + "."


_GENERIC_CITATION_FILES = {"module_graph.json", "lineage_graph.json", "survey_summary.json", "day_one_answers.json"}


def _looks_like_placeholder_answers(answers: list[dict[str, Any]]) -> bool:
    placeholders = 0
    for a in answers:
        text = str((a or {}).get("answer") or "").strip().lower()
        if "insufficient evidence in this run" in text or text in {"", "no answer provided."}:
            placeholders += 1
            continue
        if "the system appears to" in text or "detected lineage spans" in text or "prioritize stabilizing" in text:
            placeholders += 1
            continue
        cits = (a or {}).get("citations") or []
        if cits:
            all_generic = all(
                str((c or {}).get("file") or "").replace("\\", "/").split("/")[-1] in _GENERIC_CITATION_FILES
                for c in cits
            )
            if all_generic:
                placeholders += 1
    return placeholders >= max(1, len(answers) // 2)


@dataclass
class CartographyTraceLogger:
    trace_path: Path
    agent: str = "archivist"

    def log(
        self,
        action: str,
        *,
        confidence: float,
        method: str,
        evidence: list[dict[str, Any]] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "timestamp": _now_iso(),
            "agent": self.agent,
            "action": action,
            "method": method,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "evidence": evidence or [],
            "details": details or {},
        }
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _top_modules_by_pagerank(modules: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(
        modules,
        key=lambda m: (-(float(m.get("pagerank") or 0.0)), str(m.get("path") or "")),
    )
    return ranked[:n]


def _data_sources_and_sinks(lineage_graph: dict[str, Any]) -> tuple[list[str], list[str]]:
    nodes = lineage_graph.get("nodes") or []
    edges = lineage_graph.get("edges") or []
    in_deg: dict[str, int] = {}
    out_deg: dict[str, int] = {}
    for n in nodes:
        nid = str((n or {}).get("id") or "").strip()
        if nid:
            in_deg.setdefault(nid, 0)
            out_deg.setdefault(nid, 0)
    for e in edges:
        src = str((e or {}).get("source") or "").strip()
        tgt = str((e or {}).get("target") or "").strip()
        if src:
            out_deg[src] = out_deg.get(src, 0) + 1
            in_deg.setdefault(src, in_deg.get(src, 0))
        if tgt:
            in_deg[tgt] = in_deg.get(tgt, 0) + 1
            out_deg.setdefault(tgt, out_deg.get(tgt, 0))
    sources = sorted([nid for nid in in_deg if in_deg.get(nid, 0) == 0 and out_deg.get(nid, 0) > 0])
    sinks = sorted([nid for nid in out_deg if out_deg.get(nid, 0) == 0 and in_deg.get(nid, 0) > 0])
    return sources, sinks


def _known_debt(modules: list[dict[str, Any]], module_graph: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    graph_meta = module_graph.get("graph") or {}
    sccs = graph_meta.get("strongly_connected_components") or []
    circular_deps = [comp for comp in sccs if isinstance(comp, list) and len(comp) > 1]
    doc_drift = sorted(
        [
            str(m.get("path"))
            for m in modules
            if m.get("documentation_drift") is True and str(m.get("path") or "").strip()
        ]
    )
    return circular_deps, doc_drift


def _doc_drift_from_semantic_index(artifacts_dir: Path) -> list[str]:
    """Collect paths with doc drift (docstring mismatch) from semantic_index/modules.json or modules.json."""
    paths: list[str] = []
    for rel_path in ["semantic_index/modules.json", "modules.json"]:
        data = _read_json(artifacts_dir / rel_path)
        if not isinstance(data, list):
            continue
        for entry in data:
            if not isinstance(entry, dict):
                continue
            path = str((entry.get("module_name") or entry.get("path")) or "").strip()
            if not path:
                continue
            doc_match = entry.get("docstring_match")
            drift = entry.get("documentation_drift")
            if doc_match is False or drift is True:
                paths.append(path)
    return sorted(dict.fromkeys(paths))


def _high_velocity_for_codebase(
    git_velocity: dict[str, Any], survey_summary: dict[str, Any]
) -> tuple[list[tuple[str, int | None]], bool]:
    """
    Return (list of (path, count_or_none), use_survey_fallback).
    When per_file has counts, use them; else use survey_summary high_velocity with None counts.
    """
    per_file = git_velocity.get("per_file") or {}
    if per_file:
        sorted_items = sorted(
            per_file.items(),
            key=lambda kv: (-int(kv[1] or 0), kv[0]),
        )[:10]
        return [(p, int(c or 0)) for p, c in sorted_items], False
    high_velocity_paths = survey_summary.get("high_velocity") or []
    return [(p, None) for p in high_velocity_paths[:15]], True


def generate_CODEBASE_md(
    repo_root: Path,
    artifacts_dir: Path,
    *,
    trace: CartographyTraceLogger | None = None,
) -> Path:
    """
    Generate the living context file optimized for agent prompt injection.
    """
    modules = _modules_from_artifacts(artifacts_dir)
    module_graph = _read_json(artifacts_dir / "module_graph.json") or {}
    lineage_graph = _read_json(artifacts_dir / "lineage_graph.json") or {}
    git_velocity = _read_json(artifacts_dir / "git_velocity.json") or {}

    survey_summary = _read_json(artifacts_dir / "survey_summary.json") or {}
    top_modules = _top_modules_by_pagerank(modules, n=5)
    sources, sinks = _data_sources_and_sinks(lineage_graph)
    circular_deps, doc_drift = _known_debt(modules, module_graph)
    doc_drift = sorted(dict.fromkeys(doc_drift + _doc_drift_from_semantic_index(artifacts_dir)))
    high_velocity_list, velocity_from_survey = _high_velocity_for_codebase(git_velocity, survey_summary)
    purpose_map = _purpose_map_from_semantic_index(artifacts_dir)
    module_purposes = sorted(
        [
            (
                str(m.get("path") or ""),
                purpose_map.get(str(m.get("path") or ""), str(m.get("purpose_statement") or "").strip())
                or "No purpose statement yet.",
            )
            for m in modules
            if str(m.get("path") or "").strip()
        ],
        key=lambda it: it[0],
    )
    top_paths = [str(m.get("path") or "") for m in top_modules]
    architecture_overview = _synthesize_architecture_overview(
        repo_root,
        survey_summary,
        top_paths,
        sources,
        sinks,
        len(modules),
    )

    repo_name = _repo_display_name(repo_root)
    lines: list[str] = []
    lines.append(f"<!-- cartography_codebase_schema={CODEBASE_SCHEMA_VERSION} -->")
    lines.append("# CODEBASE")
    lines.append("")
    lines.append(f"**Repository:** {repo_name}")
    lines.append("")
    lines.append("## Architecture Overview")
    lines.append(architecture_overview)
    lines.append("")
    lines.append("## Critical Path")
    for idx, m in enumerate(top_modules, start=1):
        p = str(m.get("path") or "")
        lines.append(f"- {idx}. `{_short_path(p, repo_root)}` (pagerank={float(m.get('pagerank') or 0.0):.6f})")
    if not top_modules:
        lines.append("- No modules available.")
    lines.append("")
    lines.append("## Data Sources & Sinks")
    lines.append("- **Sources**")
    if sources:
        for s in sources[:15]:
            lines.append(f"  - `{_shorten_lineage_id(s, repo_root)}`")
    else:
        lines.append("  - None detected.")
    lines.append("- **Sinks**")
    if sinks:
        for s in sinks[:15]:
            lines.append(f"  - `{_shorten_lineage_id(s, repo_root)}`")
    else:
        lines.append("  - None detected.")
    lines.append("")
    lines.append("## Known Debt")
    lines.append("- **Circular Dependencies**")
    if circular_deps:
        for comp in circular_deps[:10]:
            lines.append(f"  - {', '.join(f'`{_short_path(str(p), repo_root)}`' for p in comp)}")
    else:
        lines.append("  - None detected in this repository.")
    lines.append("- **Doc Drift Flags**")
    if doc_drift:
        for path in doc_drift[:20]:
            lines.append(f"  - `{_short_path(path, repo_root)}`")
    else:
        lines.append("  - None flagged in this repository.")
    lines.append("")
    lines.append("## High-Velocity Files")
    if high_velocity_list:
        for path, count in high_velocity_list:
            short = _short_path(path, repo_root)
            if count is not None:
                lines.append(f"- `{short}` ({int(count)} commits/30d)")
            else:
                lines.append(f"- `{short}` (high-velocity from survey; no git history for counts)")
        if velocity_from_survey:
            lines.append("")
            lines.append("_(Git commit counts unavailable — shallow clone or no history; list from structural/survey data.)_")
    else:
        lines.append("- No git velocity data available for this repository.")
    lines.append("")
    lines.append("## Recent Change Velocity")
    per_file = git_velocity.get("per_file") or {}
    if per_file:
        lines.append(
            f"- Window: last {int(git_velocity.get('days') or 30)} days across {len(per_file)} files with commit activity in this repository."
        )
    else:
        n_high = len(high_velocity_list)
        lines.append(
            f"- Window: last {int(git_velocity.get('days') or 30)} days; {n_high} high-velocity files from structural analysis of this repository (git history unavailable for commit counts)."
        )
    lines.append("")
    lines.append("## Module Purpose Index")
    for path, purpose in module_purposes:
        lines.append(f"- `{_short_path(path, repo_root)}`: {purpose}")
    if not module_purposes:
        lines.append("- No module purposes available.")

    out_path = artifacts_dir / "CODEBASE.md"
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    if trace:
        trace.log(
            "generate_CODEBASE_md",
            confidence=0.92,
            method="static+llm",
            evidence=[
                {"source_file": "module_graph.json", "line_range": [1, _line_count(artifacts_dir / "module_graph.json")]},
                {"source_file": "lineage_graph.json", "line_range": [1, _line_count(artifacts_dir / "lineage_graph.json")]},
                {"source_file": "git_velocity.json", "line_range": [1, _line_count(artifacts_dir / "git_velocity.json")]},
            ],
            details={"output": str(out_path)},
        )
    return out_path


def generate_onboarding_brief_md(
    artifacts_dir: Path,
    *,
    repo_root: Path | None = None,
    trace: CartographyTraceLogger | None = None,
) -> Path:
    """
    Build day-one onboarding brief from artifact-derived evidence only.
    Always uses evidence-based answers (lineage + survey) so answers and citations are accurate and traceable.
    """
    answers = _heuristic_onboarding_answers(artifacts_dir, repo_root=repo_root)

    lines = ["# Day-One Onboarding Brief", ""]
    if repo_root is not None:
        repo_name = _repo_display_name(repo_root)
        lines.append(f"**Repository:** {repo_name}")
        lines.append("")
    lines.append("## The Five FDE Day-One Questions")
    lines.append("")
    for item in answers:
        qid = str((item or {}).get("question_id") or "unknown_question")
        qtext = _FDE_QUESTION_TEXT.get(qid, qid)
        answer = str((item or {}).get("answer") or "No answer provided.")
        lines.append(f"### {qtext}")
        lines.append(answer)
        cits = (item or {}).get("citations") or []
        lines.append("")
        lines.append("Evidence (provenance):")
        if cits:
            for c in cits:
                file_ = str((c or {}).get("file") or "")
                line_ = (c or {}).get("line")
                method_ = str((c or {}).get("method") or "artifact").strip()
                file_display = _short_path(file_, repo_root) if repo_root and file_ else file_
                if not file_display:
                    continue
                if line_ is not None:
                    loc = f"`{file_display}:{line_}`"
                else:
                    loc = f"`{file_display}`"
                if method_ and method_ != "artifact":
                    lines.append(f"- {loc} — _source: {method_}_")
                else:
                    lines.append(f"- {loc}")
        else:
            lines.append("- No citation provided.")
        lines.append("")

    # Schema tag for programmatic detection (same version as trace).
    brief_lines = [f"<!-- cartography_onboarding_schema={TRACE_SCHEMA_VERSION} -->", ""] + lines
    out_path = artifacts_dir / "onboarding_brief.md"
    out_path.write_text("\n".join(brief_lines).strip() + "\n", encoding="utf-8")
    if trace:
        trace.log(
            "generate_onboarding_brief",
            confidence=0.86,
            method="llm_inference",
            evidence=[
                {"source_file": "day_one_answers.json", "line_range": [1, _line_count(artifacts_dir / "day_one_answers.json")]}
            ],
            details={"output": str(out_path)},
        )
    return out_path


def build_semantic_index(
    artifacts_dir: Path,
    *,
    trace: CartographyTraceLogger | None = None,
) -> Path:
    """
    Build a local semantic index from module purpose statements.
    Prefer semantic_index/modules.json (Semanticist output); fallback to root modules with purpose.
    """
    semantic_dir = artifacts_dir / "semantic_index"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    path_purpose_pairs: list[tuple[str, str]] = []
    semantic_modules = _read_json(artifacts_dir / "semantic_index" / "modules.json")
    if isinstance(semantic_modules, list) and semantic_modules:
        for entry in semantic_modules:
            if not isinstance(entry, dict):
                continue
            path = str((entry.get("module_name") or entry.get("path")) or "").strip()
            purpose = str((entry.get("purpose_statement") or entry.get("purpose")) or "").strip()
            if path and purpose:
                path_purpose_pairs.append((path, purpose))
    if not path_purpose_pairs:
        modules = _modules_from_artifacts(artifacts_dir)
        for m in modules:
            path = str((m or {}).get("path") or "").strip()
            purpose = str((m or {}).get("purpose_statement") or "").strip()
            if path and purpose:
                path_purpose_pairs.append((path, purpose))
    try:
        from src.llm.embedding import EmbeddingCache

        cache = EmbeddingCache(cache_dir=artifacts_dir / "embedding_cache")
    except Exception:
        cache = None
    records: list[dict[str, Any]] = []
    for path, purpose in path_purpose_pairs:
        vector = cache.embed(purpose) if cache is not None else []
        records.append(
            {
                "path": path,
                "purpose_statement": purpose,
                "vector": vector,
                "method": "llm_inference",
            }
        )

    index_path = semantic_dir / "purpose_vectors.jsonl"
    with index_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")

    manifest = {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "record_count": len(records),
        "index_file": "purpose_vectors.jsonl",
    }
    (semantic_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if trace:
        trace.log(
            "build_semantic_index",
            confidence=0.9 if records else 0.6,
            method="llm_inference",
            evidence=[
                {"source_file": "module_graph.json", "line_range": [1, _line_count(artifacts_dir / "module_graph.json")]},
            ],
            details={"records": len(records), "output": str(index_path)},
        )
    return semantic_dir


def run_archivist(
    repo_root: Path,
    artifacts_dir: Path | None = None,
    *,
    changed_files: list[str] | None = None,
) -> dict[str, str]:
    """
    Run Archivist artifact generation and trace logging.
    """
    repo_root = Path(repo_root).resolve()
    artifacts_dir = (artifacts_dir or (repo_root / ".cartography")).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    trace = CartographyTraceLogger(trace_path=artifacts_dir / "cartography_trace.jsonl", agent="archivist")
    trace.log(
        "start",
        confidence=1.0,
        method="static",
        details={
            "repo_root": str(repo_root),
            "incremental": bool(changed_files),
            "changed_files_count": len(changed_files or []),
        },
    )

    codebase_path = generate_CODEBASE_md(repo_root, artifacts_dir, trace=trace)
    onboarding_path = generate_onboarding_brief_md(artifacts_dir, repo_root=repo_root, trace=trace)
    semantic_dir = build_semantic_index(artifacts_dir, trace=trace)

    trace.log(
        "complete",
        confidence=1.0,
        method="static",
        details={
            "CODEBASE.md": str(codebase_path),
            "onboarding_brief.md": str(onboarding_path),
            "semantic_index": str(semantic_dir),
            "lineage_graph.json": str(artifacts_dir / "lineage_graph.json"),
        },
    )
    return {
        "codebase": str(codebase_path),
        "onboarding_brief": str(onboarding_path),
        "semantic_index": str(semantic_dir),
        "trace": str(artifacts_dir / "cartography_trace.jsonl"),
    }

