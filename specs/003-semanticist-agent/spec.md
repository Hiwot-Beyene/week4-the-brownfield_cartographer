# Feature Specification: Phase 3 — The Semanticist Agent (LLM-Powered Analysis)

**Feature Branch**: `003-semanticist-agent`  
**Created**: 2025-03-13  
**Status**: Draft  
**Input**: Create the specification for Phase 3: The Semanticist Agent (LLM-Powered Analysis) of the Brownfield Cartographer challenge.

## Clarifications

### Session 2025-03-13

- Q: How should tiered LLM roles and model configuration be defined? → A: Two distinct roles (semantic_bulk, semantic_synthesis) with explicit env/config: SEMANTIC_BULK_PROVIDER, SEMANTIC_BULK_MODEL; SEMANTIC_SYNTHESIS_PROVIDER, SEMANTIC_SYNTHESIS_MODEL. User can override via env or .env (e.g. SEMANTIC_BULK_MODEL=ollama:codellama:7b).
- Q: How should ContextWindowBudget behave? → A: Estimate input tokens before each call (e.g. tiktoken or chars/4); maintain cumulative usage per run; optional cap with warning; use budget to truncate very large module code (e.g. first N lines) so bulk phase stays within context.
- Q: How must purpose statements be grounded and how is doc drift handled? → A: generate_purpose_statement MUST receive module source code (or truncated slice) as LLM input, not docstring; prompt instructs 2–3 sentence business function only; compare LLM output to docstring and set Documentation Drift flag when they contradict; store both for traceability.
- Q: How should embeddings and domain clustering work? → A: Single consistent embedding model for purpose statements; k-means k=5–8; one LLM call per cluster to infer short domain name from a sample of purposes; cache embeddings (content-hash keyed) to avoid re-embedding unchanged text on re-runs.
- Q: How must Day-One answers be structured and evidenced? → A: answer_day_one_questions takes full Surveyor + Hydrologist outputs; synthesis prompt MUST require evidence citations (file path and line); output structured as Pydantic model per question: question_id, answer, citations[] (file, line).
- Q: How should failures be handled? → A: LLM call failure (rate limit, timeout, unsupported provider) → log and skip that module/step; embedding or k-means failure for a subset → produce partial Domain Architecture Map and document what was skipped; never crash entire Semanticist run.
- Q: How must testing be done? → A: Unit tests for ContextWindowBudget (token estimation and cumulative tracking), generate_purpose_statement (mocked LLM + docstring comparison), cluster_into_domains (fixed embeddings → known k-means), answer_day_one_questions (mocked LLM structured answers with citations); tests MUST NOT call real Ollama/API; use mocks or fixtures.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Purpose Statements from Code (Priority: P1)

As an FDE onboarding to a brownfield codebase, I need each module to have a short purpose statement that describes *what* the module does (business function), not *how* it is implemented, so that I can quickly decide where to focus. The statement must be derived from the actual code, not from docstrings, so I can trust it reflects reality.

**Why this priority**: Purpose statements are the foundation of the semantic index and domain clustering; without them, the Domain Architecture Map and Day-One answers cannot be produced.

**Independent Test**: Run the Semanticist on a small set of modules; verify each module receives a 2–3 sentence purpose statement and that the source of truth for the prompt was module code (not docstring). Can be tested by inspecting inputs to the LLM and the resulting purpose_statement field.

**Acceptance Scenarios**:

1. **Given** a module with code and an existing docstring, **When** the Semanticist generates a purpose statement, **Then** the statement is 2–3 sentences, explains business function (not implementation detail), and is based on the module’s code.
2. **Given** a module where the docstring describes different behavior than the code, **When** the Semanticist compares the generated purpose to the docstring, **Then** a Documentation Drift flag is raised so the user knows the docs may be wrong.

---

### User Story 2 - Documentation Drift Detection (Priority: P2)

As an FDE, I need to know when a module’s documentation (docstring) contradicts what the code actually does, so I can prioritize fixing stale docs or risky assumptions.

**Why this priority**: Documentation drift is a direct cause of “Silent Debt”; flagging it prevents wrong mental models and wasted debugging.

**Independent Test**: Provide a module with a docstring that clearly contradicts the code; run the Semanticist; verify a Documentation Drift indicator is set for that module.

**Acceptance Scenarios**:

1. **Given** a module with a docstring that describes different behavior than the implementation, **When** the Semanticist generates a purpose statement from code and cross-references the docstring, **Then** the system flags the module for Documentation Drift.
2. **Given** a module where docstring and code align, **When** the Semanticist runs, **Then** no Documentation Drift flag is set.

---

### User Story 3 - Domain Architecture Map (Priority: P3)

As an FDE, I need modules grouped into inferred business domains (e.g. ingestion, transformation, serving, monitoring) based on semantic similarity of their purpose, so I can see where business logic is concentrated and how the system is conceptually structured.

**Why this priority**: Domain clustering produces the Domain Architecture Map; it enables answering “Where is the business logic concentrated?” and improves navigation for large codebases.

**Independent Test**: Run clustering on a set of modules with known domains; verify clusters correspond to sensible domain labels and that each cluster has an inferred domain name.

**Acceptance Scenarios**:

1. **Given** a set of modules with generated purpose statements, **When** the Semanticist clusters them by semantic similarity, **Then** modules are assigned to a bounded number of clusters (e.g. 5–8), and each cluster receives an inferred domain name.
2. **Given** the Domain Architecture Map, **When** a user inspects it, **Then** they can see which modules belong to which domain and use that for onboarding and impact analysis.

---

### User Story 4 - Five FDE Day-One Answers with Evidence (Priority: P1)

As an FDE on Day One, I need a single synthesis that answers the Five FDE Day-One Questions with specific evidence (file paths and line numbers), so I can verify answers in the codebase and build trust in the system.

**Why this priority**: The Day-One Brief is a core deliverable of the Cartographer; it directly addresses the “72 hours to become useful” objective.

**Independent Test**: Run the full pipeline (Surveyor + Hydrologist + Semanticist); run answer_day_one_questions(); verify the output contains answers to all five questions and that each answer includes citations (file path and line number where applicable).

**Acceptance Scenarios**:

1. **Given** full Surveyor and Hydrologist outputs (module graph, lineage, velocity, etc.), **When** the Semanticist runs the synthesis step, **Then** the system produces answers to all Five FDE Day-One Questions.
2. **Given** each Day-One answer, **When** a user reviews it, **Then** the answer includes evidence citations (file paths and, where applicable, line numbers) so the answer can be verified in the codebase.
3. **Given** the Day-One synthesis output, **When** it is consumed by downstream tools or tests, **Then** it is structured (e.g. Pydantic model per question with question_id, answer, and citations[] with file and line).

---

### User Story 5 - Cost-Disciplined LLM Usage (Priority: P2)

As a team running the Cartographer, I need LLM usage to be budget-aware: bulk semantic extraction (purpose statements, embeddings for clustering) should use a fast, cheap model, and only synthesis (Day-One answers) should use a stronger, more expensive model, so that runs remain affordable at scale.

**Why this priority**: Cost discipline is an explicit challenge requirement; without it, the system may be too expensive for large or frequent runs.

**Independent Test**: Run the Semanticist with budget tracking enabled; verify that bulk module summary calls use the cheap/fast tier and that synthesis uses the reserved stronger tier. Token estimates and cumulative spend can be checked via the ContextWindowBudget.

**Acceptance Scenarios**:

1. **Given** a run of the Semanticist, **When** purpose statements are generated for many modules, **Then** those calls use a fast, cheap model (tier 1).
2. **Given** the same run, **When** Day-One questions are answered, **Then** that synthesis uses a stronger model (tier 2) reserved for synthesis only.
3. **Given** any LLM call, **When** it is invoked, **Then** token count is estimated and cumulative spend is tracked so the run stays within a budget (or can be reported).
4. **Given** configuration via env or .env (e.g. SEMANTIC_BULK_MODEL, SEMANTIC_SYNTHESIS_MODEL), **When** the Semanticist runs, **Then** it uses the configured provider and model for each role (semantic_bulk vs semantic_synthesis).
5. **Given** a very large module file, **When** the bulk phase would exceed context budget, **Then** the system truncates module code (e.g. first N lines) so the run stays within budget and logs or warns as configured.
6. **Given** embeddings for purpose statements, **When** purpose text is unchanged from a previous run, **Then** the system uses a content-hash keyed cache and does not re-embed (cache hit).
7. **Given** unit tests for ContextWindowBudget, generate_purpose_statement, cluster_into_domains, and answer_day_one_questions, **When** tests run, **Then** they use mocks or fixtures and do NOT call real Ollama or external APIs.

---

### Edge Cases

- What happens when a module has no code (e.g. empty file or only comments)? System should still produce a minimal purpose or “no determinable purpose” and not crash.
- What happens when the LLM is unavailable or returns invalid output? System should log the failure, skip or mark that module/question, and continue the run (graceful degradation).
- What happens when there are too few modules to cluster meaningfully (e.g. &lt; 5)? Clustering may produce fewer clusters or a single cluster with a generic label; behavior should be defined and consistent.
- What happens when Surveyor or Hydrologist output is missing or empty? Day-One synthesis should still run with available context and clearly indicate which parts of the context were missing.
- What happens when an LLM call fails (rate limit, timeout, unsupported provider)? Log the failure, skip that module or that step, and continue the run; do not crash the entire Semanticist.
- What happens when embedding or k-means fails for a subset of modules? Produce a partial Domain Architecture Map with the modules that succeeded and document (e.g. in trace or output) which modules or steps were skipped.

## Ollama Recommendation

When using Ollama only (local, no external API), the following model roles are recommended. The user chooses based on local hardware and quality/speed tradeoffs.

- **semantic_bulk** (generate_purpose_statement, many small calls): Use a **small, code-aware** model for speed and low resource use. Examples: `deepseek-coder:6.7b`, `codellama:7b`, `llama3.2:3b`. Defaults (when not overridden via env) can be e.g. `ollama` with one of these models.
- **semantic_synthesis** (answer_day_one_questions, few large-context calls): Use a **reasoning or larger** model for quality. Examples: `deepseek-r1`, `deepseek-coder:33b`, `codellama:34b`. Defaults (when not overridden via env) can be e.g. `ollama` with one of these models.

Users override via environment or .env (e.g. `SEMANTIC_BULK_MODEL=ollama:codellama:7b`, `SEMANTIC_SYNTHESIS_MODEL=ollama:deepseek-r1`). Implementation MUST support explicit configuration and MUST NOT hardcode a single provider/model.

## Constitution Constraints *(mandatory)*

- Implementation MUST follow the TRP 1 Week 4 phases/deliverables/schema.
- All node/edge types and agent outputs MUST use Pydantic models (e.g. purpose statements, domain labels, Day-One answers).
- The pipeline MUST gracefully degrade (per-module/per-call try/except; log and skip; never crash the full run).
- The system MUST support ignore patterns consistent with the rest of the Cartographer (e.g. `.cartographyignore`).
- All agent outputs MUST cite evidence (source file + line range + method: static vs LLM).
- LLM usage MUST be tiered: cheap/fast model for bulk extraction; stronger model reserved for synthesis only.
- Work MUST be structured so each task is independently completable and testable.
- The Semanticist MUST consume: module graph / ModuleNodes, DataLineageGraph, and raw module code (not docstrings as source of truth for purpose).

## Direct Requirements from the Challenge *(verbatim)*

The following requirements are taken verbatim from the TRP 1 Week 4 challenge and MUST be satisfied by this phase.

### Phase 3: The Semanticist Agent (LLM-Powered Analysis)

**Goal:** Add semantic understanding that static analysis cannot provide.

1. **ContextWindowBudget**  
   Before calling any LLM, estimate token count and track cumulative spend. Implement tiered model selection: use a fast, cheap model (e.g. Gemini Flash / Mistral via OpenRouter, or local Ollama small model) for bulk module summaries; reserve a stronger model (e.g. Claude or GPT-4, or local Ollama larger model) for synthesis only.

2. **generate_purpose_statement(module_node)**  
   Prompt the LLM with the module’s code (not docstring). Ask for a 2–3 sentence purpose statement that explains business function, not implementation detail. Cross-reference with the existing docstring—flag discrepancies as **Documentation Drift**.

3. **cluster_into_domains()**  
   Embed all Purpose Statements. Run k-means clustering (k=5–8). Label each cluster with an inferred domain name. This produces the **Domain Architecture Map**.

4. **answer_day_one_questions()**  
   Synthesis prompt that feeds the full Surveyor + Hydrologist output. Ask the LLM to answer the **Five FDE Day-One Questions** with specific evidence citations (file paths and line numbers).

### Agent 3: The Semanticist (LLM-Powered Purpose Analyst) — core tasks

- For each module: generate a **Purpose Statement** (what this module does, not how) based on its **code**, not its docstring.
- Flag if the docstring contradicts the implementation (**Documentation Drift**).
- Identify **Business Domain** boundaries: cluster modules into inferred domains (e.g. ingestion, transformation, serving, monitoring) based on semantic similarity.
- Generate the **Five FDE Day-One Answers** by synthesizing Surveyor + Hydrologist output with LLM reasoning over the full architectural context.
- **Cost discipline:** use a fast, cheap model for bulk semantic extraction; reserve expensive models for synthesis tasks only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST implement a ContextWindowBudget that estimates input token count before each LLM call (e.g. via tiktoken or a simple heuristic such as chars/4), maintains cumulative token usage per run, and optionally caps total or per-phase usage with a logged warning when approaching the limit. The budget MUST be used to decide whether to truncate module code (e.g. first N lines) for very large files so the bulk phase stays within context.
- **FR-002**: The system MUST implement two distinct LLM roles: **semantic_bulk** (for generate_purpose_statement; many small calls; fast and cheap) and **semantic_synthesis** (for answer_day_one_questions; few large-context calls; larger or reasoning model). Configuration MUST be explicit via environment or config (e.g. SEMANTIC_BULK_PROVIDER, SEMANTIC_BULK_MODEL; SEMANTIC_SYNTHESIS_PROVIDER, SEMANTIC_SYNTHESIS_MODEL). Users MUST be able to override via env or .env (e.g. SEMANTIC_BULK_MODEL=ollama:codellama:7b, SEMANTIC_SYNTHESIS_MODEL=ollama:deepseek-r1).
- **FR-003**: The system MUST implement generate_purpose_statement(module_node) that receives the module’s source code (or a truncated slice when budget requires) as input to the LLM, not the docstring. The prompt MUST instruct the LLM to output only a 2–3 sentence purpose statement (business function, not implementation detail). The system MUST return that purpose statement and MUST compare it to the existing docstring (if any); if they contradict, set Documentation Drift and store both for traceability.
- **FR-004**: The system MUST cross-reference the generated purpose statement with the module’s existing docstring and flag discrepancies as Documentation Drift (and store both for traceability).
- **FR-005**: The system MUST implement cluster_into_domains() that embeds all purpose statements with a single consistent embedding model (e.g. sentence-transformers or a lightweight sentence/code model), runs k-means with k=5–8, then uses one LLM call per cluster to infer a short domain name (e.g. ingestion, transformation) from a sample of purpose statements in that cluster. Embeddings MUST be cacheable (e.g. content-hash keyed cache) so unchanged purpose text is not re-embedded on re-runs.
- **FR-006**: The system MUST implement answer_day_one_questions() that takes as input the full Surveyor and Hydrologist outputs (e.g. module graph, lineage graph, critical path, sources/sinks). The synthesis prompt MUST require answers to cite evidence: file paths and line numbers where applicable. Output MUST be structured (e.g. Pydantic model per question: question_id, answer, citations[] with file and line).
- **FR-007**: The Semanticist MUST consume module graph / ModuleNodes, DataLineageGraph, and raw module code; docstrings are not the source of truth for purpose.
- **FR-008**: The system MUST persist or expose purpose statements, domain labels, and Day-One answers through defined Pydantic models and integrate with existing Surveyor and Hydrologist outputs (e.g. for use by the Archivist and Navigator).
- **FR-009**: The system MUST degrade gracefully: if an LLM call fails (rate limit, timeout, unsupported provider), log and skip that module or that step; do not crash the entire Semanticist run. If embedding or k-means fails for a subset of modules, still produce a partial Domain Architecture Map and document what was skipped.

### Key Entities

- **Purpose Statement**: A 2–3 sentence description of what a module does (business function), derived from code; stored or attached to the module (e.g. on ModuleNode).
- **Documentation Drift**: A flag or indicator that the module’s docstring contradicts the implementation (or the LLM-inferred purpose).
- **Domain Cluster**: A group of modules with similar purpose; has an inferred domain name (e.g. ingestion, transformation, serving, monitoring).
- **Domain Architecture Map**: The output of cluster_into_domains(); maps modules to domains and provides domain labels.
- **Day-One Answer**: One of five FDE Day-One answers, with evidence citations (file path and line number where applicable).
- **ContextWindowBudget**: A run-time construct that estimates input token count (e.g. tiktoken or chars/4), tracks cumulative usage per run, optionally caps total or per-phase usage with warnings, and drives truncation of very large module code for the bulk phase.
- **Citation**: A reference to evidence for a Day-One answer; includes file path and, where applicable, line number; part of the structured output (e.g. citations[] on the Pydantic model per question).
- **Embedding cache**: A content-hash keyed cache for purpose-statement embeddings so that unchanged text is not re-embedded on re-runs.

### Non-Functional Requirements (Production-Grade)

- **NFR-001 (Configurability)**: Model selection MUST be driven by explicit configuration (env or .env): SEMANTIC_BULK_PROVIDER, SEMANTIC_BULK_MODEL; SEMANTIC_SYNTHESIS_PROVIDER, SEMANTIC_SYNTHESIS_MODEL. No hardcoded single provider/model for production use.
- **NFR-002 (Observability)**: Token estimation and cumulative usage MUST be available (e.g. for logging or reporting). When approaching or hitting an optional budget cap, the system MUST log a warning.
- **NFR-003 (Resilience)**: Single LLM or embedding/k-means failures MUST NOT abort the full Semanticist run; partial results (e.g. partial Domain Architecture Map) MUST be produced and what was skipped MUST be documented.
- **NFR-004 (Testability)**: Unit tests MUST cover ContextWindowBudget (token estimation and cumulative tracking), generate_purpose_statement (mocked LLM returning fixed purpose plus docstring comparison), cluster_into_domains (fixed embeddings yielding known k-means result), and answer_day_one_questions (mocked LLM returning structured answers with citations). Tests MUST NOT call real Ollama or external APIs; mocks or fixtures MUST be used.
- **NFR-005 (Traceability)**: When Documentation Drift is set, both the generated purpose and the docstring (or a reference) MUST be stored so that downstream tools or users can compare them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every analyzed module receives a purpose statement (2–3 sentences) derived from its code; at least 95% of modules in a typical run complete without fatal errors.
- **SC-002**: When docstring and code contradict, Documentation Drift is flagged for that module in a way that is visible to the user or downstream artifacts.
- **SC-003**: The Domain Architecture Map is produced with a bounded number of clusters (e.g. 5–8) and each cluster has an inferred domain name; the mapping is available for downstream use (e.g. CODEBASE.md, Navigator).
- **SC-004**: The Five FDE Day-One Questions are answered in a single synthesis output, with each answer including at least one evidence citation (file path and, where applicable, line number).
- **SC-005**: Bulk purpose-statement and clustering work uses the cheap/fast model tier; Day-One synthesis uses the stronger model tier; token usage (or equivalent) is estimated and tracked for the run.
- **SC-006**: A user can run the Semanticist after Surveyor and Hydrologist and obtain purpose statements, domain map, and Day-One answers without the process crashing; failures are logged and localized (e.g. per module or per question).
- **SC-007**: Day-One answers are emitted in a structured form (e.g. Pydantic model per question with question_id, answer, and citations[] including file and line); purpose statements are grounded in module code (or truncated code) and Documentation Drift is stored with both generated purpose and docstring for traceability.
- **SC-008**: Unit tests for ContextWindowBudget, generate_purpose_statement, cluster_into_domains, and answer_day_one_questions pass using mocks or fixtures and do not call real Ollama or external APIs.

## Assumptions

- An LLM provider (or local model) is available and configurable for both tiers (cheap/fast and stronger).
- Surveyor and Hydrologist outputs (module graph, ModuleNodes, DataLineageGraph, etc.) are available in the agreed schema and storage (e.g. .cartography artifacts and/or DB).
- The Five FDE Day-One Questions are fixed as defined in the challenge: (1) primary data ingestion path, (2) 3–5 most critical output datasets/endpoints, (3) blast radius of the most critical module, (4) where business logic is concentrated vs. distributed, (5) what has changed most in the last 90 days (git velocity).
- Purpose statements and domain labels are stored or attached in a way that the Archivist (Phase 4) and Navigator can consume them; exact storage format is an implementation detail.
- Project structure will include `src/agents/semanticist.py` and `src/models/` (Pydantic types for purpose statements, domain labels, Day-One answers with question_id, answer, citations[]); integration points with Surveyor and Hydrologist are defined in the implementation plan.
- Configuration is read from environment or .env (e.g. SEMANTIC_BULK_PROVIDER, SEMANTIC_BULK_MODEL, SEMANTIC_SYNTHESIS_PROVIDER, SEMANTIC_SYNTHESIS_MODEL); defaults for Ollama-only setups are as in the Ollama Recommendation section.
- An embedding cache (content-hash keyed) is available or can be implemented so that re-runs do not re-embed unchanged purpose text.
