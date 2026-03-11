# Implementation Plan: Phase 2 — Hydrologist Agent (Data Lineage)

**Branch**: `002-hydrologist-data-lineage` | **Date**: 2026-03-11 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification and production-grade constraints from `specs/002-hydrologist-data-lineage/spec.md`

## Summary

Implement the Hydrologist Agent to build a **DataLineageGraph** from mixed Python/SQL/YAML codebases by running three analyzers (PythonDataFlowAnalyzer, SQLLineageAnalyzer, DAGConfigAnalyzer), merging their outputs into a single NetworkX DiGraph, and exposing blast_radius(node), find_sources(), and find_sinks(). Reuse Phase 1 file discovery and ignore/sensitive-file rules; enforce per-file graceful degradation and tree-sitter–based Python detection. Serialize the lineage graph to `.cartography/lineage_graph.json`.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: tree-sitter (Python grammar), sqlglot, NetworkX, Pydantic; Phase 1: file_discovery, ignore_rules  
**Storage**: `.cartography/lineage_graph.json` (lineage artifact); no new DB tables required for Phase 2  
**Testing**: pytest; unit tests per analyzer + DataLineageGraph  
**Target Platform**: Linux CLI (same as Phase 1)  
**Project Type**: CLI + library (Brownfield Cartographer)  
**Performance Goals**: Same repo scale as Phase 1 (50+ files); lineage build in reasonable time  
**Constraints**: Per-file try/except; no regex for Python data-flow detection; visited set for blast_radius  
**Scale/Scope**: Phase 2 only (Hydrologist + DataLineageGraph)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Deliverables and phases match TRP 1 Week 4 (no missing/extra artifacts)
- [x] All node/edge/tool I/O contracts are Pydantic models (DatasetNode, TransformationNode, PRODUCES/CONSUMES)
- [x] Graceful degradation designed: per-file try/except, log+skip, no pipeline-wide crash
- [x] Ignore patterns supported; reuse Phase 1 (`.cartographyignore` / `.cgrignore`-style)
- [x] Incremental update strategy: reuse Phase 1 file discovery; re-analyze only changed files can be added later
- [x] Evidence policy designed: source_file, line_range on transformations; static analysis only in Phase 2
- [x] Tiered LLM plan: N/A for Phase 2 (static only)
- [x] Tasks are a sequential checklist; each task independently completable and testable

## Project Structure

### Documentation (this feature)

```text
specs/002-hydrologist-data-lineage/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (tree-sitter, sqlglot, Airflow/dbt)
├── data-model.md        # Phase 1 (DatasetNode, TransformationNode, edges)
├── quickstart.md        # How to run Hydrologist and use graph API
├── contracts/           # Optional: analyzer output contract
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit.tasks
```

### Source Code (repository root)

```text
src/
├── agents/
│   ├── surveyor.py           # Phase 1 (existing)
│   └── hydrologist.py        # NEW: orchestration, run analyzers, build graph, blast_radius, find_sources, find_sinks
├── analyzers/
│   ├── file_discovery.py     # Phase 1 (reuse)
│   ├── ignore_rules.py       # Phase 1 (reuse)
│   ├── tree_sitter_analyzer.py  # Phase 1 (reuse LanguageRouter / AST where possible)
│   ├── python_data_flow.py   # NEW: PythonDataFlowAnalyzer (tree-sitter queries for pandas/SQLAlchemy/PySpark)
│   ├── sql_lineage.py       # NEW: SQLLineageAnalyzer (sqlglot)
│   └── dag_config_parser.py # NEW: DAGConfigAnalyzer (Airflow DAG + dbt schema.yml)
├── models/
│   ├── module.py            # Phase 1 (existing)
│   ├── knowledge_graph.py   # Phase 1 (DatasetNode, TransformationNode, ProducesEdge, ConsumesEdge exist)
│   └── lineage.py           # NEW (optional): lineage-specific types / re-exports if needed
├── graph/
│   ├── knowledge_graph.py   # Phase 1 (existing; module graph)
│   └── lineage_graph.py     # NEW: DataLineageGraph (NetworkX DiGraph wrapper, merge, blast_radius, find_sources, find_sinks, serialize to .cartography/lineage_graph.json)
└── (cli.py, orchestrator.py) # Extend to invoke Hydrologist (e.g. subcommand or flag)

tests/
├── unit/
│   ├── test_python_data_flow.py   # NEW: PythonDataFlowAnalyzer
│   ├── test_sql_lineage.py        # NEW: SQLLineageAnalyzer
│   ├── test_dag_config.py         # NEW: DAGConfigAnalyzer
│   └── test_data_lineage_graph.py # NEW: DataLineageGraph (blast_radius, find_sources, find_sinks)
└── fixtures/
    ├── lineage/                   # NEW: mini Python/SQL/YAML files for lineage tests
    │   ├── python/
    │   ├── sql/
    │   └── dbt_airflow/
    └── (existing Phase 1 fixtures)
```

**Structure Decision**: Single `src/` tree. PythonDataFlowAnalyzer in `python_data_flow.py` (separate from `sql_lineage.py` and `dag_config_parser.py`). DataLineageGraph in `src/graph/lineage_graph.py` to keep module graph (Phase 1) and lineage graph (Phase 2) clearly separated. Reuse Phase 1 `file_discovery`, `ignore_rules`, and optionally `LanguageRouter`/parsed AST for Python.

---

## Architecture

### Components

| Component | Responsibility |
|-----------|----------------|
| **src/agents/hydrologist.py** | Orchestrates running all three analyzers and building the DataLineageGraph; exposes `blast_radius(node)`, `find_sources()`, `find_sinks()`; calls Phase 1 file discovery once, then dispatches files by type to each analyzer; runs merge step; writes `.cartography/lineage_graph.json`. |
| **src/analyzers/python_data_flow.py** | PythonDataFlowAnalyzer: tree-sitter queries to find pandas read_csv/read_sql, SQLAlchemy execute(), PySpark read/write; extract dataset names/paths from AST; emit CONSUMES/PRODUCES-style edges (or raw node/edge lists for merge). |
| **src/analyzers/sql_lineage.py** | SQLLineageAnalyzer: sqlglot to parse .sql and dbt model files; extract table dependency graph from SELECT/FROM/JOIN/WITH; support PostgreSQL, BigQuery, Snowflake, DuckDB; output DatasetNodes + edges for merge. |
| **src/analyzers/dag_config_parser.py** | DAGConfigAnalyzer: parse Airflow DAG Python files (operators, dependencies) and dbt schema.yml; extract pipeline topology; map to DatasetNode/TransformationNode and edges. |
| **src/models/lineage.py** (or reuse knowledge_graph.py) | Pydantic models for DatasetNode, TransformationNode, and any lineage-specific utility types; re-export or extend `src/models/knowledge_graph.py` so PRODUCES/CONSUMES are consistent. |
| **src/graph/lineage_graph.py** | DataLineageGraph: wrapper around NetworkX DiGraph; ingest nodes/edges from all three analyzers and merge; implement blast_radius (BFS/DFS + visited set), find_sources (in-degree 0), find_sinks (out-degree 0); serialize to `.cartography/lineage_graph.json` in stable, deterministic format. |

---

## PythonDataFlowAnalyzer Design

### Integration with Phase 1

- Reuse **file discovery**: Hydrologist calls `discover_files(repo_root, rules)` with the same `IgnoreRules.default()` as Phase 1; sensitive-file exclusion is already applied there, so no Hydrologist analyzer ever receives a path that Phase 1 would skip.
- Reuse **LanguageRouter** and parsing where possible: For `.py` files, use the same tree-sitter Python grammar (or Phase 1’s stdlib `ast` if tree-sitter Python is not yet wired). Prefer tree-sitter for consistency with spec (tree-sitter queries). If Phase 1 uses `ast` for Python, PythonDataFlowAnalyzer can use tree-sitter for Python only so that one canonical Python AST pipeline exists for data-flow (tree-sitter queries).
- **Where the safeguard is called**: In `hydrologist.py`, before any analyzer runs, call `discover_files(repo_root, IgnoreRules.default())` and filter to the extensions each analyzer needs (e.g. `.py` for PythonDataFlowAnalyzer, `.sql` for SQLLineageAnalyzer, `.py`/`.yml`/`.yaml` for DAGConfigAnalyzer). Do **not** read or parse any file that is not in this discovered list; thus sensitive and ignored files are never opened.

### Tree-sitter queries to identify calls

- **pandas**: `read_csv`, `read_sql` (and optionally `read_parquet`, `read_excel` for consistency). Query pattern: call_expression with function name matching `read_csv` / `read_sql` (e.g. via `pd.read_csv` or `pandas.read_csv`); capture first argument (file path or table/query).
- **SQLAlchemy**: `.execute()` on a connection/engine or text(). Query: method call on an object where method name is `execute`; capture argument (e.g. raw SQL string or text(...)) for table names via sqlglot in a follow-up or simple heuristic for Phase 2.
- **PySpark**: `spark.read.csv`, `spark.read.parquet`, `df.write.saveAsTable`, etc. Query: chained call (e.g. `spark.read` then `.csv(path)` or `.parquet(path)`); capture path/table argument.
- Implementation: Use tree-sitter’s S-expression queries (or equivalent) to match these patterns; from the matched node, use `child_by_field_name("arguments")` (or language-specific API) to get argument nodes. For each argument that should be a dataset path/name, call a helper that only accepts **literal strings** (and optionally simple string concatenation of literals); otherwise log "dynamic reference, cannot resolve" and do not create an edge.

### Safe argument extraction from AST

- **Literal string**: If the argument is a string literal (e.g. `"path/to/file.csv"` or `'table_name'`), use that value as the dataset name/path.
- **Non-literal** (f-string, variable, method call, complex expression): Do not resolve; log `"dynamic reference, cannot resolve"` with file and line; do not add a lineage edge for that call.
- **Determinism**: When a literal is extracted, normalize (e.g. strip whitespace, resolve relative path relative to repo_root if needed) so the same logical dataset gets the same node id across files.

---

## SQLLineageAnalyzer Design

### Parsing with sqlglot

- **Inputs**: Standalone `.sql` files and dbt model SQL files (e.g. in `models/` with or without `ref()`/`source()`).
- **API**: Use `sqlglot.parse(sql, dialect=...)` to get AST; use sqlglot’s table extraction (e.g. `sqlglot.exp.Table` or documented table-reference visitors) to list tables in FROM, JOIN, WITH (CTE), and INSERT/SELECT into.
- **Dialects**: Support at least PostgreSQL, BigQuery, Snowflake, DuckDB. Use `dialect=` parameter; dialect can be inferred from file path (e.g. `models/snowflake/`) or config, or default to a single dialect (e.g. PostgreSQL) with override in plan/tasks.

### From sqlglot AST to nodes and edges

- **Nodes**: Each referenced table becomes a DatasetNode (name = table name, storage_type = `"table"`). Optionally qualify with schema (e.g. `schema.table`).
- **Edges**: For a query that reads tables A, B and writes table C (e.g. CREATE TABLE AS SELECT, or INSERT INTO C SELECT ... FROM A JOIN B), emit CONSUMES from a transformation to A and B, and PRODUCES from that transformation to C. The “transformation” can be represented as a synthetic node (e.g. `transformation:<file>:<line>`) or as TransformationNode with source_file and line_range; edges are (transformation → dataset) for both PRODUCES and CONSUMES.
- **dbt ref()/source()**: In dbt model SQL, `ref('model_name')` and `source('source_name', 'table_name')` are references; resolve to logical table names (e.g. `ref('stg_orders')` → `stg_orders` or project-prefixed name) so they align with nodes from other models. Document resolution in research.md / tasks.

---

## DAGConfigAnalyzer Design

### Parsing Airflow DAG files

- **Input**: Python files that define Airflow DAGs (often identified by convention, e.g. under `dags/`, or by detecting `DAG(` and operator usage). Parse with Python AST or tree-sitter; detect instantiation of `DAG`, `BaseOperator` subclasses (e.g. `PythonOperator`, `BashOperator`, `SqlOperator`), and `set_downstream` / `set_upstream` or `>>` / `<<`.
- **Dataset vs transformation**: Map each **task** (operator instance) to a TransformationNode (source_file, line_range, transformation_type = e.g. "airflow_task"); task_id as identifier. If the operator references a table or file (e.g. via templated field or parameter), treat that as a DatasetNode and add CONSUMES/PRODUCES between task and dataset. Dependencies between tasks are task-to-task; for lineage we care about task ↔ dataset edges so that the merged graph can still compute sources/sinks and blast radius on dataset nodes.

### Parsing dbt schema.yml

- **Input**: YAML files (e.g. `schema.yml`, `sources.yml`) in dbt projects. Parse with a YAML parser; extract `models`, `sources`, and optionally `seeds`. Each model has a `name` and can have `ref()` dependencies in the SQL; each source has `name` and `tables`. Map model name to a dataset (output) and source tables to datasets (inputs); transformations are the dbt model runs (source_file = the YAML or the SQL file, line_range if available).
- **Topology**: In schema.yml, dependency order can be inferred from model names and refs; emit edges CONSUMES (model → upstream ref/source) and PRODUCES (model → self) so that the lineage graph has dataset nodes for each model and source table.

### Mapping to DatasetNode and TransformationNode

- **DatasetNode**: name = table/model/source name; storage_type = `"table"` or `"file"` as appropriate.
- **TransformationNode**: source_datasets = list of upstream refs/sources; target_datasets = [model name or output table]; transformation_type = `"dbt_model"` or `"airflow_task"`; source_file, line_range from config/code.

---

## DataLineageGraph

### Choice: NetworkX DiGraph

- Use **NetworkX DiGraph** to store nodes (dataset identifiers, and optionally transformation identifiers) and directed edges. Edge direction: from upstream (source) to downstream (target), i.e. data flows from source to target. So CONSUMES can be represented as (dataset → transformation) and PRODUCES as (transformation → dataset), or we can flatten to (dataset A → dataset B) when a transformation T has A as input and B as output (A → T → B becomes A → B with optional T metadata on the edge). Spec says “edges represent CONSUMES and PRODUCES”; the merge step will normalize so that the graph used for find_sources/find_sinks and blast_radius is consistent (e.g. all edges are dataset-to-dataset with optional transformation metadata, or mixed node types; design in merge step).

### Ingest and merge from analyzers

- Each analyzer returns a **list of node payloads** (DatasetNode / TransformationNode) and **list of edges** (e.g. (source_id, target_id, edge_type)). Merge step: create one DiGraph; add all nodes by id (deduplicate by node id); add all edges. If two analyzers emit the same dataset id (e.g. same table name), they map to one node. Deterministic ordering: sort node ids and edge lists before add so that serialization is stable.

### blast_radius(node)

- **Algorithm**: BFS (or DFS) starting from `node` (the node id). Use a **visited set** to avoid following cycles infinitely. Follow outgoing edges only (downstream = successors in the direction of data flow). Return the set (or sorted list) of all reached nodes (including `node` if desired, or only downstream; spec says “all downstream dependents”, so typically exclude the start node from the result set for “dependents”).
- **Determinism**: Use a fixed traversal order (e.g. BFS with sorted neighbor order) and return sorted list of node ids so that the result is deterministic.

### find_sources() and find_sinks()

- **find_sources()**: Return all nodes with **in-degree 0** (no incoming edges).
- **find_sinks()**: Return all nodes with **out-degree 0** (no outgoing edges).
- Return type: list of node ids (or list of DatasetNode snapshots); deterministic (e.g. sorted).

### Serialization to .cartography/lineage_graph.json

- **Format**: JSON object with at least: `nodes` (list of node objects with id and schema fields), `edges` (list of { source, target, type? }), and optional `schema_version`. Match Pydantic models so that DatasetNode/TransformationNode and PRODUCES/CONSUMES are serialized; use `model_dump()` and sort keys for stability. Write with `indent=2` and sorted keys so that diffs are readable.

---

## Safeguards & Reuse

### Where Phase 1 ignore and sensitive-file layer is called

- In **hydrologist.py**, at the start of the Hydrologist run:
  1. Call `rules = IgnoreRules.default()` (same as Phase 1).
  2. Call `files = discover_files(repo_root, rules)` (same as Phase 1). This returns only files that pass ignore and sensitive-file rules and have the extensions used by Phase 1 (or pass a superset of extensions including .py, .sql, .yml, .yaml for Hydrologist).
  3. Optionally restrict `discover_files` to Hydrologist-relevant extensions by passing an `exts` parameter that includes `.py`, `.sql`, `.yml`, `.yaml` (and any other needed); ensure `ignore_rules` and sensitive-file logic are unchanged.
- Then: split `files` by extension and pass only the relevant subset to each analyzer (e.g. only `.py` to PythonDataFlowAnalyzer for data-flow; only `.sql` to SQLLineageAnalyzer; `.py` and `.yml`/`.yaml` to DAGConfigAnalyzer). No analyzer receives a path that was not in `files`; hence sensitive and ignored files are never read or parsed.

### Per-file try/except

- In **hydrologist.py** (or inside each analyzer’s “run on repo” method): for each file in the analyzer’s file list, wrap `analyzer.analyze_file(path)` (or equivalent) in try/except; on exception, log a structured warning (e.g. `logging.warning("hydrologist_skip", extra={"path": str(path), "analyzer": "PythonDataFlowAnalyzer", "error": str(e)})`) and continue. Same pattern for SQLLineageAnalyzer and DAGConfigAnalyzer. One bad file must never crash the full run.

---

## Testing Strategy

### Where tests live

- **tests/unit/test_python_data_flow.py**: PythonDataFlowAnalyzer. Fixtures: small Python files in `tests/fixtures/lineage/python/` (e.g. `read_csv_literal.py`, `read_sql_variable.py`, `pyspark_read.py`). Tests: (1) literal path/table name is extracted and appears in output; (2) f-string or variable argument triggers "dynamic reference, cannot resolve" log and no edge for that call.
- **tests/unit/test_sql_lineage.py**: SQLLineageAnalyzer. Fixtures: `tests/fixtures/lineage/sql/` (e.g. simple SELECT from one table; CTE with two tables; INSERT INTO ... SELECT). Tests: verify correct set of input and output tables and that edges match expected CONSUMES/PRODUCES.
- **tests/unit/test_dag_config.py**: DAGConfigAnalyzer. Fixtures: `tests/fixtures/lineage/dbt_airflow/` (minimal Airflow DAG file; minimal dbt schema.yml). Tests: verify extracted task/model nodes and edges.
- **tests/unit/test_data_lineage_graph.py**: DataLineageGraph. Build a small DiGraph in test (e.g. A → B → C, A → C); test find_sources() returns [A], find_sinks() returns [C]; test blast_radius(A) returns {B, C} (or [A, B, C] depending on spec) with visited set and no infinite loop on cycles (add a cycle and ensure blast_radius terminates and returns deterministic set).

### Fixtures

- **tests/fixtures/lineage/python/**: Mini `.py` files with `pd.read_csv("x.csv")`, `pd.read_sql("SELECT ...", conn)`, variable path, f-string path, PySpark read/write.
- **tests/fixtures/lineage/sql/**: Simple `.sql` and dbt-style SQL with ref()/source() if needed.
- **tests/fixtures/lineage/dbt_airflow/**: One minimal Airflow DAG (e.g. two tasks with set_downstream); one minimal schema.yml with one model and one source.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | — | — |
