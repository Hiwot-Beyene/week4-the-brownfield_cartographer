# Feature Specification: Phase 1 — Surveyor Agent (Static Structure)

**Feature Branch**: `001-surveyor-agent`  
**Created**: 2026-03-10  
**Status**: Draft  
**Input**: User description: "@TRP 1 Challenge Week 4_ The Brownfield Cartographer.md — Implement Phase 1 only: Surveyor Agent (Static Structure)"

## Clarifications

### Session 2026-03-10

- Q: Production-grade LanguageRouter + grammar handling? → A: Use a single authoritative extension→(language, grammar, queries) mapping that is easy to extend; validate required grammars at startup and clearly report missing grammars; if a grammar is missing/unavailable at runtime, log and skip that file type without crashing; prefer pip/uv-installed grammar packages and pin/lock them for reproducible installs.
- **Implementation note (Phase 1)**: Python extraction is implemented via the stdlib `ast` module; the LanguageRouter maps `.py`, `.sql`, `.yml`/`.yaml`, `.js`, `.ts`/`.tsx`. Non-Python files receive a minimal ModuleNode with the **correct language label** (e.g. `language="sql"`, `language="yaml"`) from the router; full structural extraction (imports, functions, classes) is Python-only. Git velocity: `extract_git_velocity(repo_root, days=90)` runs `git log --numstat` and writes `.cartography/git_velocity.json`; default 90 days aligns with the challenge question *"What has changed most frequently in the last 90 days?"*.
- **Local and remote repositories**: The system ingests any GitHub repository (or local path) per the challenge mission. The CLI `analyze` command accepts either a local directory path or a Git URL (e.g. `https://github.com/owner/repo`). Remote URLs are cloned (or updated) into a configurable clone directory (under the data dir by default); analysis then runs on the resolved local path. Options: `--branch` for remote ref, `--depth N` for shallow clone (default 1; use `--depth 0` for full history).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cold-start static structure map (Priority: P1)

As an FDE, I want to point the Cartographer at a local path or repository checkout and get a structural map of modules and their import relationships so I can quickly identify architectural hubs and navigate the codebase.

**Why this priority**: A correct module graph is the foundation for later phases (lineage, semantics, onboarding brief) and immediately improves onboarding speed.

**Independent Test**: Run the Surveyor over a real repo and verify it produces `.cartography/module_graph.json` containing a directed module import graph with nodes for analyzed files and edges for imports.

**Acceptance Scenarios**:

1. **Given** a repository with multiple source files, **When** I run the Surveyor analysis, **Then** it writes `.cartography/module_graph.json` and the file contains nodes representing modules and edges representing imports.
2. **Given** a repository containing an unparseable or malformed source file, **When** I run the Surveyor analysis, **Then** the run completes successfully and the problematic file is skipped with a logged error.

---

### User Story 2 - Identify architectural hubs and cycles (Priority: P2)

As an FDE, I want the Surveyor to compute graph signals (PageRank and circular dependency detection) so I can immediately focus on the critical path and risky dependency cycles.

**Why this priority**: Hubs and cycles are high-leverage areas for understanding blast radius and architectural risk.

**Independent Test**: Run the Surveyor over a repo known to have import hubs and/or cycles; verify the output graph includes computed hub rankings and identifies strongly connected components.

**Acceptance Scenarios**:

1. **Given** an import graph, **When** the Surveyor computes PageRank, **Then** the output includes a ranking or score per module sufficient to list the top hubs.
2. **Given** a repo with circular imports, **When** the Surveyor analyzes the graph, **Then** it identifies strongly connected components representing cycles.

---

### User Story 3 - Surface high-velocity files (Priority: P3)

As an FDE, I want the Surveyor to compute change velocity from version control history so I can prioritize files that are frequently modified and likely to be operational hotspots.

**Why this priority**: High-velocity files often correlate with unstable contracts, ongoing refactors, and sources of incidents. The challenge asks: *"What has changed most frequently in the last 90 days (git velocity map)?"*

**Independent Test**: Run the velocity extraction and verify it returns change counts for files over a given window and identifies the high-velocity core (top 20% files responsible for ~80% of changes).

**Acceptance Scenarios**:

1. **Given** a git repository with commit history, **When** I run `extract_git_velocity(repo_root, days=30)` (or `days=90` for the last 90 days), **Then** it returns per-file change frequencies for that window.
2. **Given** the per-file change frequencies, **When** the Surveyor summarizes velocity, **Then** it identifies the high-velocity core using the 80/20 heuristic.
3. **Given** a successful Surveyor run, **When** the run completes, **Then** `.cartography/git_velocity.json` is written with `days`, `per_file`, and `high_velocity_core` (git velocity map for the last 90 days by default).

### Edge Cases

- What happens when the repository contains files in unsupported languages or unknown extensions?
- What happens when a supported file is syntactically invalid or partially written?
- How does the system handle binary files or very large files?
- How does the system behave when git metadata is unavailable (no `.git/`, shallow clone, missing history)?
- How does the system handle dynamic imports or non-literal import targets?
- How does the system behave when encountering environment/secret material (e.g., `.env`, private keys)?

## Constitution Constraints *(mandatory)*

- Implementation MUST follow the TRP 1 Week 4 phases/deliverables/schema.
- All node/edge types and tool outputs MUST be Pydantic models.
- The pipeline MUST gracefully degrade (per-file try/except; log+skip; never crash full run).
- The system MUST support ignore patterns (`.cartographyignore` or `.cgrignore`-style).
- The system SHOULD support incremental updates (re-analyze only changed files when possible).
- All agent outputs MUST cite evidence (source file + line range + method: static vs LLM).
- LLM usage MUST be tiered (cheap/fast for bulk extraction; stronger only for synthesis).
- Work MUST be structured as a sequential checklist; each task independently completable/testable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-000**: Surveyor Phase 1 components MUST be implemented using Test Driven Development (TDD): tests are written before or alongside implementation, and MUST pass locally without Docker.
- **FR-001**: System MUST support tree-sitter based parsing for at least Python, SQL, YAML, and JavaScript/TypeScript files.
- **FR-002**: System MUST provide a LanguageRouter that selects the correct parsing strategy/grammar based on file extension.
- **FR-002a**: LanguageRouter MUST be implemented as a single authoritative mapping from file extension → (language identifier, parser/grammar loader, and language-specific queries), so adding a new language requires adding one entry (no scattered conditionals).
- **FR-002b**: If a required grammar is missing or unavailable, the system MUST gracefully degrade by logging and skipping analysis for that file (or file type) and MUST NOT crash the full run.
- **FR-002c**: System MUST validate required grammars at startup and report a clear error listing missing grammars.
- **FR-002d**: Grammar installation MUST be reproducible: prefer Python-installable grammar packages (pip/uv) over manual compilation, and versions MUST be pinned/locked via `pyproject.toml` + lockfile.
- **FR-003**: System MUST apply ignore patterns (e.g., `.cartographyignore` / `.cgrignore` style) to exclude vendor/build/generated paths, including at minimum: `node_modules/`, `.git/`, and common build/output directories.
- **FR-003a**: System MUST exclude sensitive files and directories by default to ensure the analyzer NEVER ingests secrets from environment files or common secret material.
- **FR-004**: System MUST implement `analyze_module(path)` that returns a `ModuleNode` containing, at minimum:
  - Module identity (path and detected language)
  - Imports (including Python import statements and resolvable relative-path targets)
  - Public functions (excluding private/underscore-prefixed functions; decorated functions included)
  - Class definitions and inheritance (base classes)
- **FR-005**: System MUST define `ModuleNode` as a Pydantic model and MUST use Pydantic models for analyzer outputs.
- **FR-006**: System MUST implement bounded parsing and caching to avoid re-parsing trees excessively and to control memory usage.
- **FR-007**: System MUST implement `extract_git_velocity(repo_root, days=90)` (configurable `days`; default 90 for the challenge question *"What has changed most frequently in the last 90 days?"*) that computes change frequency per file for the given window and MUST write the git velocity map to `.cartography/git_velocity.json` (fields: `days`, `per_file`, `high_velocity_core`).
- **FR-008**: System MUST identify the high-velocity core using the heuristic “top 20% of files responsible for ~80% of changes” based on the computed velocity.
- **FR-009**: System MUST build a module import graph as a directed graph with modules as nodes and import relationships as edges.
- **FR-010**: System MUST compute PageRank over the module import graph and make it possible to list the most imported/central modules.
- **FR-011**: System MUST identify circular dependencies using strongly connected components.
- **FR-012**: System MUST serialize the module import graph to `.cartography/module_graph.json`. System MUST also write the git velocity map to `.cartography/git_velocity.json` (see FR-007).
- **FR-013**: System MUST gracefully degrade: per-file analysis failures MUST be logged and skipped; the overall run MUST still complete.
- **FR-014**: Outputs produced by the Surveyor MUST be evidence-backed: each derived claim (e.g., extracted import/function/class) MUST retain traceability to its source file and the extraction method used (static vs LLM).
- **FR-015**: System MUST exclude, from parsing/indexing/output artifacts, the following by default (non-exhaustive list):
  - Files: `.env`, `.env.*`, `.envrc`, `.secrets`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`
  - Directories: `.env/`, `env/`, `.venv/`, `venv/` (and similar virtual environment directories)
- **FR-016**: Ignore mechanism MUST support explicit exclude and explicit unignore so users can intentionally override defaults.
- **FR-017**: When a file is skipped for safety, the system MUST log an event `skipped_sensitive_file` including the file path and reason, and MUST NOT print file contents.

### Key Entities *(include if feature involves data)*

- **ModuleNode**: A structured representation of a source file/module, including identity, extracted symbols, and import relationships.
- **Module Import Graph**: A directed graph representing module-to-module import relationships, with derived analytics (PageRank, SCCs).
- **Git Velocity Summary / Git velocity map**: Per-file change frequencies over a configurable time window (default 90 days) plus an identified high-velocity core; persisted as `.cartography/git_velocity.json` with `days`, `per_file`, and `high_velocity_core`.
- **Central store (production)**: Each run is persisted so multiple repos/runs do not overwrite each other:
  - **SQLite** (`cartographer.db`): versioned analyses keyed by `repo_id` and `run_at`; tables `analyses`, `modules`, `import_edges` only (Phase 1). Schema includes full ModuleNode fields (path, language, pagerank, purpose_statement, domain_cluster, complexity_score, change_velocity_30d, is_dead_code_candidate, last_modified). NaN/Inf pagerank values are stored as NULL. Existing DBs are migrated via `_migrate_modules_columns` to add new columns if missing.
  - **Vector store (Chroma)**: embeddings of module documents (path, language, function/class names, purpose_statement, domain_cluster, last_modified) for semantic search. Collection name `modules`; embedding model `all-MiniLM-L6-v2`. Optional; degrades gracefully if Chroma/sentence-transformers are unavailable (log + stderr warning, run continues).
  - **Data directory**: Resolved by `get_data_dir(repo_root)`. If `CARTOGRAPHER_DATA_DIR` is set (env or `.env` from repo root or cwd), that path is used. Else if `repo_root` is provided (e.g. when running the surveyor), `repo_root/.cartography` is used (project storage). Else `~/.brownfield-cartographer`. When analyzing a **remote** repo, the orchestrator passes `project_data_dir=Path.cwd()` so SQLite and Chroma are always written to the **invoking project’s** `.cartography/`, not the clone’s.
  - **JSON artifacts**: Four files are **always overwritten** at the end of each run (via `_write_all_json_artifacts`): `file_hashes.json`, `modules.json`, `module_graph.json`, `git_velocity.json`. When the analyzed path is a remote clone, these are also copied into `cwd/.cartography/` so the project always has the latest artifacts.
  - **Deduplication**: Files are deduplicated by resolved absolute path before analysis; modules are deduplicated by resolved path so the modules table and JSON outputs contain no duplicate module rows.
  - **Persistence errors**: SQLite and vector-store writes are in separate try/except blocks; failure of one is logged with full traceback and a warning printed to stderr, but the run completes and JSON artifacts are still written.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a target repo with at least 50 source files, the Surveyor produces `.cartography/module_graph.json` on a single run without crashing.
- **SC-002**: When encountering at least one unparseable file in a supported language, the Surveyor completes and reports the skip in logs.
- **SC-003**: PageRank results can be used to list the top 5 hub modules deterministically from the generated graph.
- **SC-004**: Circular dependencies are detected and represented as strongly connected components in the Surveyor results.
- **SC-005**: Git velocity output reports per-file change frequencies for a specified window (default 90 days for the challenge question) and identifies a high-velocity core; `.cartography/git_velocity.json` is produced on each run.
- **SC-006**: When the target repo contains `.env`/key material (e.g., `.env`, `id_rsa`, `*.pem`), the Surveyor skips these files, emits `skipped_sensitive_file` logs (path + reason), and no output artifact contains their contents.
- **SC-007**: Phase 1 unit tests run locally without Docker and validate, at minimum:
  1) LanguageRouter routes `.py`, `.sql`, `.yml`/`.yaml`, `.js`, `.ts`/`.tsx` and handles unknown extensions gracefully
  2) `analyze_module(path)` extracts imports, public functions, classes, and inheritance on small fixture files
  3) `extract_git_velocity(repo_root, days)` parses git output robustly, returns {} when not a git repo (graceful degradation), and returns deterministic results using a fixture or mocked git output
  4) Module import graph build produces expected edges; PageRank ordering is stable on a small known graph; SCC detects cycles
  5) Ignore & safety: default ignore patterns work; sensitive files (e.g., `.env`, `.env.*`) are skipped by default and never read/parsed

---

## Implementation summary (for future developers)

This section documents how Phase 1 is **actually implemented** so future developers are not confused by the codebase.

### Entry points and flow

- **CLI**: `python -m src.cli analyze <repo>` where `repo` is a local path or Git URL (e.g. `https://github.com/owner/repo`). Options: `--branch`, `--depth` (default 1; 0 = full history).
- **Orchestrator**: `src/orchestrator.analyze(repo_input, branch, clone_depth)` calls `repo_resolver.resolve_repo()` to get a local path (cloning if remote), then `run_surveyor(repo_path, project_data_dir=Path.cwd())`, then copies the four JSON artifacts from the analyzed repo’s `.cartography/` into `cwd/.cartography/`.
- **Surveyor**: `src/agents/surveyor.run_surveyor(repo_root, project_data_dir=None)` does: file discovery (ignore/safety) → content-hash-based incremental analysis with `analyze_module(path, router)` → build NetworkX graph, PageRank, SCCs → persist to SQLite and Chroma (using `store_root = project_data_dir or repo_root`) → call `_write_all_json_artifacts()` to overwrite all four JSON files in `repo_root/.cartography/`.

### Language routing

- **Router**: `src/analyzers/tree_sitter_analyzer.LanguageRouter.default()` maps extensions `.py`, `.sql`, `.yml`, `.yaml`, `.js`, `.ts`, `.tsx` to language ids (e.g. `python`, `sql`, `yaml`, `javascript`, `typescript`). Unknown extensions are not routed (caller may treat as `"unknown"`).
- **analyze_module(path, router=None)**: Uses `router.route(path)` to set `ModuleNode.language`. Only Python (`.py`) gets full AST extraction (imports, public_functions, classes); other supported extensions get a minimal ModuleNode with correct `language` and empty structural lists. So **no file is labeled "unknown"** if its extension is in the router.

### Local vs remote repository

- **Resolver**: `src/repo_resolver.resolve_repo(repo_input, clone_root=None, branch=None, depth=1)`. Local paths must exist and be directories; remote URLs (GitHub HTTPS/SSH or generic `git@`/`https://`) are cloned via `clone_or_update_remote()` into `clone_root` (default `get_data_dir(Path.cwd())/"cloned"`), with slug from URL (e.g. `owner_repo`). Clone directory is under the **project’s** data dir so clones live in `.cartography/cloned/` when using project storage.
- **Storage location**: For both local and remote analysis, the orchestrator passes `project_data_dir=Path.cwd()`, so `get_data_dir(store_root)` with `store_root=cwd` yields `cwd/.cartography` (unless `CARTOGRAPHER_DATA_DIR` is set). Thus SQLite and Chroma always live in the **project** that ran the command; JSON artifacts are written in the analyzed repo’s `.cartography/` and then copied to `cwd/.cartography/` so the project always has the latest outputs.

### Database integration

- **SQLite**: `src/store/sqlite_store`. `get_data_dir(repo_root)` loads `.env` from repo root or cwd and returns `CARTOGRAPHER_DATA_DIR` if set, else `repo_root/.cartography` if repo_root given, else `~/.brownfield-cartographer`. `init_db(db_path)` creates tables `analyses`, `modules`, `import_edges` and runs `_migrate_modules_columns`. `insert_analysis(repo_root, artifacts_dir, modules, pagerank_by_path, edges, db_path)` inserts one run; pagerank is stored with non-finite values converted to NULL via `_safe_float`.
- **Chroma**: `src/store/vector_store`. Persist dir is `get_data_dir(repo_root)/"chroma"`. `init_vector_store(persist_dir, repo_root)` creates a persistent client and `modules` collection with `SentenceTransformerEmbeddingFunction("all-MiniLM-L6-v2")`. `add_modules_to_vector_store(analysis_id, repo_id, modules, persist_dir)` adds module documents; IDs include analysis_id for multiple runs. If Chroma or sentence-transformers are missing, the surveyor catches exceptions, logs, and prints a stderr warning without failing the run.

### Artifacts and schema

- **JSON files** (all in `.cartography/`, overwritten each run): `file_hashes.json` (path → SHA256), `modules.json` (list of ModuleNode dicts), `module_graph.json` (Knowledge Graph shape: `nodes` with `type: "module"` and schema fields, `edges` with `type: "IMPORTS"`, `source`, `target`, `weight`), `git_velocity.json` (`days`, `per_file`, `high_velocity_core`).
- **module_graph.json** is produced by `build_knowledge_graph_payload()` when full module/graph/velocity data is available; otherwise `write_module_graph_json()` can write a graph-only fallback (nodes from graph, edges with weight 1).
- **Pydantic models**: `src/models/module` (ModuleNode, Evidence, ImportRef, FunctionRef, ClassRef); `src/models/knowledge_graph` (DatasetNode, FunctionNode, TransformationNode, edge types including ImportEdge; Phase 1 only populates module nodes and IMPORTS edges).

### Ignore and safety

- **IgnoreRules.default()** in `src/analyzers/ignore_rules` includes sensitive file/dir patterns (e.g. `.env`, `*.pem`, `id_rsa`, `.venv/`). File discovery uses these so such paths are never read or parsed; when a file is skipped for safety, the system logs `skipped_sensitive_file` (path + reason) and never prints file contents.
- **.gitignore**: The repo ignores the entire `.cartography/` directory and `/module_graph.json` at repo root so generated outputs and DBs are not committed; re-run the surveyor to regenerate locally.