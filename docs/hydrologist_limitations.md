# Hydrologist Agent: Parser Boundaries and Failure Modes

This note documents known limitations of the Hydrologist data-lineage pipeline for future maintainers. The Hydrologist orchestrates **SQLLineageAnalyzer** (sqlglot), **PythonDataFlowAnalyzer** (AST), and **DAGConfigAnalyzer** (YAML/dbt). Understanding these boundaries helps avoid false confidence in lineage and clarifies where to extend or work around.

---

## SQL Lineage (SQLLineageAnalyzer)

### What works

- **Standard DML**: `SELECT`/`FROM`/`JOIN`, `INSERT`/`SELECT`, `CREATE TABLE AS SELECT`, `MERGE`.
- **CTEs**: `WITH cte AS (SELECT ...) SELECT ...`; nested CTEs are traversed and base tables are extracted.
- **Multi-dialect**: Postgres (default), BigQuery, Snowflake, Redshift, Spark, Trino, DuckDB. Dialect can be inferred from path (e.g. `models/bigquery/`) or passed explicitly.
- **dbt templating**: `{{ ref('model') }}` and `{{ source('src','table') }}` are stripped or replaced so sqlglot can parse; refs/sources are also extracted via regex and appear in lineage and summary. When full parse fails, fallback lineage is built from ref/source only.

### Parser boundaries and failure modes

1. **Vendor-specific syntax**
   - Some vendor constructs (e.g. BigQuery `QUALIFY`, Snowflake `SAMPLE`, Redshift `LISTAGG` with distinct options) may parse only with the correct dialect. If the wrong dialect is used or the parser does not support the construct, the file may fall back to dbt ref/source-only lineage or empty nodes/edges.
   - **Mitigation**: Set dialect via path convention or explicitly; add dialect-specific fixtures and tests when adding support for new syntax.

2. **Complex or invalid SQL**
   - If SQL is unparseable across all tried dialects (including after Jinja/ref/source sanitization), the analyzer returns empty nodes/edges and a summary with `error` set. It does not raise. dbt model files may still get fallback lineage from ref/source.

3. **Subqueries and aliases**
   - Table extraction walks FROM, JOIN, WITH (CTE), and subqueries. In rare cases, highly complex nesting or alias handling may miss a table or duplicate it. Rely on tests (e.g. `deeply_nested_cte.sql`) when changing traversal logic.

4. **Templated SQL**
   - After replacing `{{ ref(...) }}` / `{{ source(...) }}` and other Jinja, the remainder must be valid SQL. Large or unusual macros can leave invalid fragments and cause parse failure; fallback lineage still uses ref/source when present.

---

## Python Data Flow (PythonDataFlowAnalyzer)

### What works

- **Literal string arguments only**: `read_csv("path/to/file.csv")`, `read_sql("SELECT * FROM my_table", conn)`, `execute("SELECT ...")`, Spark `csv("path")` / `parquet("path")` / `saveAsTable("table")`. These produce dataset nodes and CONSUMES/PRODUCES-style edges.

### Parser boundaries and failure modes

1. **Dynamic query construction**
   - Any non-literal table or file path (e.g. variable, `"SELECT * FROM " + tbl`, `"SELECT * FROM {}".format(tbl)`, `f"SELECT * FROM {table}"`, `text(query)`) is **not** resolved. The analyzer logs “dynamic reference, cannot resolve” and does **not** add an edge for that call. This is by design: we do not execute or interpret Python.

2. **Indirection**
   - If the path or query is built in another function or module, or read from config/env, the analyzer will not see it. Only direct literal arguments at the call site are used.

3. **Unsupported APIs**
   - Only a fixed set of patterns are recognized (e.g. pandas `read_csv`/`read_sql`/`read_parquet`, SQLAlchemy `execute`, Spark `csv`/`parquet`/`saveAsTable`). Other readers/writers (e.g. `read_excel`, custom ETL) are ignored unless the analyzer is extended.

4. **Invalid Python**
   - On syntax error, the file is skipped: returns `([], [])` and does not raise. The Hydrologist logs the skip and continues.

---

## DAG / dbt Config (DAGConfigAnalyzer)

- Parses YAML (e.g. dbt `schema.yml`, Airflow DAG config) for model/source/task nodes and dependencies. Unparseable or non-standard YAML is skipped; no lineage from that file.

---

## Hydrologist Orchestration

- **File discovery**: Only `.py`, `.sql`, `.yml`, `.yaml` under the repo (respecting ignore rules). Files under `macros/` are skipped for SQL to avoid macro-only files.
- **Per-file errors**: If one file raises in an analyzer, that file is skipped and the run continues. Partial lineage is written; check logs for “hydrologist_skip” and the reported path/analyzer.
- **Merge and idempotency**: Nodes/edges from all analyzers are merged into one graph. Duplicate (source, target) edges are deduplicated. Outputs are written to `.cartography/lineage_graph.json` and `sql_lineage_summary.json`, and optionally persisted to SQLite when `analysis_id` is set.

---

## Adding or Changing Behavior

- **SQL**: Add fixtures under `tests/fixtures/lineage/sql/` for new dialect or CTE/complex cases; add tests in `test_sql_lineage.py` or `test_sql_lineage_edge_cases.py`.
- **Python**: Add fixtures under `tests/fixtures/lineage/python/` for dynamic vs literal cases; extend `test_python_data_flow.py` and document expected “no edge” or “dynamic reference” behavior.
- **Limitations**: Update this document when you add a new known failure mode or parser boundary.
