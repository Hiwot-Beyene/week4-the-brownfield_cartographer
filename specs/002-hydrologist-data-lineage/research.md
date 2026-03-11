# Research: Phase 2 — Hydrologist Agent (Data Lineage)

**Branch**: 002-hydrologist-data-lineage | **Date**: 2026-03-11

Resolves technical unknowns for implementing PythonDataFlowAnalyzer (tree-sitter), SQLLineageAnalyzer (sqlglot), and DAGConfigAnalyzer (Airflow/dbt), and for merging into DataLineageGraph.

---

## 1. Tree-sitter Python queries for data-flow calls

**Decision**: Use tree-sitter Python grammar and S-expression queries to match call expressions for `read_csv`, `read_sql`, `execute`, and PySpark read/write. Extract first (path/table) argument via `child_by_field_name("arguments")` and only accept string literals; otherwise log "dynamic reference, cannot resolve".

**Rationale**: Spec and NFR require tree-sitter queries (not regex) and AST-derived arguments. Tree-sitter gives a consistent AST across the codebase and supports robust argument extraction.

**Alternatives considered**:
- **Regex on source**: Rejected; spec explicitly requires tree-sitter queries.
- **stdlib ast only**: Acceptable for Python-only; tree-sitter preferred for alignment with Phase 1’s multi-language router and future consistency.

**References**: tree-sitter Python grammar (e.g. `call` node with `function` and `arguments`); use query like `(call function: (attribute object: (identifier) @obj attribute: (identifier) @method) arguments: (argument_list))` and filter by @method for `read_csv`, `read_sql`, `execute`, etc.

---

## 2. sqlglot for SQL lineage and multi-dialect support

**Decision**: Use **sqlglot** to parse SQL and extract table references. Use `sqlglot.parse(sql, dialect=dialect)` with dialect one of PostgreSQL, BigQuery, Snowflake, DuckDB. Walk the AST for tables in FROM, JOIN, WITH, INSERT/SELECT; build CONSUMES (query → input tables) and PRODUCES (query → output table). For dbt, resolve `ref()` and `source()` to logical names (e.g. ref to model name, source to `source_name.table_name`).

**Rationale**: Challenge mandates sqlglot and minimum support for PostgreSQL, BigQuery, Snowflake, DuckDB. sqlglot supports these dialects and exposes table/alias structure.

**Alternatives considered**:
- **sqlparse**: Less structured AST, harder to get full table dependency graph; rejected.
- **Manual regex**: Fragile for nested queries and CTEs; rejected.

**References**: sqlglot docs for parsing, dialect option, and visitor/walker APIs for table extraction.

---

## 3. Airflow DAG and dbt schema parsing

**Decision**:
- **Airflow**: Parse DAG Python files with Python AST (or tree-sitter). Detect `DAG(…)`, operator instantiations (e.g. `PythonOperator`, `BashOperator`), and dependency edges (`set_downstream`, `>>`, `<<`). Map each task to a TransformationNode; if an operator has a table/file reference in a templated field, add DatasetNode and CONSUMES/PRODUCES edges.
- **dbt**: Parse `schema.yml` / `sources.yml` with a YAML parser. Extract `models` and `sources`; each model name is an output dataset; refs and sources in SQL (or in YAML config) are input datasets. Emit transformations with source_file (YAML or SQL path) and line_range when available.

**Rationale**: Config-driven topology is required; Airflow and dbt are the two explicitly called out. Python AST is sufficient for DAG structure; YAML parsing is standard.

**Alternatives considered**:
- **Import and execute DAG**: Security and environment issues; rejected; static parsing only.
- **Heuristic grep**: Too brittle for nested structures; rejected.

---

## 4. DataLineageGraph merge and edge direction

**Decision**: Store lineage as a NetworkX DiGraph. Edge direction: **data flow** from producer to consumer (e.g. transformation T that reads A and writes B: edges A → T and T → B, or flatten to A → B with T as edge metadata). find_sources = in-degree 0; find_sinks = out-degree 0; blast_radius(node) = BFS/DFS along **outgoing** edges (downstream) with a visited set. Merge: each analyzer emits (node_id, node_attrs) and (source_id, target_id, edge_type); merge step adds all nodes and edges, deduplicating by node_id.

**Rationale**: Single directed graph allows uniform algorithms; PRODUCES/CONSUMES map to directed edges; visited set avoids cycles (NFR).

**Alternatives considered**:
- **Separate graphs per analyzer**: Would require a merge step anyway; single merged graph is simpler for API (blast_radius, find_sources, find_sinks).

---

## 5. Dialect detection for SQL files

**Decision**: Default dialect to **PostgreSQL** for unknown context. Allow optional override (e.g. config file or path convention: `models/snowflake/` → Snowflake). Do not auto-detect from SQL content in Phase 2 to keep behavior deterministic and simple.

**Rationale**: Covers “support at minimum PostgreSQL, BigQuery, Snowflake, DuckDB” without over-engineering; per-file or per-dir override can be added in tasks.

**Alternatives considered**:
- **Heuristic from SQL syntax**: Possible but brittle; deferred.
- **Always PostgreSQL**: Chosen as default; others via explicit config/path.
