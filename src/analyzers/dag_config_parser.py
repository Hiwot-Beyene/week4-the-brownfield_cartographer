"""
DAGConfigAnalyzer: extract pipeline topology from Airflow DAG files and dbt schema.yml.
Emits DatasetNode and TransformationNode (or dicts) and edges for merge into DataLineageGraph.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import yaml

from src.models.knowledge_graph import DatasetNode

logger = logging.getLogger(__name__)


def _analyze_airflow_dag(path: Path) -> tuple[list[Any], list[Any]]:
    """Parse Python file for DAG(…) and operator tasks; extract task ids and >> / set_downstream."""
    nodes: list[Any] = []
    edges: list[Any] = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.warning("hydrologist_skip path=%s analyzer=DAGConfig parse_error=%s", path, e)
        return [], []

    path_str = str(path)
    var_to_task_id: dict[str, str] = {}  # variable name -> full task id

    dag_id = f"dag:{path_str}"
    # First pass: DAG node and task nodes (Assign with Operator)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "DAG":
                if not any(isinstance(n, dict) and n.get("id") == dag_id for n in nodes):
                    nodes.append({"id": dag_id, "type": "transformation"})
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value, ast.Call):
                    call = node.value
                    attr_or_id = (call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")) or ""
                    if "Operator" in attr_or_id:
                        task_id = None
                        for kw in call.keywords:
                            if kw.arg == "task_id" and isinstance(kw.value, ast.Constant):
                                task_id = kw.value.value
                                break
                        if task_id:
                            tid = f"task:{path_str}:{task_id}"
                            var_to_task_id[t.id] = tid
                            nodes.append({"id": tid, "type": "transformation", "task_id": task_id})
    # Second pass: >> / set_downstream edges (need var_to_task_id populated)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left, right = node.left, node.right
            if isinstance(left, ast.Name) and isinstance(right, ast.Name):
                lid = var_to_task_id.get(left.id)
                rid = var_to_task_id.get(right.id)
                if lid and rid:
                    edges.append({"source": lid, "target": rid})

    return nodes, edges


def _analyze_dbt_schema(path: Path) -> tuple[list[Any], list[Any]]:
    """Parse dbt schema.yml for sources and models; emit dataset and transformation nodes."""
    nodes: list[Any] = []
    edges: list[Any] = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        data = yaml.safe_load(source)
    except (yaml.YAMLError, OSError) as e:
        logger.warning("hydrologist_skip path=%s analyzer=DAGConfig yaml_error=%s", path, e)
        return [], []

    if not isinstance(data, dict):
        return [], []

    path_str = str(path)
    # Sources
    for s in data.get("sources", []):
        name = s.get("name", "")
        for t in s.get("tables", []):
            table_name = t.get("name", name)
            full = f"{name}.{table_name}" if name else table_name
            nodes.append(DatasetNode(name=full, storage_type="table"))
            trans_id = f"dbt_source:{path_str}:{full}"
            nodes.append({"id": trans_id, "type": "transformation"})
            edges.append({"source": full, "target": trans_id})
    # Models
    for m in data.get("models", []):
        model_name = m.get("name", "")
        if not model_name:
            continue
        nodes.append(DatasetNode(name=model_name, storage_type="table"))
        trans_id = f"dbt_model:{path_str}:{model_name}"
        nodes.append({"id": trans_id, "type": "transformation"})
        edges.append({"source": trans_id, "target": model_name})

    return nodes, edges


def analyze_dag_config(path: Path) -> tuple[list[Any], list[Any]]:
    """
    Analyze a file for DAG/pipeline config. Python → Airflow DAG; .yml/.yaml → dbt schema.
    Returns (nodes, edges) for merge. On error returns ([], []) and does not raise.
    """
    path = Path(path).resolve()
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _analyze_airflow_dag(path)
    if suffix in (".yml", ".yaml"):
        return _analyze_dbt_schema(path)
    return [], []
