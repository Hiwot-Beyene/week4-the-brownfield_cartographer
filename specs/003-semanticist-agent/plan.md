# Implementation Plan: Phase 3 — The Semanticist Agent (LLM-Powered Analysis)

**Branch**: `003-semanticist-agent` | **Date**: 2025-03-13 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification and clarifications from `specs/003-semanticist-agent/spec.md`

## Summary

Implement the Semanticist Agent that adds LLM-powered semantic understanding to the Brownfield Cartographer: purpose statements per module (from code, not docstring), Documentation Drift detection, Domain Architecture Map via embedding + k-means + LLM naming, and Five FDE Day-One answers with evidence citations. Two LLM roles (semantic_bulk / semantic_synthesis) with explicit env configuration; ContextWindowBudget for token estimation and truncation; embedding cache for re-runs; full graceful degradation. Purpose and domain data extend ModuleNode and are serialized to `.cartography/` and optionally a semantic index; Day-One output is a structured Pydantic list.

---

## 1) Architecture

### Entrypoint and orchestration

- **`src/agents/semanticist.py`** is the entrypoint. It:
  - Loads Surveyor and Hydrologist outputs (see below).
  - Instantiates **ContextWindowBudget** (token estimation, cumulative counter, optional cap, truncation policy).
  - Runs **generate_purpose_statement** (bulk) for each module using **semantic_bulk** LLM; per-module try/except, log and skip on failure.
  - Runs **cluster_into_domains** (embed → k-means → LLM naming).
  - Runs **answer_day_one_questions** (synthesis) using **semantic_synthesis** LLM with full context.
  - Returns or persists purpose statements, domain labels, and Day-One answers.

### Where purpose statements and domain labels are stored

- **Extend ModuleNode** (in `src/models/module.py`): `purpose_statement` and `domain_cluster` already exist; add **`documentation_drift: Optional[bool] = None`** and **`docstring_snippet: Optional[str] = None`** (for traceability when drift is set). Semanticist writes these fields on the same ModuleNode instances that come from the Surveyor.
- **Serialization**: Write updated modules (with purpose, domain, drift) back to **`.cartography/modules.json`** (or a dedicated **`.cartography/semantic_modules.json`** if the team prefers to keep Surveyor-only vs Semanticist-enriched separate). Domain Architecture Map (module path → domain name) is written to **`.cartography/domain_architecture_map.json`**. Day-One answers (structured list) to **`.cartography/day_one_answers.json`**.
- **Semantic index**: If the project already has a vector store (e.g. Chroma) for modules, the Semanticist can **add or update** embeddings for purpose statements there (e.g. for `find_implementation` in Phase 4). Optional: a small **`semantic_index/`** under `.cartography/` for embedding cache and/or domain map artifacts. Decision: reuse existing `.cartography/` and existing vector store where applicable; no separate “semantic_index” directory unless needed for embedding cache (see §5).

### How Surveyor and Hydrologist outputs are loaded

- **Surveyor**: Read **`.cartography/module_graph.json`** and/or **`.cartography/modules.json`** to obtain the list of ModuleNodes (path, language, imports, etc.). Module **source code** is read from disk using `path` (repo root relative). If modules are also in SQLite, optionally load from DB; primary contract for this phase is JSON + filesystem.
- **Hydrologist**: Read **`.cartography/lineage_graph.json`** (and optionally **`.cartography/sql_lineage_summary.json`**) for the DataLineageGraph, sources/sinks, and table references.
- **Additional context**: Read **`.cartography/survey_summary.json`** (or equivalent) for critical path, high-impact, high-velocity, dead-code lists to feed into the Day-One synthesis prompt.
- **API**: Semanticist exposes a function that accepts `(repo_root, artifacts_dir=.cartography)` or `(modules: list[ModuleNode], lineage_graph, survey_summary, ...)` so the orchestrator can pass in-memory data when available, or the Semanticist can load from `artifacts_dir` when run standalone. Implementation will support both: load from `.cartography/*` when paths are given, or accept pre-loaded structures from the orchestrator.

---

## 2) ContextWindowBudget

- **Token estimation**: Use **tiktoken** when available (e.g. `cl100k_base` for OpenAI-compatible tokenization) or a **simple heuristic** (e.g. `len(text) // 4` or configurable chars-per-token). Estimation runs **before** each LLM call; result is stored in the budget instance.
- **Stored where**: A **ContextWindowBudget** class (or struct) holds: `cumulative_input_tokens: int`, `cumulative_output_tokens: int` (if available), optional `cap_total: int | None`, optional `cap_bulk_phase: int | None`. Log a **warning** when cumulative approaches or exceeds cap (e.g. 80% of cap).
- **Truncation policy**: For **generate_purpose_statement**, if the module’s source code (or current slice) would cause the **bulk phase** to exceed its budget (or a per-call limit), truncate module code to the **first N lines** (e.g. N = 500 or configurable). Log that truncation occurred. Synthesis phase (**answer_day_one_questions**) receives **full** context (no truncation of Surveyor/Hydrologist summary); only bulk phase may truncate.
- **How budget chooses roles**: The budget does **not** switch between semantic_bulk and semantic_synthesis; the **orchestrator** always uses **semantic_bulk** for purpose statements and cluster naming, and **semantic_synthesis** for Day-One. The budget is used only to (1) decide truncation for each module in the bulk phase, and (2) optionally refuse to start synthesis if total usage is already over cap (or log and proceed anyway per config).

---

## 3) Tiered LLM configuration

- **Two roles**: **semantic_bulk** (many small calls: generate_purpose_statement, and optionally one LLM call per cluster for domain name) and **semantic_synthesis** (few large calls: answer_day_one_questions).
- **Configuration**: Env vars **SEMANTIC_BULK_PROVIDER**, **SEMANTIC_BULK_MODEL**, **SEMANTIC_SYNTHESIS_PROVIDER**, **SEMANTIC_SYNTHESIS_MODEL**. Load from `os.environ` with optional `.env` via `python-dotenv`. Example: `SEMANTIC_BULK_MODEL=ollama:codellama:7b`, `SEMANTIC_SYNTHESIS_MODEL=ollama:deepseek-r1`. Provider can be `ollama` or a label for future OpenRouter/API.
- **Calling Ollama**: Use a single HTTP client (e.g. `httpx` or `requests`) to the local Ollama API (e.g. `http://localhost:11434/api/generate` or `/api/chat`). The **model_id** is parsed from `SEMANTIC_*_MODEL` (e.g. `codellama:7b`, `deepseek-r1`). Same client pattern as code-graph-rag: one client, different `model` parameter per role. No separate “orchestrator” process; the Semanticist process calls Ollama directly with the configured model for each role.
- **Defaults (Ollama only)**: If env is unset, defaults: **semantic_bulk** → `ollama` / `deepseek-coder:6.7b` (or `codellama:7b`); **semantic_synthesis** → `ollama` / `deepseek-r1` (or `deepseek-coder:33b`). Document in quickstart and README that users can override via env.

---

## 4) generate_purpose_statement

- **Input**: `module_node: ModuleNode` (path, language), **code_slice: str** (full or truncated module source), optional **docstring: str | None** (extracted from module or from ModuleNode if stored).
- **Prompt template**: System/user prompt instructs: “Given the following module source code, output only a 2–3 sentence purpose statement that describes what this module does (business function), not implementation detail. Output nothing else.” Code is pasted into the user message (or equivalent). No docstring in the prompt for the primary answer; docstring is used only for comparison after the fact.
- **Output**: A small Pydantic model or typed tuple: **`purpose_statement: str`**, **`documentation_drift: bool`**, and optionally **`docstring_snippet: str | None`** (for trace). Compare LLM output to docstring (e.g. semantic similarity or simple contradiction heuristic); if they contradict, set `documentation_drift=True` and store both. Attach to ModuleNode: `purpose_statement`, `documentation_drift`, `docstring_snippet`.
- **Per-module try/except**: Wrap each LLM call in try/except; on timeout, rate limit, or parse error, log (with module path), skip that module, and continue. Do not crash the run.

---

## 5) cluster_into_domains

- **Embedding**: Use a **single consistent embedding model** for all purpose statements, e.g. **sentence-transformers** `all-MiniLM-L6-v2` (or a code-oriented model if preferred). Produce a vector per module (from its `purpose_statement` text). **Caching**: **Content-hash keyed cache** (e.g. hash of `purpose_statement` text → embedding vector). Store cache under `.cartography/` or a subdir (e.g. `.cartography/embedding_cache/` or in existing cache dir). On re-run, if purpose text unchanged, reuse cached embedding.
- **k-means**: **k** in 5–8 (configurable, e.g. default 6). Input = matrix of embeddings (one row per module). Output = **cluster label index** per module (0..k-1). Use scikit-learn or numpy-only k-means. Handle &lt; k modules (e.g. fewer clusters or single cluster).
- **Naming**: **One LLM call per cluster** (or one batch prompt listing all clusters and sample purposes): provide a sample of purpose statements in that cluster and ask the LLM to infer a **short domain name** (e.g. “ingestion”, “transformation”, “serving”). Use **semantic_bulk** model (or configurable) for these naming calls. Result: mapping cluster_id → domain_name; then module path → domain_name. Write **Domain Architecture Map** to `.cartography/domain_architecture_map.json` and set **`domain_cluster`** on each ModuleNode.

---

## 6) answer_day_one_questions

- **Input**: Full Surveyor + Hydrologist outputs: **module graph** (or list of ModuleNodes with purpose/domain), **lineage graph** (nodes/edges, sources/sinks), **critical path / high-impact**, **high-velocity files**, **survey_summary**-like structure. Passed as in-memory structures or loaded from `.cartography/module_graph.json`, `lineage_graph.json`, `survey_summary.json`.
- **Synthesis prompt**: Single (or few) prompt(s) that include a condensed representation of the above (e.g. summary of modules and purposes, lineage edges, top N critical paths, top N velocity files). Instruction: “Answer the following Five FDE Day-One Questions. For each answer, cite evidence: file path and line number where applicable.”
- **Model**: **semantic_synthesis** only.
- **Output**: Structured **list of five answers**. Pydantic model: e.g. **DayOneAnswer** with **question_id: str** (e.g. "q1".."q5"), **answer: str**, **citations: list[Citation]** where **Citation** has **file: str**, **line: int | None**. Serialize to `.cartography/day_one_answers.json`. Return value from Semanticist run is this list (or a wrapper containing it plus updated modules and domain map).

---

## 7) Safeguards and reuse

- **Reuse Phase 1 rules**: Semanticist does **not** perform its own file discovery or ignore logic. It runs only on **modules that were already produced by the Surveyor** (i.e. the list of ModuleNodes from `module_graph.json` / `modules.json`). So ignore/sensitive-file rules are fully delegated to the Surveyor; Semanticist just consumes its output and reads file content for those paths.
- **Graceful degradation**: **Per-call try/except** for every LLM call and for embedding/k-means. Optional **retries** (e.g. 1–2 retries with backoff for transient Ollama errors). **Structured logging**: log level, module path or step, and error message so runs are debuggable. On partial failure: partial Domain Architecture Map and partial purpose statements; document skipped modules/steps in the output or in a small `semanticist_skipped.json` (or in trace log).

---

## 8) Testing strategy

- **tests/unit/test_context_window_budget.py**: Test token estimation (heuristic and/or tiktoken), cumulative counter increment, cap warning when approaching limit, truncation decision (e.g. when code length would exceed budget).
- **tests/unit/test_generate_purpose_statement.py**: **Mocked LLM** (e.g. patch the Ollama client or a thin wrapper) that returns a fixed string. Test: (1) purpose_statement and documentation_drift set correctly when docstring contradicts; (2) no drift when docstring aligns; (3) on mock raise exception, module is skipped and run continues.
- **tests/unit/test_cluster_into_domains.py**: **Fixed embeddings** (e.g. 10 modules, 5-dim stub vectors) so k-means result is deterministic; assert cluster labels and that domain names are produced (mock the LLM for cluster naming). Test cache: same purpose text → same embedding, no duplicate call.
- **tests/unit/test_answer_day_one_questions.py**: **Mocked LLM** returning a structured blob that parses to five DayOneAnswer with citations. Test: output shape, presence of file/line in citations, and that synthesis model role is used (via mock assertion).
- **No real Ollama in unit tests**: All tests use mocks or fixtures; no network calls. **Document** in quickstart or README how to run **one manual e2e** with real Ollama (e.g. `uv run python -m src.agents.semanticist --repo . --e2e` or a small script that loads a few modules and calls the agent with real Ollama).

---

## Technical Context

**Language/Version**: Python 3.11+ (match existing project)  
**Primary Dependencies**: pydantic, httpx or requests (Ollama), sentence-transformers or minimal embedder, scikit-learn or numpy (k-means), tiktoken (optional), python-dotenv  
**Storage**: `.cartography/*.json` (modules, domain_architecture_map, day_one_answers); optional SQLite for modules (existing); embedding cache on disk (content-hash keyed)  
**Testing**: pytest; mocks for LLM and embedding in unit tests  
**Target Platform**: Same as rest of Cartographer (Linux/macOS, CLI)  
**Project Type**: CLI / multi-agent pipeline (library-style agents)  
**Performance Goals**: Bulk phase: avoid excessive latency per module (truncation when needed); synthesis: one or few calls  
**Constraints**: No hardcoded provider/model; env-driven config; graceful degradation  
**Scale/Scope**: Hundreds to low-thousands of modules per run; context budget caps to avoid OOM or timeout

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Deliverables and phases match TRP 1 Week 4 (no missing/extra artifacts)
- [x] All node/edge/tool I/O contracts are Pydantic models (no primary dict contracts)
- [x] Graceful degradation designed: per-module/per-call try/except, log+skip, no pipeline-wide crash
- [x] Ignore patterns supported (Semanticist reuses Surveyor output; no new file scanning)
- [x] Incremental update strategy defined (embedding cache by content-hash; re-run only changed modules could be Phase 4)
- [x] Evidence policy designed: Day-One answers cite file+line; method = LLM
- [x] Tiered LLM plan: semantic_bulk for bulk; semantic_synthesis for synthesis only
- [x] Tasks are a sequential checklist; each task independently completable and testable

## Project Structure

### Documentation (this feature)

```text
specs/003-semanticist-agent/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1 (LLM client, embedding, config)
└── tasks.md             # From /speckit.tasks
```

### Source Code (repository root)

```text
src/
├── agents/
│   ├── surveyor.py      # Existing
│   ├── hydrologist.py   # Existing
│   └── semanticist.py   # NEW: entrypoint, ContextWindowBudget, generate_purpose_statement, cluster_into_domains, answer_day_one_questions
├── models/
│   ├── module.py        # Extend: documentation_drift, docstring_snippet
│   └── semanticist.py   # NEW (optional): PurposeResult, DayOneAnswer, Citation, DomainArchitectureMap, etc.
├── llm/                 # NEW (optional): ollama_client.py, config loading
├── graph/
├── store/
└── ...

tests/
├── unit/
│   ├── test_context_window_budget.py
│   ├── test_generate_purpose_statement.py
│   ├── test_cluster_into_domains.py
│   └── test_answer_day_one_questions.py
└── ...
```

**Structure Decision**: Single project layout; Semanticist lives in `src/agents/semanticist.py`; new Pydantic models in `src/models/` (either in `module.py` or a new `semanticist.py`); optional `src/llm/` for Ollama client and config so that other agents can reuse it later.

## Complexity Tracking

No constitution violations. Table left empty.
