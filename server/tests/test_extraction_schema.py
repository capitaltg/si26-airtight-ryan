import json

import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    Addressed,
    Claim,
    ConsistencyFlag,
    Dodge,
    DodgeType,
    Extraction,
    FactCheck,
    RedLineHit,
    SourceDocument,
    SubQuestionCoverage,
    Verdict,
)


def _valid_extraction_dict() -> dict:
    return {
        "claims": [
            {
                "text": "The PM has 12 years of federal case-management experience.",
                "type": "commitment",
                "backing": "backed",
                "span": "our PM brings 12 years running federal case systems",
            }
        ],
        "sub_question_coverage": [
            {"id": "staffing", "addressed": "full", "span": "three named leads are assigned"}
        ],
        "dodges": [
            {
                "sub_question_id": "transition",
                "type": "non_commitment",
                "answer_span": "answered with enthusiasm but no date",
            }
        ],
        "consistency_flags": [
            {
                "conflicts_with_turn": 2,
                "current_answer_span": "we now say 60 days",
                "prior_answer_span": "earlier said 90 days",
                "acknowledged_revision": False,
            }
        ],
        "fact_checks": [
            {
                "claim": "we hold FedRAMP High",
                "answer_span": "we hold FedRAMP High",
                "source_document_id": "written_proposal",
                "source_quote": "proposal states Moderate",
                "tier": 1,
                "verdict": "refuted",
            }
        ],
        "red_line_hits": [
            {
                "source_id": "marcus_pws",
                "source_kind": "non_negotiable",
                "span": "we'll also handle work outside the PWS",
                "why": "promised work outside the stated scope",
            }
        ],
    }


def test_valid_extraction_parses() -> None:
    ext = Extraction.model_validate(_valid_extraction_dict())
    assert ext.claims[0].type.value == "commitment"
    assert ext.red_line_hits[0].source_kind.value == "non_negotiable"
    assert ext.fact_checks[0].verdict.value == "refuted"


def test_empty_extraction_defaults_to_empty_lists() -> None:
    ext = Extraction()
    assert ext.claims == []
    assert ext.red_line_hits == []


def test_commitment_claim_requires_backing() -> None:
    with pytest.raises(ValidationError):
        Claim(text="we will staff it", type="commitment", backing=None, span="we will staff it")


def test_non_commitment_claim_allows_null_backing() -> None:
    claim = Claim(
        text="this matters to us", type="value_opinion", backing=None, span="this matters"
    )
    assert claim.backing is None


def test_red_line_hit_requires_source_id_and_span() -> None:
    with pytest.raises(ValidationError):
        RedLineHit(source_kind="non_negotiable", why="missing source_id and span")  # type: ignore[call-arg]


def test_extraction_json_schema_exposes_red_line_hits() -> None:
    schema = Extraction.model_json_schema()
    assert "red_line_hits" in schema["properties"]


def test_extraction_rejects_unknown_fields() -> None:
    # fail loud: an adversarial/hallucinated tool response with extra structure
    # must not slip through with silent field loss
    bad = _valid_extraction_dict()
    bad["hallucinated_field"] = "surprise"
    with pytest.raises(ValidationError):
        Extraction.model_validate(bad)


def test_nested_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Claim(text="x", type="rhetorical", span="x", bogus=1)  # type: ignore[call-arg]


def test_conciseness_not_part_of_extraction_tool_schema() -> None:
    # conciseness is computed in code and attached later — never a model-emitted field
    schema = Extraction.model_json_schema()
    assert "conciseness" not in schema["properties"]


def test_dodge_requires_an_answer_span_and_takes_optional_prose() -> None:
    dodge = Dodge(
        sub_question_id="hosting",
        type=DodgeType.non_commitment,
        answer_span="we are exploring options",
        explanation="never named an environment",
    )
    assert dodge.answer_span == "we are exploring options"
    with pytest.raises(ValidationError):
        Dodge(sub_question_id="hosting", type=DodgeType.non_commitment)  # type: ignore[call-arg]


def test_consistency_flag_requires_both_sides_of_the_conflict() -> None:
    with pytest.raises(ValidationError):
        ConsistencyFlag(
            conflicts_with_turn=1,
            current_answer_span="a",
            acknowledged_revision=False,
        )  # type: ignore[call-arg]


def test_fact_check_requires_a_registered_document_and_a_source_quote() -> None:
    check = FactCheck(
        claim="claims 25 million records",
        answer_span="roughly 25 million case records",
        source_document_id=SourceDocument.rfp_pws,
        source_quote="approximately 42 million case records",
        tier=1,
        verdict=Verdict.refuted,
    )
    assert check.source_document_id is SourceDocument.rfp_pws
    with pytest.raises(ValidationError):
        FactCheck(
            claim="c",
            answer_span="a",
            source_document_id="some_other_doc",
            source_quote="q",
            tier=1,
            verdict=Verdict.refuted,
        )


def test_extraction_tool_schema_forbids_the_dropped_free_text_fields() -> None:
    schema = json.dumps(Extraction.model_json_schema())
    assert '"evidence"' not in schema
    assert '"detail"' not in schema


def test_coverage_carries_evidence_claim_spans() -> None:
    cov = SubQuestionCoverage(
        id="pm_commitment",
        addressed=Addressed.full,
        span="she is committed full-time",
        evidence_claim_spans=["she is committed full-time for the base period"],
    )
    assert cov.evidence_claim_spans == ["she is committed full-time for the base period"]


def test_coverage_without_links_defaults_to_empty() -> None:
    # A row stored before this field existed must still validate.
    cov = SubQuestionCoverage.model_validate(
        {"id": "hosting", "addressed": "partial", "span": "on GovCloud"}
    )
    assert cov.evidence_claim_spans == []
