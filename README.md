# Brownfield Cartographer

Ingest any GitHub repository (or local path) and produce a queryable knowledge graph: **module graph** (Surveyor) and **data lineage graph** (Hydrologist). Outputs are serialized under `.cartography/`.

## Repository structure

```
src/
  cli.py                    # Entry point: takes repo path (local or GitHub URL), runs analysis
  orchestrator.py           # Wires Surveyor + Hydrologist in sequence, serializes to .cartography/
  repo_resolver.py          # Resolves local path or clones GitHub URL
  models/                   # All Pydantic schemas (Node types, Edge types, Graph types)
    module.py
    knowledge_graph.py
    lineage.py
  analyzers/
    tree_sitter_analyzer.py # Multi-language AST parsing with LanguageRouter
    sql_lineage.py          # sqlglot-based SQL dependency extraction
    dag_config_parser.py    # Airflow / dbt YAML config parsing
    python_data_flow.py     # Python data-flow (pandas, SQLAlchemy, PySpark)
    file_discovery.py
    ignore_rules.py
  agents/
    surveyor.py             # Module graph, PageRank, git velocity, dead-code candidates
    hydrologist.py          # DataLineageGraph, blast_radius, find_sources/find_sinks
  graph/
    knowledge_graph.py      # NetworkX wrapper with serialization (module graph)
    lineage_graph.py        # DataLineageGraph with serialization (lineage)
  store/                    # SQLite + optional vector store
```

## Install

**Using pip (any venv/conda):**

```bash
pip install -r requirements.txt
# or editable
pip install -e .
```

**Using uv (locked deps):**

```bash
uv sync
# or create lockfile from pyproject.toml
uv lock
uv sync
```

## Run analysis

From the repository root:

**Full analysis (Surveyor + Hydrologist)** — produces both `module_graph.json` and `lineage_graph.json` in `.cartography/`:

```bash
python -m src.cli analyze .
```

**Local path or GitHub URL:**

```bash
python -m src.cli analyze /path/to/repo
python -m src.cli analyze https://github.com/owner/repo
```

**Survey only (no lineage):**

```bash
python -m src.cli analyze . --skip-lineage
```

**Lineage only** (e.g. for an already-cloned repo):

```bash
python -m src.cli lineage .
```

**Options:**

- `--output-dir DIR` / `-o DIR` — write `.cartography/` under `DIR` (default: current directory)
- `--branch BRANCH` / `-b BRANCH` — branch to use when cloning a remote repo
- `--depth N` — clone depth (default 1); use 0 for full history
- `-v` / `--verbose` — progress logging

## Cartography artifacts

After a successful run, at least one target codebase produces:

| Artifact | Description |
|----------|-------------|
| `.cartography/module_graph.json` | Module graph (Surveyor): nodes, IMPORTS edges, PageRank, SCCs |
| `.cartography/lineage_graph.json` | Data lineage (Hydrologist); at minimum SQL lineage via sqlglot |

Additional artifacts: `file_hashes.json`, `git_velocity.json`, `modules.json`, `survey_summary.json`.

## Tests

```bash
pytest -q
# or
uv run pytest -q
```
