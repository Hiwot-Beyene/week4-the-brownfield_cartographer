# Implementation Plan: Phase 1 — Surveyor Agent (Static Structure)

**Branch**: `001-surveyor-agent` | **Date**: 2026-03-10 | **Spec**: `./spec.md`
**Input**: Feature specification from `/specs/001-surveyor-agent/spec.md`

**Note**: Phase 1 only (Surveyor). Later phases (Hydrologist/Semanticist/Archivist/Navigator) are out of scope.

## Summary

Implement the Surveyor Agent to statically analyze a target repository and produce a module import graph with hub/cycle signals and git velocity, using tree-sitter for multi-language parsing and NetworkX for graph analytics, while enforcing ignore patterns, bounded parsing cache, and graceful degradation.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: tree-sitter (core + grammar packages), NetworkX, Pydantic  
**Storage**: Filesystem artifacts under `.cartography/`  
**Testing**: pytest (Phase 1 = fast local unit tests only; no Docker)  
**Target Platform**: Linux CLI  
**Project Type**: CLI + library modules  
**Performance Goals**: Handle repos with 50+ files without re-parsing unchanged files excessively  
**Constraints**: Must not crash on unparseable files; bounded AST/cache memory  
**Scale/Scope**: Phase 1 only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Deliverables and phases match TRP 1 Week 4 (no missing/extra artifacts)
- [x] All node/edge/tool I/O contracts are Pydantic models (no primary dict contracts)
- [x] Graceful degradation designed: per-file try/except, log+skip, no pipeline-wide crash
- [x] Ignore patterns supported (`.cartographyignore` or `.cgrignore`-style)
- [x] Incremental update strategy defined (content hash and/or git; re-analyze changed files)
- [x] Evidence policy designed: every output cites file+line range+method (static vs LLM)
- [x] Tiered LLM plan: cheap model for bulk extraction; strong model only for synthesis
- [x] Tasks are a sequential checklist; each task independently completable and testable

## Project Structure

### Documentation (this feature)

```text
specs/001-surveyor-agent/
├── plan.md
├── spec.md
├── tasks.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
src/
├── agents/
│   └── surveyor.py         # run_surveyor(), graph build, _write_all_json_artifacts(), DB/Chroma persistence
├── analyzers/
│   ├── tree_sitter_analyzer.py  # LanguageRouter, analyze_module(path, router), validate_required_grammars
│   ├── ignore_rules.py          # IgnoreRules.default() — vendor + sensitive file/dir patterns
│   ├── file_discovery.py        # discover_files(repo_root, rules)
│   └── parse_cache.py           # Bounded cache for parsed trees
├── graph/
│   └── knowledge_graph.py  # KnowledgeGraph class; write_module_graph uses fallback graph-only payload
├── models/
│   ├── module.py           # ModuleNode, Evidence, ImportRef, FunctionRef, ClassRef (full KG schema fields)
│   └── knowledge_graph.py  # DatasetNode, FunctionNode, TransformationNode, edge Pydantic models (Phase 1 uses IMPORTS only)
├── repo_resolver.py        # is_remote_repo(), resolve_repo(), clone_or_update_remote(); slug from GitHub/generic URL
├── store/
│   ├── sqlite_store.py    # get_data_dir(repo_root), init_db(), insert_analysis(), _migrate_modules_columns, _safe_float
│   └── vector_store.py    # init_vector_store(), add_modules_to_vector_store(), _module_document(); Chroma "modules" collection
├── cli.py                  # analyze repo [--branch] [--depth N]
└── orchestrator.py         # analyze(repo_input, branch, clone_depth) → resolve_repo, run_surveyor(project_data_dir=cwd), _copy_json_artifacts_to_cwd
```

**Output and storage (implementation)**:

- **Per-run JSON artifacts** (overwritten every run, in the **analyzed** repo’s `.cartography/`): `file_hashes.json`, `modules.json`, `module_graph.json`, `git_velocity.json`. Written in one place at end of `run_surveyor` via `_write_all_json_artifacts()`. When the analyzed path is a **remote clone**, the orchestrator copies these four files into **cwd/.cartography/** so the project that ran the command always has the latest artifacts.
- **SQLite and Chroma** are stored in the **invoking project’s** data directory: `run_surveyor(repo_path, project_data_dir=Path.cwd())` uses `store_root = project_data_dir or repo_root`, and `get_data_dir(store_root)` resolves to `cwd/.cartography` (unless `CARTOGRAPHER_DATA_DIR` is set). So for both local and remote analysis, `cartographer.db` and `chroma/` live under the project that executed `analyze`.
- **Data directory resolution** (`get_data_dir(repo_root)`): (1) Load `.env` from `repo_root/.env` or cwd `.env`. (2) If `CARTOGRAPHER_DATA_DIR` is set, use it. (3) Else if `repo_root` is provided, use `repo_root/.cartography`. (4) Else use `~/.brownfield-cartographer`. Cloned remotes live under `get_data_dir(Path.cwd())/cloned/<slug>`.

```text
.cartography/   (in project or repo; created by surveyor)
├── file_hashes.json
├── modules.json
├── module_graph.json      # Knowledge Graph schema: nodes[type, id, path, language, ...], edges[type IMPORTS, source, target, weight]
├── git_velocity.json
├── cartographer.db        # SQLite: analyses, modules, import_edges (Phase 1 only)
├── chroma/                # Chroma persistent client; collection "modules"
└── cloned/                # Only when analyzing remote: owner_repo clones
```

**Repository input (local and remote)**:

- CLI: `analyze <repo>` with `repo` = local path or Git URL. `--branch`, `--depth` (default 1; 0 = full history).
- `repo_resolver.resolve_repo(repo_input, clone_root=None, branch=None, depth=1)`: local path must exist and be a directory; remote URLs (GitHub HTTPS/SSH, or generic `git@`/`http(s)://`) are cloned into `clone_root` (default `get_data_dir(Path.cwd())/"cloned"`) with slug from URL (e.g. `owner_repo`). `clone_or_update_remote()` does `git pull --rebase` if clone already exists.

**Structure decision**: Single project under `src/` with clear separation: `models/` (Pydantic), `analyzers/` (parsing, ignore, discovery, cache), `agents/` (Surveyor), `graph/` (NetworkX + serialization), `store/` (SQLite + Chroma), `repo_resolver` for local/remote resolution.

## Design Notes (Phase 1)

- **LanguageRouter (production-grade)**:
  - Implement routing as a single authoritative mapping: file extension → (language identifier, grammar/parser loader, and language-specific queries).
  - Make it extensible: adding a new language requires adding one entry (no scattered conditionals).
  - Graceful degradation: if a grammar is missing/unavailable, log and skip that file type; do not crash the whole run.
  - Startup validation: assert required grammars load at startup; if any are missing, fail fast with a clear error listing missing grammars.
- **Grammar installation (reproducible)**:
  - Prefer Python-installable grammar packages (pip/uv) over manual compilation.
  - Document and pin Phase 1 packages in `pyproject.toml` and lock via `uv.lock` (or equivalent lockfile).
  - Phase 1 minimum dependency set to pin/lock includes: `pydantic`, `networkx`, `tree-sitter`, and a Python-provided bundle or per-language grammar packages covering Python/SQL/YAML/JS/TS.
- **Bounded parse cache**: Cache parsed trees keyed by `(path, content_hash)` with an upper bound (count or estimated size). Evict least-recently-used entries.
- **Per-file resilience**: Wrap parse and extraction per file; on exception, log `{path, error, analyzer_stage}` and continue.
- **Ignore patterns**: Load ignore file (if present) and apply default excludes (`.git/`, `node_modules/`, build artifacts).
  - **Production safety**: Exclude sensitive files and directories by default so the analyzer NEVER ingests secrets.
    - Default sensitive file excludes (non-exhaustive): `.env`, `.env.*`, `.envrc`, `.secrets`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`.
    - Default sensitive directory excludes (non-exhaustive): `.env/`, `env/`, `.venv/`, `venv/`.
  - **Override**: Ignore mechanism must support explicit exclude + explicit unignore so users can opt-in intentionally.
  - **Safe logging**: When skipping for safety, log `skipped_sensitive_file` with `{path, reason}` and NEVER print file contents.
  - Treat ignore match as “do not analyze”.
- **analyze_module(path, router=None) → ModuleNode** (as implemented):
  - Uses `LanguageRouter.default()` (or passed router); `router.route(path)` sets language from extension (`.py`→python, `.sql`→sql, `.yml`/`.yaml`→yaml, `.js`→javascript, `.ts`/`.tsx`→typescript). Unknown extensions yield `language="unknown"`; all mapped extensions get the correct language label (no "unknown" for .sql/.yml/.js/.ts).
  - Python (`.py`): full extraction via stdlib `ast` — imports, public functions, classes with bases; evidence (source_file, start_line, end_line, method) on each ref.
  - Non-Python: return minimal ModuleNode with correct `language` and empty imports/public_functions/classes.
  - Surveyor deduplicates files by resolved path before calling analyze_module; deduplicates modules by resolved path before graph build and persistence.
- **Git velocity (git velocity map)**: Answer the challenge question *"What has changed most frequently in the last 90 days?"* by running `extract_git_velocity(repo_root, days=90)` (configurable). Parse `git log --numstat` for the window; compute per-file change counts; derive 80/20 “high velocity core”. Write `.cartography/git_velocity.json` with `days`, `per_file`, and `high_velocity_core`. If not a git repo or git fails, return empty and still complete the run (graceful degradation).
- **Graph build**: Create NetworkX DiGraph from ModuleNodes/imports, compute PageRank, compute SCCs, attach results as node/graph metadata.
- **Serialization**: All four JSON artifacts are written once at end of run via `_write_all_json_artifacts()`. `module_graph.json` uses Knowledge Graph schema: `nodes` (type, id, path, language, pagerank, purpose_statement, domain_cluster, complexity_score, change_velocity_30d, is_dead_code_candidate, last_modified, imports, public_functions, classes), `edges` (type `IMPORTS`, source, target, weight). `write_module_graph_json()` supports a fallback when only the NetworkX graph is available (graph-only nodes/edges). `git_velocity.json`: `days`, `per_file`, `high_velocity_core`.
- **Central store (SQLite + vector)** (as implemented):
  - **Data dir**: `get_data_dir(repo_root)` — env `CARTOGRAPHER_DATA_DIR` (from `.env` at repo root or cwd) overrides; else `repo_root/.cartography` if repo_root given, else `~/.brownfield-cartographer`. When analyzing a remote repo, orchestrator passes `project_data_dir=Path.cwd()` so store_root is cwd and DB/Chroma go to **project** `.cartography/`.
  - **SQLite**: Tables `analyses`, `modules`, `import_edges` only. Modules table includes full ModuleNode columns (path, language, pagerank, purpose_statement, domain_cluster, complexity_score, change_velocity_30d, is_dead_code_candidate, last_modified). `_migrate_modules_columns` adds missing columns to existing DBs. Non-finite pagerank stored as NULL (`_safe_float`).
  - **Chroma**: Persist dir = data_dir / `chroma`; collection `modules`; embedding `all-MiniLM-L6-v2`. Module document text includes path, language, function/class names, purpose_statement, domain_cluster, last_modified.
  - **Error handling**: SQLite and vector persistence are in separate try/except in surveyor; failure logs full traceback and prints stderr warning but run continues; JSON artifacts are always written.
- **Deduplication**: Files deduplicated by resolved absolute path before analysis; modules deduplicated by resolved path so modules list and DB have no duplicate module rows.

## Testing Strategy (Phase 1)

- **Approach**: Test Driven Development (TDD). For each capability, write unit tests first (or alongside) and keep feedback loops fast.
- **Scope**: Phase 1 is **unit tests only**. No Docker. No network. Avoid integration tests until later phases.
- **Tooling**: `pytest` as the test runner.
- **Fixtures**:
  - Use small deterministic “fixture repos” and files under `tests/fixtures/` (e.g., tiny Python modules, tiny SQL/YAML files).
  - For git velocity, prefer mocked `git` output or a controlled fixture history so results are deterministic.
- **Test targets (minimum)**:
  - LanguageRouter routing by extension (+ unknown extension handling).
  - `analyze_module(path)` extraction for imports, public functions, classes, inheritance using fixture files.
  - `extract_git_velocity(repo_root, days)` parsing robustness, determinism, and graceful degradation when not a git repo (returns {}).
  - Graph build edges + stable PageRank ordering on a known graph + SCC cycle detection.
  - Ignore and safety: default ignores apply; sensitive files are skipped and never read/parsed; skip logs do not include contents.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
