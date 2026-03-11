from __future__ import annotations

import networkx as nx


def test_pagerank_stable_ordering_and_scc_detection() -> None:
    from src.agents.surveyor import compute_pagerank, compute_sccs

    g = nx.DiGraph()
    g.add_edges_from(
        [
            ("a", "b"),
            ("b", "c"),
            ("c", "b"),  # cycle between b and c
            ("d", "b"),
        ]
    )

    pr = compute_pagerank(g)
    # b should be high because multiple nodes point to it.
    assert pr["b"] >= pr["a"]
    assert pr["b"] >= pr["d"]

    sccs = compute_sccs(g)
    assert any(set(comp) == {"b", "c"} for comp in sccs)

