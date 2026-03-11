from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.models.module import ModuleNode


class DatasetNode(BaseModel):
    """
    Dataset node in the knowledge graph.

    Mirrors the TRP knowledge graph schema:
    - name
    - storage_type: table | file | stream | api
    - schema_snapshot
    - freshness_sla
    - owner
    - is_source_of_truth
    """

    name: str
    storage_type: Literal["table", "file", "stream", "api"]
    schema_snapshot: Optional[dict] = None
    freshness_sla: Optional[str] = None
    owner: Optional[str] = None
    is_source_of_truth: Optional[bool] = None


class FunctionNode(BaseModel):
    """
    Function node in the knowledge graph.

    Mirrors the TRP knowledge graph schema:
    - qualified_name
    - parent_module
    - signature
    - purpose_statement
    - call_count_within_repo
    - is_public_api
    """

    qualified_name: str
    parent_module: str
    signature: str
    purpose_statement: Optional[str] = None
    call_count_within_repo: Optional[int] = None
    is_public_api: Optional[bool] = None


class TransformationNode(BaseModel):
    """
    Transformation node in the knowledge graph.

    Mirrors the TRP knowledge graph schema:
    - source_datasets
    - target_datasets
    - transformation_type
    - source_file
    - line_range
    - sql_query_if_applicable
    """

    source_datasets: list[str] = Field(default_factory=list)
    target_datasets: list[str] = Field(default_factory=list)
    transformation_type: Optional[str] = None
    source_file: Optional[str] = None
    line_range: Optional[tuple[int, int]] = None
    sql_query_if_applicable: Optional[str] = None


class ImportEdge(BaseModel):
    """
    IMPORTS edge: source_module -> target_module.
    Weight represents import_count.
    """

    type: Literal["IMPORTS"] = "IMPORTS"
    source_module: str
    target_module: str
    weight: int = 1


class ProducesEdge(BaseModel):
    """
    PRODUCES edge: transformation -> dataset.
    Captures data lineage.
    """

    type: Literal["PRODUCES"] = "PRODUCES"
    transformation: str
    dataset: str


class ConsumesEdge(BaseModel):
    """
    CONSUMES edge: transformation -> dataset.
    Captures upstream dependencies.
    """

    type: Literal["CONSUMES"] = "CONSUMES"
    transformation: str
    dataset: str


class LineageEdgeSchema(BaseModel):
    """
    Serializable lineage edge with optional metadata for round-trip and query helpers.
    Used by the graph service for add_edge and JSON persist/load.
    """

    source: str
    target: str
    edge_type: Literal["CONSUMES", "PRODUCES"]
    transformation_type: Optional[str] = None
    source_file: Optional[str] = None
    line_range: Optional[tuple[int, int]] = None
    is_write: Optional[bool] = None  # True for PRODUCES, False for CONSUMES when present


class LineageNodeSchema(BaseModel):
    """
    Serializable lineage node for round-trip. id is the graph node id; type discriminates dataset vs transformation.
    """

    id: str
    type: Literal["dataset", "transformation"]
    name: Optional[str] = None  # for dataset
    storage_type: Optional[str] = None  # for dataset
    extra: Optional[dict] = None


class CallsEdge(BaseModel):
    """
    CALLS edge: function -> function.
    Used for call graph analysis.
    """

    type: Literal["CALLS"] = "CALLS"
    caller: str
    callee: str


class ConfiguresEdge(BaseModel):
    """
    CONFIGURES edge: config_file -> module/pipeline.
    Models YAML/ENV configuration relationships.
    """

    type: Literal["CONFIGURES"] = "CONFIGURES"
    config_file: str
    target: str


class KnowledgeGraphSnapshot(BaseModel):
    """
    High-level Pydantic view of the knowledge graph.

    This aggregates all node and edge types under a single schema.
    Phase 1 primarily populates ModuleNode + ImportEdge; other
    node/edge types are reserved for later agents (Hydrologist,
    Semanticist, Archivist).
    """

    modules: list[ModuleNode] = Field(default_factory=list)
    datasets: list[DatasetNode] = Field(default_factory=list)
    functions: list[FunctionNode] = Field(default_factory=list)
    transformations: list[TransformationNode] = Field(default_factory=list)

    imports: list[ImportEdge] = Field(default_factory=list)
    produces: list[ProducesEdge] = Field(default_factory=list)
    consumes: list[ConsumesEdge] = Field(default_factory=list)
    calls: list[CallsEdge] = Field(default_factory=list)
    configures: list[ConfiguresEdge] = Field(default_factory=list)

