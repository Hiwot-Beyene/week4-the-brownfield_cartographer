"""
Lineage types for Phase 2 Hydrologist.
Re-exports from knowledge_graph so analyzers can import from one place.
"""

from __future__ import annotations

from src.models.knowledge_graph import (
    ConsumesEdge,
    DatasetNode,
    ProducesEdge,
    TransformationNode,
)

__all__ = [
    "DatasetNode",
    "TransformationNode",
    "ProducesEdge",
    "ConsumesEdge",
]
