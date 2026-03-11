# Data Model: Phase 2 — Hydrologist (Data Lineage)

**Branch**: 002-hydrologist-data-lineage | **Date**: 2026-03-11

Entities and relationships for the DataLineageGraph. All types are implemented as Pydantic models (in `src/models/knowledge_graph.py` and optionally `src/models/lineage.py`).

---

## Node types

### DatasetNode

Represents a dataset or table in the lineage graph.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | str | Yes | Dataset/table identifier (logical name or path). |
| storage_type | Literal["table", "file", "stream", "api"] | Yes | How the dataset is stored. |
| schema_snapshot | dict \| None | No | Optional schema info (e.g. columns). |
| freshness_sla | str \| None | No | Optional freshness expectation. |
| owner | str \| None | No | Optional owner. |
| is_source_of_truth | bool \| None | No | Whether this is the source of truth. |

**Identity**: `name` (or a qualified form like `schema.name`) is the stable id for merging. Same name from different analyzers → one node.

---

### TransformationNode

Represents a transformation that consumes and/or produces datasets.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| source_datasets | list[str] | Yes (default []) | Upstream dataset ids (CONSUMES). |
| target_datasets | list[str] | Yes (default []) | Downstream dataset ids (PRODUCES). |
| transformation_type | str \| None | No | e.g. "python_read", "sql_query", "dbt_model", "airflow_task". |
| source_file | str \| None | No | File where the transformation is defined. |
| line_range | tuple[int, int] \| None | No | (start_line, end_line) for evidence. |
| sql_query_if_applicable | str \| None | No | Raw SQL if applicable. |

**Identity**: For merge, transformations can be represented as nodes (e.g. id `transformation:<source_file>:<line>`) or only as edge metadata; graph algorithms (blast_radius, find_sources, find_sinks) operate on dataset nodes. Plan uses dataset-centric graph with optional transformation nodes or edge attributes.

---

## Edge types

### PRODUCES

- **Semantics**: A transformation produces a dataset (transformation → dataset).
- **Representation**: In NetworkX, either (transformation_id, dataset_id) or, when flattened, (source_dataset_id, target_dataset_id) for “A feeds B” with optional edge attr `type: "PRODUCES"`.
- **Pydantic**: `ProducesEdge`: type = "PRODUCES", transformation: str, dataset: str (existing in knowledge_graph.py).

### CONSUMES

- **Semantics**: A transformation consumes a dataset (dataset → transformation, or transformation → dataset depending on direction convention).
- **Representation**: Consistent with PRODUCES; e.g. (dataset_id, transformation_id) for “dataset feeds transformation”.
- **Pydantic**: `ConsumesEdge`: type = "CONSUMES", transformation: str, dataset: str (existing in knowledge_graph.py).

**Graph direction**: In the DataLineageGraph DiGraph, edges are stored so that **data flows in the direction of the edge**: e.g. (upstream_dataset, downstream_dataset) or (dataset, transformation) and (transformation, dataset). find_sources = nodes with in-degree 0; find_sinks = out-degree 0; blast_radius follows outgoing edges (downstream).

---

## DataLineageGraph (in-memory)

- **Structure**: NetworkX `DiGraph`. Nodes: dataset ids (str); optional: transformation ids as nodes. Edges: (source_id, target_id) with optional edge attributes (type: "PRODUCES" | "CONSUMES", transformation_id, etc.).
- **Operations**:
  - **merge(nodes, edges)**: Add all nodes and edges; deduplicate by node id; deterministic order (sort before add).
  - **blast_radius(node_id)**: BFS/DFS outgoing, with visited set; return set or sorted list of downstream node ids.
  - **find_sources()**: List of node ids with in_degree 0.
  - **find_sinks()**: List of node ids with out_degree 0.
- **Serialization**: `.cartography/lineage_graph.json` — nodes array (DatasetNode/TransformationNode dicts), edges array (source, target, type), schema_version. Deterministic: sort keys and node/edge lists.

---

## Validation rules (from spec)

- DatasetNode.name must be non-empty.
- TransformationNode.source_datasets and target_datasets are lists of strings (dataset ids).
- All node and edge types used in the graph must be representable by these Pydantic models; no ad-hoc dict shapes for persisted artifacts.
