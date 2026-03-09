---
description: "Task list for Phase 1 Surveyor Agent"
---

# Tasks: Phase 1 — Surveyor Agent (Static Structure)

**Input**: Design documents from `/specs/001-surveyor-agent/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Included (Phase 1 requires TDD + fast local unit tests; no Docker).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

**Cartographer constraints**: Tasks MUST be a sequential checklist, and each task MUST include an explicit verification step.

**Implementation note**: Phase 1 implements `extract_git_velocity(repo_root, days=90)` and writes `.cartography/git_velocity.json` (git velocity map) on each run, answering the challenge question *"What has changed most frequently in the last 90 days?"*.

### Implemented behavior (for future developers)

- **Language routing**: `LanguageRouter` maps `.py`, `.sql`, `.yml`/`.yaml`, `.js`, `.ts`/`.tsx` to language ids. `analyze_module(path, router)` sets `ModuleNode.language` from the router; only Python gets full AST extraction; other extensions get correct language label and empty structural fields (no "unknown" for supported extensions).
- **Local and remote repos**: CLI `analyze <repo>` accepts local path or Git URL. `repo_resolver.resolve_repo()` clones remotes into `get_data_dir(cwd)/cloned/<slug>`; options `--branch`, `--depth` (default 1; 0 = full history). Orchestrator passes `project_data_dir=Path.cwd()` so SQLite and Chroma are always written to the **project’s** `.cartography/`; JSON artifacts are written in the analyzed repo’s `.cartography/` then copied to `cwd/.cartography/`.
- **Database integration**: SQLite (`cartographer.db`) and Chroma (`chroma/`) in `get_data_dir(store_root)` — env `CARTOGRAPHER_DATA_DIR` (from `.env`) overrides; else project `repo_root/.cartography` when repo_root given. Tables: `analyses`, `modules`, `import_edges`. Module columns include full KG schema; `_migrate_modules_columns` for existing DBs. Chroma collection `modules`, embedding `all-MiniLM-L6-v2`. Persistence errors are caught separately (log + stderr), run continues; JSON artifacts always written via `_write_all_json_artifacts()`.
- **Artifacts**: Four JSON files overwritten each run: `file_hashes.json`, `modules.json`, `module_graph.json` (KG schema: nodes with type + schema fields, edges IMPORTS with weight), `git_velocity.json`. Deduplication by resolved file path (files) and resolved module path (modules). `.gitignore` excludes `.cartography/` and root `module_graph.json` so generated output is not committed.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create Phase 1 source layout in `src/agents/`, `src/analyzers/`, `src/models/`, `src/graph/`
- [x] T002 Add Phase 1 dependencies to `pyproject.toml` (pin versions): Pydantic, NetworkX, tree-sitter core + Python-provided grammar packages for Python/SQL/YAML/JS/TS
- [x] T003 Update the project lockfile after dependency changes (e.g., `uv.lock`) to ensure reproducible installs
- [x] T004 Create test layout and fixtures directories: `tests/unit/` and `tests/fixtures/`
- [x] T005 Add pytest configuration (test discovery + fast defaults) in `pyproject.toml` (or `pytest.ini` if preferred)
- [x] T006 Define `.cartography/` artifact output directory contract (create if missing) in `src/agents/surveyor.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Write unit tests for ignore rules + safety (default ignores + explicit unignore; sensitive files skipped; never read/parsed) in `tests/unit/test_ignore_rules.py`
- [x] T008 Implement ignore rules + safety behaviors to make tests pass in `src/analyzers/ignore_rules.py` and `src/analyzers/logging.py`
- [x] T009 Refactor ignore/safety implementation for clarity and maintainability (no behavior change) in `src/analyzers/ignore_rules.py` and `src/analyzers/logging.py`

- [x] T010 Write unit tests for LanguageRouter routing by extension + unknown extension handling in `tests/unit/test_language_router.py`
- [x] T011 Implement LanguageRouter mapping (single authoritative extension→(language, grammar loader, queries)) to make tests pass in `src/analyzers/tree_sitter_analyzer.py`
- [x] T012 Refactor LanguageRouter mapping to remove scattered conditionals and make adding a language a one-entry change in `src/analyzers/tree_sitter_analyzer.py`

- [x] T013 Write unit tests for startup grammar validation and missing-grammar graceful degradation in `tests/unit/test_grammar_loading.py`
- [x] T014 Implement startup grammar validation + missing-grammar skip behavior to make tests pass in `src/analyzers/tree_sitter_analyzer.py`
- [x] T015 Refactor grammar loading/validation code to keep logs clear and avoid duplicated checks in `src/analyzers/tree_sitter_analyzer.py`

- [x] T016 Write unit tests for file discovery applying ignore/unignore + sensitive skipping in `tests/unit/test_file_discovery.py`
- [x] T017 Implement file discovery to make tests pass in `src/analyzers/file_discovery.py`
- [x] T018 Refactor file discovery for readability (no behavior change) in `src/analyzers/file_discovery.py`

- [x] T019 Write unit tests for bounded parse cache behavior (cache hit by content hash; eviction) in `tests/unit/test_parse_cache.py`
- [x] T020 Implement bounded parse cache to make tests pass in `src/analyzers/parse_cache.py`
- [x] T021 Refactor parse cache implementation (no behavior change) in `src/analyzers/parse_cache.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Cold-start static structure map (Priority: P1) 🎯 MVP

**Goal**: Produce a module import graph for a target repo while skipping unsafe/unparseable files safely.

**Independent Test**: Run Surveyor on a repo containing a mix of source files + `.env`/key material and confirm:
- `.cartography/module_graph.json` is produced
- sensitive files are skipped with `skipped_sensitive_file` logs
- the run completes without crashing

### Implementation for User Story 1

- [x] T022 [US1] Write unit tests for `analyze_module(path)` extraction using fixture files in `tests/unit/test_analyze_module.py`
- [x] T023 [US1] Implement minimal Pydantic `ModuleNode` + evidence types needed for tests in `src/models/module.py`
- [x] T024 [US1] Implement `analyze_module(path) -> ModuleNode` to make tests pass in `src/analyzers/tree_sitter_analyzer.py`
- [x] T025 [US1] Refactor `analyze_module` extraction code (imports/functions/classes/inheritance) for maintainability in `src/analyzers/tree_sitter_analyzer.py`

- [x] T026 [US1] Write unit tests for module import graph edges + JSON export shape in `tests/unit/test_module_graph.py`
- [x] T027 [US1] Implement module graph build + `.cartography/module_graph.json` export to make tests pass in `src/agents/surveyor.py`
- [x] T028 [US1] Refactor graph build/export code for clarity (no behavior change) in `src/agents/surveyor.py`

**Checkpoint**: At this point, US1 produces `.cartography/module_graph.json` without ingesting secrets.

---

## Phase 4: User Story 2 - Identify architectural hubs and cycles (Priority: P2)

**Goal**: Add graph analytics (PageRank + SCC cycle detection) to make hubs/cycles discoverable.

**Independent Test**: Run Surveyor on a repo with known import hubs/cycles and confirm:
- top hubs are reproducible from PageRank output
- SCCs identify cycles when present

### Implementation for User Story 2

- [x] T029 [US2] Write unit tests for PageRank stable ordering and SCC cycle detection in `tests/unit/test_graph_analytics.py`
- [x] T030 [US2] Implement PageRank + SCC analytics and persist results to make tests pass in `src/agents/surveyor.py`
- [x] T031 [US2] Refactor analytics code paths (PageRank/SCC/metadata persistence) for clarity in `src/agents/surveyor.py`

**Checkpoint**: US2 enriches the module graph with hub/cycle signals.

---

## Phase 5: User Story 3 - Surface high-velocity files (Priority: P3)

**Goal**: Compute git velocity and identify high-velocity core files.

**Independent Test**: Run velocity extraction on a repo with history and confirm it returns per-file counts and a high-velocity core set.

### Implementation for User Story 3

- [x] T032 [US3] Write unit tests for `extract_git_velocity(path, days=30)` and 80/20 core logic using mocked or fixture git output in `tests/unit/test_git_velocity.py`
- [x] T033 [US3] Implement git velocity parsing + 80/20 core + attach metrics to make tests pass in `src/agents/surveyor.py`
- [x] T034 [US3] Refactor git velocity code for determinism and readability in `src/agents/surveyor.py`

**Checkpoint**: US3 provides change velocity signals for onboarding prioritization.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion
- **User Story 3 (Phase 5)**: Depends on Foundational completion (can be done after US1 if preferred)

### Parallel Opportunities

- [P] Not used in this plan to keep a strict sequential checklist for Phase 1.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (includes sensitive-file exclusions + safe skip logging)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Verify `.cartography/module_graph.json` exists and that sensitive files were skipped safely
