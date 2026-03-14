# Tasks: Phase 3 — The Semanticist Agent

**Input**: Design documents from `/specs/003-semanticist-agent/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: TDD requested — test tasks come before implementation where applicable.

**Organization**: Tasks are grouped by capability/user story slices so each group can be implemented and tested independently.

**Cartographer constraints**: Tasks are a strict sequential checklist; each task should be completable in 30–60 minutes and has an implicit verification step (run or update the named tests).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5 from `spec.md`)
- Descriptions include exact file paths

---

## Phase 1: Config & Budget (User Story 5 — Cost-Disciplined LLM Usage)

**Goal**: Introduce tiered LLM configuration (semantic_bulk, semantic_synthesis) and ContextWindowBudget with token estimation and truncation.

**Independent Test**: Run `tests/unit/test_context_window_budget.py` and `tests/unit/test_semantic_config.py` in isolation; verify budget behavior and env-driven config.

- [x] T001 [US5] Add failing tests for `ContextWindowBudget` behavior in `tests/unit/test_context_window_budget.py` (token estimation, cumulative tracking, cap warning, truncation decision).
- [x] T002 [US5] Implement `ContextWindowBudget` class and helpers in `src/agents/semanticist.py` (or `src/agents/semanticist_budget.py`) so T001 passes.
- [x] T003 [US5] Add env/config parsing for `SEMANTIC_BULK_PROVIDER/MODEL` and `SEMANTIC_SYNTHESIS_PROVIDER/MODEL` in `src/llm/config.py` (or `src/agents/semanticist.py`), with defaults for Ollama-only setups.
- [x] T004 [US5] Add tests for semanticist config parsing and defaults in `tests/unit/test_semantic_config.py` (including parsing `ollama:codellama:7b` style values).
- [x] T005 [US5] Wire `ContextWindowBudget` into the Semanticist entrypoint in `src/agents/semanticist.py` so every LLM call estimates tokens and updates the cumulative counter.

---

## Phase 2: Purpose Statements & Documentation Drift (User Stories 1 & 2)

**Goal**: Generate 2–3 sentence purpose statements per module from code (not docstring) and detect Documentation Drift, attaching results to `ModuleNode` and JSON artifacts.

**Independent Test**: Run `tests/unit/test_generate_purpose_statement.py` with mocked LLM; then run Semanticist on a small repo and inspect `.cartography/modules.json` for `purpose_statement`, `documentation_drift`, and `docstring_snippet`.

### Tests for Purpose & Drift (TDD)

- [x] T006 [US1] Add failing tests for `generate_purpose_statement` behavior in `tests/unit/test_generate_purpose_statement.py` (mock LLM, code-only prompt, 2–3 sentence output, docstring comparison, drift flag, per-module try/except).
- [x] T007 [US2] Extend tests in `tests/unit/test_generate_purpose_statement.py` to cover Documentation Drift cases (contradicting docstring vs aligned docstring) and traceability via `docstring_snippet`.

### Implementation for Purpose & Drift

- [x] T008 [US2] Extend `ModuleNode` in `src/models/module.py` with `documentation_drift: Optional[bool]` and `docstring_snippet: Optional[str]`, and ensure existing serialization/model tests (if any) still pass.
- [x] T009 [US1] Implement `generate_purpose_statement` in `src/agents/semanticist.py` to accept `ModuleNode` + `code_slice`, call the `semantic_bulk` LLM with a code-only prompt, and return `purpose_statement`, `documentation_drift`, and `docstring_snippet` so T006–T007 pass.
- [x] T010 [US1] Add logic in `src/agents/semanticist.py` to load the ModuleNode list from `.cartography/modules.json` (or Surveyor in-memory output), read module source from disk, and call `generate_purpose_statement` for each module using `ContextWindowBudget`.
- [x] T011 [US1] Update the Semanticist run pipeline in `src/agents/semanticist.py` to write enriched modules (with `purpose_statement`, `documentation_drift`, `docstring_snippet`) back to `.cartography/modules.json` and document this in `specs/003-semanticist-agent/quickstart.md`.

---

## Phase 3: Embedding & Clustering (User Story 3 — Domain Architecture Map)

**Goal**: Embed purpose statements, cluster modules into domains (k-means k=5–8), infer domain names per cluster, and persist the Domain Architecture Map.

**Independent Test**: Run `tests/unit/test_embedding_cache.py` and `tests/unit/test_cluster_into_domains.py`; then run Semanticist on a small repo and inspect `.cartography/domain_architecture_map.json` and `ModuleNode.domain_cluster`.

### Tests for Embedding & Clustering (TDD)

- [x] T012 [P] [US3] Add failing tests for embedding cache behavior in `tests/unit/test_embedding_cache.py` (content-hash key, cache hit vs miss, disk persistence stub).
- [x] T013 [P] [US3] Add failing tests for `cluster_into_domains` in `tests/unit/test_cluster_into_domains.py` using fixed stub embeddings (deterministic k-means labels, one LLM call per cluster for domain name, assignment of `domain_cluster`).

### Implementation for Embedding & Clustering

- [x] T014 [US3] Implement embedding cache and `embed(text: str) -> list[float]` in `src/llm/embedding.py` using sentence-transformers (e.g. `all-MiniLM-L6-v2`) and on-disk cache under `.cartography/embedding_cache/`.
- [x] T015 [US3] Implement `cluster_into_domains` in `src/agents/semanticist.py` (or `src/agents/semanticist_cluster.py`) to: (1) embed all `ModuleNode.purpose_statement` values via the cache, (2) run k-means (k in 5–8, configurable), (3) call `semantic_bulk` LLM once per cluster to infer short domain names, and (4) attach `domain_cluster` to each ModuleNode.
- [x] T016 [US3] Implement serialization of a `DomainArchitectureMap` Pydantic model in `src/models/semanticist.py` (or similar) and write it from `src/agents/semanticist.py` to `.cartography/domain_architecture_map.json` with `module_to_domain`, `cluster_to_domain`, and `skipped_modules` fields.

---

## Phase 4: Day-One Synthesis (User Story 4 — Five FDE Day-One Answers)

**Goal**: Synthesize the Five FDE Day-One answers from Surveyor + Hydrologist outputs using the `semantic_synthesis` model, with structured answers and evidence citations.

**Independent Test**: Run `tests/unit/test_day_one_models.py` and `tests/unit/test_answer_day_one_questions.py` with mocked synthesis LLM; then inspect `.cartography/day_one_answers.json` for 5 structured answers with citations.

### Models & Tests for Day-One Answers

- [x] T017 [P] [US4] Define Pydantic models `Citation` and `DayOneAnswer` (and optional wrapper) in `src/models/semanticist.py`, and add tests in `tests/unit/test_day_one_models.py` for validation and JSON shape.
- [x] T018 [US4] Add failing tests for `answer_day_one_questions` in `tests/unit/test_answer_day_one_questions.py` using a mocked `semantic_synthesis` LLM (ensuring five answers, correct `question_id` values, and at least one `Citation` per answer when evidence is available).

### Implementation for Day-One Synthesis

- [x] T019 [US4] Implement `answer_day_one_questions` in `src/agents/semanticist.py` to load Surveyor + Hydrologist artifacts (`.cartography/module_graph.json`, `lineage_graph.json`, `survey_summary.json`), build a condensed prompt with context, call `semantic_synthesis`, and parse the result into a list of `DayOneAnswer` models.
- [x] T020 [US4] Implement serialization of Day-One answers from `src/agents/semanticist.py` to `.cartography/day_one_answers.json` and reference this artifact in `specs/003-semanticist-agent/quickstart.md`.

---

## Phase 5: Integration & Outputs (Cross-Cutting)

**Goal**: Wire the Semanticist into the orchestrator/CLI, ensure it respects Surveyor ignore rules, and validate the full pipeline end-to-end.

**Independent Test**: Run the full Cartographer pipeline on a small repo with Ollama running; inspect `.cartography/modules.json`, `domain_architecture_map.json`, and `day_one_answers.json` for sensible values.

- [x] T021 Wire `src/agents/semanticist.py` into `src/orchestrator.py` so the Semanticist runs after Hydrologist, reusing the same analysis_id and `.cartography` artifacts.
- [x] T022 Update `src/cli.py` to expose a Semanticist-aware analyze command (or flag) that runs Surveyor → Hydrologist → Semanticist in sequence.
- [x] T023 Ensure `src/agents/semanticist.py` only processes modules that come from Surveyor (`.cartography/modules.json` or in-memory list) and does not perform its own file discovery, so ignore rules are reused.
- [x] T024 Add structured logging and per-call try/except wrappers around all LLM and embedding calls in `src/agents/semanticist.py` and `src/llm/*`, ensuring failures are logged and skipped without crashing the pipeline.
- [x] T025 Run the new unit tests for Semanticist components with `uv run pytest tests/unit/test_context_window_budget.py tests/unit/test_generate_purpose_statement.py tests/unit/test_embedding_cache.py tests/unit/test_cluster_into_domains.py tests/unit/test_day_one_models.py tests/unit/test_answer_day_one_questions.py -v` and fix any failures.
- [ ] T026 Perform a manual end-to-end run against a small target repo with Ollama configured (as in `quickstart.md`), then inspect `.cartography/modules.json`, `.cartography/domain_architecture_map.json`, and `.cartography/day_one_answers.json` to confirm purpose statements, domains, and Day-One answers look correct.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Config & Budget)**: No prior dependencies; must complete before using LLM roles or budget elsewhere.
- **Phase 2 (Purpose & Drift)**: Depends on Phase 1; `generate_purpose_statement` must use configured `semantic_bulk` and `ContextWindowBudget`.
- **Phase 3 (Embedding & Clustering)**: Depends on Phase 2; requires purpose statements on ModuleNodes.
- **Phase 4 (Day-One Synthesis)**: Depends on Phases 1–3; expects semantic_enriched modules and lineage/survey artifacts.
- **Phase 5 (Integration & Outputs)**: Depends on all previous phases; wires everything into orchestrator/CLI and validates end-to-end.

### Parallel Opportunities

- Tasks marked **[P]** (e.g. T012–T013, T017) can run in parallel by different developers since they touch different files and have no direct dependencies.
- Within a phase, test-writing tasks (T006–T007, T012–T013, T017–T018) can proceed in parallel as long as files and expected interfaces are agreed.
- Phases should still be completed in order; do not start implementation tasks for a phase until its tests are in place and earlier phases are stable.

### Implementation Strategy

- **MVP**: Complete Phases 1–2 (Config & Budget, Purpose & Drift) to get purpose statements and drift detection working end-to-end for a small repo.
- **Next**: Add Phase 3 (Embedding & Clustering) to produce the Domain Architecture Map.
- **Then**: Add Phase 4 (Day-One Synthesis) to generate structured answers with citations.
- **Finally**: Finish Phase 5 integration and polish, then run the full pipeline demo as in the challenge.
