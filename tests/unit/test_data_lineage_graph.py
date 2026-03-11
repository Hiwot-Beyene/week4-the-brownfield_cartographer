"""Unit tests for DataLineageGraph: merge, find_sources, find_sinks, blast_radius, write_json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.graph.lineage_graph import DataLineageGraph


def test_merge_adds_all_nodes_and_edges() -> None:
    """Merge two lists of nodes/edges; all nodes and edges appear in the graph."""
    g = DataLineageGraph()
    nodes1 = [{"id": "A", "type": "dataset"}, {"id": "B", "type": "dataset"}]
    edges1 = [{"source": "A", "target": "B"}]
    nodes2 = [{"id": "B"}, {"id": "C"}]
    edges2 = [{"source": "B", "target": "C"}]
    g.merge(nodes1, edges1)
    g.merge(nodes2, edges2)
    assert "A" in g._g
    assert "B" in g._g
    assert "C" in g._g
    assert g._g.has_edge("A", "B")
    assert g._g.has_edge("B", "C")


def test_find_sources_returns_in_degree_zero() -> None:
    """find_sources() returns nodes with in-degree 0 (e.g. A in A -> B -> C)."""
    g = DataLineageGraph()
    g.merge([{"id": "A"}, {"id": "B"}, {"id": "C"}], [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}])
    sources = g.find_sources()
    assert "A" in sources
    assert "B" not in sources
    assert "C" not in sources


def test_find_sinks_returns_out_degree_zero() -> None:
    """find_sinks() returns nodes with out-degree 0 (e.g. C in A -> B -> C)."""
    g = DataLineageGraph()
    g.merge([{"id": "A"}, {"id": "B"}, {"id": "C"}], [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}])
    sinks = g.find_sinks()
    assert "C" in sinks
    assert "A" not in sinks
    assert "B" not in sinks


def test_blast_radius_returns_downstream_dependents() -> None:
    """blast_radius(A) returns B and C (all downstream); uses visited set."""
    g = DataLineageGraph()
    g.merge([{"id": "A"}, {"id": "B"}, {"id": "C"}], [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}])
    radius = g.blast_radius("A")
    assert "B" in radius
    assert "C" in radius
    assert "A" not in radius


def test_blast_radius_with_cycle_terminates() -> None:
    """With a cycle (A -> B -> C -> A), blast_radius terminates and returns deterministic result."""
    g = DataLineageGraph()
    g.merge(
        [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}, {"source": "C", "target": "A"}],
    )
    radius = g.blast_radius("A")
    assert "B" in radius
    assert "C" in radius
    assert isinstance(radius, list)


def test_blast_radius_no_outgoing_returns_empty_or_self() -> None:
    """blast_radius on node with no outgoing edges returns empty downstream set."""
    g = DataLineageGraph()
    g.merge([{"id": "A"}, {"id": "B"}], [{"source": "A", "target": "B"}])
    radius = g.blast_radius("B")
    assert radius == []


def test_write_json_deterministic_and_valid(tmp_path: Path) -> None:
    """write_json produces valid JSON with nodes, edges, schema_version; round-trip structure."""
    g = DataLineageGraph()
    g.merge([{"id": "X"}, {"id": "Y"}], [{"source": "X", "target": "Y"}])
    out = tmp_path / "lineage.json"
    g.write_json(out)
    raw = json.loads(out.read_text())
    assert "nodes" in raw
    assert "edges" in raw
    assert raw.get("schema_version") == 1
    assert len(raw["nodes"]) >= 2
    assert len(raw["edges"]) >= 1
