"""Per-turn extraction schema (spec §5).

Every field here is filled by the model via forced Bedrock tool-use and then
validated. The JSON Schema generated from ``Extraction`` is the tool spec.
``Conciseness`` is defined here for reuse but is deliberately NOT a field on
``Extraction`` — it is computed in pure code and attached after extraction, so
the model can never emit those numbers.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    """Base for model-emitted schemas: reject unexpected keys so a hallucinated
    or adversarial tool response fails loud in validate+retry instead of passing
    with silent field loss.
    """

    model_config = ConfigDict(extra="forbid")


class ClaimType(StrEnum):
    empirical_checkable = "empirical_checkable"
    commitment = "commitment"
    value_opinion = "value_opinion"
    rhetorical = "rhetorical"


class Backing(StrEnum):
    bare = "bare"
    specified = "specified"
    backed = "backed"


class Addressed(StrEnum):
    full = "full"
    partial = "partial"
    none = "none"


class DodgeType(StrEnum):
    topic_switch = "topic_switch"
    non_commitment = "non_commitment"
    deflection = "deflection"
    pure_affect = "pure_affect"
    filibuster = "filibuster"


class Verdict(StrEnum):
    supported = "supported"
    refuted = "refuted"
    unverifiable = "unverifiable"


class RedLineSourceKind(StrEnum):
    non_negotiable = "non_negotiable"
    concern_red_line = "concern_red_line"


class SourceDocument(StrEnum):
    """The frozen documents a Tier-1 fact check may cite.

    A registry, not free text: ``source_quote`` is verified against the document
    named here. Tier 2 (open web) has no entry, so a tier-2 check has no
    verifiable source and never survives grounding.
    """

    rfp_pws = "rfp_pws"
    written_proposal = "written_proposal"


class Claim(_Strict):
    text: str
    type: ClaimType
    # bare | specified | backed | null. Required to be present for commitments —
    # a commitment with no backing is what the scorer needs to see, so the model
    # must classify it rather than omit it.
    backing: Backing | None = None
    span: str  # verbatim quote from the answer; no quote → the claim does not count

    @model_validator(mode="after")
    def _commitment_requires_backing(self) -> "Claim":
        if self.type is ClaimType.commitment and self.backing is None:
            raise ValueError("commitment claims must classify backing (bare|specified|backed)")
        return self


class SubQuestionCoverage(_Strict):
    id: str
    addressed: Addressed
    span: str | None = None
    # Verbatim spans of the claims in `claims` that carry this sub-question's
    # answer. Each must quote a `Claim.span` from the same extraction; grounding
    # discards the rest, and `pipeline.coverage_contract` reads what survives
    # against the sub-question's authored `requires`. Defaults to empty so a row
    # stored before this field existed still validates — an old row simply has no
    # links, which is what the contract check treats as no evidence.
    evidence_claim_spans: list[str] = Field(default_factory=list)


class Dodge(_Strict):
    sub_question_id: str
    type: DodgeType
    # A dodge is about what is absent, but there is always present text standing
    # in for the missing answer. That text is what the report quotes, so it must
    # be verbatim; the prose reason moves to `explanation`, which no path quotes.
    answer_span: str
    explanation: str | None = None


class ConsistencyFlag(_Strict):
    conflicts_with_turn: int  # Tier-0, index into the claim ledger
    current_answer_span: str  # verbatim from the answer being scored
    prior_answer_span: str  # verbatim from that turn's stored answer
    # True when the presenter openly revised the earlier statement. Recorded and
    # displayed; deliberately does NOT change the score (see the spec).
    acknowledged_revision: bool
    explanation: str | None = None


class FactCheck(_Strict):
    claim: str  # model restatement; never rendered as a quote
    answer_span: str  # verbatim from the answer being scored
    source_document_id: SourceDocument
    source_quote: str  # verbatim from the document named above
    # 0 = consistency, 1 = RFP + proposal, 2 = open web (deferred, unverifiable)
    tier: int = Field(ge=0, le=2)
    verdict: Verdict


class RedLineHit(_Strict):
    source_id: str
    source_kind: RedLineSourceKind
    span: str
    why: str


class Conciseness(_Strict):
    """Computed in code (pipeline.conciseness), NOT emitted by the model."""

    word_count: int
    filler_ratio: float
    density: float


class Extraction(_Strict):
    claims: list[Claim] = Field(default_factory=list)
    sub_question_coverage: list[SubQuestionCoverage] = Field(default_factory=list)
    dodges: list[Dodge] = Field(default_factory=list)
    consistency_flags: list[ConsistencyFlag] = Field(default_factory=list)
    fact_checks: list[FactCheck] = Field(default_factory=list)
    red_line_hits: list[RedLineHit] = Field(default_factory=list)
    # conciseness is attached in code after extraction — never part of the tool schema
