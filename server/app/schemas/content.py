"""Authored-content schemas (spec §5).

Loaded from version-tagged files (persona markdown, ``concerns.yaml``,
``rubric.yaml``), validated at startup, and rehydrated into every prompt. Never
stored in the DB.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class RedLine(BaseModel):
    """An authored hard limit on a concern, addressed by a stable id.

    The id is what makes ``RedLineHit.source_id`` checkable: grounding matches
    against it exactly the way it already matches ``SubQuestion.id``. Authored
    rather than derived, so rewording the text never repoints a stored finding.
    """

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class NonNegotiable(BaseModel):
    """An authored persona-level hard limit, addressed by a stable id."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class NonNegotiableUpdate(BaseModel):
    """One non-negotiable as the editor sends it.

    ``id`` is absent for an entry the editor just added; the write side assigns a
    slug. An existing entry round-trips its id, so an edit to the wording cannot
    repoint a finding that already cited it.
    """

    id: str | None = None
    text: str = Field(min_length=1)


class PersonaDefinition(BaseModel):
    id: str
    display_name: str
    # One or two authored sentences the persona opens with the first time they
    # speak in a session: name, role, what they watch for. Required — a persona
    # file without one must fail this load rather than ship a personaless
    # handoff to a presenter. Never part of the prompt text itself.
    intro: str = Field(min_length=1)
    voice: str
    demographics: str
    values: list[str] = Field(default_factory=list)
    wants: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    non_negotiables: list[NonNegotiable] = Field(default_factory=list)
    rubric_version: int
    polly_voice_id: str
    exemplars: list[Exemplar] = Field(default_factory=list)

    @model_validator(mode="after")
    def _non_negotiable_ids_are_unique(self) -> "PersonaDefinition":
        ids = [nn.id for nn in self.non_negotiables]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate non_negotiable ids on persona {self.id}")
        return self


class ExemplarUpdate(BaseModel):
    """One exemplar as the editor sends it.

    No ``persona`` field: the server stamps it from the requested persona id.
    """

    user: str
    support_delta: int = Field(ge=-2, le=2)
    note: str


class PersonaUpdate(BaseModel):
    """The editable subset of ``PersonaDefinition``.

    Locked identity and rubric ownership fields are absent by construction.
    Extra fields are ignored so a stale editor payload still saves its editable
    content without accepting a locked-field change.
    """

    model_config = ConfigDict(extra="ignore")

    display_name: str
    intro: str = Field(min_length=1)
    voice: str
    demographics: str
    values: list[str] = Field(default_factory=list)
    wants: list[str] = Field(default_factory=list)
    non_negotiables: list[NonNegotiableUpdate] = Field(default_factory=list)
    polly_voice_id: str
    exemplars: list[ExemplarUpdate] = Field(default_factory=list)


class SubQuestion(BaseModel):
    id: str
    text: str
    requires: Requires


class Concern(BaseModel):
    concern_id: str
    core_ask: str
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    red_lines: list[RedLine] = Field(default_factory=list)
    what_would_satisfy: str

    @model_validator(mode="after")
    def _red_line_ids_are_unique(self) -> "Concern":
        ids = [rl.id for rl in self.red_lines]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate red_line ids on concern {self.concern_id}")
        return self


class RubricRow(BaseModel):
    id: str
    description: str
    support_value: int
    cap: int | None = None  # if set, crossing this row pins the meter at <= cap, sticky forever
    ceiling: int | None = None  # if set, matching this row holds the turn's delta at <= ceiling
    note: str | None = None


class Rubric(BaseModel):
    version: int
    rows: list[RubricRow] = Field(default_factory=list)
    combination: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _red_line_must_carry_a_cap(self) -> "Rubric":
        """Guard the scoring contract: the red_line row pins the meter.

        ``score_turn`` returns ``capped=True`` on a red line, but the pin is
        enforced only through ``cap_ceiling`` in ``apply_to_meter``. If the
        red_line row loses its ``cap`` the ceiling would silently fall back to
        100 and never pin, so require the cap here instead of failing quietly.
        """
        red_line = next((row for row in self.rows if row.id == "red_line"), None)
        if red_line is not None and red_line.cap is None:
            raise ValueError("the red_line rubric row must carry a cap")
        return self

    @model_validator(mode="after")
    def _integrity_rows_must_carry_a_ceiling(self) -> "Rubric":
        """Guard the scoring contract: a false fact or an unexplained
        contradiction holds the turn at or below its ceiling.

        ``score_turn`` reads ``ceiling`` off the matched rows and nothing else
        enforces it, so a row that quietly loses the field would let on-topic
        credit neutralize a false statement again — the exact regression rubric
        v4 exists to prevent. Fail the load instead of scoring wrong.
        """
        for row_id in ("false_fact", "contradiction"):
            row = next((r for r in self.rows if r.id == row_id), None)
            if row is not None and row.ceiling is None:
                raise ValueError(f"the {row_id} rubric row must carry a ceiling")
        return self

    @property
    def cap_ceiling(self) -> int:
        """Sticky per-persona ceiling once a capping row is crossed.

        Derived from whichever row carries a ``cap`` (the red line). Falls back
        to 100 (no effective ceiling, since the meter is already clamped to <=100).
        """
        for row in self.rows:
            if row.cap is not None:
                return row.cap
        return 100
