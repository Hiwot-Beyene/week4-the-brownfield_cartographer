---
description: "Task list for Phase 2 Hydrologist Agent (Data Lineage)"
---

# Tasks: Phase 2 — Hydrologist Agent (Data Lineage)

**Input**: Design documents from `specs/002-hydrologist-data-lineage/` (spec.md, plan.md, data-model.md, contracts/)

**Prerequisites**: plan.md (required), spec.md (required)

**Tests**: TDD required — write tests first for each functional piece, then implement to make tests pass.

**Organization**: Tasks grouped by setup → PythonDataFlowAnalyzer → SQLLineageAnalyzer → DAGConfigAnalyzer → DataLineageGraph → final validation. Each analyzer phase: fixtures → tests → implementation → integration.

**Cartographer constraints**: Sequential checklist; each task has explicit file paths and verification step.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = lineage trace/sources/sinks, US2 = blast radius, US3 = graceful degradation
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup & Plumbing

**Purpose**: Wire Hydrologist entrypoint, reuse Phase 1 file-scanning and ignore/sensitive-file exclusion, and prepare lineage types and fixture layout.

- [x] T001 Add Phase 2 dependencies to `pyproject.toml` and `requirements.txt`: sqlglot; ensure tree-sitter (Python) is available for PythonDataFlowAnalyzer. Run `pip install -e .` or `pip install -r requirements.txt` and verify imports.

- [x] T002 [P] Create `tests/fixtures/lineage/` directory structure: `tests/fixtures/lineage/python/`, `tests/fixtures/lineage/sql/`, `tests/fixtures/lineage/dbt_airflow/`. Add a README or placeholder so the directories are tracked. Verification: directories exist.

- [x] T003 [P] Ensure DatasetNode and TransformationNode (and ProducesEdge/ConsumesEdge) are importable for lineage. If needed, add `src/models/lineage.py` that re-exports from `src/models/knowledge_graph.py`, or document that analyzers import directly from `src.models.knowledge_graph`. Verification: `from src.models.knowledge_graph import DatasetNode, TransformationNode` (and edges) works.

- [x] T004 Create `src/agents/hydrologist.py` stub: define `run_hydrologist(repo_root: Path) -> "DataLineageGraph"` (return type can be a forward ref or None initially). Inside: call `discover_files(repo_root, IgnoreRules.default())` from `src.analyzers.file_discovery` and `src.analyzers.ignore_rules`; filter the returned list to extensions `.py`, `.sql`, `.yml`, `.yaml`; do not read any file yet. Return a placeholder or raise NotImplementedError. Verification: import runs; calling with a Path does not read sensitive or ignored paths (unit test or manual check that only discover_files is used).

- [x] T005 Add Hydrologist entrypoint to CLI: in `src/cli.py`, add a subcommand (e.g. `lineage`) that takes a repo path and calls `run_hydrologist(Path(repo))`; or add a flag to the existing `analyze` command to also run lineage. Document in `specs/002-hydrologist-data-lineage/quickstart.md` which command to use. Verification: `python -m src.cli lineage /path/to/repo` (or equivalent) runs without error (may return or print placeholder).

- [x] T006 In `src/agents/hydrologist.py`, add per-file try/except scaffolding: for a given list of files, loop over files and call a placeholder `_analyze_python_file(path)` (or similar) in try/except; on exception log a structured warning with path and analyzer name and continue. Verification: unit test that a failing file (e.g. invalid Python) is skipped and run completes.

---

## Phase 2: PythonDataFlowAnalyzer (TDD)

**Purpose**: Implement PythonDataFlowAnalyzer with tree-sitter queries; literal path extraction only; "dynamic reference, cannot resolve" for non-literals. (US1, US3)

**Independent Test**: Run PythonDataFlowAnalyzer on fixture with `pd.read_csv("x.csv")` and on fixture with `pd.read_csv(path_var)`; assert first yields a dataset node/edge and second logs dynamic reference and yields no edge.

- [x] T007 [US1] [US3] Create fixture files in `tests/fixtures/lineage/python/`: (1) `read_csv_literal.py` with `pd.read_csv("data/file.csv")`; (2) `read_sql_variable.py` with `pd.read_sql("SELECT 1", conn)` and one with a variable as path; (3) `dynamic_ref.py` with `pd.read_csv(f"{base}/x.csv")` or `pd.read_csv(some_var)`. Verification: files exist and contain the expected code.

- [x] T008 [US1] [US3] Write unit tests in `tests/unit/test_python_data_flow.py`: (1) test that analyzing `read_csv_literal.py` returns at least one dataset with name/path equal to the literal string; (2) test that analyzing `dynamic_ref.py` (or variable-path fixture) triggers a log/capture of "dynamic reference, cannot resolve" and no lineage edge is added for that call; (3) test that invalid Python file is skipped (exception caught) and run continues. Run pytest; tests must FAIL (red). Verification: `pytest tests/unit/test_python_data_flow.py -v` fails for missing implementation.

- [x] T009 [US1] [US3] Implement `src/analyzers/python_data_flow.py`: define class or function `PythonDataFlowAnalyzer` (or `analyze_python_data_flow(path: Path) -> tuple[list, list]` returning nodes and edges). Use tree-sitter (or stdlib ast if tree-sitter Python not yet wired) to find call expressions for pandas `read_csv`/`read_sql`, SQLAlchemy `execute()`, PySpark read/write; extract first argument; if it is a string literal use it as dataset name/path and emit a node/edge; otherwise log "dynamic reference, cannot resolve" and do not emit an edge. Return list of DatasetNode (or dicts) and list of edges per contract. Verification: T008 tests pass.

- [x] T010 [US1] [US3] Refactor `python_data_flow.py` for clarity: extract helper to resolve argument to literal string or None; use tree-sitter queries (S-expression or equivalent) as specified in plan.md; ensure only literal strings produce edges. Verification: tests still pass; no regex used for call detection.

- [x] T011 [US1] Integrate PythonDataFlowAnalyzer into `src/agents/hydrologist.py`: for each `.py` file in the discovered list, call the analyzer in per-file try/except; collect nodes and edges into lists. Do not merge into a graph yet; just aggregate. Verification: run hydrologist on a repo containing the fixture Python files and assert aggregated output contains expected dataset from literal fixture.

---

## Phase 3: SQLLineageAnalyzer (TDD)

**Purpose**: Implement SQLLineageAnalyzer using sqlglot; parse .sql and dbt model files; extract table dependency graph; support PostgreSQL, BigQuery, Snowflake, DuckDB. (US1)

**Independent Test**: Analyze a fixture SQL file with SELECT FROM A JOIN B and optionally INSERT INTO C; assert output contains dataset nodes for A, B, C and correct CONSUMES/PRODUCES edges.

- [x] T012 [US1] Create fixture files in `tests/fixtures/lineage/sql/`: (1) `simple_select.sql` with `SELECT * FROM schema.table_a`; (2) `cte_and_join.sql` with WITH cte AS (SELECT ... FROM t1) SELECT ... FROM cte JOIN t2; (3) `insert_select.sql` with INSERT INTO out_tab SELECT ... FROM in_tab. Verification: files exist.

- [x] T013 [US1] Write unit tests in `tests/unit/test_sql_lineage.py`: (1) test that analyzing `simple_select.sql` returns a dataset node for the FROM table; (2) test that analyzing `cte_and_join.sql` returns nodes for all referenced tables and edges reflecting dependencies; (3) test that analyzing `insert_select.sql` returns input and output table nodes and PRODUCES/CONSUMES edges; (4) test that invalid SQL file is skipped (exception logged) and no crash. Run pytest; tests must FAIL. Verification: `pytest tests/unit/test_sql_lineage.py -v` fails.

- [x] T014 [US1] Implement `src/analyzers/sql_lineage.py`: define SQLLineageAnalyzer (or `analyze_sql_lineage(path: Path, dialect: str = "postgres") -> tuple[list, list]`). Use sqlglot.parse(sql, dialect=dialect); walk AST to extract tables from FROM, JOIN, WITH, INSERT/SELECT; build DatasetNode per table (storage_type "table"); build edges (CONSUMES from query/transformation to input tables, PRODUCES to output table). Return nodes and edges per contract. Verification: T013 tests pass.

- [x] T015 [US1] Add dialect support in `sql_lineage.py`: allow dialect to be one of PostgreSQL, BigQuery, Snowflake, DuckDB (e.g. via parameter or config); add a test that parses a minimal BigQuery-style SQL if possible. Verification: unit test for at least one additional dialect passes.

- [x] T016 [US1] Integrate SQLLineageAnalyzer into `src/agents/hydrologist.py`: for each `.sql` file in the discovered list, call the analyzer in per-file try/except; append nodes and edges to the same aggregates used for Python. Verification: run hydrologist on a repo with fixture SQL and assert aggregated output contains expected table nodes.

---

## Phase 4: DAGConfigAnalyzer (TDD)

**Purpose**: Implement DAGConfigAnalyzer; parse Airflow DAG Python files and dbt schema.yml; extract pipeline topology; map to DatasetNode and TransformationNode and edges. (US1)

**Independent Test**: Analyze a minimal Airflow DAG fixture and a minimal dbt schema.yml; assert output contains task/model nodes and edges.

- [x] T017 [US1] Create fixture files in `tests/fixtures/lineage/dbt_airflow/`: (1) `minimal_dag.py` with a single DAG and two tasks with set_downstream or `>>`; (2) `schema.yml` with one dbt model and one source (minimal valid YAML). Verification: files exist and are valid.

- [x] T018 [US1] Write unit tests in `tests/unit/test_dag_config.py`: (1) test that analyzing `minimal_dag.py` returns at least one transformation/task node and dependency edges; (2) test that analyzing `schema.yml` returns model and source dataset nodes and transformation nodes (or edges) as per plan; (3) test that invalid YAML or non-DAG Python is skipped without crash. Run pytest; tests must FAIL. Verification: `pytest tests/unit/test_dag_config.py -v` fails.

- [ ] T019 [US1] Implement `src/analyzers/dag_config_parser.py`: define DAGConfigAnalyzer (or `analyze_dag_config(path: Path) -> tuple[list, list]`). For Python: use ast or tree-sitter to detect DAG(…), operator instances, set_downstream/>>/<<; emit TransformationNode per task and optional DatasetNode if table/file refs found. For YAML: parse with PyYAML; extract models and sources; emit DatasetNode and TransformationNode per model/source; emit edges. Return nodes and edges per contract. Verification: T018 tests pass.

- [x] T020 [US1] Integrate DAGConfigAnalyzer into `src/agents/hydrologist.py`: for each `.py` and `.yml`/`.yaml` file in the discovered list (or a subset: e.g. only files under `dags/` or containing "DAG" for Python, and `schema.yml`/`sources.yml` for YAML if desired), call the analyzer in per-file try/except; append nodes and edges. Verification: run hydrologist on a repo with DAG and schema fixtures and assert aggregated output contains expected nodes/edges.

---

## Phase 5: DataLineageGraph (TDD)

**Purpose**: Merge all analyzer outputs into a single NetworkX DiGraph; implement blast_radius(node), find_sources(), find_sinks(); serialize to .cartography/lineage_graph.json. (US1, US2)

**Independent Test**: Build a small graph in test (A → B → C); find_sources() returns [A], find_sinks() returns [C], blast_radius(A) returns downstream set including B and C; graph with cycle does not loop forever.

- [x] T021 [US1] [US2] Write unit tests in `tests/unit/test_data_lineage_graph.py`: (1) test merge: create two lists of nodes/edges (e.g. from mock analyzers), merge into DataLineageGraph, assert all nodes and edges are in the graph; (2) test find_sources(): graph with nodes A (in-degree 0), B, C; assert find_sources() returns A or [A]; (3) test find_sinks(): assert find_sinks() returns C or [C]; (4) test blast_radius(A): assert result contains B and C (downstream), uses visited set (add a cycle and assert termination and deterministic result); (5) test blast_radius on node with no outgoing edges returns only that node or empty downstream set per spec. Run pytest; tests must FAIL. Verification: `pytest tests/unit/test_data_lineage_graph.py -v` fails.

- [x] T022 [US1] [US2] Implement `src/graph/lineage_graph.py`: define class DataLineageGraph wrapping a NetworkX DiGraph. Implement `merge(nodes: list, edges: list)` (or `add_from_analyzer(nodes, edges)`): add each node by id, add each edge; deduplicate by node id; sort for determinism. Verification: T021 merge and find_sources/find_sinks tests pass (stub blast_radius if needed).

- [ ] T023 [US2] Implement `blast_radius(node_id: str)` in `src/graph/lineage_graph.py`: BFS or DFS from node_id following outgoing edges; use a visited set; return sorted list or set of downstream node ids (spec: "all downstream dependents"). Verification: T021 blast_radius tests pass.

- [x] T024 [US1] Implement `find_sources()` and `find_sinks()` in `src/graph/lineage_graph.py`: find_sources returns nodes with in-degree 0; find_sinks returns nodes with out-degree 0; return deterministic (e.g. sorted) list of node ids. Verification: T021 tests pass.

- [ ] T025 [US1] Implement serialization in `src/graph/lineage_graph.py`: method `write_json(out_path: Path)` (or equivalent) that writes the graph to JSON with nodes array, edges array, and optional schema_version; use stable sort (e.g. sort_keys=True, sorted node/edge lists) so output is deterministic. Verification: unit test that writes to a temp file and asserts valid JSON and expected keys; re-read and assert round-trip or structure.

- [x] T026 [US1] [US2] Complete `src/agents/hydrologist.py`: after collecting nodes/edges from all three analyzers, instantiate DataLineageGraph, call merge for each analyzer output (or merge once with combined lists), write `.cartography/lineage_graph.json` via write_json(repo_root / ".cartography" / "lineage_graph.json"); expose blast_radius, find_sources, find_sinks on the graph (return the graph object or attach methods to it). Ensure .cartography directory is created if missing. Verification: run hydrologist on a repo with Python + SQL fixtures; assert lineage_graph.json exists and contains nodes/edges; assert find_sources() and find_sinks() return lists; assert blast_radius(some_node) returns deterministic result.

---

## Phase 6: Final Validation

**Purpose**: Run full Phase 2 test suite and a small end-to-end lineage run.

- [x] T027 Run the Phase 2 unit test suite: `pytest tests/unit/test_python_data_flow.py tests/unit/test_sql_lineage.py tests/unit/test_dag_config.py tests/unit/test_data_lineage_graph.py -v`. Fix any failing tests. Verification: all tests pass.

- [x] T028 Run a small end-to-end lineage run: execute `python -m src.cli lineage <path>` (or equivalent) where `<path>` is the project root or a small fixture repo containing at least one .py file with read_csv/read_sql, one .sql file, and optionally a DAG or schema.yml. Confirm (1) run completes without crash, (2) `.cartography/lineage_graph.json` is written, (3) file contains nodes and edges, (4) find_sources() and find_sinks() return sensible results when invoked programmatically on the returned graph. Verification: manual or scripted check; document result in quickstart or a short e2e note.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start here.
- **Phase 2 (PythonDataFlowAnalyzer)**: Depends on T001–T006 (setup and hydrologist stub with file discovery and per-file try/except).
- **Phase 3 (SQLLineageAnalyzer)**: Depends on Phase 1; can follow Phase 2 or run after T011 (integration is in hydrologist which aggregates all).
- **Phase 4 (DAGConfigAnalyzer)**: Depends on Phase 1; can follow Phase 3.
- **Phase 5 (DataLineageGraph)**: Depends on Phase 1; merge step needs analyzer output shape (contract), so T009–T010, T014–T015, T019 define that. Full integration (T026) depends on T011, T016, T020.
- **Phase 6 (Final)**: Depends on all prior phases.

### Task Order Within Phases

- Within each analyzer phase: fixtures → tests (red) → implementation (green) → refactor → integration into hydrologist.
- DataLineageGraph: tests first (T021), then merge (T022), then blast_radius (T023), find_sources/find_sinks (T024), serialization (T025), full hydrologist (T026).

### Parallel Opportunities

- T002 (fixture dirs) and T003 (lineage models) can be done in parallel after T001.
- After T008 passes, T012 (SQL fixtures) and T017 (DAG fixtures) can be done in parallel with T009–T011.
- Test-writing tasks (T008, T013, T018, T021) are independent of each other once fixtures exist; implementation tasks for each analyzer are independent across analyzers after Phase 1.

---

## Implementation Strategy

### MVP First (Lineage trace + sources/sinks)

1. Complete Phase 1 (T001–T006).
2. Complete Phase 2 (PythonDataFlowAnalyzer) and Phase 5 (DataLineageGraph) with a single analyzer: e.g. T007–T011, then T021–T026 with only Python data flow feeding the graph. Validate find_sources(), find_sinks(), and lineage_graph.json.
3. Add Phase 3 (SQLLineageAnalyzer) and Phase 4 (DAGConfigAnalyzer); integrate; re-validate.
4. Complete Phase 6.

### TDD Enforcement

- For each analyzer and for DataLineageGraph: write tests first, run to see red, implement to green, refactor. Do not implement without a failing test for the behavior.

### Verification Checklist

- Each task ends with a verification step (run pytest, run CLI, or assert file/import).
- Sensitive files are never read: file set comes only from discover_files(repo_root, IgnoreRules.default()).
- Per-file try/except: one bad file never crashes the run.
- blast_radius uses a visited set and is deterministic.
