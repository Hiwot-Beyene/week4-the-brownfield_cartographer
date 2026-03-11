"""Unit tests for DAGConfigAnalyzer: Airflow DAG and dbt schema.yml topology."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzers.dag_config_parser import analyze_dag_config

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "lineage" / "dbt_airflow"


def test_analyze_minimal_dag_returns_task_nodes_and_edges() -> None:
    """Analyzing minimal_dag.py returns at least one transformation/task node and dependency edges."""
    path = FIXTURES / "minimal_dag.py"
    nodes, edges = analyze_dag_config(path)
    ids_or_names = [
        n.get("id", n.get("name", "")) if isinstance(n, dict) else getattr(n, "name", str(n))
        for n in nodes
    ]
    assert len(nodes) >= 1
    assert "task_a" in str(ids_or_names) or "task_b" in str(ids_or_names)
    assert len(edges) >= 1


def test_analyze_schema_yml_returns_models_and_sources() -> None:
    """Analyzing schema.yml returns model and source dataset nodes and transformation nodes or edges."""
    path = FIXTURES / "schema.yml"
    nodes, edges = analyze_dag_config(path)
    ids_or_names = [
        n.get("id", n.get("name", "")) if isinstance(n, dict) else getattr(n, "name", str(n))
        for n in nodes
    ]
    assert "stg_events" in str(ids_or_names) or "raw_events" in str(ids_or_names) or "events" in str(ids_or_names)
    assert len(nodes) >= 1


def test_analyze_invalid_yaml_skipped_no_crash() -> None:
    """Invalid YAML or non-DAG Python is skipped without crash."""
    path = FIXTURES / "invalid.yml"
    path.write_text("not: valid: yaml: [")
    try:
        nodes, edges = analyze_dag_config(path)
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
    finally:
        if path.exists():
            path.unlink()
