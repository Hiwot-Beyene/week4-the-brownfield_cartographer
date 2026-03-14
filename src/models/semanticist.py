"""Pydantic models for Semanticist outputs: PurposeResult, Citation, DayOneAnswer, DomainArchitectureMap."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PurposeResult(BaseModel):
    """Return type of generate_purpose_statement before attaching to ModuleNode."""
    purpose_statement: str
    documentation_drift: bool = False
    docstring_snippet: Optional[str] = None


class Citation(BaseModel):
    """Evidence for a Day-One answer."""
    file: str
    line: Optional[int] = None


class DayOneAnswer(BaseModel):
    """One of the Five FDE Day-One answers."""
    question_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class DayOneOutput(BaseModel):
    """Top-level output of answer_day_one_questions()."""
    answers: list[DayOneAnswer] = Field(default_factory=list)


class DomainArchitectureMap(BaseModel):
    """Produced by cluster_into_domains()."""
    module_to_domain: dict[str, str] = Field(default_factory=dict)
    cluster_to_domain: dict[int, str] = Field(default_factory=dict)
    skipped_modules: list[str] = Field(default_factory=list)
