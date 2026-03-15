"""
Phase 3: Semanticist Agent — LLM-powered purpose statements, domain clustering, Day-One answers.
Uses tiered LLM (semantic_bulk / semantic_synthesis), ContextWindowBudget, and graceful degradation.
"""
from __future__ import annotations

import json
import logging
import os
import re
import hashlib
import time
from pathlib import Path
from typing import Any, Optional

from src.models.module import ModuleNode
from src.models.semanticist import (
    PurposeResult,
    DomainArchitectureMap,
    DayOneAnswer,
    DayOneOutput,
)
from src.llm.config import get_semantic_config

logger = logging.getLogger(__name__)

# Prompt template: code only, no docstring (docstring used only for comparison after)
# Tightened for consistent output: business/functional intent only, no implementation detail.
PURPOSE_PROMPT_TEMPLATE = """You are a semantic code analyst. From the module source below, output exactly one purpose statement (1-2 sentences) describing what this module does from a business or functional perspective. Do not describe implementation details, file structure, or code patterns. Output only the purpose statement, no prefix or JSON.

Code:
"""

# Default chars-per-token heuristic when tiktoken not used
CHARS_PER_TOKEN = 4
MAX_BULK_PROMPT_CHARS = 16000
DEFAULT_BATCH_SIZE = 8
SEMANTIC_INDEX_DIRNAME = "semantic_index"
FDE_DAY_ONE_QUESTION_IDS = [
    "fde_q1_business_capability",
    "fde_q2_key_data_flow",
    "fde_q3_change_risk",
    "fde_q4_operational_hotspots",
    "fde_q5_first_90_days",
]


def _semantic_mode() -> str:
    """Semantic mode: 'llm' (default) or 'deterministic'."""
    raw = (os.environ.get("SEMANTIC_MODE") or "llm").strip().lower()
    return "deterministic" if raw in {"deterministic", "fallback", "heuristic", "none"} else "llm"


def _is_ollama_oom_error(exc: Exception) -> bool:
    """Detect Ollama 'insufficient memory' server errors."""
    try:
        import httpx

        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            text = (exc.response.text or "").lower()
            return "requires more system memory" in text or "not enough memory" in text
    except Exception:
        return False
    return False


def _timeout_seconds_from_env(var_name: str, default_seconds: float) -> float:
    """Parse timeout seconds from env; fall back to default when unset/invalid."""
    raw = (os.environ.get(var_name) or "").strip()
    if not raw:
        return default_seconds
    try:
        parsed = float(raw)
        return parsed if parsed > 0 else default_seconds
    except Exception:
        return default_seconds


def _openrouter_headers(cfg: Any) -> dict[str, str]:
    """Build OpenRouter auth headers from config/env."""
    api_key = (cfg.openrouter_api_key or "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required when using openrouter provider")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    site_url = (os.environ.get("OPENROUTER_SITE_URL") or "").strip()
    app_name = (os.environ.get("OPENROUTER_APP_NAME") or "Brownfield Cartographer").strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers


def _extract_openrouter_text(payload: dict[str, Any]) -> str:
    """Extract text from OpenRouter chat completion response."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(parts).strip()
    return ""


def _call_openrouter_chat(
    prompt: str,
    model_id: str,
    *,
    timeout_seconds: float,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call OpenRouter chat-completions endpoint with retries."""
    import httpx

    cfg = get_semantic_config()
    url = f"{cfg.openrouter_base_url}/chat/completions"
    headers = _openrouter_headers(cfg)
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                return _extract_openrouter_text(data)
            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code if e.response is not None else 0
                if status >= 500 and attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
    return ""


class ContextWindowBudget:
    """
    Tracks token usage per run; estimates tokens before each LLM call;
    supports optional caps and truncation of module code for bulk phase.
    """
    def __init__(
        self,
        cap_total: Optional[int] = None,
        cap_bulk_phase: Optional[int] = None,
        truncate_lines: int = 500,
    ):
        self.cumulative_input_tokens: int = 0
        self.cumulative_output_tokens: int = 0
        self.cap_total = cap_total
        self.cap_bulk_phase = cap_bulk_phase
        self.truncate_lines = truncate_lines

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (heuristic: len/4). Tiktoken can be wired later."""
        if not text:
            return 0
        return max(0, len(text) // CHARS_PER_TOKEN)

    def consume_input_tokens(self, n: int) -> None:
        """Record n input tokens and optionally log cap warning."""
        self.cumulative_input_tokens += n
        if self.cap_total and self.cumulative_input_tokens >= self.cap_total * 80 // 100:
            logger.warning(
                "ContextWindowBudget: cumulative input tokens %s approaches cap_total %s",
                self.cumulative_input_tokens,
                self.cap_total,
            )
        if self.cap_total and self.cumulative_input_tokens >= self.cap_total:
            logger.warning(
                "ContextWindowBudget: cumulative input tokens %s >= cap_total %s",
                self.cumulative_input_tokens,
                self.cap_total,
            )

    def consume_output_tokens(self, n: int) -> None:
        """Record n output tokens (used for rough run-cost accounting)."""
        self.cumulative_output_tokens += max(0, n)

    def truncate_module_code(self, code: str, max_lines: Optional[int] = None) -> str:
        """Return first max_lines lines of code (for bulk phase when over budget)."""
        n = max_lines if max_lines is not None else self.truncate_lines
        lines = code.splitlines()
        if len(lines) <= n:
            return code
        truncated = "\n".join(lines[:n])
        logger.info("ContextWindowBudget: truncated module code to first %s lines", n)
        return truncated


def _make_budget() -> ContextWindowBudget:
    """Build ContextWindowBudget from env config; used by run_semanticist so every LLM call can estimate and track tokens."""
    cfg = get_semantic_config()
    return ContextWindowBudget(
        cap_total=cfg.budget_cap_total,
        cap_bulk_phase=cfg.budget_cap_bulk,
        truncate_lines=cfg.truncate_lines,
    )


def run_semanticist(
    repo_root: Path,
    artifacts_dir: Optional[Path] = None,
    modules: Optional[list[ModuleNode]] = None,
    changed_files: Optional[list[str]] = None,
) -> tuple[list[ModuleNode], dict[str, Any], list[Any]]:
    """
    Run Semanticist: purpose statements, domain clustering, Day-One answers.
    Uses ContextWindowBudget for token estimation and cumulative tracking on every LLM call.
    Returns (enriched_modules, domain_architecture_map_dict, day_one_answers_list).
    """
    repo_root = Path(repo_root)
    artifacts_dir = artifacts_dir or repo_root / ".cartography"
    mode = _semantic_mode()
    budget = _make_budget()
    run_started = time.perf_counter()
    logger.info(
        "semanticist: loading semantic inputs from %s and %s",
        artifacts_dir / "module_graph.json",
        artifacts_dir / "lineage_graph.json",
    )
    input_hash = _hash_inputs(
        [
            artifacts_dir / "modules.json",
            artifacts_dir / "module_graph.json",
            artifacts_dir / "lineage_graph.json",
            artifacts_dir / "survey_summary.json",
        ],
        mode=mode,
        model_hint=f"{get_semantic_config().bulk_model_id}:{get_semantic_config().synthesis_model_id}",
    )
    cached = _load_cached_semantic_outputs(artifacts_dir, input_hash)
    if cached is not None:
        logger.info("semanticist: input artifacts unchanged; reusing cached semantic_index outputs")
        return cached
    # Load modules from artifacts if not provided
    if modules is None:
        modules = _load_modules_from_artifacts(artifacts_dir)
    if not modules:
        logger.info("semanticist: no modules found; skipping")
        return [], {"module_to_domain": {}, "cluster_to_domain": {}, "skipped_modules": []}, []
    _enrich_modules_with_purpose(
        repo_root,
        artifacts_dir,
        modules,
        budget,
        changed_files=changed_files,
    )
    summaries = _build_semantic_summaries(modules, artifacts_dir)
    (_semantic_index_dir(artifacts_dir) / "module_summaries.json").write_text(
        json.dumps(summaries, indent=2),
        encoding="utf-8",
    )
    from src.agents.semanticist_cluster import cluster_into_domains

    domain_map_model: DomainArchitectureMap = cluster_into_domains(modules)
    _write_domain_architecture_map(artifacts_dir, domain_map_model.model_dump(mode="json"))
    _write_enriched_modules(artifacts_dir, modules)
    # Day-One synthesis (may fail gracefully)
    day_one_answers: list[DayOneAnswer] = answer_day_one_questions(
        artifacts_dir,
        budget=budget,
        use_llm=(mode == "llm"),
    )
    _write_semantic_modules_json(artifacts_dir, modules)
    day_one_dump = [a.model_dump(mode="json") for a in day_one_answers]
    summary_stats = _compute_semantic_summary_stats(
        modules,
        domain_map_model.model_dump(mode="json"),
    )
    _write_semantic_index_outputs(
        artifacts_dir,
        modules=modules,
        domains=domain_map_model.model_dump(mode="json"),
        day_one=day_one_dump,
        input_hash=input_hash,
        mode=mode,
        summary_stats=summary_stats,
    )
    if summary_stats:
        logger.info(
            "semanticist: summary_stats drift_rate=%.2f%% ambiguous=%d clusters=%d coherence_avg=%.1f",
            (summary_stats.get("drift_rate") or 0) * 100,
            summary_stats.get("ambiguous_count", 0),
            summary_stats.get("cluster_count", 0),
            summary_stats.get("cluster_coherence_avg_size", 0),
        )
    logger.info(
        "semanticist: completed in %.1fs (modules=%d answers=%d input_tokens=%d output_tokens=%d)",
        time.perf_counter() - run_started,
        len(modules),
        len(day_one_answers),
        budget.cumulative_input_tokens,
        budget.cumulative_output_tokens,
    )
    return modules, domain_map_model.model_dump(mode="json"), [
        a.model_dump(mode="json") for a in day_one_answers
    ]


def _call_llm_bulk(prompt: str) -> str:
    """Call semantic_bulk LLM with provider-specific backend."""
    import httpx
    cfg = get_semantic_config()
    provider = (cfg.bulk_provider or "").strip().lower()
    bulk_fallback_model = (os.environ.get("SEMANTIC_BULK_FALLBACK_MODEL") or "").strip()
    bulk_timeout_seconds = _timeout_seconds_from_env("SEMANTIC_BULK_TIMEOUT_SECONDS", 3600.0)
    ollama_num_ctx = int((os.environ.get("SEMANTIC_OLLAMA_NUM_CTX") or "2048").strip() or "2048")
    ollama_num_thread = int((os.environ.get("SEMANTIC_OLLAMA_NUM_THREAD") or "0").strip() or "0")

    if provider == "openrouter":
        return _call_openrouter_chat(
            prompt,
            cfg.bulk_model_id,
            timeout_seconds=bulk_timeout_seconds,
            temperature=0.2,
            max_tokens=220,
        )
    if provider != "ollama":
        raise ValueError(f"Unsupported semantic_bulk provider: {cfg.bulk_provider}")

    url = f"{cfg.ollama_base_url}/api/generate"

    def _request_with_model(client: httpx.Client, model_id: str) -> str:
        options: dict[str, Any] = {"temperature": 0.2, "num_predict": 180, "num_ctx": ollama_num_ctx}
        if ollama_num_thread > 0:
            options["num_thread"] = ollama_num_thread
        body = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            # Keep completions concise and reduce generation load.
            "options": options,
        }
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = client.post(url, json=body)
                resp.raise_for_status()
                data = resp.json()
                return (data.get("response") or "").strip()
            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code if e.response is not None else 0
                if status >= 500 and attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
        return ""

    with httpx.Client(timeout=bulk_timeout_seconds) as client:
        try:
            return _request_with_model(client, cfg.bulk_model_id)
        except Exception as e:
            if bulk_fallback_model and _is_ollama_oom_error(e):
                logger.warning(
                    "semantic_bulk model '%s' OOM; retrying with fallback model '%s'",
                    cfg.bulk_model_id,
                    bulk_fallback_model,
                )
                return _request_with_model(client, bulk_fallback_model)
            raise
    return ""


def _call_llm_synthesis(prompt: str) -> str:
    """Call semantic_synthesis LLM with provider-specific backend."""
    import httpx

    cfg = get_semantic_config()
    provider = (cfg.synthesis_provider or "").strip().lower()
    synthesis_fallback_model = (os.environ.get("SEMANTIC_SYNTHESIS_FALLBACK_MODEL") or "").strip()
    synthesis_timeout_seconds = _timeout_seconds_from_env("SEMANTIC_SYNTHESIS_TIMEOUT_SECONDS", 3600.0)
    ollama_num_ctx = int((os.environ.get("SEMANTIC_OLLAMA_NUM_CTX") or "2048").strip() or "2048")
    ollama_num_thread = int((os.environ.get("SEMANTIC_OLLAMA_NUM_THREAD") or "0").strip() or "0")

    if provider == "openrouter":
        return _call_openrouter_chat(
            prompt,
            cfg.synthesis_model_id,
            timeout_seconds=synthesis_timeout_seconds,
            temperature=0.15,
            max_tokens=1200,
        )
    if provider != "ollama":
        raise ValueError(f"Unsupported semantic_synthesis provider: {cfg.synthesis_provider}")

    url = f"{cfg.ollama_base_url}/api/generate"

    def _request_with_model(client: httpx.Client, model_id: str) -> str:
        options: dict[str, Any] = {"temperature": 0.2, "num_predict": 800, "num_ctx": ollama_num_ctx}
        if ollama_num_thread > 0:
            options["num_thread"] = ollama_num_thread
        body = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        resp = client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("response") or "").strip()

    with httpx.Client(timeout=synthesis_timeout_seconds) as client:
        try:
            return _request_with_model(client, cfg.synthesis_model_id)
        except Exception as e:
            if synthesis_fallback_model and _is_ollama_oom_error(e):
                logger.warning(
                    "semantic_synthesis model '%s' OOM; retrying with fallback model '%s'",
                    cfg.synthesis_model_id,
                    synthesis_fallback_model,
                )
                return _request_with_model(client, synthesis_fallback_model)
            raise


def _docstring_contradicts(purpose: str, docstring: str) -> bool:
    """Simple heuristic: if docstring and purpose share few significant words, treat as contradiction."""
    if not purpose or not docstring:
        return False
    a = set(p.lower() for p in purpose.split() if len(p) > 2)
    b = set(d.lower() for d in docstring.split() if len(d) > 2)
    if not a or not b:
        return False
    # Low overlap of docstring words in purpose => likely different topic
    overlap = len(a & b) / min(len(a), len(b))
    return overlap < 0.5


def generate_purpose_statement(
    module_node: ModuleNode,
    code_slice: str,
    docstring: Optional[str] = None,
    budget: Optional[ContextWindowBudget] = None,
) -> Optional[PurposeResult]:
    """
    Generate a 2-3 sentence purpose statement from module code (not docstring).
    Compare to docstring and set documentation_drift if they contradict; store both for traceability.
    On LLM failure, return None (caller skips module).
    """
    try:
        # Always enforce per-call truncation to avoid oversized prompts causing Ollama 500s.
        safe_code = code_slice or ""
        if budget:
            safe_code = budget.truncate_module_code(safe_code, max_lines=budget.truncate_lines)
        if len(safe_code) > MAX_BULK_PROMPT_CHARS:
            safe_code = safe_code[:MAX_BULK_PROMPT_CHARS]
            logger.info(
                "generate_purpose_statement: truncated code chars to %s for %s",
                MAX_BULK_PROMPT_CHARS,
                getattr(module_node, "path", "?"),
            )
        prompt = PURPOSE_PROMPT_TEMPLATE + safe_code
        response = _call_llm_bulk(prompt)
    except Exception as e:
        logger.warning("generate_purpose_statement failed for %s: %s", getattr(module_node, "path", "?"), e)
        return None
    if budget:
        budget.consume_input_tokens(budget.estimate_tokens(prompt))
        budget.consume_output_tokens(budget.estimate_tokens(response or ""))
    purpose_statement = (response or "").strip() or "No determinable purpose."
    documentation_drift = False
    docstring_snippet = None
    if docstring and docstring.strip():
        documentation_drift = _docstring_contradicts(purpose_statement, docstring)
        docstring_snippet = docstring[:2000] if documentation_drift else None  # store for traceability
    return PurposeResult(
        purpose_statement=purpose_statement,
        documentation_drift=documentation_drift,
        docstring_snippet=docstring_snippet,
    )


def _extract_docstring_from_code(code: str) -> Optional[str]:
    """Extract first module-level docstring (triple-quoted string) from code."""
    if not code or not code.strip():
        return None
    s = code.strip()
    for quote in ('"""', "'''"):
        if s.startswith(quote):
            end = s.find(quote, len(quote))
            if end != -1:
                return s[len(quote):end].strip()
    return None


def _read_module_source(repo_root: Path, module_path: str) -> tuple[str, Optional[str]]:
    """Read module file; return (full_code, docstring_or_none)."""
    full_path = repo_root / module_path
    if not full_path.exists():
        return "", None
    try:
        code = full_path.read_text(encoding="utf-8", errors="replace")
        return code, _extract_docstring_from_code(code)
    except Exception as e:
        logger.warning("Failed to read %s: %s", full_path, e)
        return "", None


def _load_modules_from_artifacts(artifacts_dir: Path) -> list[ModuleNode]:
    """Load ModuleNode list with module_graph.json as primary source, modules.json as fallback."""
    graph_path = artifacts_dir / "module_graph.json"
    if graph_path.exists():
        try:
            raw_graph = json.loads(graph_path.read_text(encoding="utf-8"))
            nodes = raw_graph.get("nodes") or []
            modules = []
            for node in nodes:
                if str((node or {}).get("type") or "").lower() == "module":
                    modules.append(ModuleNode.model_validate(node))
            if modules:
                return modules
        except Exception as e:
            logger.warning("Failed to load modules from %s: %s", graph_path, e)
    path = artifacts_dir / "modules.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [ModuleNode.model_validate(item) for item in raw]
    except Exception as e:
        logger.warning("Failed to load modules from %s: %s", path, e)
        return []


def _extract_signature_lines(code: str, max_lines: int = 80) -> list[str]:
    lines: list[str] = []
    for line in code.splitlines():
        s = line.strip()
        if s.startswith("def ") or s.startswith("async def ") or s.startswith("class "):
            lines.append(s[:220])
            if len(lines) >= max_lines:
                break
    return lines


def _extract_critical_lines(code: str, max_lines: int = 30) -> list[str]:
    keywords = (
        "select ",
        "insert ",
        "update ",
        "delete ",
        "merge ",
        "http",
        "requests.",
        "spark",
        "pandas",
        "read_",
        "write_",
        "dag",
        "airflow",
    )
    lines: list[str] = []
    for line in code.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        low = s.lower()
        if any(k in low for k in keywords):
            lines.append(s[:220])
            if len(lines) >= max_lines:
                break
    return lines


def _lineage_hints_by_source_file(artifacts_dir: Path) -> dict[str, list[str]]:
    lineage_path = artifacts_dir / "lineage_graph.json"
    if not lineage_path.exists():
        return {}
    try:
        raw = json.loads(lineage_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    hints: dict[str, list[str]] = {}
    for edge in raw.get("edges") or []:
        source_file = str((edge or {}).get("source_file") or "").strip()
        if not source_file:
            continue
        edge_type = str((edge or {}).get("edge_type") or "")
        src = str((edge or {}).get("source") or "")
        tgt = str((edge or {}).get("target") or "")
        if edge_type and src and tgt:
            hints.setdefault(source_file, []).append(f"{edge_type}:{src}->{tgt}")
    return hints


def _build_semantic_summaries(
    modules: list[ModuleNode],
    artifacts_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Build per-module semantic summaries from Surveyor nodes + lineage context."""
    lineage_ctx_map = _lineage_context_by_module(artifacts_dir)
    out: dict[str, dict[str, Any]] = {}
    for m in modules:
        out[m.path] = {
            "module_path": m.path,
            "imports": [imp.raw for imp in (m.imports or [])[:25]],
            "exported_functions": [f.name for f in (m.public_functions or [])[:40]],
            "classes": [c.name for c in (m.classes or [])[:30]],
            "complexity_score": m.complexity_score,
            "api_surface_count": len(m.public_functions or []) + len(m.classes or []),
            "lineage": lineage_ctx_map.get(m.path, {"upstream": [], "downstream": [], "transformation_types": []}),
        }
    return out


def _module_graph_context_by_module(artifacts_dir: Path) -> dict[str, dict[str, list[str]]]:
    raw = _load_json_if_exists(artifacts_dir / "module_graph.json") or {}
    edges = raw.get("edges") or []
    parents: dict[str, set[str]] = {}
    deps: dict[str, set[str]] = {}
    for e in edges:
        src = str((e or {}).get("source_module") or (e or {}).get("source") or "").strip()
        tgt = str((e or {}).get("target_module") or (e or {}).get("target") or "").strip()
        if not src or not tgt:
            continue
        deps.setdefault(src, set()).add(tgt)
        parents.setdefault(tgt, set()).add(src)
    out: dict[str, dict[str, list[str]]] = {}
    all_nodes = set(parents) | set(deps)
    for m in all_nodes:
        pkg = m.split("/")[0] if "/" in m else m.split(".")[0]
        shared = sorted(
            [
                n
                for n in all_nodes
                if n != m and ((n.split("/")[0] if "/" in n else n.split(".")[0]) == pkg)
            ]
        )[:6]
        out[m] = {
            "parents": sorted(parents.get(m, set()))[:10],
            "dependencies": sorted(deps.get(m, set()))[:10],
            "shared_packages": shared,
        }
    return out


def _lineage_context_by_module(artifacts_dir: Path) -> dict[str, dict[str, list[str]]]:
    raw = _load_json_if_exists(artifacts_dir / "lineage_graph.json") or {}
    edges = raw.get("edges") or []
    out: dict[str, dict[str, set[str]]] = {}
    for e in edges:
        source_file = str((e or {}).get("source_file") or "").strip()
        if not source_file:
            continue
        src = str((e or {}).get("source") or "").strip()
        tgt = str((e or {}).get("target") or "").strip()
        edge_type = str((e or {}).get("edge_type") or "").strip()
        bucket = out.setdefault(source_file, {"upstream": set(), "downstream": set(), "transformation_types": set()})
        if edge_type == "CONSUMES" and src:
            bucket["upstream"].add(src)
        if edge_type == "PRODUCES" and tgt:
            bucket["downstream"].add(tgt)
        if (e or {}).get("transformation_type"):
            bucket["transformation_types"].add(str((e or {}).get("transformation_type")))
    normalized: dict[str, dict[str, list[str]]] = {}
    for k, v in out.items():
        normalized[k] = {
            "upstream": sorted(v["upstream"])[:20],
            "downstream": sorted(v["downstream"])[:20],
            "transformation_types": sorted(v["transformation_types"])[:10],
        }
    return normalized


def _compressed_module_context(
    module: ModuleNode,
    code: str,
    lineage_hints: list[str],
    module_graph_ctx: dict[str, list[str]] | None = None,
    lineage_ctx: dict[str, list[str]] | None = None,
) -> str:
    imports = [imp.raw.strip() for imp in (module.imports or [])[:20]]
    funcs = [f.name for f in (module.public_functions or [])[:40]]
    classes = [c.name for c in (module.classes or [])[:30]]
    signatures = _extract_signature_lines(code, max_lines=120)
    critical = _extract_critical_lines(code, max_lines=40)
    tables = [t for t in (module.tables_referenced or [])[:30]]
    keys = [k for k in (module.structural_keys or [])[:30]]
    lines = [f"MODULE: {module.path}", f"LANGUAGE: {module.language}"]
    lines.append("IMPORTS:")
    lines.extend([f"- {i}" for i in imports] if imports else ["- (none)"])
    lines.append("PUBLIC_FUNCTIONS:")
    lines.extend([f"- {f}" for f in funcs] if funcs else ["- (none)"])
    lines.append("CLASSES:")
    lines.extend([f"- {c}" for c in classes] if classes else ["- (none)"])
    lines.append("SIGNATURE_SKELETON:")
    lines.extend([f"- {s}" for s in signatures] if signatures else ["- (none)"])
    lines.append("CRITICAL_OPERATIONS:")
    lines.extend([f"- {c}" for c in critical] if critical else ["- (none)"])
    if tables:
        lines.extend(["TABLES_REFERENCED:", *[f"- {t}" for t in tables]])
    if keys:
        lines.extend(["STRUCTURAL_KEYS:", *[f"- {k}" for k in keys]])
    if lineage_hints:
        lines.extend(["LINEAGE_HINTS:", *[f"- {h}" for h in lineage_hints[:20]]])
    if module_graph_ctx:
        if module_graph_ctx.get("parents"):
            lines.extend(["GRAPH_PARENTS:", *[f"- {p}" for p in module_graph_ctx.get("parents", [])[:10]]])
        if module_graph_ctx.get("dependencies"):
            lines.extend(["GRAPH_DEPENDENCIES:", *[f"- {d}" for d in module_graph_ctx.get("dependencies", [])[:10]]])
        if module_graph_ctx.get("shared_packages"):
            lines.extend(["GRAPH_SHARED_PACKAGES:", *[f"- {d}" for d in module_graph_ctx.get("shared_packages", [])[:6]]])
        lines.append(f"API_EXPOSURE_COUNT: {len(module.public_functions or []) + len(module.classes or [])}")
        if module.complexity_score is not None:
            lines.append(f"COMPLEXITY_SCORE: {module.complexity_score}")
    if lineage_ctx:
        if lineage_ctx.get("upstream"):
            lines.extend(["DATA_UPSTREAM:", *[f"- {x}" for x in lineage_ctx.get("upstream", [])[:15]]])
        if lineage_ctx.get("downstream"):
            lines.extend(["DATA_DOWNSTREAM:", *[f"- {x}" for x in lineage_ctx.get("downstream", [])[:15]]])
        if lineage_ctx.get("transformation_types"):
            lines.extend(["DATA_TRANSFORMATION_TYPES:", *[f"- {x}" for x in lineage_ctx.get("transformation_types", [])[:8]]])
    return "\n".join(lines)


def _extract_json_from_text(text: str) -> Any:
    s = (text or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    code_block = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", s, flags=re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except Exception:
            return None
    start = min([i for i in (s.find("{"), s.find("[")) if i != -1], default=-1)
    if start >= 0:
        tail = s[start:]
        for end in range(len(tail), 0, -1):
            chunk = tail[:end]
            try:
                return json.loads(chunk)
            except Exception:
                continue
    return None


def _batch_generate_purposes(
    modules: list[ModuleNode],
    contexts: dict[str, str],
    budget: ContextWindowBudget,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[dict[str, str], dict[str, Optional[bool]]]:
    def _extract_row(row: Any) -> tuple[str, str]:
        """Best-effort row extractor for varied small-model JSON outputs."""
        if isinstance(row, dict):
            module_name = str(
                row.get("module_name")
                or row.get("module")
                or row.get("path")
                or row.get("file")
                or ""
            ).strip()
            purpose = str(
                row.get("purpose_statement")
                or row.get("purpose")
                or row.get("summary")
                or ""
            ).strip()
            return module_name, purpose
        if isinstance(row, str):
            # Accept compact "path: purpose" rows.
            if ":" in row:
                left, right = row.split(":", 1)
                return left.strip(), right.strip()
        return "", ""

    out: dict[str, str] = {}
    doc_match: dict[str, Optional[bool]] = {}
    if not modules:
        return out, doc_match
    for i in range(0, len(modules), max(1, batch_size)):
        batch = modules[i : i + max(1, batch_size)]
        sections: list[str] = []
        for m in batch:
            ctx = contexts.get(m.path, "")
            if len(ctx) > MAX_BULK_PROMPT_CHARS:
                ctx = ctx[:MAX_BULK_PROMPT_CHARS]
            sections.append(f"### {m.path}\n{ctx}")
        prompt = (
            "You are a semantic code analyst. For each module below return valid JSON only, no other text.\n"
            "Required shape: {\"results\": [{\"module_name\": \"<exact path>\", \"purpose_statement\": \"<1-2 sentences, business/functional intent only>\", \"docstring_match\": true|false|null}]}\n"
            "Rules: purpose_statement must describe what the module does, not how; one entry per module in order; docstring_match is true if module docstring aligns with purpose, false if they contradict.\n\n"
            + "\n\n".join(sections)
        )
        budget.consume_input_tokens(budget.estimate_tokens(prompt))
        try:
            raw = _call_llm_bulk(prompt)
            budget.consume_output_tokens(budget.estimate_tokens(raw or ""))
            parsed = _extract_json_from_text(raw)
            rows = []
            if isinstance(parsed, dict):
                maybe_rows = parsed.get("results")
                if isinstance(maybe_rows, list):
                    rows = maybe_rows
                elif isinstance(maybe_rows, dict):
                    # Some models return {"results": {"path": "purpose", ...}}
                    rows = [{"module_name": k, "purpose_statement": v} for k, v in maybe_rows.items()]
                else:
                    # Alternate dict response shape: {"path": "...", "purpose_statement": "..."}
                    rows = [parsed]
            elif isinstance(parsed, list):
                rows = parsed
            for row in rows:
                module_name, purpose = _extract_row(row)
                if module_name and purpose:
                    out[module_name] = purpose
                    if isinstance(row, dict):
                        val = row.get("docstring_match")
                        if isinstance(val, bool):
                            doc_match[module_name] = val
                        elif val is None:
                            doc_match[module_name] = None
        except Exception as e:
            logger.warning("semanticist: batched purpose generation failed for batch %d-%d: %s", i, i + len(batch), e)
            continue
    return out, doc_match


def _write_semantic_modules_json(
    artifacts_dir: Path,
    modules: list[ModuleNode],
) -> None:
    payload = []
    for m in modules:
        payload.append(
            {
                "module_name": m.path,
                "purpose_statement": m.purpose_statement,
                "docstring_match": False if m.documentation_drift else True,
                "domain_cluster": m.domain_cluster,
                "optional_day_one_answer": None,
            }
        )
    path = artifacts_dir / "semantic_modules.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _heuristic_purpose(module: ModuleNode) -> str:
    path = (module.path or "").replace("\\", "/").lower()
    terms = [f.name.lower() for f in (module.public_functions or [])[:8]]
    imports = [imp.raw.lower() for imp in (module.imports or [])[:12]]
    corpus = " ".join([path, *terms, *imports])
    if any(k in corpus for k in ("ingest", "extract", "source", "raw", "fetch")):
        return "Performs data ingestion and source acquisition for upstream pipelines."
    if any(k in corpus for k in ("transform", "aggregate", "dbt", "sql", "normalize", "feature")):
        return "Transforms and prepares data for downstream analytics or serving layers."
    if any(k in corpus for k in ("api", "serve", "endpoint", "view", "report")):
        return "Serves application or analytics interfaces over processed data."
    if any(k in corpus for k in ("dag", "workflow", "schedule", "airflow", "orchestr")):
        return "Coordinates workflow orchestration and scheduled execution."
    if any(k in corpus for k in ("monitor", "alert", "metric", "health", "log")):
        return "Monitors system or data quality health and operational signals."
    if module.public_functions:
        names = ", ".join(f.name for f in module.public_functions[:3])
        return f"Implements module logic exposed through public functions ({names})."
    if module.classes:
        names = ", ".join(c.name for c in module.classes[:3])
        return f"Defines core classes ({names}) supporting module behavior."
    return "Provides supporting module-level functionality within the codebase."


def _enrich_modules_with_purpose(
    repo_root: Path,
    artifacts_dir: Path,
    modules: list[ModuleNode],
    budget: ContextWindowBudget,
    changed_files: Optional[list[str]] = None,
) -> None:
    """Per-module purpose generation: full source in LLM mode, heuristics in deterministic mode."""
    mode = _semantic_mode()
    changed_set = {str(Path(p)).replace("\\", "/") for p in (changed_files or [])}
    lineage_hints_map = _lineage_hints_by_source_file(artifacts_dir)
    graph_ctx_map = _module_graph_context_by_module(artifacts_dir)
    lineage_ctx_map = _lineage_context_by_module(artifacts_dir)
    total = len(modules)
    processed = 0
    skipped_unchanged = 0
    selected: list[ModuleNode] = []
    code_by_path: dict[str, str] = {}
    docstring_by_path: dict[str, Optional[str]] = {}
    contexts: dict[str, str] = {}
    for idx, m in enumerate(modules, start=1):
        try:
            if changed_set:
                norm = str(Path(m.path)).replace("\\", "/")
                if norm not in changed_set:
                    # Incremental mode: preserve existing purpose/doc drift for unchanged modules.
                    skipped_unchanged += 1
                    continue
            code, docstring = _read_module_source(repo_root, m.path)
            if not code:
                continue
            if budget.cap_bulk_phase and budget.estimate_tokens(code) + budget.cumulative_input_tokens > budget.cap_bulk_phase:
                code = budget.truncate_module_code(code, max_lines=budget.truncate_lines)
            code_by_path[m.path] = code
            docstring_by_path[m.path] = docstring
            contexts[m.path] = _compressed_module_context(
                m,
                code,
                lineage_hints_map.get(m.path, []),
                module_graph_ctx=graph_ctx_map.get(m.path),
                lineage_ctx=lineage_ctx_map.get(m.path),
            )
            selected.append(m)
        except Exception as e:
            logger.warning("Purpose enrichment failed for %s: %s", m.path, e)
        if idx % 100 == 0 or idx == total:
            logger.info(
                "semanticist: context pass %d/%d (eligible=%d skipped_unchanged=%d)",
                idx,
                total,
                len(selected),
                skipped_unchanged,
            )

    if mode == "deterministic":
        for m in selected:
            m.purpose_statement = _heuristic_purpose(m)
            m.documentation_drift = None
            m.docstring_snippet = None
            processed += 1
        logger.info(
            "semanticist: deterministic mode complete (processed=%d total_selected=%d)",
            processed,
            len(selected),
        )
        return

    for m in selected:
        # LLM mode: use full source (bounded by budget truncation above).
        result = generate_purpose_statement(
            m,
            code_slice=code_by_path.get(m.path, ""),
            docstring=docstring_by_path.get(m.path),
            budget=budget,
        )
        if result is None:
            # If LLM call fails, degrade gracefully to heuristic purpose.
            m.purpose_statement = _heuristic_purpose(m)
            m.documentation_drift = None
            m.docstring_snippet = None
            processed += 1
            continue
        m.purpose_statement = result.purpose_statement
        m.documentation_drift = result.documentation_drift
        m.docstring_snippet = result.docstring_snippet
        processed += 1
    logger.info(
        "semanticist: purpose extraction complete (processed=%d total_selected=%d)",
        processed,
        len(selected),
    )


def _write_enriched_modules(artifacts_dir: Path, modules: list[ModuleNode]) -> None:
    """Write enriched modules (with purpose_statement, documentation_drift, docstring_snippet) to .cartography/modules.json."""
    path = artifacts_dir / "modules.json"
    try:
        payload = [m.model_dump(mode="json") for m in modules]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Wrote %s modules to %s", len(modules), path)
    except Exception as e:
        logger.warning("Failed to write modules to %s: %s", path, e)


def _write_domain_architecture_map(artifacts_dir: Path, domain_map: dict[str, Any]) -> None:
    """Write domain architecture mapping to .cartography/domain_architecture_map.json."""
    path = artifacts_dir / "domain_architecture_map.json"
    try:
        path.write_text(json.dumps(domain_map, indent=2), encoding="utf-8")
        logger.info("Wrote domain architecture map to %s", path)
    except Exception as e:
        logger.warning("Failed to write domain architecture map to %s: %s", path, e)


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to read JSON from %s: %s", path, e)
        return None


def _semantic_index_dir(artifacts_dir: Path) -> Path:
    p = artifacts_dir / SEMANTIC_INDEX_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash_inputs(paths: list[Path], *, mode: str, model_hint: str) -> str:
    h = hashlib.sha256()
    h.update(mode.encode("utf-8"))
    h.update(model_hint.encode("utf-8"))
    for p in paths:
        h.update(str(p).encode("utf-8"))
        if not p.exists():
            h.update(b"<missing>")
            continue
        try:
            b = p.read_bytes()
        except Exception:
            b = b""
        h.update(hashlib.sha256(b).digest())
    return h.hexdigest()


def _load_cached_semantic_outputs(artifacts_dir: Path, expected_hash: str) -> tuple[list[ModuleNode], dict[str, Any], list[Any]] | None:
    idx = _semantic_index_dir(artifacts_dir)
    meta_path = idx / "run_meta.json"
    modules_path = artifacts_dir / "modules.json"
    domains_path = idx / "domains.json"
    day_one_path = idx / "day_one_answers.json"
    if not (meta_path.exists() and modules_path.exists() and domains_path.exists() and day_one_path.exists()):
        return None
    meta = _load_json_if_exists(meta_path) or {}
    if str(meta.get("input_hash") or "") != expected_hash:
        return None
    try:
        modules_raw = _load_json_if_exists(modules_path) or []
        modules = [ModuleNode.model_validate(m) for m in modules_raw]
        domains = _load_json_if_exists(domains_path) or {"module_to_domain": {}, "cluster_to_domain": {}, "skipped_modules": []}
        day_one = _load_json_if_exists(day_one_path) or []
        if isinstance(day_one, dict) and "answers" in day_one:
            day_one = day_one.get("answers") or []
        return modules, domains, day_one
    except Exception:
        return None


def _compute_semantic_summary_stats(
    modules: list[ModuleNode],
    domains: dict[str, Any],
) -> dict[str, Any]:
    """Compute drift rate, ambiguous-module count, and cluster coherence for artifact logging."""
    n_total = len(modules)
    n_drift = sum(1 for m in modules if m.documentation_drift is True)
    ambiguous_phrases = (
        "no determinable purpose",
        "no purpose",
        "no purpose statement yet",
        "unknown",
        "n/a",
    )
    n_ambiguous = sum(
        1
        for m in modules
        if not (m.purpose_statement or "").strip()
        or (m.purpose_statement or "").strip().lower().rstrip(".") in ambiguous_phrases
    )
    module_to_domain = domains.get("module_to_domain") or {}
    cluster_sizes: dict[str, int] = {}
    for _path, domain in module_to_domain.items():
        cluster_sizes[domain] = cluster_sizes.get(domain, 0) + 1
    sizes = list(cluster_sizes.values()) if cluster_sizes else [0]
    n_clusters = len(cluster_sizes)
    avg_per_cluster = sum(sizes) / n_clusters if n_clusters else 0
    # Coherence: lower variance = more even/coherent; also report min cluster size (singletons = weak).
    variance = sum((s - avg_per_cluster) ** 2 for s in sizes) / n_clusters if n_clusters else 0
    return {
        "total_modules": n_total,
        "drift_count": n_drift,
        "drift_rate": round(n_drift / n_total, 4) if n_total else 0.0,
        "ambiguous_count": n_ambiguous,
        "cluster_count": n_clusters,
        "cluster_sizes": cluster_sizes,
        "cluster_coherence_avg_size": round(avg_per_cluster, 2),
        "cluster_coherence_variance": round(variance, 2),
    }


def _write_semantic_index_outputs(
    artifacts_dir: Path,
    *,
    modules: list[ModuleNode],
    domains: dict[str, Any],
    day_one: list[Any],
    input_hash: str,
    mode: str,
    summary_stats: Optional[dict[str, Any]] = None,
) -> None:
    idx = _semantic_index_dir(artifacts_dir)
    modules_payload = []
    for m in modules:
        modules_payload.append(
            {
                "module_name": m.path,
                "purpose_statement": m.purpose_statement,
                "docstring_match": "unknown" if m.documentation_drift is None else (not bool(m.documentation_drift)),
                "domain_cluster": m.domain_cluster,
                "optional_day_one_answer": None,
            }
        )
    (idx / "modules.json").write_text(json.dumps(modules_payload, indent=2), encoding="utf-8")
    (idx / "domains.json").write_text(json.dumps(domains, indent=2), encoding="utf-8")
    # Keep backward-compatible root artifact and semantic_index copy.
    day_one_payload = {"answers": day_one} if isinstance(day_one, list) else day_one
    (idx / "day_one_answers.json").write_text(json.dumps(day_one_payload, indent=2), encoding="utf-8")
    run_meta: dict[str, Any] = {
        "input_hash": input_hash,
        "mode": mode,
        "generated_at": time.time(),
    }
    if summary_stats:
        run_meta["summary_stats"] = summary_stats
    (idx / "run_meta.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")


def _normalize_fde_answers(raw_answers: list[DayOneAnswer]) -> list[DayOneAnswer]:
    """Guarantee exactly five FDE answers in canonical order."""
    by_id = {a.question_id: a for a in raw_answers}
    # Backward compatibility for legacy question ids (q1..q5) from older prompts/tests.
    if not any(qid in by_id for qid in FDE_DAY_ONE_QUESTION_IDS) and len(raw_answers) == 5:
        return raw_answers[:5]
    normalized: list[DayOneAnswer] = []
    for qid in FDE_DAY_ONE_QUESTION_IDS:
        if qid in by_id:
            normalized.append(by_id[qid])
        else:
            normalized.append(
                DayOneAnswer(
                    question_id=qid,
                    answer="Insufficient evidence in this run to produce a high-confidence answer.",
                    citations=[],
                )
            )
    return normalized


def _heuristic_day_one_answers(
    module_graph: dict[str, Any],
    lineage_graph: dict[str, Any],
    survey_summary: dict[str, Any],
) -> list[DayOneAnswer]:
    nodes = len((module_graph or {}).get("nodes") or [])
    edges = len((module_graph or {}).get("edges") or [])
    lineage_nodes = len((lineage_graph or {}).get("nodes") or [])
    lineage_edges = len((lineage_graph or {}).get("edges") or [])
    high_impact = (survey_summary or {}).get("high_impact") or []
    high_velocity = (survey_summary or {}).get("high_velocity") or []
    risky = (survey_summary or {}).get("risky") or []
    canned = {
        "fde_q1_business_capability": f"The system appears to support software/data platform capabilities across {nodes} modules with {edges} dependency links.",
        "fde_q2_key_data_flow": f"Detected lineage spans {lineage_nodes} nodes and {lineage_edges} edges, indicating active upstream-to-downstream data movement.",
        "fde_q3_change_risk": f"Highest structural risk concentrates around {', '.join(high_impact[:3]) if high_impact else 'core modules'} with additional change pressure in {', '.join(high_velocity[:3]) if high_velocity else 'recently modified files'}.",
        "fde_q4_operational_hotspots": f"Operational hotspots likely include {', '.join(risky[:3]) if risky else 'modules with high connectivity and velocity'} based on static and history signals.",
        "fde_q5_first_90_days": "Prioritize stabilizing high-impact modules, validating lineage-critical transformations, and improving documentation for rapidly changing code paths.",
    }
    answers: list[DayOneAnswer] = []
    for qid in FDE_DAY_ONE_QUESTION_IDS:
        answers.append(
            DayOneAnswer(
                question_id=qid,
                answer=canned.get(qid, "Insufficient static evidence."),
                citations=[{"file": "module_graph.json", "line": 1}, {"file": "lineage_graph.json", "line": 1}],
            )
        )
    return answers


def answer_day_one_questions(
    artifacts_dir: Path,
    budget: Optional[ContextWindowBudget] = None,
    *,
    use_llm: bool = True,
) -> list[DayOneAnswer]:
    """
    Load Surveyor + Hydrologist artifacts and use semantic_synthesis model
    to answer the Five FDE Day-One questions with evidence citations.

    On any failure, log and return an empty list (graceful degradation).
    """
    artifacts_dir = Path(artifacts_dir)
    try:
        module_graph = _load_json_if_exists(artifacts_dir / "module_graph.json")
        lineage_graph = _load_json_if_exists(artifacts_dir / "lineage_graph.json")
        survey_summary = _load_json_if_exists(artifacts_dir / "survey_summary.json")
        if not use_llm:
            answers = _heuristic_day_one_answers(module_graph or {}, lineage_graph or {}, survey_summary or {})
            out = DayOneOutput(answers=answers)
            out_path = artifacts_dir / "day_one_answers.json"
            out_path.write_text(json.dumps(out.model_dump(mode="json"), indent=2), encoding="utf-8")
            logger.info("Wrote heuristic Day-One answers to %s", out_path)
            return answers

        prompt = (
            "You are the Semanticist agent. Answer exactly the Five FDE Day-One questions using only the provided graphs and survey.\n"
            f"Return valid JSON only: an array of exactly 5 objects with keys question_id, answer, citations. "
            f"question_id must be one of: {', '.join(FDE_DAY_ONE_QUESTION_IDS)}. "
            "answer: 1-3 concise sentences with concrete file/module names. citations: list of {file, line?} from the evidence.\n\n"
            f"MODULE_GRAPH:\n{json.dumps(module_graph or {}, indent=2)}\n\n"
            f"LINEAGE_GRAPH:\n{json.dumps(lineage_graph or {}, indent=2)}\n\n"
            f"SURVEY_SUMMARY:\n{json.dumps(survey_summary or {}, indent=2)}\n"
        )

        if budget:
            budget.consume_input_tokens(budget.estimate_tokens(prompt))
        raw = _call_llm_synthesis(prompt)
        if budget:
            budget.consume_output_tokens(budget.estimate_tokens(raw or ""))
        parsed = _extract_json_from_text(raw)
        if isinstance(parsed, dict):
            parsed = parsed.get("answers") if "answers" in parsed else parsed.get("results")
        if not isinstance(parsed, list):
            logger.warning("answer_day_one_questions: synthesis output not a list; falling back to heuristic answers")
            answers = _heuristic_day_one_answers(module_graph or {}, lineage_graph or {}, survey_summary or {})
            out = DayOneOutput(answers=answers)
            out_path = artifacts_dir / "day_one_answers.json"
            out_path.write_text(json.dumps(out.model_dump(mode="json"), indent=2), encoding="utf-8")
            return answers
        answers: list[DayOneAnswer] = []
        for item in parsed:
            try:
                answers.append(DayOneAnswer.model_validate(item))
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("answer_day_one_questions: skipping invalid item %s: %s", item, e)

        answers = _normalize_fde_answers(answers)

        # Persist to .cartography/day_one_answers.json
        out = DayOneOutput(answers=answers)
        out_path = artifacts_dir / "day_one_answers.json"
        out_path.write_text(json.dumps(out.model_dump(mode="json"), indent=2), encoding="utf-8")
        logger.info("Wrote Day-One answers to %s", out_path)
        return answers
    except Exception as e:
        logger.warning("answer_day_one_questions failed: %s; falling back to heuristic answers", e)
        module_graph = _load_json_if_exists(artifacts_dir / "module_graph.json") or {}
        lineage_graph = _load_json_if_exists(artifacts_dir / "lineage_graph.json") or {}
        survey_summary = _load_json_if_exists(artifacts_dir / "survey_summary.json") or {}
        answers = _heuristic_day_one_answers(module_graph, lineage_graph, survey_summary)
        out = DayOneOutput(answers=answers)
        out_path = artifacts_dir / "day_one_answers.json"
        out_path.write_text(json.dumps(out.model_dump(mode="json"), indent=2), encoding="utf-8")
        return answers

