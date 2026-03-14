"""
Unit tests for Day-One Pydantic models (Citation, DayOneAnswer, DayOneOutput).
"""
from __future__ import annotations

from src.models.semanticist import Citation, DayOneAnswer, DayOneOutput


def test_citation_and_answer_shape() -> None:
    c = Citation(file="src/app.py", line=42)
    assert c.file == "src/app.py"
    assert c.line == 42

    a = DayOneAnswer(question_id="q1", answer="Some answer", citations=[c])
    assert a.question_id == "q1"
    assert a.citations[0].file == "src/app.py"


def test_day_one_output_contains_five_answers() -> None:
    answers = [
        DayOneAnswer(question_id=f"q{i}", answer=f"Answer {i}", citations=[])
        for i in range(1, 6)
    ]
    out = DayOneOutput(answers=answers)
    assert len(out.answers) == 5
    ids = {a.question_id for a in out.answers}
    assert ids == {"q1", "q2", "q3", "q4", "q5"}

