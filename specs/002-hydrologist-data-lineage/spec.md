# Feature Specification: Phase 2 — Hydrologist Agent (Data Lineage)

**Feature Branch**: `002-hydrologist-data-lineage`  
**Created**: 2026-03-11  
**Status**: Draft  
**Input**: Create the specification for Phase 2: The Hydrologist Agent (Data Lineage) of the Brownfield Cartographer challenge.

## Clarifications

### Session 2026-03-11

- Q: Production-grade implementation constraints (inspired by code-graph-rag)? → A: Added as explicit acceptance criteria and Non-Functional / Production Requirements: shared safeguards (reuse Phase 1 file-scanning and ignore/sensitive-file rules), per-file graceful degradation, tree-sitter-based Python data flow detection, analyzer separation and merge, blast_radius traversal with visited set, graph schema and Pydantic alignment, and TDD/testing coverage for all new Hydrologist functionality.

## Scope

- This phase **only** covers the Hydrologist Agent and the DataLineageGraph.
- The project structure and naming **must** follow the challenge document (see Project Structure below).
- Reuse the same file-scanning, ignore patterns, and sensitive-file exclusion rules established in Phase 1 (Surveyor). The Hydrologist operates over the same discovered file set, subject to the same safety and ignore rules.

## Direct Requirements from the Challenge (verbatim)

The following requirements are taken verbatim from the TRP 1 Week 4 challenge and must be satisfied by this phase.

**Phase 2: The Hydrologist Agent (Data Lineage)**

**Goal:** Build the data lineage layer for mixed Python/SQL/YAML codebases.

1) **Implement PythonDataFlowAnalyzer:**
   - Use tree-sitter to find:
     - pandas read_csv/read_sql
     - SQLAlchemy execute()
     - PySpark read/write calls
   - Extract dataset names/paths as strings.
   - Handle f-strings and variable references gracefully:
     - If a dataset/path cannot be statically resolved, log as "dynamic reference, cannot resolve" and do NOT create a lineage edge.

2) **Implement SQLLineageAnalyzer using sqlglot:**
   - Parse .sql files and dbt model files.
   - Extract full table dependency graph from SELECT/FROM/JOIN/WITH (CTE) chains.
   - Support at minimum PostgreSQL, BigQuery, Snowflake, and DuckDB dialects.

3) **Implement DAGConfigAnalyzer:**
   - Parse Airflow DAG files or dbt schema.yml.
   - Extract pipeline topology from configuration (not just code).

4) **Merge all three analyzers into a DataLineageGraph:**
   - Represent lineage as a directed graph (NetworkX DiGraph).
   - Implement blast_radius(node): BFS/DFS from a node to find all downstream dependents.

5) **Implement find_sources() and find_sinks():**
   - find_sources(): nodes with in-degree = 0 (entry points).
   - find_sinks(): nodes with out-degree = 0 (exit points).

## Project Structure (mandatory)

Structure and naming must follow the challenge document:

- `src/agents/hydrologist.py` — Hydrologist agent orchestration
- `src/analyzers/sql_lineage.py` — SQLLineageAnalyzer (sqlglot-based)
- `src/analyzers/dag_config_parser.py` — DAGConfigAnalyzer (Airflow/dbt schema)
- `src/analyzers/` — PythonDataFlowAnalyzer (Python data flow; may live in a dedicated module or alongside existing analyzers per plan)
- `src/models/` — Pydantic node/edge types (DatasetNode, TransformationNode, PRODUCES/CONSUMES edges; extend existing knowledge graph schemas)
- `src/graph/knowledge_graph.py` (or equivalent lineage graph module) — DataLineageGraph construction and merge

## Production-Grade Implementation Constraints (Acceptance Criteria)

The following constraints MUST be satisfied by the implementation. They do not change the challenge-required structure or outcomes but enforce production-grade behavior and testability.

### Shared safeguards (reuse Phase 1 behavior)

- Use the **same** file-scanning and ignore mechanism as Phase 1 (Surveyor):
  - Ignore common non-source directories: `node_modules`, `venv`/`.venv`, `dist`, `build`, `.git`, `__pycache__`, and equivalent patterns as in Phase 1.
  - Exclude sensitive files by default: `.env`, `.env.*`, `.secrets`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, and equivalent patterns as in Phase 1.
  - Sensitive file exclusion runs **before** any Hydrologist analyzer runs; these files must **never** be read or parsed.
- All analyzers (PythonDataFlowAnalyzer, SQLLineageAnalyzer, DAGConfigAnalyzer) MUST honor the same ignore and sensitive-file rules. The Hydrologist MUST operate only on the file set produced by Phase 1–compatible discovery (or the same discovery logic).

### Per-file graceful degradation

- Each analyzer MUST use per-file try/except (or equivalent): if a Python, SQL, YAML, or DAG file fails to parse or analyze, log a structured warning and skip that file.
- One bad file must **never** crash the entire Phase 2 run.

### Tree-sitter–based detection for Python data flow

- PythonDataFlowAnalyzer MUST:
  - Use **tree-sitter queries** (not regex) to locate pandas `read_csv`/`read_sql`, SQLAlchemy `execute()`, and PySpark read/write calls.
  - Derive the call target and arguments from the AST (e.g. child_by_field_name / argument nodes), in spirit similar to call_processor patterns in code-graph-rag.
  - Treat non-literal dataset/path expressions (f-strings, variables, complex expressions) as "dynamic reference, cannot resolve" and **skip** adding lineage edges for them.

### Analyzer separation and merge

- Hydrologist MUST be structured as:
  - **PythonDataFlowAnalyzer** (separate, independently testable).
  - **SQLLineageAnalyzer** (separate, independently testable).
  - **DAGConfigAnalyzer** (separate, independently testable).
  - A **separate merge step** that ingests outputs from all three into a single DataLineageGraph (NetworkX DiGraph).
- Logic MUST NOT be mixed into one mega function; each analyzer is independently testable.

### Blast radius traversal

- `blast_radius(node)` MUST:
  - Perform BFS or DFS over the DataLineageGraph starting from the given node.
  - Use a **visited set** to avoid infinite loops on cycles.
  - Return all downstream dependents **deterministically**.

### Graph schema and Pydantic

- DatasetNode and TransformationNode MUST be defined as Pydantic models per the challenge’s Knowledge Graph schema:
  - **DatasetNode**: name, storage_type [table | file | stream | api], schema_snapshot, freshness_sla, owner, is_source_of_truth.
  - **TransformationNode**: source_datasets, target_datasets, transformation_type, source_file, line_range, sql_query_if_applicable.
- Edges PRODUCES and CONSUMES MUST be represented **consistently** for all analyzers.

### Testing & TDD (Phase 2)

- All new Hydrologist functionality MUST be covered by pytest unit tests:
  - **PythonDataFlowAnalyzer**: small fixture code exercising `read_csv`/`read_sql`, SQLAlchemy, PySpark read/write; tests verify extracted dataset names/paths and "dynamic reference" logging when path is non-literal.
  - **SQLLineageAnalyzer**: fixture SQL/dbt files with simple and CTE-based queries; tests verify the correct input/output table graph from sqlglot.
  - **DAGConfigAnalyzer**: minimal Airflow/dbt config fixtures; tests verify extracted task/nodes and edges.
  - **DataLineageGraph**: tests for `blast_radius()`, `find_sources()`, `find_sinks()` on a small, known graph.
- Favor TDD-style development: write or update tests when adding each new analyzer or graph operation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trace data flow from sources to sinks (Priority: P1)

As an FDE, I want to see the full data lineage from raw sources to final outputs so I can understand how data moves through the pipeline and answer "what produces this table?" and "what consumes it?"

**Why this priority**: Lineage is the core value of the Hydrologist; without a merged graph from Python, SQL, and config, the FDE cannot reason about data flow.

**Independent Test**: Run the Hydrologist on a repo containing Python read/write calls, SQL files, and at least one DAG/config source; verify the DataLineageGraph contains nodes for datasets/tables and edges representing transformations, and that find_sources() and find_sinks() return sensible entry and exit points.

**Acceptance Scenarios**:

1. **Given** a repository with pandas/SQLAlchemy/PySpark read/write and .sql (or dbt) files, **When** I run the Hydrologist, **Then** the DataLineageGraph includes dataset nodes and CONSUMES/PRODUCES (or equivalent) edges derived from Python and SQL analysis.
2. **Given** a repository with Airflow DAG or dbt schema.yml, **When** I run the Hydrologist, **Then** pipeline topology from config is reflected in the lineage graph (tasks/datasets and their ordering or dependencies).
3. **Given** the merged DataLineageGraph, **When** I call find_sources(), **Then** I get nodes with in-degree 0 (entry points); when I call find_sinks(), **Then** I get nodes with out-degree 0 (exit points).

---

### User Story 2 - Blast radius for impact analysis (Priority: P2)

As an FDE, I want to compute the blast radius from any node (all downstream dependents) so I can assess impact before changing a dataset or transformation.

**Why this priority**: Answering "what breaks if I change this?" is one of the five FDE day-one questions and depends on lineage.

**Independent Test**: Run blast_radius(node) on a node that has downstream dependents; verify the result includes all reachable nodes downstream (e.g. via BFS/DFS) and is deterministic.

**Acceptance Scenarios**:

1. **Given** a DataLineageGraph and a node that has downstream dependents, **When** I call blast_radius(node), **Then** I receive the set (or ordered list) of all nodes reachable downstream from that node.
2. **Given** a node with no outgoing edges, **When** I call blast_radius(node), **Then** the result contains only that node (or is empty for downstream dependents, per defined behavior).

---

### User Story 3 - Graceful handling of unresolved and invalid inputs (Priority: P3)

As an FDE, I expect the Hydrologist to never crash the run: dynamic or unresolvable references are logged and skipped, and invalid or unparseable files are skipped with clear logging.

**Why this priority**: Production codebases contain f-strings, variables, and malformed files; the system must degrade gracefully and remain usable.

**Independent Test**: Run the Hydrologist on a repo containing f-strings or variable-based dataset paths, and on a file that is not valid SQL/YAML; verify the run completes, no lineage edge is created for unresolved references, and failures are logged.

**Acceptance Scenarios**:

1. **Given** Python code where a dataset path is an f-string or variable that cannot be statically resolved, **When** the PythonDataFlowAnalyzer runs, **Then** it logs "dynamic reference, cannot resolve" (or equivalent) and does NOT create a lineage edge for that reference.
2. **Given** a file that is unparseable (e.g. invalid SQL or YAML), **When** the Hydrologist runs, **Then** that file is skipped, the error is logged, and the pipeline continues to completion.

---

### Edge Cases

- What happens when the same dataset is read in Python and referenced in SQL? (Merge into one node; edges from both analyzers.)
- What happens when a DAG references a dataset that is not produced by any analyzed file? (Node exists; in-degree may be 0 or edges may be partial; find_sources may include it.)
- How does the system handle multiple SQL dialects in one repo? (SQLLineageAnalyzer supports the required dialects; dialect detection or per-file dialect may be needed.)
- How are dbt ref() and source() resolved for lineage? (In-scope for Phase 2; exact resolution strategy in plan/tasks.)
- What happens when Airflow DAG and dbt schema define overlapping or conflicting topology? (Both contribute to the graph; merge strategy in plan.)

## Constitution Constraints *(mandatory)*

- Implementation MUST follow the TRP 1 Week 4 phases/deliverables/schema.
- All node/edge types and tool outputs MUST be Pydantic models.
- The pipeline MUST gracefully degrade (per-file try/except; log+skip; never crash full run).
- The system MUST support ignore patterns (`.cartographyignore` or `.cgrignore`-style); reuse Phase 1 rules.
- The system MUST exclude sensitive files and directories as in Phase 1 (no ingestion of secrets).
- All agent outputs MUST cite evidence (source file + line range + method: static vs LLM).
- Work MUST be structured as a sequential checklist; each task independently completable/testable.

## Requirements *(mandatory)*

### Functional Requirements (from the challenge)

These requirements are derived from the TRP 1 Week 4 challenge and define *what* the Hydrologist must do.

- **FR-001**: System MUST implement a PythonDataFlowAnalyzer that detects pandas read_csv/read_sql, SQLAlchemy execute(), and PySpark read/write calls and extracts dataset names/paths as strings.
- **FR-002**: System MUST handle f-strings and variable references in dataset/path positions gracefully: if a dataset/path cannot be statically resolved, the system MUST log it (e.g. "dynamic reference, cannot resolve") and MUST NOT create a lineage edge for it.
- **FR-003**: System MUST implement an SQLLineageAnalyzer using sqlglot that parses .sql files and dbt model files and extracts the full table dependency graph from SELECT/FROM/JOIN/WITH (CTE) chains.
- **FR-004**: SQLLineageAnalyzer MUST support at minimum PostgreSQL, BigQuery, Snowflake, and DuckDB dialects.
- **FR-005**: System MUST implement a DAGConfigAnalyzer that parses Airflow DAG files or dbt schema.yml and extracts pipeline topology from configuration.
- **FR-006**: System MUST merge all three analyzers' outputs into a single DataLineageGraph represented as a directed graph (e.g. NetworkX DiGraph).
- **FR-007**: System MUST implement blast_radius(node) that returns all downstream dependents from the given node (e.g. via BFS/DFS).
- **FR-008**: System MUST implement find_sources() returning nodes with in-degree 0 (entry points) and find_sinks() returning nodes with out-degree 0 (exit points).
- **FR-009**: DataLineageGraph nodes and edges MUST conform to the Knowledge Graph schema (DatasetNode, TransformationNode; PRODUCES/CONSUMES edges) and MUST be representable as Pydantic models.
- **FR-010**: Hydrologist MUST reuse Phase 1 file discovery, ignore rules, and sensitive-file exclusion so that the same files and directories are excluded from analysis.
- **FR-011**: On parse or analysis failure for a single file, the system MUST log the error and skip that file without failing the entire run.

### Non-Functional / Production Requirements

These requirements enforce production-grade implementation and testability without changing challenge outcomes.

- **NFR-001**: The same file-scanning and ignore mechanism as Phase 1 MUST be used: ignore non-source directories (e.g. node_modules, venv/.venv, dist, build, .git, __pycache__) and exclude sensitive files by default (.env, .env.*, .secrets, *.pem, *.key, id_rsa, credentials.json, etc.). Sensitive file exclusion MUST run before any Hydrologist analyzer; those files must never be read or parsed.
- **NFR-002**: All three analyzers (PythonDataFlowAnalyzer, SQLLineageAnalyzer, DAGConfigAnalyzer) MUST honor the same ignore and sensitive-file rules.
- **NFR-003**: Each analyzer MUST use per-file try/except (or equivalent): on parse/analysis failure for a single file, log a structured warning and skip that file; one bad file MUST NOT crash the entire Phase 2 run.
- **NFR-004**: PythonDataFlowAnalyzer MUST use tree-sitter queries (not regex) to locate pandas/SQLAlchemy/PySpark calls and MUST derive call target and arguments from the AST; non-literal dataset/path expressions MUST be treated as "dynamic reference, cannot resolve" with no lineage edge created.
- **NFR-005**: Hydrologist MUST be structured as three separate, independently testable analyzers plus a separate merge step that builds the DataLineageGraph; logic MUST NOT be combined into one mega function.
- **NFR-006**: blast_radius(node) MUST use BFS or DFS with a visited set to avoid infinite loops on cycles and MUST return downstream dependents deterministically.
- **NFR-007**: DatasetNode and TransformationNode MUST be Pydantic models matching the challenge schema; PRODUCES/CONSUMES edges MUST be represented consistently across all analyzers.
- **NFR-008**: All new Hydrologist functionality MUST be covered by pytest unit tests (PythonDataFlowAnalyzer, SQLLineageAnalyzer, DAGConfigAnalyzer, DataLineageGraph blast_radius/find_sources/find_sinks); TDD-style development (tests written or updated when adding each analyzer or graph operation) is required.

### Key Entities *(include if feature involves data)*

- **DatasetNode**: A dataset or table in the lineage graph. Attributes align with the Knowledge Graph schema: name, storage_type (table | file | stream | api), schema_snapshot, freshness_sla, owner, is_source_of_truth. Used as nodes in the DataLineageGraph.
- **TransformationNode**: A transformation step that consumes and/or produces datasets. Attributes: source_datasets, target_datasets, transformation_type, source_file, line_range, sql_query_if_applicable. Connects datasets via CONSUMES and PRODUCES edges.
- **DataLineageGraph**: A directed graph (e.g. NetworkX DiGraph) whose nodes are datasets (and optionally transformations); edges represent CONSUMES (transformation → upstream dataset) and PRODUCES (transformation → downstream dataset), or equivalent. Supports blast_radius(node), find_sources(), and find_sinks().
- **PythonDataFlowAnalyzer**: Analyzer that extracts dataset read/write from Python code (pandas, SQLAlchemy, PySpark); outputs candidate dataset names/paths and transformation metadata for merge into the lineage graph.
- **SQLLineageAnalyzer**: Analyzer that uses sqlglot to parse SQL and dbt models and extract table dependencies; outputs table-level lineage for merge.
- **DAGConfigAnalyzer**: Analyzer that parses Airflow DAG and dbt schema.yml to extract pipeline topology (tasks, dependencies, dataset references) for merge.

## Success Criteria *(mandatory)*

### Measurable Outcomes (functional)

- **SC-001**: For a repository containing Python data read/write, SQL files (or dbt models), and at least one DAG or dbt schema config, the Hydrologist produces a DataLineageGraph that includes nodes for datasets and edges representing flow, and find_sources() and find_sinks() return non-empty results where the repo has clear entry and exit points.
- **SC-002**: When a dataset path in Python cannot be statically resolved (f-string or variable), the system logs it and creates no lineage edge for that reference; the run completes successfully.
- **SC-003**: blast_radius(node) returns a deterministic set of all nodes reachable downstream from the given node for a graph built from a fixed repo snapshot.
- **SC-004**: Unparseable or invalid files (e.g. malformed SQL or YAML) are skipped with logging and do not cause the Hydrologist run to fail.
- **SC-005**: All lineage graph nodes and edges are representable with the existing Knowledge Graph Pydantic schemas (DatasetNode, TransformationNode, PRODUCES/CONSUMES) or documented extensions thereof.

### Production and Testing Acceptance Criteria (non-functional)

- **SC-006**: Sensitive files (e.g. .env, *.pem) are never read or parsed by any Hydrologist analyzer; the same ignore/sensitive-file list as Phase 1 is applied before analysis.
- **SC-007**: Each analyzer uses per-file isolation: one failing file results in a logged skip and does not abort the Phase 2 run.
- **SC-008**: PythonDataFlowAnalyzer uses tree-sitter (not regex) for call detection; unit tests verify extraction from fixture code and "dynamic reference" behavior for non-literal paths.
- **SC-009**: SQLLineageAnalyzer and DAGConfigAnalyzer have unit tests with fixture SQL/dbt and Airflow/dbt config files verifying extracted tables/tasks and edges.
- **SC-010**: DataLineageGraph has unit tests for blast_radius(), find_sources(), and find_sinks() on a small, known graph; blast_radius uses a visited set and is deterministic.
