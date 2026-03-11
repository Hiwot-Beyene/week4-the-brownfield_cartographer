from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


AnalysisMethod = Literal["static", "llm"]


class Evidence(BaseModel):
    """
    Evidence describing where and how a fact was extracted.
    """

    source_file: str
    start_line: int
    end_line: int
    method: AnalysisMethod = "static"


class ImportRef(BaseModel):
    """
    Reference to an import statement inside a module.
    """

    raw: str
    evidence: Evidence


class FunctionRef(BaseModel):
    """
    Reference to a function defined in a module.
    """

    name: str
    evidence: Evidence


class ClassRef(BaseModel):
    """
    Reference to a class defined in a module, including its base classes.
    """

    name: str
    bases: list[str] = Field(default_factory=list)
    evidence: Evidence


class ModuleNode(BaseModel):
    """
    Core knowledge-graph representation of a module.

    This aligns with the TRP knowledge graph schema while retaining
    Phase 1 structural fields used by the Surveyor.
    """

    # Required core identity fields from the challenge schema.
    path: str
    language: str

    # Extended semantic / analytic fields (populated by later agents).
    purpose_statement: Optional[str] = None
    domain_cluster: Optional[str] = None
    complexity_score: Optional[float] = None
    change_velocity_30d: Optional[float] = None
    is_dead_code_candidate: Optional[bool] = None
    last_modified: Optional[str] = None

    # Phase 1 structural extraction fields (Surveyor output).
    imports: list[ImportRef] = Field(default_factory=list)
    public_functions: list[FunctionRef] = Field(default_factory=list)
    classes: list[ClassRef] = Field(default_factory=list)

