from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


def test_build_module_graph_edges(tmp_path: Path) -> None:
    from src.agents.surveyor import build_module_graph, write_module_graph_json
    from src.models.module import Evidence, ImportRef, ModuleNode

    a = ModuleNode(
        path="a.py",
        language="python",
        imports=[
            ImportRef(raw="import b", evidence=Evidence(source_file="a.py", start_line=1, end_line=1)),
        ],
    )
    b = ModuleNode(path="b.py", language="python", imports=[])

    g = build_module_graph([a, b])
    assert isinstance(g, nx.DiGraph)
    assert g.has_edge("a.py", "b")

    out = tmp_path / "module_graph.json"
    write_module_graph_json(
        out, [a, b], g, [], {}, tmp_path, {"a.py": 0.5, "b.py": 0.5}
    )

    data = json.loads(out.read_text())
    assert "nodes" in data
    assert "edges" in data
    assert data["nodes"][0]["type"] == "module"
    assert data["edges"][0]["type"] == "IMPORTS"
    assert data["edges"][0]["weight"] == 1

