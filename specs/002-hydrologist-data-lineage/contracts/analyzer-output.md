# Contract: Lineage analyzer output

**Purpose**: Define the output shape that each lineage analyzer (PythonDataFlowAnalyzer, SQLLineageAnalyzer, DAGConfigAnalyzer) returns so the Hydrologist merge step can ingest them uniformly.

## Output type

Each analyzer returns a value that can be normalized to:

- **nodes**: List of Pydantic-serializable node objects (DatasetNode and/or TransformationNode). Each must have a stable **id** (e.g. `name` for DatasetNode, or `transformation:<source_file>:<line>` for TransformationNode).
- **edges**: List of tuples or dicts `(source_id, target_id)` or `{"source": id, "target": id, "type": "PRODUCES"|"CONSUMES"}`.

The merge step in `DataLineageGraph` accepts these and adds all nodes and edges to the NetworkX DiGraph, deduplicating nodes by id.

## Per-analyzer expectations

| Analyzer | Nodes | Edges |
|----------|--------|--------|
| PythonDataFlowAnalyzer | DatasetNode (name = path/table, storage_type = "file" or "table"); optional TransformationNode per call site | CONSUMES (transformation or dataset → dataset read); PRODUCES (transformation or dataset → dataset written) |
| SQLLineageAnalyzer | DatasetNode per table (storage_type = "table") | CONSUMES from query to input tables; PRODUCES from query to output table |
| DAGConfigAnalyzer | DatasetNode for tables/models/sources; TransformationNode for tasks/models | CONSUMES/PRODUCES between tasks and datasets per DAG/schema topology |

## Evidence

Where applicable, transformations include `source_file` and `line_range` so that lineage is evidence-backed (Constitution).
