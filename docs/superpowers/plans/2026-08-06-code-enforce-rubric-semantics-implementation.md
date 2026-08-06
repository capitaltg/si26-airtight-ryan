# Code Enforces the Rubric's Semantics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `SubQuestion.requires`, `approach_cited`, and `evidence_backed` deterministic predicates over verified evidence links instead of broad model labels.

**Architecture:** The extractor gains one new field — `SubQuestionCoverage.evidence_claim_spans`, verbatim quotes of the claims that carry each sub-question's answer. `grounding.drop_ungrounded` trims those links to claims that survived grounding; a new pure module `pipeline/coverage_contract.py` then demotes any coverage row whose authored `requires` type has no surviving, unrefuted claim behind it. Because that demotion happens once inside `run_extraction` — before scoring, before the orchestrator's follow-up decision, and before the extraction is persisted — `score_turn`, `_next_status`, `_unique_coverage`, and `_turn_findings` all read the already-enforced coverage with no signature changes. `score_turn` separately broadens `evidence_backed` to cover a document-confirmed empirical claim.

**Tech Stack:** Python 3.12 / Pydantic v2 / FastAPI / pytest (`server/`), authored YAML content (`server/app/content/store/`), React + TS (`frontend/`), Playwright (`e2e/`).

## Context

`docs/issues/code-enforce-rubric-semantics.md` reports that the scorer is deterministic in arithmetic but not in semantics. Three concrete defects:

1. **`requires` is decoration.** `SubQuestion.requires` (`fact` | `commitment` | `fact_or_commitment`) is rendered into the extraction prompt at `server/app/pipeline/extraction.py:97` and read nowhere else. A repo-wide search for `requires` finds only that render plus unrelated error strings. The issue's closing question — "what does `requires: commitment` change in deterministic code today?" — has the answer "nothing."
2. **`approach_cited` fires on any full/partial label.** `scoring.py:90-93` asks only `cov.addressed in (full, partial)`. Grounding proves the coverage *span* is quoted (`grounding.py:94`), but nothing proves a concrete claim stands behind it, so a rhetorical span the model labeled `partial` earns +1.
3. **`evidence_backed` is narrower than its own description.** `scoring.py:82-85` requires `type == commitment and backing == backed`. The rubric row (`rubric.yaml:59-61`) advertises "staffing, schedule, or **past-performance** evidence." The golden case `approach_past_performance` documents the mismatch in its own note: a fully documented, proposal-consistent past-performance answer is capped at +1.

**Intended outcome:** a positive row is paid only against a verified link — an authored sub-question, a grounded claim of the type that sub-question asks for, and (for the empirical `evidence_backed` path) a document quote proven present in the RFP or proposal. `what_would_satisfy` stays authored prose for the prompt and the presenter; the deterministic satisfaction contract is the per-sub-question `requires` check, which `_coverage_state` already aggregates into the `satisfied` terminal state.

**Decisions taken (confirmed with the requester):**
- `requires` unmet → **code demotes the coverage row to `none`**, which flows through to scoring, the follow-up decision, the concern's terminal state, and the report's coverage counts.
- `evidence_backed` **broadens and keeps its name**: a backed commitment *or* a document-confirmed empirical claim.
- The coverage→claim link is an **explicit new schema field**, not inferred span overlap.
- The live golden corpus expectations are **updated but not run** (no usable AWS credentials in this environment); pure unit tests pin every new combination offline.

## Global Constraints

- `score_turn` and `apply_limit_penalty` stay pure: no I/O, no model call, no concern argument added. Anything needing authored content happens upstream in `run_extraction`.
- `grounding.drop_ungrounded` never raises and never invents a value. It may remove a finding or remove a link; it must not rewrite the *content* of a field.
- `coverage_contract.enforce_requires` rewrites exactly one field, `SubQuestionCoverage.addressed`, and only ever downward (`full`/`partial` → `none`).
- `Extraction` is `extra="forbid"`. Every new field carries a default so an extraction row stored before this change still validates.
- `EXTRACTOR_CONTRACT_VERSION` goes `1 → 2`. The prompt's ask changes and the tool schema changes, which is exactly the bump condition documented at `extraction.py:42-49`. Every pinned extraction re-runs.
- `rubric.yaml` `version` goes `2 → 3`. The match conditions move, which is the bump condition documented at `rubric.yaml:5-6`. Two tests assert the literal `2` and must move with it: `server/tests/test_api.py:48`, `server/tests/test_content_loader.py:19`.
- Rubric row **ids stay stable** (`approach_cited`, `evidence_backed`). Archived sessions carry them in `matched_rows`, the frontend keys chips off them (`frontend/src/components/ui/VerdictChip.tsx:5-16`), and e2e specs assert them. No rename, no new row id.
- Prose written for the model or the presenter follows the repo's humanizer rules already stated in the extraction prompt: plain, short sentences, no em dashes, no three-part lists, no promotional adjectives.
- Run all server commands from `server/`: `pytest`, `ruff check .`, `mypy .`.

## File Structure

**Create**
- `server/app/pipeline/coverage_contract.py` — the `requires` predicate and coverage demotion. Pure.
- `server/tests/test_coverage_contract.py` — unit tests for the above.

**Modify**
- `server/app/schemas/extraction.py` — add `SubQuestionCoverage.evidence_claim_spans`.
- `server/app/pipeline/span_anchor.py` — reanchor the new spans.
- `server/app/pipeline/grounding.py` — trim links to surviving claims; fix the `unchanged` fast path.
- `server/app/pipeline/extraction.py` — prompt rules, `requires` legend, contract version bump, call `enforce_requires`.
- `server/app/pipeline/scoring.py` — broaden `evidence_backed`; update the module docstring's row table.
- `server/app/content/store/rubric.yaml` — version 3, row copy, combination disclosure.
- `server/app/content/store/concerns.yaml` — correct `risk.named_risk`'s `requires`.
- `server/tests/test_scoring.py`, `test_grounding.py`, `test_extraction_schema.py`, `test_extraction.py`, `test_orchestrator.py`, `test_report.py`, `test_api.py`, `test_content_loader.py` — new cases and the two version assertions.
- `server/tests/golden/cases.yaml` — header prose and the expectations the new engine changes.
- `docs/ideation/8-how-scoring-works.md`, `docs/issues/code-enforce-rubric-semantics.md` — documentation and resolution note.

**Deliberately untouched:** `frontend/` (rubric copy is served from `GET /content/rubric` and rendered, not hardcoded — a grep for `Backed with specific` and `Cited a concrete` across `frontend/src` and `e2e/tests` returns nothing), `server/app/report/builder.py` (it reads the already-enforced coverage), `server/app/pipeline/orchestrator.py` (same), `app/schemas/scoring.py`, `app/schemas/report.py`.

---

### Task 1: Carry the coverage→claim link through the schema and the anchor pass

**Files:**
- Modify: `server/app/schemas/extraction.py:90-94`
- Modify: `server/app/pipeline/span_anchor.py:76-109`
- Test: `server/tests/test_extraction_schema.py`, `server/tests/test_span_anchor.py`

**Interfaces:**
- Produces: `SubQuestionCoverage.evidence_claim_spans: list[str]` (default `[]`). Every later task reads it.

- [ ] **Step 1: Write the failing tests**

In `server/tests/test_extraction_schema.py`:

```python
def test_coverage_carries_evidence_claim_spans():
    cov = SubQuestionCoverage(
        id="pm_commitment",
        addressed=Addressed.full,
        span="she is committed full-time",
        evidence_claim_spans=["she is committed full-time for the base period"],
    )
    assert cov.evidence_claim_spans == ["she is committed full-time for the base period"]


def test_coverage_without_links_defaults_to_empty():
    # A row stored before this field existed must still validate.
    cov = SubQuestionCoverage.model_validate(
        {"id": "hosting", "addressed": "partial", "span": "on GovCloud"}
    )
    assert cov.evidence_claim_spans == []
```

In `server/tests/test_span_anchor.py`:

```python
def test_reanchor_maps_evidence_claim_spans_onto_the_current_answer():
    extraction = Extraction(
        claims=[
            Claim(
                text="full-time for the base period",
                type=ClaimType.commitment,
                backing=Backing.specified,
                span="She is committed full-time",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="pm_commitment",
                addressed=Addressed.full,
                span="She is committed full-time",
                evidence_claim_spans=["She is committed full-time"],
            )
        ],
    )
    # Same words, different spacing and case: the pinned spans came from the
    # earlier phrasing and must be mapped back onto this text.
    answer = "she  is\ncommitted   FULL-TIME for the base period."
    out = reanchor_spans(extraction, answer)
    link = out.sub_question_coverage[0].evidence_claim_spans[0]
    assert link in answer
    assert link == out.claims[0].span
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd server && pytest tests/test_extraction_schema.py tests/test_span_anchor.py -v`
Expected: FAIL — `evidence_claim_spans` is not a field, and `_Strict` forbids extra keys, so construction raises `ValidationError`.

- [ ] **Step 3: Add the field**

In `server/app/schemas/extraction.py`, replace `SubQuestionCoverage`:

```python
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
```

- [ ] **Step 4: Reanchor the new spans**

In `server/app/pipeline/span_anchor.py`, in `reanchor_spans`, replace the `sub_question_coverage` entry of the update dict:

```python
            "sub_question_coverage": [
                cov.model_copy(
                    update={
                        "span": fix(cov.span),
                        # Links quote the answer just like `span` does, so a
                        # replayed link needs the same mapping. Anchored one by
                        # one; a link that cannot be located is left alone and
                        # grounding drops it in Task 2.
                        "evidence_claim_spans": [
                            _anchor(link, answer, folded_answer, origin)
                            for link in cov.evidence_claim_spans
                        ],
                    }
                )
                for cov in extraction.sub_question_coverage
            ],
```

Add a sentence to the module docstring after the "Only quoted fields are rewritten" paragraph:

```
``SubQuestionCoverage.evidence_claim_spans`` quotes the answer as well, so it is
anchored here too. Anchoring it is what keeps a replayed link matchable against
the claim span it names, since both sides get mapped onto the same current text.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd server && pytest tests/test_extraction_schema.py tests/test_span_anchor.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/app/schemas/extraction.py server/app/pipeline/span_anchor.py server/tests/test_extraction_schema.py server/tests/test_span_anchor.py
git commit -m "feat(extraction): link sub-question coverage to the claims behind it"
```

---

### Task 2: Ground the links against claims that survived

**Files:**
- Modify: `server/app/pipeline/grounding.py:1-21` (docstring), `:82-104` (claims + coverage loops), `:182-192` (the `unchanged` fast path)
- Test: `server/tests/test_grounding.py`

**Interfaces:**
- Consumes: `SubQuestionCoverage.evidence_claim_spans` (Task 1).
- Produces: the guarantee `coverage_contract` relies on — every surviving link fold-matches the `span` of a claim that also survived.

- [ ] **Step 1: Write the failing tests**

Add to `server/tests/test_grounding.py` (reuse that file's existing `concern` / `persona` / `_drop` helpers; if it builds them inline, follow the same style):

```python
def test_link_naming_a_dropped_claim_is_removed():
    answer = "We run on AWS GovCloud."
    extraction = Extraction(
        claims=[
            Claim(
                text="hosted on GovCloud",
                type=ClaimType.empirical_checkable,
                span="We run on AWS GovCloud",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="hosting",
                addressed=Addressed.full,
                span="We run on AWS GovCloud",
                evidence_claim_spans=[
                    "We run on AWS GovCloud",     # real claim, kept
                    "we hold a FedRAMP High ATO",  # no such claim, dropped
                ],
            )
        ],
    )
    out = _drop(extraction, answer)
    assert out.sub_question_coverage[0].evidence_claim_spans == ["We run on AWS GovCloud"]


def test_link_survives_when_it_quotes_part_of_a_claim_span():
    answer = "We run on AWS GovCloud and PostgreSQL is the system of record."
    extraction = Extraction(
        claims=[
            Claim(
                text="hosted on GovCloud",
                type=ClaimType.empirical_checkable,
                span="We run on AWS GovCloud and PostgreSQL is the system of record",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="hosting",
                addressed=Addressed.full,
                span="We run on AWS GovCloud",
                evidence_claim_spans=["we run on aws govcloud"],  # folded fragment
            )
        ],
    )
    out = _drop(extraction, answer)
    assert out.sub_question_coverage[0].evidence_claim_spans == ["we run on aws govcloud"]


def test_link_broader_than_the_claim_it_names_is_removed():
    # A link may quote part of a claim, never more than the claim: otherwise a
    # coverage row could stretch one short claim over a whole paragraph.
    answer = "We run on AWS GovCloud and we will also rewrite the payments engine."
    extraction = Extraction(
        claims=[
            Claim(
                text="hosted on GovCloud",
                type=ClaimType.empirical_checkable,
                span="We run on AWS GovCloud",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="hosting",
                addressed=Addressed.full,
                span="We run on AWS GovCloud",
                evidence_claim_spans=[
                    "We run on AWS GovCloud and we will also rewrite the payments engine"
                ],
            )
        ],
    )
    out = _drop(extraction, answer)
    assert out.sub_question_coverage[0].evidence_claim_spans == []


def test_trimming_only_links_still_returns_the_trimmed_copy():
    # Every list keeps its length here, so the length-based fast path would have
    # returned the untrimmed original. Guards that regression directly.
    answer = "We run on AWS GovCloud."
    extraction = Extraction(
        claims=[
            Claim(
                text="hosted on GovCloud",
                type=ClaimType.empirical_checkable,
                span="We run on AWS GovCloud",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="hosting",
                addressed=Addressed.full,
                span="We run on AWS GovCloud",
                evidence_claim_spans=["a claim nobody made"],
            )
        ],
    )
    out = _drop(extraction, answer)
    assert out is not extraction
    assert out.sub_question_coverage[0].evidence_claim_spans == []
    assert len(out.claims) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd server && pytest tests/test_grounding.py -v -k link_ or trimming`
Expected: FAIL — links pass through untouched, so the first, third, and fourth assertions all see the original list.

- [ ] **Step 3: Trim the links in `drop_ungrounded`**

In `server/app/pipeline/grounding.py`, add the helper next to `_is_quoted`:

```python
def _links_a_claim(link: str, folded_claim_spans: list[str]) -> bool:
    """True when ``link`` quotes the span of a claim that survived grounding.

    Equal or narrower than a claim span, never broader: a coverage row may cite
    part of a claim, but stretching one short claim across a wider quote would
    let a single grounded phrase carry text it never covered.
    """
    needle, _ = fold(link)
    if not needle:
        return False
    return any(needle == span or needle in span for span in folded_claim_spans)
```

Then, immediately after the `claims` loop (which ends at the current line 87), and replacing the `coverage` loop:

```python
    # Folded once, from the claims that SURVIVED: a link naming a claim this pass
    # just discarded is not evidence of anything.
    folded_claim_spans = [fold(claim.span)[0] for claim in claims]

    coverage = []
    links_trimmed = False
    for cov in extraction.sub_question_coverage:
        if cov.id not in sub_question_ids:
            logger.warning("dropped coverage naming unknown sub-question %r", cov.id)
            continue
        if cov.addressed in (Addressed.full, Addressed.partial) and not _is_quoted(
            cov.span, folded_answer
        ):
            logger.warning(
                "dropped %s coverage for %s with ungrounded span: %r",
                cov.addressed.value,
                cov.id,
                cov.span,
            )
            continue
        kept = [
            link for link in cov.evidence_claim_spans
            if _links_a_claim(link, folded_claim_spans)
        ]
        if len(kept) != len(cov.evidence_claim_spans):
            logger.warning(
                "trimmed %d evidence_claim_span(s) on coverage %s naming no surviving claim",
                len(cov.evidence_claim_spans) - len(kept),
                cov.id,
            )
            cov = cov.model_copy(update={"evidence_claim_spans": kept})
            links_trimmed = True
        coverage.append(cov)
```

- [ ] **Step 4: Fix the `unchanged` fast path**

Link trimming leaves every list the same length, so the existing length comparison would discard the trimmed copy. Replace the `unchanged` expression (currently `grounding.py:182-189`):

```python
    unchanged = (
        not links_trimmed
        and len(red_line_hits) == len(extraction.red_line_hits)
        and len(claims) == len(extraction.claims)
        and len(coverage) == len(extraction.sub_question_coverage)
        and len(dodges) == len(extraction.dodges)
        and len(flags) == len(extraction.consistency_flags)
        and len(fact_checks) == len(extraction.fact_checks)
    )
```

- [ ] **Step 5: Update the module docstring**

In `grounding.py`, change the "It only ever removes; it never rewrites a field" sentence to:

```
Pure code, no model call, no I/O. It only ever removes: a whole finding, or a
link inside one. It never rewrites the content of a field and never raises.
```

And append a paragraph:

```
``SubQuestionCoverage.evidence_claim_spans`` names the claims that carry a
sub-question's answer. A link is kept only when it quotes the span of a claim
that survived this same pass, so a link cannot point at evidence that was just
discarded. ``pipeline.coverage_contract`` reads what is left.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd server && pytest tests/test_grounding.py -v`
Expected: PASS, including every pre-existing case in that file.

- [ ] **Step 7: Commit**

```bash
git add server/app/pipeline/grounding.py server/tests/test_grounding.py
git commit -m "feat(grounding): keep only coverage links that name a surviving claim"
```

---

### Task 3: Enforce `requires` in a pure module

**Files:**
- Create: `server/app/pipeline/coverage_contract.py`
- Test: `server/tests/test_coverage_contract.py`

**Interfaces:**
- Consumes: grounded `Extraction` (Task 2), `app.schemas.content.Concern`, `app.pipeline.span_anchor.fold`.
- Produces: `enforce_requires(extraction: Extraction, concern: Concern) -> Extraction`. Task 4 calls it; nothing else does.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_coverage_contract.py`:

```python
"""The authored `requires` contract, enforced in pure code.

`SubQuestion.requires` used to reach the prompt and stop there. These tests pin
what it now changes: a coverage row keeps its degree only when an unrefuted claim
of the required type is linked to it.
"""

from app.pipeline.coverage_contract import enforce_requires
from app.schemas.content import Concern, Requires, SubQuestion
from app.schemas.extraction import (
    Addressed,
    Backing,
    Claim,
    ClaimType,
    Extraction,
    FactCheck,
    SourceDocument,
    SubQuestionCoverage,
    Verdict,
)


def _concern(requires: Requires) -> Concern:
    return Concern(
        concern_id="key_personnel",
        core_ask="Tell us about the PM.",
        sub_questions=[SubQuestion(id="pm", text="Who is the PM?", requires=requires)],
        red_lines=[],
        what_would_satisfy="A named, qualified, committed PM.",
    )


def _covered(links: list[str]) -> SubQuestionCoverage:
    return SubQuestionCoverage(
        id="pm",
        addressed=Addressed.full,
        span="Karen Holloway",
        evidence_claim_spans=links,
    )


def _claim(kind: ClaimType, span: str, backing: Backing | None = None) -> Claim:
    return Claim(text="restated", type=kind, backing=backing, span=span)


def test_commitment_requirement_met_by_a_commitment_claim():
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.commitment, "she is full-time", Backing.bare)],
            sub_question_coverage=[_covered(["she is full-time"])],
        ),
        _concern(Requires.commitment),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.full


def test_commitment_requirement_not_met_by_an_empirical_claim():
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.empirical_checkable, "she has twelve years")],
            sub_question_coverage=[_covered(["she has twelve years"])],
        ),
        _concern(Requires.commitment),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_fact_requirement_not_met_by_a_commitment_claim():
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.commitment, "she is full-time", Backing.bare)],
            sub_question_coverage=[_covered(["she is full-time"])],
        ),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_either_requirement_accepts_a_fact_and_a_commitment():
    for kind, backing in (
        (ClaimType.empirical_checkable, None),
        (ClaimType.commitment, Backing.bare),
    ):
        out = enforce_requires(
            Extraction(
                claims=[_claim(kind, "she has twelve years", backing)],
                sub_question_coverage=[_covered(["she has twelve years"])],
            ),
            _concern(Requires.fact_or_commitment),
        )
        assert out.sub_question_coverage[0].addressed is Addressed.full


def test_rhetorical_and_value_claims_satisfy_nothing():
    for kind in (ClaimType.rhetorical, ClaimType.value_opinion):
        out = enforce_requires(
            Extraction(
                claims=[_claim(kind, "our people love the mission")],
                sub_question_coverage=[_covered(["our people love the mission"])],
            ),
            _concern(Requires.fact_or_commitment),
        )
        assert out.sub_question_coverage[0].addressed is Addressed.none


def test_coverage_with_no_links_is_demoted():
    out = enforce_requires(
        Extraction(sub_question_coverage=[_covered([])]),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_a_refuted_claim_does_not_satisfy_the_contract():
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.empirical_checkable, "eighteen years")],
            sub_question_coverage=[_covered(["eighteen years"])],
            fact_checks=[
                FactCheck(
                    claim="PM has eighteen years",
                    answer_span="eighteen years",
                    source_document_id=SourceDocument.written_proposal,
                    source_quote="twelve years",
                    tier=1,
                    verdict=Verdict.refuted,
                )
            ],
        ),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_a_tier_zero_refutation_does_not_disqualify_a_claim():
    # Tier 0 is a self-contradiction, which the `contradiction` row already
    # charges. It is not a document proving the claim false.
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.empirical_checkable, "eighteen years")],
            sub_question_coverage=[_covered(["eighteen years"])],
            fact_checks=[
                FactCheck(
                    claim="PM has eighteen years",
                    answer_span="eighteen years",
                    source_document_id=SourceDocument.written_proposal,
                    source_quote="twelve years",
                    tier=0,
                    verdict=Verdict.refuted,
                )
            ],
        ),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.full


def test_partial_keeps_its_degree_when_the_contract_is_met():
    # Demotion is binary on the evidence type. The model still owns the degree.
    extraction = Extraction(
        claims=[_claim(ClaimType.empirical_checkable, "she has twelve years")],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="pm",
                addressed=Addressed.partial,
                span="twelve years",
                evidence_claim_spans=["she has twelve years"],
            )
        ],
    )
    out = enforce_requires(extraction, _concern(Requires.fact))
    assert out.sub_question_coverage[0].addressed is Addressed.partial


def test_an_already_none_row_and_an_unchanged_extraction_pass_through():
    extraction = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id="pm", addressed=Addressed.none, span=None)
        ]
    )
    assert enforce_requires(extraction, _concern(Requires.fact)) is extraction
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd server && pytest tests/test_coverage_contract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.pipeline.coverage_contract'`

- [ ] **Step 3: Write the module**

Create `server/app/pipeline/coverage_contract.py`:

```python
"""Enforce each sub-question's authored evidence contract, in code.

``SubQuestion.requires`` (``fact`` | ``commitment`` | ``fact_or_commitment``)
reached the extraction prompt and stopped there, so nothing downstream checked
it. A rhetorical span the model happened to label ``partial`` earned the same
``approach_cited`` credit as a documented one. This module closes that: a
coverage row keeps the degree the model gave it only when a surviving claim of
the required type is linked to it and no document refutes that claim. Otherwise
the row is demoted to ``none``, and ``none`` earns nothing anywhere downstream.

Pure code, no model call, no I/O. It rewrites exactly one field,
``SubQuestionCoverage.addressed``, only ever downward, and never adds or removes
a row.

Runs after ``grounding.drop_ungrounded``, which has already discarded ungrounded
claims and trimmed ``evidence_claim_spans`` to links naming a claim that
survived. Every link read here therefore points at text quoted from the answer.

Demotion is binary on the evidence type, not graded. ``full`` and ``partial``
both survive intact once the contract is met: how completely a sub-question was
answered is still the model's judgment. What code owns is whether there is any
verified evidence of the required kind behind the judgment.

Called once, from ``run_extraction``, before scoring and before the extraction is
persisted. That single choke point is why ``score_turn``, the orchestrator's
follow-up decision, and the report all read enforced coverage without knowing
this module exists.
"""

from __future__ import annotations

import logging

from app.pipeline.span_anchor import fold
from app.schemas.content import Concern, Requires
from app.schemas.extraction import Addressed, Claim, ClaimType, Extraction, Verdict

logger = logging.getLogger(__name__)

# Which claim types satisfy which authored requirement. `rhetorical` and
# `value_opinion` satisfy nothing: those are precisely the spans the old engine
# paid `approach_cited` for.
_SATISFYING_TYPES: dict[Requires, frozenset[ClaimType]] = {
    Requires.fact: frozenset({ClaimType.empirical_checkable}),
    Requires.commitment: frozenset({ClaimType.commitment}),
    Requires.fact_or_commitment: frozenset(
        {ClaimType.empirical_checkable, ClaimType.commitment}
    ),
}


def _overlaps(a: str, b: str) -> bool:
    """True when two folded spans quote overlapping text, either way round."""
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def _refuted_spans(extraction: Extraction) -> list[str]:
    """Folded answer spans a surviving document refutation lands on.

    Tier 0 is excluded for the same reason ``score_turn`` excludes it from
    ``false_fact``: a Tier-0 conflict is the presenter disagreeing with their own
    earlier answer, which the ``contradiction`` row charges. It is not a document
    proving the claim false, so it does not disqualify the claim as evidence.
    """
    return [
        fold(fc.answer_span)[0]
        for fc in extraction.fact_checks
        if fc.verdict is Verdict.refuted and fc.tier >= 1
    ]


def _qualifies(claim: Claim, wanted: frozenset[ClaimType], refuted: list[str]) -> bool:
    """True when ``claim`` is of a required type and no document refutes it."""
    if claim.type not in wanted:
        return False
    folded, _ = fold(claim.span)
    return not any(_overlaps(folded, span) for span in refuted)


def enforce_requires(extraction: Extraction, concern: Concern) -> Extraction:
    """Demote every coverage row whose authored evidence contract is unmet."""
    requires_by_id = {sq.id: sq.requires for sq in concern.sub_questions}
    refuted = _refuted_spans(extraction)
    folded_claims = [(fold(c.span)[0], c) for c in extraction.claims]

    def satisfied(cov_links: list[str], wanted: frozenset[ClaimType]) -> bool:
        for link in cov_links:
            folded_link, _ = fold(link)
            for folded_span, claim in folded_claims:
                if not _overlaps(folded_link, folded_span):
                    continue
                if _qualifies(claim, wanted, refuted):
                    return True
        return False

    rows = []
    demoted = False
    for cov in extraction.sub_question_coverage:
        requires = requires_by_id.get(cov.id)
        wanted = _SATISFYING_TYPES.get(requires) if requires is not None else None
        # An id the concern does not author is already dropped by grounding; if
        # one reaches here, pass it through rather than inventing a verdict.
        if cov.addressed is Addressed.none or wanted is None:
            rows.append(cov)
            continue
        if satisfied(cov.evidence_claim_spans, wanted):
            rows.append(cov)
            continue
        logger.info(
            "demoted %s coverage on %s to none: no unrefuted %s claim is linked",
            cov.addressed.value,
            cov.id,
            requires.value,
        )
        rows.append(cov.model_copy(update={"addressed": Addressed.none}))
        demoted = True

    if not demoted:
        return extraction
    return extraction.model_copy(update={"sub_question_coverage": rows})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd server && pytest tests/test_coverage_contract.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add server/app/pipeline/coverage_contract.py server/tests/test_coverage_contract.py
git commit -m "feat(scoring): enforce a sub-question's authored requires contract in code"
```

---

### Task 4: Wire the contract into the pipeline and ask the model for the links

**Files:**
- Modify: `server/app/pipeline/extraction.py:41-50` (contract version), `:95-111` (`_render_concern`), `:151-184` (static prefix rules), `:357-379` (post-processing)
- Test: `server/tests/test_extraction.py`, `server/tests/test_orchestrator.py`, `server/tests/test_api.py`

**Interfaces:**
- Consumes: `enforce_requires` (Task 3).
- Produces: `ExtractionResult.extraction` is contract-enforced. Every downstream reader — `score_turn`, `_next_status`, `repo.append_turn`, the report — gets the enforced value with no change of its own.

**This is the task that breaks existing fixtures.** Every test that drives the real pipeline (`run_extraction` or `submit_answer`) and hands in a coverage row with no `evidence_claim_spans` will now see that row demoted to `none`. Step 6 migrates them. Tests that call `score_turn` or `build_scored_report` directly are unaffected, because `enforce_requires` runs upstream of both.

- [ ] **Step 1: Write the failing tests**

In `server/tests/test_extraction.py` — reuse `FakeBedrockClient` (`:36`) and `_fixture()` (`:61`), and add `key_personnel` to the imports you need:

```python
def test_run_extraction_demotes_coverage_whose_requires_contract_is_unmet() -> None:
    """key_personnel/pm_commitment requires a commitment. Link an empirical claim
    to it and the coverage must come back `none`."""
    content, persona, _ = _fixture()
    concern = content.concerns["key_personnel"]
    answer = "Karen Holloway has twelve years managing federal software programs."
    scripted = Extraction(
        claims=[
            Claim(
                text="twelve years of federal software programs",
                type=ClaimType.empirical_checkable,
                span="Karen Holloway has twelve years",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="pm_commitment",
                addressed=Addressed.full,
                span="Karen Holloway has twelve years",
                evidence_claim_spans=["Karen Holloway has twelve years"],
            )
        ],
    )
    result = run_extraction(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        prior_answers={},
        client=FakeBedrockClient(scripted),
    )
    assert result.extraction.sub_question_coverage[0].addressed is Addressed.none


def test_run_extraction_keeps_coverage_whose_requires_contract_is_met() -> None:
    """The same shape with a commitment claim linked instead. Proves the demotion
    above is the contract firing, not the link being dropped."""
    content, persona, _ = _fixture()
    concern = content.concerns["key_personnel"]
    answer = "Karen Holloway is committed full-time for the base period."
    scripted = Extraction(
        claims=[
            Claim(
                text="full-time for the base period",
                type=ClaimType.commitment,
                backing=Backing.specified,
                span="Karen Holloway is committed full-time",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="pm_commitment",
                addressed=Addressed.full,
                span="Karen Holloway is committed full-time",
                evidence_claim_spans=["Karen Holloway is committed full-time"],
            )
        ],
    )
    result = run_extraction(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        prior_answers={},
        client=FakeBedrockClient(scripted),
    )
    assert result.extraction.sub_question_coverage[0].addressed is Addressed.full


def test_prompt_states_the_requires_contract_and_the_link_field() -> None:
    content, persona, concern = _fixture()
    prompt = build_extraction_prompt(
        answer="We run on AWS GovCloud.",
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
    )
    assert "evidence_claim_spans" in prompt
    assert "fact_or_commitment" in prompt
    assert "verdict: supported" in prompt
    # The rule belongs in the cached prefix, not the per-turn rebuild.
    prefix = build_extraction_static_prefix(persona=persona, content=content)
    assert "evidence_claim_spans" in prefix


def test_extractor_contract_version_is_two() -> None:
    # The prompt's ask and the tool schema both changed, so a v1 pin — which has
    # no links at all, and would therefore demote every coverage row — must miss.
    assert EXTRACTOR_CONTRACT_VERSION == 2
```

In `server/tests/test_orchestrator.py` — reuse the `db` / `content` fixtures and `ScriptedClient` (`:59`):

```python
def _rhetoric_only(concern: Concern) -> Extraction:
    """Every sub-question marked full, but the only claim behind them is
    rhetorical. The contract check must demote all of them."""
    return Extraction(
        claims=[
            Claim(
                text="reassurance about the team",
                type=ClaimType.rhetorical,
                span="you are in good hands",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id=sq.id,
                addressed=Addressed.full,
                span="you are in good hands",
                evidence_claim_spans=["you are in good hands"],
            )
            for sq in concern.sub_questions
        ],
    )


def test_unmet_requires_contract_keeps_the_concern_open_for_a_follow_up(
    db: Session, content: Content
) -> None:
    client = ScriptedClient()
    session = orchestrator.start_session(db, content)
    assignment = orchestrator.next_concern(db, content, session)
    assert assignment is not None
    client.next_extraction = _rhetoric_only(assignment.concern)

    result = orchestrator.submit_answer(
        db, content, client, session, "We take this seriously, you are in good hands."
    )

    assert result.support_delta == 0
    assert result.matched_rows == ["unsubstantiated"]
    assert result.concern_status == "partial"  # not satisfied: nothing was proven
    assert result.next is not None and result.next.is_follow_up
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd server && pytest tests/test_extraction.py tests/test_orchestrator.py -v -k "requires or contract_version or prompt_states"`
Expected: FAIL — coverage comes back `full`, the prompt has no link rule, and the version is still `1`.

- [ ] **Step 3: Add the prompt rules**

In `server/app/pipeline/extraction.py`, add two blocks to `build_extraction_static_prefix`, after the existing "Evidence rules." block and before the free-text style block:

```python
            "Coverage rules. Each sub-question in the active concern carries a "
            "`requires` tag. `fact` means an `empirical_checkable` claim, "
            "`commitment` means a `commitment` claim, and `fact_or_commitment` "
            "means either one. When you mark a sub-question `full` or `partial`, "
            "put in `evidence_claim_spans` the span of every claim in `claims` "
            "that carries that answer, copied character for character from the "
            "claim's own `span`. Do not link a claim you did not also emit in "
            "`claims`. A coverage row with no linked claim of the required type "
            "is scored as not addressed, so restating the question or answering "
            "it with enthusiasm earns nothing.",
            "Fact-check rules. Record a `fact_check` when the solicitation or the "
            "written proposal CONFIRMS a checkable claim, not only when one is "
            "refuted. Use `tier: 1`, `verdict: supported`, and the confirming "
            "`source_quote`. A confirmed checkable claim is real evidence and "
            "the scorer credits it, so leaving it out costs the presenter.",
```

In `_render_concern`, make the `requires` tag legible where it appears (the concern block is in the dynamic suffix, so keep this short — the rule itself lives in the cached prefix):

```python
def _render_concern(concern: Concern) -> str:
    sub = "\n".join(
        f"  - [{sq.id}] {sq.text} (requires: {sq.requires.value})"
        for sq in concern.sub_questions
    )
    red = "\n".join(f"  - [{line.id}] {line.text}" for line in concern.red_lines)
    return "\n".join(
        [
            f"Concern: {concern.concern_id}",
            f"Core ask: {concern.core_ask}",
            "Sub-questions (the `requires` tag names the kind of claim that "
            "counts; see the coverage rules above):",
            sub,
            "Red lines (crossing any is a hard cap):",
            red,
            f"What would satisfy: {concern.what_would_satisfy}",
        ]
    )
```

- [ ] **Step 4: Bump the contract version**

Replace `EXTRACTOR_CONTRACT_VERSION = 1` with:

```python
# 2: the coverage and fact-check rules were added to the prompt and
# `SubQuestionCoverage.evidence_claim_spans` was added to the tool schema. A
# pinned v1 extraction has no links at all, so replaying it would demote every
# coverage row to `none`. The bump makes those pins miss on purpose.
EXTRACTOR_CONTRACT_VERSION = 2
```

- [ ] **Step 5: Call the contract check**

Add the import beside the grounding import:

```python
from app.pipeline.coverage_contract import enforce_requires
```

And in `run_extraction`, replace the post-processing tail:

```python
    anchored = reanchor_spans(extraction, answer)
    grounded = drop_ungrounded(
        anchored,
        answer=answer,
        concern=concern,
        persona=persona,
        prior_answers=prior_answers,
        documents={
            SourceDocument.rfp_pws: content.rfp_text,
            SourceDocument.written_proposal: content.proposal_text,
        },
    )
    # Last of the three pure passes, and the only one that needs the authored
    # concern's `requires` tags. Runs after grounding so every link it reads
    # names a claim that survived. Its output is what gets scored, what decides
    # the follow-up, and what is persisted, so scoring and the report never see
    # an unenforced coverage row.
    checked = enforce_requires(grounded, concern)
    conciseness = compute_conciseness(answer, checked)
    return ExtractionResult(
        extraction=checked,
        conciseness=conciseness,
        provenance=ExtractionProvenance(
            source=source,
            key=key,
            contract_version=EXTRACTOR_CONTRACT_VERSION,
            model_id=model_id,
        ),
    )
```

Update the `run_extraction` docstring's post-processing paragraph to name the third pass and its order:

```
Post-processing runs on the replay path too, and the order matters. A pinned span
was quoted out of an earlier phrasing, so ``reanchor_spans`` maps it onto this
answer first; then ``drop_ungrounded`` discards anything the answer does not
actually support, Tier-0 contradictions included; then ``enforce_requires``
demotes any sub-question whose authored ``requires`` type has no surviving claim
behind it. Running grounding before anchoring would throw out real findings
whenever a presenter retypes the same answer with different spacing, and running
the contract check before grounding would let a discarded claim satisfy a
sub-question.
```

- [ ] **Step 6: Migrate the pipeline-driving fixtures**

Every coverage row in a fixture that reaches `run_extraction` or `submit_answer` needs a link to a claim of the type its sub-question asks for. Add the link and, where the fixture has no claim of that type, add the claim.

`server/tests/test_orchestrator.py:94-124` — `_full` promises a satisfied concern, so it has to satisfy every `requires` value the concern carries. Give it one claim of each kind on the same span and link both from every row:

```python
_COVERED_SPAN = "named lead, 12 years, full-time"


def _full(concern: Concern) -> Extraction:
    """A backed answer that fully covers every sub-question → satisfies, +2.

    Carries a commitment claim and an empirical claim on the same span, and links
    both from every coverage row, so the row satisfies whichever `requires` value
    its sub-question is authored with.
    """
    return Extraction(
        claims=[
            Claim(
                text="A named lead is committed with specific experience.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span=_COVERED_SPAN,
            ),
            Claim(
                text="The named lead has 12 years of relevant experience.",
                type=ClaimType.empirical_checkable,
                span=_COVERED_SPAN,
            ),
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id=sq.id,
                addressed=Addressed.full,
                span=_COVERED_SPAN,
                evidence_claim_spans=[_COVERED_SPAN],
            )
            for sq in concern.sub_questions
        ],
    )
```

The tests using `_full` submit `_BACKED_ANSWER` (`:38`), which contains `named lead, 12 years, full-time`, so the span stays grounded. `_partial` (`:112-124`) has no claims at all; give it the same two-claim block and link them from its single row, keeping its docstring's point about the span having to appear in the submitted answer.

`server/tests/test_api.py:60-110` — two scripted clients. The first (`:74-84`) already emits a `backed` commitment claim on span `architecture`, but `technical_approach.hosting` is `requires: fact`, so add an `empirical_checkable` claim on the same span and set `evidence_claim_spans=["architecture"]` on all three rows. The second (`:104-109`) emits no claims; it exists to produce a *partial* turn that earns a follow-up, so decide per test whether the partial should still count — if it should, add an empirical claim on span `architecture` and link it; if the test only needs "not satisfied", leave it linkless and update the assertion comment to say the contract check is now what makes it fall short.

Anywhere a fixture's intent is "this turn should score nothing", leaving it linkless is now the *correct* fixture. Do not add links to make an old number come back; check what the test is asserting first.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd server && pytest tests/test_extraction.py tests/test_extraction_pin.py tests/test_orchestrator.py tests/test_api.py tests/test_session_archive.py -v`
Expected: PASS. `test_extraction_pin.py:80` and `:181` already parameterize `extractor_contract_version=2` as the *miss* case; confirm they still express "a different version misses" rather than hardcoding today's live value — if either now collides with the live version, change the probe to `3`.

- [ ] **Step 8: Commit**

```bash
git add server/app/pipeline/extraction.py server/tests/test_extraction.py server/tests/test_orchestrator.py server/tests/test_extraction_pin.py server/tests/test_api.py
git commit -m "feat(extraction): ask for coverage evidence links and enforce the contract"
```

---

### Task 5: Broaden `evidence_backed` to verified empirical evidence

**Files:**
- Modify: `server/app/pipeline/scoring.py:1-20` (docstring), `:82-98` (the two positive rows)
- Modify: `server/app/content/store/rubric.yaml`
- Test: `server/tests/test_scoring.py`, `server/tests/test_api.py:48`, `server/tests/test_content_loader.py:19`

**Interfaces:**
- Consumes: enforced `Extraction` (Task 4), `app.pipeline.span_anchor.fold`.
- Produces: no signature change. `score_turn(extraction, rubric) -> ScoreOutput` as before.

- [ ] **Step 1: Write the failing tests**

Add to `server/tests/test_scoring.py`:

```python
def _supported_check(answer_span: str) -> FactCheck:
    return FactCheck(
        claim="comparable-scale migration on the record",
        answer_span=answer_span,
        source_document_id=SourceDocument.written_proposal,
        source_quote="1.8 million cases migrated with zero data loss",
        tier=1,
        verdict=Verdict.supported,
    )


def test_a_document_confirmed_empirical_claim_is_evidence_backed():
    ext = Extraction(
        claims=[
            Claim(
                text="migrated a 1.8M-case system with zero data loss",
                type=ClaimType.empirical_checkable,
                span="we migrated a 1.8-million-case system with zero data loss",
            )
        ],
        fact_checks=[_supported_check("we migrated a 1.8-million-case system")],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="comparable_scale",
                addressed=Addressed.full,
                span="a 1.8-million-case system",
                evidence_claim_spans=["we migrated a 1.8-million-case system with zero data loss"],
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 2
    assert out.matched_rows == ["evidence_backed"]  # approach_cited still suppressed


def test_an_unconfirmed_empirical_claim_is_only_approach_cited():
    ext = Extraction(
        claims=[
            Claim(
                text="migrated a 1.8M-case system",
                type=ClaimType.empirical_checkable,
                span="we migrated a 1.8-million-case system",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="comparable_scale",
                addressed=Addressed.full,
                span="a 1.8-million-case system",
                evidence_claim_spans=["we migrated a 1.8-million-case system"],
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 1
    assert out.matched_rows == ["approach_cited"]


def test_a_supported_check_with_no_empirical_claim_behind_it_is_not_backed():
    # The row rewards a verified CLAIM, not a stray check. Nothing to attach to.
    ext = Extraction(fact_checks=[_supported_check("we migrated a system")])
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows
    assert out.matched_rows == ["unsubstantiated"]


def test_a_tier_zero_supported_check_does_not_back_a_claim():
    ext = Extraction(
        claims=[
            Claim(
                text="migrated a 1.8M-case system",
                type=ClaimType.empirical_checkable,
                span="we migrated a 1.8-million-case system",
            )
        ],
        fact_checks=[
            FactCheck(
                claim="c",
                answer_span="we migrated a 1.8-million-case system",
                source_document_id=SourceDocument.written_proposal,
                source_quote="q",
                tier=0,
                verdict=Verdict.supported,
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows


def test_a_confirmed_commitment_claim_alone_is_not_the_empirical_path():
    # The empirical path is for `empirical_checkable`. A commitment still needs
    # `backing == backed`; a supported check does not substitute for it.
    ext = Extraction(
        claims=[
            Claim(
                text="we commit to 90 days",
                type=ClaimType.commitment,
                backing=Backing.specified,
                span="we complete transition-in within 90 calendar days",
            )
        ],
        fact_checks=[_supported_check("we complete transition-in within 90 calendar days")],
    )
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows
```

Also update the two rubric-version assertions:

```python
# server/tests/test_api.py:48
        assert content.rubric.version == 3

# server/tests/test_content_loader.py:19
    assert content.rubric.version == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd server && pytest tests/test_scoring.py tests/test_api.py tests/test_content_loader.py -v`
Expected: FAIL — the confirmed-empirical case scores `1 / [approach_cited]`, and both version assertions read `2`.

- [ ] **Step 3: Broaden the row**

In `server/app/pipeline/scoring.py`, add the import:

```python
from app.pipeline.span_anchor import fold
```

Add the helper above `score_turn`:

```python
def _verified_empirical(extraction: Extraction) -> bool:
    """True when a document-confirmed checkable claim survives in ``extraction``.

    A ``fact_check`` at tier 1 or higher with a ``supported`` verdict has both
    halves of its evidence already proven by ``grounding.drop_ungrounded``: the
    ``answer_span`` is quoted in the answer and the ``source_quote`` is quoted in
    the document it names. When such a check lands on an
    ``empirical_checkable`` claim, that is verified evidence — the empirical half
    of what the ``evidence_backed`` row has always described ("staffing,
    schedule, or past-performance evidence"). Before this, a fully documented
    past-performance answer was capped at ``approach_cited``.

    Tier 0 is excluded for the same reason it is excluded from ``false_fact``: it
    is a comparison against the presenter's own earlier answer, not against a
    frozen document, so it verifies nothing.
    """
    supported = [
        fold(fc.answer_span)[0]
        for fc in extraction.fact_checks
        if fc.verdict is Verdict.supported and fc.tier >= 1
    ]
    if not supported:
        return False
    for claim in extraction.claims:
        if claim.type is not ClaimType.empirical_checkable:
            continue
        span, _ = fold(claim.span)
        if span and any(span == s or span in s or s in span for s in supported):
            return True
    return False
```

Replace the `backed` computation:

```python
    # Two ways to earn the row, and both are verified rather than asserted. A
    # commitment the model classified as `backed` carries its own specifics; an
    # empirical claim earns it by being confirmed against a frozen document.
    backed = any(
        claim.type is ClaimType.commitment and claim.backing is Backing.backed
        for claim in extraction.claims
    ) or _verified_empirical(extraction)
```

Update the module docstring's row list:

```
- ``evidence_backed`` (+2) — a commitment claim with ``backing == backed``, or an
  ``empirical_checkable`` claim confirmed by a tier-1+ ``supported`` fact_check
- ``approach_cited`` (+1) — any sub-question still full/partial after the
  ``requires`` contract check, and not already evidence_backed
```

- [ ] **Step 4: Update the authored rubric**

In `server/app/content/store/rubric.yaml`: header comment, `version: 3`, two `combination` bullets, and the two positive rows.

```yaml
# Scoring rubric v3. Row ids are a contract the scoring engine (#5) matches on via
# matched_rows; keep them stable. Mirrors docs/ideation/2-scoring-and-drift.md:43-51.
#
# `note` and `combination` are disclosure copy only. `version` moved to 3 because
# the match conditions moved: a sub-question now counts only when a claim of the
# kind it asks for stands behind it, and Evidence Backed now covers a confirmed
# checkable fact as well as a backed commitment. Bump it when the math moves.

version: 3
```

Append to `combination` (after the Evidence Backed bullet):

```yaml
  - >-
    A sub-question counts as answered only when a claim of the kind it asks for
    stands behind it. Naming the topic without a fact or a commitment counts as
    nothing, and a claim the solicitation or your proposal refutes does not count
    either.
```

And replace the two positive rows:

```yaml
  - id: approach_cited
    support_value: 1
    description: Cited a concrete, compliant piece of the approach.
    note: >-
      Needs a claim of the kind the sub-question asks for. Not paid when Evidence
      Backed already fired on the same answer.
  - id: evidence_backed
    support_value: 2
    description: >-
      Backed with specific staffing, schedule, or past-performance evidence, or a
      checkable fact the solicitation or your written proposal confirms.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd server && pytest tests/test_scoring.py tests/test_api.py tests/test_content_loader.py tests/test_report.py -v`
Expected: PASS. If a `test_report.py` fixture asserts an `evidence_backed` finding count, check whether its extraction now takes the new empirical path and update the fixture, not the engine.

- [ ] **Step 6: Commit**

```bash
git add server/app/pipeline/scoring.py server/app/content/store/rubric.yaml server/tests/test_scoring.py server/tests/test_api.py server/tests/test_content_loader.py
git commit -m "feat(scoring): pay evidence_backed for confirmed empirical evidence"
```

---

### Task 6: Correct the one authored `requires` value the new enforcement exposes

**Files:**
- Modify: `server/app/content/store/concerns.yaml:141-156`
- Test: `server/tests/test_content_loader.py`

**Interfaces:**
- Consumes: `Requires` (unchanged), `enforce_requires` (Task 3).

`requires` was decoration until now, so its authored values were never pressure-tested. Auditing all sixteen sub-questions against `_SATISFYING_TYPES`, exactly one is wrong: `risk.named_risk` asks "Is a genuine, specific risk named rather than deflected?" and is tagged `requires: commitment`. Naming a risk is a statement about the world, not a promise, so the model will classify it `empirical_checkable` and the contract will demote a correct answer. The other fifteen hold: the `commitment` ones all ask what the presenter will do (`pm_commitment`, `schedule`, `continuity`, `price_stability`, `ato`, `cutover_day`, `support_model`, `mitigation`), and the `fact` ones all ask what is already true (`hosting`, `pm_experience`, `comparable_scale`, `outcome`, `baseline`).

- [ ] **Step 1: Write the failing test**

Add to `server/tests/test_content_loader.py`:

```python
def test_naming_a_risk_is_satisfiable_by_a_fact():
    """`requires` now demotes coverage, so a sub-question asking what is true
    must not demand a commitment. Naming a risk is a statement, not a promise."""
    concern = load_content().concerns["risk"]
    named_risk = next(sq for sq in concern.sub_questions if sq.id == "named_risk")
    assert named_risk.requires is Requires.fact_or_commitment
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd server && pytest tests/test_content_loader.py -k named_risk -v`
Expected: FAIL — `assert <Requires.commitment: 'commitment'> is <Requires.fact_or_commitment: ...>`

- [ ] **Step 3: Correct the authored value**

In `server/app/content/store/concerns.yaml`, under `concern_id: risk`:

```yaml
    - id: named_risk
      text: Is a genuine, specific risk named rather than deflected?
      requires: fact_or_commitment
```

Add a line to the file's header comment:

```yaml
# `requires` is enforced in code (app/pipeline/coverage_contract.py): a
# sub-question counts as answered only when an unrefuted claim of that type is
# linked to it. Tag what the question actually asks for — `commitment` for what
# the presenter will do, `fact` for what is already true.
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd server && pytest tests/test_content_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/content/store/concerns.yaml server/tests/test_content_loader.py
git commit -m "fix(content): naming a risk is a fact, not a commitment"
```

---

### Task 7: Re-baseline the golden corpus

**Files:**
- Modify: `server/tests/golden/cases.yaml`

The harness at `server/tests/golden/test_golden.py` runs `run_extraction` then `score_turn` against live Bedrock and needs AWS credentials. It is skipped in this environment. The `expected` blocks are hand grades against the engine *as built*, so they go stale the moment the engine's match conditions move. This task updates the prose and the grades; the unit tests in Tasks 3 and 5 are what actually pin the new engine offline.

- [ ] **Step 1: Rewrite the header prose**

Replace the two engine-behaviour bullets (`cases.yaml:12-16`) with:

```yaml
#   - A crossed red line fires FIRST and alone: delta -2, capped, rows [red_line].
#   - A sub-question counts as addressed only when `evidence_claim_spans` links a
#     claim of the kind its `requires` tag asks for, and no document refutes that
#     claim. `approach_cited` (+1) then fires on any surviving full/partial row,
#     unless `evidence_backed` already did. So an on-topic negative answer (a
#     wrong fact, a contradiction) that still answers the question with a real
#     claim nets that -1 against a +1 -> delta 0. That is the engine.
#   - `evidence_backed` (+2) fires two ways: a commitment with
#     `backing == backed`, or an `empirical_checkable` claim confirmed by a
#     tier-1 `supported` fact_check. The second path is new in rubric v3, and it
#     is why several cases below are marked FRAGILE: whether the model bothers to
#     record a supported check decides +1 vs +2.
```

- [ ] **Step 2: Flip the case the issue named**

`approach_past_performance` is the case whose own note documented the defect ("evidence_backed requires a *commitment* with backing; past performance is empirical, so this lands on approach_cited"). Its answer's outcome and CPARS rating are in the written proposal, so a `supported` tier-1 check is exactly what the new prompt asks for:

```yaml
- id: approach_past_performance
  concern_id: past_performance
  persona_id: technical_evaluator
  answer: >-
    On the Veterans Claims Office modernization from 2021 to 2024 we migrated a
    1.8-million-case system to a cloud-native platform on schedule with zero
    data loss, and we hold an Exceptional CPARS rating for it.
  expected:
    support_delta: 2
    capped: false
    matched_rows: [evidence_backed]
  note: >-
    The written proposal confirms this project, so the checkable claims come back
    as tier-1 `supported` and the empirical path to evidence_backed fires. Under
    rubric v2 this was capped at approach_cited, which is the defect
    docs/issues/code-enforce-rubric-semantics.md reported.
```

- [ ] **Step 3: Mark the cases the empirical path can now move**

Three cases carry empirical claims the proposal supports, so they may score +2 where they used to score +1. Leave the grade at the pre-change value — the empirical path fires only if the model records a supported check, and until the suite runs live that is unproven — but say so in the note, so a calibration run reads as a decision rather than a surprise.

Append to `approach_architecture_concrete`'s note:

```yaml
    FRAGILE: the proposal names AWS GovCloud and the integration set, so if the
    model records a tier-1 `supported` check against those claims this becomes
    evidence_backed +2. Decide which is right on the first live run.
```

Append to `false_fact_pm_years`'s note (and replace the stale FRAGILE sentence about `backed`):

```yaml
    FRAGILE under v3 for a different reason than v2: the "eighteen years" claim
    is refuted, so it can no longer satisfy pm_experience's `requires: fact`.
    The +1 now has to come from pm_commitment ("committed full-time"), which is a
    commitment claim and stands. If the model does not emit that claim the case
    falls to -1 [false_fact].
```

Append to `combo_dodge_plus_approach`'s note:

```yaml
    FRAGILE: the proposal supports both the twelve years and the VCO
    modernization, so a tier-1 `supported` check on either would make this
    evidence_backed and net 0 instead of -1.
```

- [ ] **Step 4: Strengthen the two notes the contract check makes safer**

`unsubstantiated_support`'s note currently says the case is fragile because "if it credits partial coverage it becomes +1". The contract check removes that path — there is no fact or commitment claim in that answer to link. Replace that clause:

```yaml
  note: >-
    On-topic reassurance with no specifics and no sub-question concretely
    addressed -> unsubstantiated fallback. Under rubric v3 the "+1 if it credits
    partial coverage" risk is gone: the answer holds no fact and no commitment,
    so any coverage row the model marks is demoted to none. The remaining risk is
    the other direction, a pure_affect dodge at -2.
```

`dodge_culture_topic_switch`'s note can drop its "clean dodge with no approach_cited" hedge in favour of the structural reason — same edit style, one sentence.

- [ ] **Step 5: Leave the rest**

`red_line_*` (×4), `approach_transition_compliant`, `backed_pm_qualified`, `backed_transition_migration_lead`, `dodge_risk_deflection`, `false_fact_record_count`, `contradiction_top_risk`, `contradiction_cutover_plan` keep their grades. Verify each by hand against the new rules before moving on; note in the commit message that the corpus was not run live.

- [ ] **Step 6: Confirm the file still parses and the harness still collects**

Run: `cd server && pytest tests/golden --collect-only -q`
Expected: 15 tests collected, all skipped for missing credentials. A YAML error surfaces here.

- [ ] **Step 7: Commit**

```bash
git add server/tests/golden/cases.yaml
git commit -m "test(golden): re-grade the corpus against the v3 rubric semantics

Not run live: this environment has no usable AWS credentials, so the grades are
authored from the deterministic rules and the model-dependent ones are marked
FRAGILE. Tasks 3 and 5 pin the engine offline."
```

---

### Task 8: Document the new stage and close the issue

**Files:**
- Modify: `docs/ideation/8-how-scoring-works.md`
- Modify: `docs/ideation/2-scoring-and-drift.md:43-51`
- Modify: `docs/issues/code-enforce-rubric-semantics.md`
- Create: `docs/superpowers/plans/2026-08-06-code-enforce-rubric-semantics-implementation.md` (this plan, committed to the repo where the other plans live)

- [ ] **Step 0: Re-sync the rubric table `rubric.yaml` mirrors**

`rubric.yaml`'s header names `docs/ideation/2-scoring-and-drift.md:43-51` as the table it mirrors, so the two positive rows there go stale with Task 5. In that file's "Turning signals into a support change" table, replace the last two rows:

```markdown
| Cited a concrete, compliant piece of the approach that answers the ask, with a fact or a commitment behind it | +1 |
| Backed it with specific staffing, schedule, or past-performance evidence, or with a checkable fact the solicitation or the written proposal confirms | +2 |
```

And append a sentence to the paragraph that follows ("Rows combine; the answer doesn't just pick one."):

```markdown
A row only pays against evidence of the kind the question asked for. Each
sub-question is authored with what would answer it — a fact, a commitment, or
either — and code checks that a claim of that kind is actually behind the answer
before any positive row can fire.
```

- [ ] **Step 1: Add the contract-check stage to the walkthrough**

`8-how-scoring-works.md` describes five stages and says only 3 and 5 touch the number. That is still true, but stage 2 now has a second half. Under "## 2. The grounding filter discards hallucinated evidence", append:

```markdown
`drop_ungrounded` also trims `SubQuestionCoverage.evidence_claim_spans` down to
links that name a claim which survived the same pass, and then
`coverage_contract.enforce_requires` (`server/app/pipeline/coverage_contract.py`)
reads each authored `requires` tag against what is left. A sub-question tagged
`commitment` with only an empirical claim linked to it comes out of this stage as
`none`, and so does one with nothing linked at all. That is what makes
`requires` a deterministic contract rather than prompt decoration, and it is why
`approach_cited` can no longer be earned by a rhetorical span.

Three passes, in this order, all pure: anchor, ground, enforce. Anchoring before
grounding keeps a retyped answer's real findings; grounding before enforcement
keeps a discarded claim from satisfying a sub-question.
```

- [ ] **Step 2: Update the row table**

In the same file, replace the two positive rows of the stage-3 table:

```markdown
| `evidence_backed` | a commitment claim with `backing == backed`, **or** an `empirical_checkable` claim confirmed by a tier-1+ `supported` fact_check | +2 | once |
| `approach_cited` | any sub-question still full/partial after the `requires` check, **and not** already `evidence_backed` | +1 | once |
```

And replace the second "deliberate asymmetry" bullet's neighbours with a third bullet:

```markdown
- **`evidence_backed` has two doors, and both are verified.** A backed commitment
  carries its own specifics. An empirical claim earns the row by being confirmed
  against a frozen document, which is checked the same way a refutation is. The
  row's description always said "past-performance evidence"; before rubric v3 the
  code did not.
```

Add a dated note under the file's existing "> Written 2026-08-01" line:

```markdown
> Updated 2026-08-06 for rubric v3: the `requires` contract check and the
> empirical path to `evidence_backed`.
```

- [ ] **Step 3: Append the resolution to the issue**

Follow the format `docs/issues/score-bearing-verified-evidence.md:55-124` established. Append to `docs/issues/code-enforce-rubric-semantics.md`:

```markdown
### Resolution (2026-08-06)

Answered the closing question directly: `requires: commitment` now demotes a
coverage row to `none` when no unrefuted commitment claim is linked to it, and a
`none` row earns no positive rubric row, does not count toward `_coverage_state`,
and does not close the concern as `satisfied`.

- **`requires` is enforced.** `SubQuestionCoverage.evidence_claim_spans` (new)
  carries the coverage-to-claim link. `grounding.drop_ungrounded` keeps only links
  naming a claim that survived, and `pipeline/coverage_contract.py` demotes any row
  whose authored type is missing. Rhetorical and value-opinion claims satisfy
  nothing; a claim a document refutes satisfies nothing.
- **`approach_cited` needs a concrete grounded claim.** No change in
  `score_turn` was needed for this: the row still reads full/partial coverage,
  but coverage now means the contract was met.
- **`evidence_backed` rewards verified evidence either way.** It fires for a
  backed commitment or for an `empirical_checkable` claim confirmed by a tier-1+
  `supported` fact_check, both halves of whose evidence grounding has already
  proven. The row keeps its name; its description now matches its predicate.
- **`what_would_satisfy` stays authored prose** for the prompt and the presenter.
  The deterministic satisfaction contract is the per-sub-question `requires` check
  that `_coverage_state` already aggregates.
- **One authored value was wrong.** `risk.named_risk` demanded a `commitment` for
  a question that asks what is true; corrected to `fact_or_commitment`.

Rubric `version` 2 -> 3 (match conditions moved). `EXTRACTOR_CONTRACT_VERSION`
1 -> 2 (prompt ask and tool schema both changed), so every pinned extraction
re-runs on purpose.

**Not verified live:** `server/tests/golden` needs AWS credentials this
environment does not have. Its expectations were re-graded from the deterministic
rules and the model-dependent ones marked FRAGILE. The offline pins are
`server/tests/test_coverage_contract.py` and the new cases in
`server/tests/test_scoring.py`.
```

- [ ] **Step 4: Commit**

```bash
git add docs/ideation/8-how-scoring-works.md docs/ideation/2-scoring-and-drift.md docs/issues/code-enforce-rubric-semantics.md docs/superpowers/plans/2026-08-06-code-enforce-rubric-semantics-implementation.md
git commit -m "docs(scoring): record the requires contract and the v3 rubric semantics"
```

---

### Task 9: Verification sweep

**Files:** none modified unless the sweep finds a break.

- [ ] **Step 1: Full server suite**

Run: `cd server && pytest -q`
Expected: every test passes; the voice/AWS-gated tests and `tests/golden` skip. Compare the pass/skip counts against the pre-plan baseline (446 passed / 17 skipped as of `docs/issues/score-bearing-verified-evidence.md`) plus the ~20 tests this plan adds.

- [ ] **Step 2: Lint and types**

Run: `cd server && ruff check . && mypy .`
Expected: `ruff` clean. `mypy` has a large pre-existing error count from a dependency-version mismatch (217 as of the last sweep, spread across test files). Capture the count and confirm no *new* error appears in `app/pipeline/coverage_contract.py`, `app/pipeline/scoring.py`, `app/pipeline/grounding.py`, `app/pipeline/span_anchor.py`, or `app/schemas/extraction.py`:

```bash
cd server && mypy . 2>&1 | grep -E "app/(pipeline|schemas)/"
```

Expected: no output.

- [ ] **Step 3: Frontend lint**

Run: `cd frontend && npm run lint`
Expected: clean. No frontend source was touched; this catches an accidental edit.

- [ ] **Step 4: End-to-end**

Run: `cd e2e && npx playwright test`
Expected: all pass. This is the sweep that has caught fixture drift twice before — mocked `/report` and `/content/rubric` payloads in `e2e/tests/` can carry a shape or a version this change moved. `e2e/tests/scoring-legibility.spec.ts:97` mocks `version: 2`; it is a fixture, not an assertion about the live rubric, so it passes either way, but update it to `3` if it reads as documentation of the current rubric.

- [ ] **Step 5: One real rehearsal turn**

With the stack up (`docker compose up`), run a rehearsal and submit an answer that names a topic without a fact or a commitment behind it — for example, to the `risk` concern: *"We take risk very seriously and our team is experienced, so you are in good hands."*

Expected: `support_delta` 0, the transcript chip reads `Unsubstantiated`, and the persona presses the same concern again rather than moving on. Then answer it properly — *"The biggest risk is data-migration integrity across the 42 million legacy records. We mitigate it with three oldest-first waves and an automated reconciliation report after each wave."* — and expect a positive delta with a `Approach Cited` or `Evidence Backed` chip. If AWS credentials are unavailable, say so and skip this step rather than reporting it as passed.

- [ ] **Step 6: Report the sweep honestly**

Write the results into the resolution note added in Task 8: actual counts, actual skips, and anything deferred.

---

## Notes and known risks

**The `requires` check will lower scores.** That is the point, but the magnitude depends on whether the model reliably emits `evidence_claim_spans`. If it omits them, every coverage row demotes to `none`, every turn drops to `unsubstantiated`, and every concern takes its follow-up. The single sharpest signal is Task 9 step 5. If the model omits the links, the fix per `docs/ideation/2-scoring-and-drift.md` is a worked exemplar in the persona files, not a code change — but sharpening the prompt's coverage rule is also fair game before reaching for an exemplar.

**The empirical `evidence_backed` path depends on the model volunteering supported checks.** Nothing forces it to fact-check a claim it believes. The prompt now asks for it explicitly and tells the model that omitting it costs the presenter. If the golden run shows it never happens, the fallback worth considering is treating `Backing.backed` on an `empirical_checkable` claim as a second empirical door — weaker, because it is a model label rather than a verified link, which is what the issue objected to in the first place.

**Legacy extraction rows are not retroactively enforced.** A turn stored before this change has no links, so `_unique_coverage` and the report render it as it was scored. The `score_audit` in `report/builder.py` re-runs `score_turn` on the stored extraction, not `enforce_requires`, so an archived session keeps agreeing with itself. New sessions are enforced from the first turn. Do not backfill.
