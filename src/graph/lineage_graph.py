"""
DataLineageGraph: merged lineage from PythonDataFlow, SQLLineage, DAGConfig analyzers.
NetworkX DiGraph wrapper with merge(), blast_radius(), find_sources(), find_sinks(), write_json().
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx


class DataLineageGraph:
    """Directed graph of dataset/transformation nodes and CONSUMES/PRODUCES edges."""

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()

    def merge(self, nodes: list[Any], edges: list[Any]) -> None:
        """
        Add nodes and edges to the graph. Nodes can be dicts with 'id' or 'name', or Pydantic models.
        Edges can be (source_id, target_id) or dicts with 'source'/'target'.
        """
        seen: set[str] = set()
        for n in sorted(nodes, key=lambda x: _node_id(x)):
            nid = _node_id(n)
            if nid not in seen:
                seen.add(nid)
                self._g.add_node(nid, **_node_attrs(n))
        for e in sorted(edges, key=lambda x: (_edge_src(x), _edge_tgt(x))):
            src, tgt = _edge_src(e), _edge_tgt(e)
            if src and tgt:
                self._g.add_edge(src, tgt)

    def find_sources(self) -> list[str]:
        """Nodes with in-degree 0 (entry points)."""
        return sorted(n for n in self._g.nodes() if self._g.in_degree(n) == 0)

    def find_sinks(self) -> list[str]:
        """Nodes with out-degree 0 (exit points)."""
        return sorted(n for n in self._g.nodes() if self._g.out_degree(n) == 0)

    def blast_radius(self, node_id: str) -> list[str]:
        """All downstream dependents from node_id (BFS with visited set)."""
        if node_id not in self._g:
            return []
        visited: set[str] = set()
        q: deque[str] = deque([node_id])
        while q:
            n = q.popleft()
            if n in visited:
                continue
            visited.add(n)
            for succ in sorted(self._g.successors(n)):
                if succ not in visited:
                    q.append(succ)
        # Downstream only (exclude start node per "dependents")
        result = sorted(visited - {node_id})
        return result

    def write_json(self, out_path: Path) -> None:
        """Write nodes and edges to JSON (deterministic, stable sort)."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        nodes = [{"id": n, **dict(self._g.nodes[n])} for n in sorted(self._g.nodes())]
        edges = [{"source": u, "target": v} for u, v in sorted(self._g.edges())]
        payload = {"schema_version": 1, "nodes": nodes, "edges": edges}
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _node_id(n: Any) -> str:
    if hasattr(n, "name"):
        return getattr(n, "name", str(n))
    if isinstance(n, dict):
        return n.get("id") or n.get("name") or ""
    return str(n)


def _node_attrs(n: Any) -> dict:
    if isinstance(n, dict):
        return {k: v for k, v in n.items() if k not in ("id", "name")}
    if hasattr(n, "model_dump"):
        return n.model_dump()
    return {}


def _edge_src(e: Any) -> str:
    if isinstance(e, (list, tuple)) and len(e) >= 2:
        return str(e[0])
    if isinstance(e, dict):
        return str(e.get("source", e.get("src", "")))
    return ""


def _edge_tgt(e: Any) -> str:
    if isinstance(e, (list, tuple)) and len(e) >= 2:
        return str(e[1])
    if isinstance(e, dict):
        return str(e.get("target", e.get("tgt", "")))
    return ""
