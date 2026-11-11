"""Data models shared by every stage of the pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Chunk(BaseModel):
    """A passage of a source document, the unit that gets embedded and retrieved."""

    id: str
    doc: str = Field(description="Source file name (relative to the docs folder)")
    heading: str = ""
    text: str
    cert: str | None = None


class Retrieved(BaseModel):
    chunk: Chunk
    score: float


class Question(BaseModel):
    """A multiple-choice question in the format the web app imports."""

    id: str = ""
    q: str
    o: list[str] = Field(min_length=3, max_length=6)
    a: int | list[int] | None = None  # None = no answer key yet (imported)
    e: str = ""
    s: str = ""  # exam section key
    t: str = ""  # section/topic display name
    src: str = "rag"
    cert: str = ""
    sources: list[str] = Field(default_factory=list, description="Chunk ids used as grounding")
    meta: dict = Field(default_factory=dict)

    @field_validator("o")
    @classmethod
    def _options_distinct(cls, v: list[str]) -> list[str]:
        v = [str(x).strip() for x in v]
        if any(not x for x in v):
            raise ValueError("empty option")
        if len({x.lower() for x in v}) != len(v):
            raise ValueError("duplicate options")
        return v

    @model_validator(mode="after")
    def _answer_in_range(self) -> "Question":
        if self.a is None:
            return self
        idx = self.a if isinstance(self.a, list) else [self.a]
        if not idx or any(i < 0 or i >= len(self.o) for i in idx):
            raise ValueError("answer index out of range")
        if isinstance(self.a, list):
            if len(set(self.a)) != len(self.a):
                raise ValueError("duplicate answer index")
            self.a = sorted(self.a)
            if len(self.a) == 1:
                self.a = self.a[0]
        return self

    def answers(self) -> list[int]:
        if self.a is None:
            return []
        return self.a if isinstance(self.a, list) else [self.a]


class Verdict(BaseModel):
    """Result of the independent verification of one question."""

    question_id: str
    solver_answer: list[int]
    agrees: bool
    grounded: bool
    grounding_score: float = Field(ge=0, le=1)
    ambiguous: bool = False
    issues: list[str] = Field(default_factory=list)
    status: Literal["accepted", "review", "rejected"] = "review"


class ExamSection(BaseModel):
    k: str
    name: str
    w: int | None = None
    topics: str = Field("", description="Objectives of the section; used to build the retrieval query")


class ExamOutline(BaseModel):
    id: str
    name: str
    code: str
    sections: list[ExamSection]

    def section(self, key: str) -> ExamSection:
        for s in self.sections:
            if s.k == key:
                return s
        raise KeyError(f"unknown section '{key}' for {self.id}")
