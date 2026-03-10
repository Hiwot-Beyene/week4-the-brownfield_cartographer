"""
DataLineageGraph: Pydantic-validated lineage graph service.
Accepts only validated node/edge objects (or dicts validated against schemas).
Typed add_node/add_edge, symmetric JSON serialization/deserialization, blast_radius with optional filters.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx

from src.models.knowledge_graph import (
    ConsumesEdge,
    DatasetNode,
    LineageEdgeSchema,
    LineageNodeSchema,
    ProducesEdge,
    TransformationNode,
)

logger = logging.getLogger(__name__)

LINEAGE_SCHEMA_VERSION = 2  # nodes/edges with metadata, round-trip


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the dict with keys whose value is None removed."""
    return {k: v for k, v in d.items() if v is not None}


def _drop_none_and_empty(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys that are None, empty list, or empty dict (so we don't store null or [] or {} in JSON)."""
    return {
        k: v
        for k, v in d.items()
        if v is not None and not (isinstance(v, list) and len(v) == 0) and not (isinstance(v, dict) and len(v) == 0)
    }


def _node_id_from_model(n: DatasetNode | TransformationNode | LineageNodeSchema) -> str:
    if isinstance(n, DatasetNode):
        return n.name
    if isinstance(n, TransformationNode):
        if n.line_range:
            return f"{n.source_file or 'transformation'}:{n.line_range[0]}"
        return n.source_file or "transformation"
    return n.id


def _node_attrs_from_model(n: DatasetNode | TransformationNode | LineageNodeSchema) -> dict:
    if isinstance(n, DatasetNode):
        d = n.model_dump()
        d["type"] = "dataset"
        return d
    if isinstance(n, TransformationNode):
        d = n.model_dump()
        d["type"] = "transformation"
        return d
    return {"type": n.type, "name": n.name, "storage_type": n.storage_type, **(n.extra or {})}


def _validate_node(n: Any) -> DatasetNode | TransformationNode | LineageNodeSchema:
    if isinstance(n, (DatasetNode, TransformationNode, LineageNodeSchema)):
        return n
    if isinstance(n, dict):
        if "name" in n and "storage_type" in n:
            return DatasetNode.model_validate(n)
        if "id" in n:
            t = n.get("type", "transformation")
            extra = {k: v for k, v in n.items() if k not in ("id", "type", "name", "storage_type")}
            return LineageNodeSchema(id=n["id"], type=t, name=n.get("name"), storage_type=n.get("storage_type"), extra=extra or None)
        if "name" in n:
            return DatasetNode.model_validate(n)
    raise TypeError(f"Invalid node: expected DatasetNode, TransformationNode, LineageNodeSchema, or valid dict, got {type(n)}")


def _edge_to_schema(e: Any) -> LineageEdgeSchema:
    if isinstance(e, LineageEdgeSchema):
        return e
    if isinstance(e, ProducesEdge):
        return LineageEdgeSchema(source=e.transformation, target=e.dataset, edge_type="PRODUCES", is_write=True)
    if isinstance(e, ConsumesEdge):
        return LineageEdgeSchema(source=e.transformation, target=e.dataset, edge_type="CONSUMES", is_write=False)
    if isinstance(e, dict):
        src = e.get("source", e.get("src", ""))
        tgt = e.get("target", e.get("tgt", ""))
        edge_type = e.get("edge_type", "CONSUMES" if e.get("is_write") is False else "PRODUCES")
        if "type" in e and e["type"] in ("PRODUCES", "CONSUMES"):
            edge_type = e["type"]
        return LineageEdgeSchema(
            source=src,
            target=tgt,
            edge_type=edge_type,
            transformation_type=e.get("transformation_type"),
            source_file=e.get("source_file"),
            line_range=tuple(e["line_range"]) if isinstance(e.get("line_range"), (list, tuple)) and len(e.get("line_range", [])) >= 2 else e.get("line_range"),
            is_write=e.get("is_write"),
        )
    raise TypeError(f"Invalid edge: expected ProducesEdge, ConsumesEdge, LineageEdgeSchema, or dict, got {type(e)}")


class DataLineageGraph:
    """
    Directed graph of dataset/transformation nodes and CONSUMES/PRODUCES edges.
    All nodes/edges validated via Pydantic. Symmetric JSON read/write.
    """

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()

    def add_node(self, node: DatasetNode | TransformationNode | LineageNodeSchema | dict[str, Any]) -> None:
        """Add a single node. Validates dicts against DatasetNode, TransformationNode, or LineageNodeSchema."""
        n = _validate_node(node)
        nid = _node_id_from_model(n) if not isinstance(n, LineageNodeSchema) else n.id
        attrs = _node_attrs_from_model(n)
        self._g.add_node(nid, **attrs)

    def add_edge(
        self,
        edge: ProducesEdge | ConsumesEdge | LineageEdgeSchema | dict[str, Any],
    ) -> None:
        """Add a single edge with optional metadata. Validates dicts against LineageEdgeSchema."""
        e = _edge_to_schema(edge)
        if not e.source or not e.target:
            return
        self._g.add_edge(
            e.source,
            e.target,
            edge_type=e.edge_type,
            transformation_type=e.transformation_type,
            source_file=e.source_file,
            line_range=e.line_range,
            is_write=e.is_write,
        )

    def merge(self, nodes: list[Any], edges: list[Any]) -> None:
        """
        Add nodes and edges. Each item is validated (Pydantic or dict validated against models).
        Duplicate node ids overwrite attrs; duplicate edges are deduplicated.
        """
        seen_nodes: set[str] = set()
        for n in nodes:
            try:
                validated = _validate_node(n)
                nid = _node_id_from_model(validated) if not isinstance(validated, LineageNodeSchema) else validated.id
                if nid not in seen_nodes:
                    seen_nodes.add(nid)
                    self.add_node(validated)
            except Exception as err:
                logger.warning("merge_skip_node error=%s node=%s", err, n)
        seen_edges: set[tuple[str, str]] = set()
        for e in edges:
            try:
                schema = _edge_to_schema(e)
                if (schema.source, schema.target) in seen_edges:
                    continue
                seen_edges.add((schema.source, schema.target))
                self.add_edge(schema)
            except Exception as err:
                logger.warning("merge_skip_edge error=%s edge=%s", err, e)

    def find_sources(self) -> list[str]:
        """Nodes with in-degree 0 (entry points)."""
        return sorted(n for n in self._g.nodes() if self._g.in_degree(n) == 0)

    def find_sinks(self) -> list[str]:
        """Nodes with out-degree 0 (exit points)."""
        return sorted(n for n in self._g.nodes() if self._g.out_degree(n) == 0)

    def blast_radius(
        self,
        node_id: str,
        *,
        domain_prefix: str | None = None,
        dataset_prefix: str | None = None,
        max_depth: int | None = None,
    ) -> list[str]:
        """
        All downstream dependents from node_id (BFS with visited set).
        Optional filters: domain_prefix (e.g. "dbt."), dataset_prefix (e.g. "raw_"); max_depth limits BFS depth.
        """
        if node_id not in self._g:
            return []
        visited: set[str] = set()
        q: deque[tuple[str, int]] = deque([(node_id, 0)])
        while q:
            n, depth = q.popleft()
            if n in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue
            visited.add(n)
            for succ in sorted(self._g.successors(n)):
                if succ not in visited:
                    if domain_prefix and not str(succ).startswith(domain_prefix):
                        continue
                    if dataset_prefix and not str(succ).startswith(dataset_prefix):
                        continue
                    q.append((succ, depth + 1))
        result = sorted(visited - {node_id})
        return result

    def upstream_depth(self, node_id: str, max_depth: int = 10) -> list[str]:
        """Nodes reachable by following incoming edges up to max_depth (BFS backward)."""
        if node_id not in self._g:
            return []
        visited: set[str] = set()
        q: deque[tuple[str, int]] = deque([(node_id, 0)])
        while q:
            n, depth = q.popleft()
            if n in visited:
                continue
            if depth > max_depth:
                continue
            visited.add(n)
            for pred in sorted(self._g.predecessors(n)):
                if pred not in visited:
                    q.append((pred, depth + 1))
        return sorted(visited - {node_id})

    def path_explanation(self, source_id: str, target_id: str, max_paths: int = 3) -> list[list[str]]:
        """Up to max_paths simple paths from source to target (for explanations)."""
        if source_id not in self._g or target_id not in self._g:
            return []
        try:
            gen = nx.all_simple_paths(self._g, source_id, target_id, cutoff=15)
            return [p for i, p in enumerate(gen) if i < max_paths]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_nodes_and_edges(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return (nodes, edges) as list of dicts for persistence (e.g. SQLite). Same shape as JSON.
        Omits keys whose value is None so JSON/DB don't store null."""
        nodes = []
        for n in sorted(self._g.nodes()):
            attrs = dict(self._g.nodes[n])
            nodes.append(_drop_none_and_empty(_drop_none({"id": n, **attrs})))
        edges = []
        for u, v in sorted(self._g.edges()):
            data = dict(self._g.edges[u, v])
            payload = _drop_none_and_empty(_drop_none({"source": u, "target": v, **data}))
            edge_type = str(payload.get("edge_type") or "")
            # Schema-aligned aliases while preserving existing source/target consumers.
            if edge_type in ("PRODUCES", "CONSUMES"):
                payload["transformation"] = u
                payload["dataset"] = v
            edges.append(payload)
        return (nodes, edges)

    def write_json(self, out_path: Path) -> None:
        """Write nodes and edges to JSON (schema_version, deterministic). Includes edge metadata."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        nodes, edges = self.get_nodes_and_edges()
        payload = {
            "schema_version": LINEAGE_SCHEMA_VERSION,
            "nodes": nodes,
            "edges": edges,
        }
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def read_json(cls, path: Path) -> "DataLineageGraph":
        """
        Load graph from JSON. Validates nodes/edges and reconstructs graph (symmetric with write_json).
        Supports schema_version 1 (source/target only) and 2 (with metadata).
        """
        path = Path(path).resolve()
        if not path.is_file():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("lineage_read_json failed path=%s error=%s", path, e)
            return cls()
        graph = cls()
        nodes = raw.get("nodes", [])
        edges = raw.get("edges", [])
        for n in nodes:
            try:
                if isinstance(n, dict):
                    graph.add_node(n)
                else:
                    graph.add_node(LineageNodeSchema.model_validate(n))
            except Exception as err:
                logger.debug("read_json_skip_node %s %s", err, n)
        for e in edges:
            try:
                if isinstance(e, dict):
                    # Legacy v1: only source/target
                    if "edge_type" not in e and "source" in e and "target" in e:
                        e = {**e, "edge_type": "CONSUMES"}
                    graph.add_edge(e)
                else:
                    graph.add_edge(LineageEdgeSchema.model_validate(e))
            except Exception as err:
                logger.debug("read_json_skip_edge %s %s", err, e)
        return graph
