from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from src.agents.surveyor import write_module_graph_json


@dataclass
class KnowledgeGraph:
    module_graph: nx.DiGraph

    def write_module_graph(self, out_path: Path) -> None:
        write_module_graph_json(out_path, None, self.module_graph)

