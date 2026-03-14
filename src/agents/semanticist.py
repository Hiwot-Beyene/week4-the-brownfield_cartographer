"""
Phase 3: Semanticist Agent — LLM-powered purpose statements, domain clustering, Day-One answers.
Uses tiered LLM (semantic_bulk / semantic_synthesis), ContextWindowBudget, and graceful degradation.
"""
from __future__ import annotations

import json
import logging
import os
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
PURPOSE_PROMPT_TEMPLATE = """Given the following module source code, output only a 2-3 sentence purpose statement that describes what this module does (business function), not implementation detail. Output nothing else.

Code:
"""

# Default chars-per-token heuristic when tiktoken not used
CHARS_PER_TOKEN = 4
MAX_BULK_PROMPT_CHARS = 16000
FDE_DAY_ONE_QUESTION_IDS = [
    "fde_q1_business_capability",
    "fde_q2_key_data_flow",
    "fde_q3_change_risk",
    "fde_q4_operational_hotspots",
    "fde_q5_first_90_days",
]


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
    try:
        parsed = float(raw)
        return parsed if parsed > 0 else default_seconds
    except Exception:
        return default_seconds


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
) -> tuple[list[ModuleNode], dict[str, Any], list[Any]]:
    """
    Run Semanticist: purpose statements, domain clustering, Day-One answers.
    Uses ContextWindowBudget for token estimation and cumulative tracking on every LLM call.
    Returns (enriched_modules, domain_architecture_map_dict, day_one_answers_list).
    """
    repo_root = Path(repo_root)
    artifacts_dir = artifacts_dir or repo_root / ".cartography"
    budget = _make_budget()
    # Load modules from artifacts if not provided
    if modules is None:
        modules = _load_modules_from_artifacts(artifacts_dir)
    if not modules:
        return [], {"module_to_domain": {}, "cluster_to_domain": {}, "skipped_modules": []}, []
    _enrich_modules_with_purpose(repo_root, modules, budget)
    from src.agents.semanticist_cluster import cluster_into_domains

    domain_map_model: DomainArchitectureMap = cluster_into_domains(modules)
    _write_domain_architecture_map(artifacts_dir, domain_map_model.model_dump(mode="json"))
    _write_enriched_modules(artifacts_dir, modules)
    # Day-One synthesis (may fail gracefully)
    day_one_answers: list[DayOneAnswer] = answer_day_one_questions(artifacts_dir, budget=budget)
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
        body = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            # Keep completions concise and reduce generation load.
            "options": {"temperature": 0.2, "num_predict": 180},
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
        body = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 800},
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
    """Load ModuleNode list from .cartography/modules.json."""
    path = artifacts_dir / "modules.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [ModuleNode.model_validate(item) for item in raw]
    except Exception as e:
        logger.warning("Failed to load modules from %s: %s", path, e)
        return []


def _enrich_modules_with_purpose(
    repo_root: Path,
    modules: list[ModuleNode],
    budget: ContextWindowBudget,
) -> None:
    """Load source per module, call generate_purpose_statement, attach result to each ModuleNode."""
    for m in modules:
        try:
            code, docstring = _read_module_source(repo_root, m.path)
            if not code:
                continue
            if budget.cap_bulk_phase and budget.estimate_tokens(code) + budget.cumulative_input_tokens > budget.cap_bulk_phase:
                code = budget.truncate_module_code(code, max_lines=budget.truncate_lines)
            result = generate_purpose_statement(m, code_slice=code, docstring=docstring, budget=budget)
            if result is None:
                continue
            m.purpose_statement = result.purpose_statement
            m.documentation_drift = result.documentation_drift
            m.docstring_snippet = result.docstring_snippet
        except Exception as e:
            logger.warning("Purpose enrichment failed for %s: %s", m.path, e)


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


def answer_day_one_questions(artifacts_dir: Path, budget: Optional[ContextWindowBudget] = None) -> list[DayOneAnswer]:
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

        prompt = (
            "You are the Semanticist agent for the Brownfield Cartographer.\n"
            "Given the module graph, lineage graph, and survey summary, answer the Five FDE Day-One questions.\n"
            f"Use these exact question_id values: {', '.join(FDE_DAY_ONE_QUESTION_IDS)}.\n"
            "Return a JSON array of exactly five objects with fields: question_id, answer, citations[]. "
            "Each citation has file and optional line.\n\n"
            f"MODULE_GRAPH:\n{json.dumps(module_graph or {}, indent=2)}\n\n"
            f"LINEAGE_GRAPH:\n{json.dumps(lineage_graph or {}, indent=2)}\n\n"
            f"SURVEY_SUMMARY:\n{json.dumps(survey_summary or {}, indent=2)}\n"
        )

        if budget:
            budget.consume_input_tokens(budget.estimate_tokens(prompt))
        raw = _call_llm_synthesis(prompt)
        if budget:
            budget.consume_output_tokens(budget.estimate_tokens(raw or ""))
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            logger.warning("answer_day_one_questions: synthesis output not a list")
            return []
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
        logger.warning("answer_day_one_questions failed: %s", e)
        return []

