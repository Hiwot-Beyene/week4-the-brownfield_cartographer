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
│   └── surveyor.py
├── analyzers/
│   └── tree_sitter_analyzer.py
├── graph/
│   └── knowledge_graph.py
├── models/
│   └── (pydantic schemas for Phase 1)
├── repo_resolver.py      # Resolve local path or GitHub/Git URL → local Path (clone if remote)
├── store/
│   ├── sqlite_store.py   # Central SQLite: analyses, modules, import_edges
│   └── vector_store.py   # Chroma: semantic search over modules
└── (cli/orchestrator)

.cartography/   (per-repo, latest run)
├── module_graph.json
├── git_velocity.json
├── file_hashes.json
└── modules.json

~/.brownfield-cartographer/   (or repo .cartography/; CARTOGRAPHER_DATA_DIR)
├── cartographer.db   # SQLite: versioned runs
├── chroma/           # Chroma persistent vector store
└── cloned/           # Cloned remote repos (owner_repo per URL)
```

**Repository input (local and remote)**: The CLI `analyze` command accepts either a local path or a Git URL (e.g. `https://github.com/owner/repo`). `repo_resolver.resolve_repo()` detects remote URLs and clones (or pulls) into `get_data_dir(cwd)/cloned/<slug>`; local paths are resolved as-is. Surveyor and store then run on the resolved local path. Options: `--branch`, `--depth` (shallow clone; 0 = full history).

**Structure Decision**: Single project under `src/` with clear separation: `models/` (Pydantic), `analyzers/` (parsing/extraction), `agents/` (Surveyor orchestration), `graph/` (NetworkX wrappers + serialization).

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
- **analyze_module(path) → ModuleNode**:
  - Extract imports for Python (and a minimal best-effort strategy for other languages where feasible in Phase 1).
  - Extract public functions and classes with inheritance from AST queries.
  - Retain evidence metadata (source file path, line ranges) for each extracted element.
- **Git velocity (git velocity map)**: Answer the challenge question *"What has changed most frequently in the last 90 days?"* by running `extract_git_velocity(repo_root, days=90)` (configurable). Parse `git log --numstat` for the window; compute per-file change counts; derive 80/20 “high velocity core”. Write `.cartography/git_velocity.json` with `days`, `per_file`, and `high_velocity_core`. If not a git repo or git fails, return empty and still complete the run (graceful degradation).
- **Graph build**: Create NetworkX DiGraph from ModuleNodes/imports, compute PageRank, compute SCCs, attach results as node/graph metadata.
- **Serialization**: Use NetworkX JSON serialization to write `.cartography/module_graph.json`. Write `.cartography/git_velocity.json` for the git velocity map (90-day default).
- **Central store (SQLite + vector)**: After each run, persist to a central data dir so multiple repos/runs do not overwrite each other. SQLite holds `analyses` (repo_id, commit_sha, run_at, artifacts_dir), `modules` (analysis_id, path, language, pagerank), and `import_edges` (analysis_id, source_module, target_module, weight). Chroma holds module documents (path + symbols, and later purpose_statement) for semantic search; if Chroma or sentence-transformers are missing, vector indexing is skipped (graceful degradation). Data dir defaults to `~/.brownfield-cartographer`, overridable via `CARTOGRAPHER_DATA_DIR`.

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
