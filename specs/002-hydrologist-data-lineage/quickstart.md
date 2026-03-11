# Quickstart: Phase 2 — Hydrologist Agent (Data Lineage)

**Branch**: 002-hydrologist-data-lineage | **Date**: 2026-03-11

How to run the Hydrologist and use the DataLineageGraph API (blast_radius, find_sources, find_sinks) and artifact.

---

## Prerequisites

- Python 3.11+, same as Phase 1.
- Dependencies: tree-sitter (Python), sqlglot, NetworkX, Pydantic; Phase 1 deps (file_discovery, ignore_rules).
- Repository to analyze (local path or clone); Phase 1 Surveyor can be run first to produce module graph; Hydrologist can run independently for lineage-only.

---

## Running the Hydrologist

(Exact entry point will be defined in tasks; one of the following patterns.)

**Option A — CLI subcommand**:

```bash
python -m src.cli analyze /path/to/repo    # Phase 1 Surveyor
python -m src.cli lineage /path/to/repo    # Phase 2 Hydrologist; writes to project .cartography/lineage_graph.json
```

When run from the project root, `lineage` writes **to the project’s** `.cartography/` (current working directory), so the latest lineage analysis is kept there for both local and cloned repos.

**Option B — Programmatic**:

```python
from pathlib import Path
from src.agents.hydrologist import run_hydrologist

repo_root = Path("/path/to/repo")
# Write to project .cartography (e.g. cwd) so latest analysis is kept there
graph = run_hydrologist(repo_root, project_data_dir=Path.cwd())
# Artifact written to project_data_dir / ".cartography" / "lineage_graph.json"
# Without project_data_dir, artifact is written to repo_root / ".cartography" / "lineage_graph.json"
```

---

## Using the DataLineageGraph API

Assume `graph` is a `DataLineageGraph` instance (wrapper around NetworkX DiGraph).

### find_sources()

Entry points (nodes with no incoming edges):

```python
sources = graph.find_sources()  # list[str] of node ids
```

### find_sinks()

Exit points (nodes with no outgoing edges):

```python
sinks = graph.find_sinks()  # list[str] of node ids
```

### blast_radius(node_id)

All downstream dependents from a node (e.g. “what is affected if this table changes”):

```python
downstream = graph.blast_radius("my_table")  # set[str] or list[str] of node ids
```

Uses BFS/DFS with a visited set; deterministic (e.g. sorted result).

---

## Artifact: .cartography/lineage_graph.json

When run via the CLI (from project root), lineage is written to the **project’s** `.cartography/lineage_graph.json` (current working directory), so the latest analysis is kept there for both local and cloned repos. When calling `run_hydrologist` programmatically, pass `project_data_dir=Path.cwd()` to get the same behavior. Format (stable, deterministic):

- **nodes**: List of objects with id and schema fields (DatasetNode / TransformationNode).
- **edges**: List of { source, target [, type ] }.
- **schema_version**: Optional integer for compatibility.

Use for downstream tooling, diffing between runs, or loading the graph in another process.

---

## End-to-end example

From repo root, run lineage on the fixtures (or any path with `.py`/`.sql`/`.yml`):

```bash
python -m src.cli lineage tests/fixtures/lineage
```

Then:

1. `.cartography/lineage_graph.json` is written in the **project root** (cwd), so the latest analysis is kept there.
2. Programmatic use: `graph = run_hydrologist(Path("tests/fixtures/lineage"), project_data_dir=Path.cwd()); graph.find_sources(); graph.find_sinks(); graph.blast_radius("data/file.csv")`.

---

## File discovery and safety

Hydrologist uses the **same** file discovery and ignore/sensitive-file rules as Phase 1. Only files that pass `discover_files(repo_root, IgnoreRules.default())` are considered; sensitive files (e.g. `.env`, `*.pem`) are never read or parsed. Per-file parse failures are logged and skipped without failing the run.
