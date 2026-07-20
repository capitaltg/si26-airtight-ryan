"""Authored-content schemas (spec §5).

Loaded from version-tagged files (persona markdown, ``concerns.yaml``,
``rubric.yaml``), validated at startup, and rehydrated into every prompt. Never
stored in the DB.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Requires(StrEnum):
    commitment = "commitment"
    fact = "fact"
    fact_or_commitment = "fact_or_commitment"


class Exemplar(BaseModel):
    """A hand-graded worked example living in a persona's markdown body."""

    persona: str
    user: str
    support_delta: int = Field(ge=-2, le=2)
    note: str


class PersonaDefinition(BaseModel):
    id: str
    display_name: str
    voice: str
    demographics: str
    values: list[str] = Field(default_factory=list)
    wants: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    non_negotiables: list[str] = Field(default_factory=list)
    rubric_version: int
    exemplars: list[Exemplar] = Field(default_factory=list)


class SubQuestion(BaseModel):
    id: str
    text: str
    requires: Requires


class Concern(BaseModel):
    concern_id: str
    core_ask: str
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    red_lines: list[str] = Field(default_factory=list)
    what_would_satisfy: str


class RubricRow(BaseModel):
    id: str
    description: str
    support_value: int


class Rubric(BaseModel):
    version: int
    rows: list[RubricRow] = Field(default_factory=list)
    cap_ceiling: int = 25  # sticky per-persona ceiling once a red line is crossed
