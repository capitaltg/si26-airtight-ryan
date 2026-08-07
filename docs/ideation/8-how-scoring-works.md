# How Scoring Works

An end-to-end walkthrough of what happens between a presenter's answer and the number
that moves. Companion to `2-scoring-and-drift.md`, which argues *why* the design is
shaped this way; this file traces *how* the current code executes it.

> Written 2026-08-01 against the engine as it stands. It cites `file:line`, so treat the
> line numbers as signposts rather than a contract — the prose is the durable part.
>
> Updated 2026-08-06 for rubric v3: the `requires` contract check and the
> empirical path to `evidence_backed`.
>
> Updated 2026-08-06 for rubric v4: the integrity ceiling and the
> `acknowledged_revision` row.

Five stages. Only stages 3 and 5 touch the number, and both are pure code.

## 1. The model extracts; it never scores

`server/app/pipeline/extraction.py` makes one tool call at temperature 0. The model
returns structured lists and no numbers at all
(`server/app/schemas/extraction.py:118-125`):

`claims`, `sub_question_coverage`, `dodges`, `consistency_flags`, `fact_checks`,
`red_line_hits`.

Its only job is sorting the answer into small enums — `addressed: full/partial/none`,
`backing: bare/specified/backed`, `verdict: refuted/...`, `tier: 0/1`. Models are stable
at that. They are not stable at inventing a score. That split is the entire design: it
moves the reproducibility problem off the number and onto classification.

## 2. The grounding filter discards hallucinated evidence

Every finding carries a verbatim `span`. `drop_ungrounded`
(`server/app/pipeline/grounding.py:38-121`) checks that the quote actually occurs in the
answer and drops it if not, before scoring ever sees it. `drop_unanchored_flags`
(`server/app/pipeline/extraction.py:166-199`) does the same for consistency flags.

A finding that survives this stage is one you can click through to in the transcript.

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

## 3. `score_turn` — a pure function, and the whole number lives in it

`server/app/pipeline/scoring.py:46-104`. Reads the extraction, matches rubric rows, sums.

**A red line short-circuits everything:**

```python
if extraction.red_line_hits:
    return ScoreOutput(support_delta=-2, matched_rows=["red_line"], capped=True)
```

No other row is evaluated. The persona's meter pins at 25 for the rest of the session.

**Otherwise each row asks one yes/no question of the extraction:**

| Row | Fires when | Value | Times applied |
|---|---|---|---|
| `dodge` | any dodge present | -2 | once |
| `false_fact` | refuted fact_check with `tier >= 1` | -1 | **once per fact** |
| `contradiction` | any *unacknowledged* consistency flag | -1 | once |
| `acknowledged_revision` | any consistency flag the presenter openly explained | 0 | once |
| `evidence_backed` | a commitment claim with `backing == backed`, **or** an `empirical_checkable` claim confirmed by a tier-1+ `supported` fact_check | +2 | once |
| `approach_cited` | any sub-question still full/partial after the `requires` check, **and not** already `evidence_backed` | +1 | once |
| `unsubstantiated` | nothing else matched | 0 | once |

Row values are authored in `server/app/content/store/rubric.yaml`, not hardcoded.

After the clamp, any matched row that declares a `ceiling` in `rubric.yaml` holds
the delta at or below it. `false_fact` and `contradiction` both declare `0`, so a
turn containing a false statement cannot finish above 0 no matter what it also
earned. `ScoreOutput.integrity_ceiling` records whether that actually lowered the
number, which the reaction prompt reads to name the withheld credit. The over-limit
penalty runs later and is not re-ceilinged, so a long answer with a false fact
still reaches -1.

Three deliberate asymmetries in that table account for most of the confusion this engine
generates:

- **`false_fact` is the only row that multiplies.** Three refuted facts charge -3 before
  the clamp; three dodges still charge -2. See the open question at the end.
- **`evidence_backed` has two doors, and both are verified.** A backed commitment
  carries its own specifics. An empirical claim earns the row by being confirmed
  against a frozen document, which is checked the same way a refutation is. The
  row's description always said "past-performance evidence"; before rubric v3 the
  code did not.
- **Two rows fire off the same finding, and which one decides the ceiling.** A
  consistency flag lands on `contradiction` or on `acknowledged_revision`
  depending on one bool the extractor sets under a three-part bar (name the old
  position, the new one, and the reason). Only the first ceilings. This is the
  one place a model classification, rather than a code check, decides whether a
  ceiling applies — `docs/ideation/2-scoring-and-drift.md` covers what to do when
  it proves unstable.

**Tier matters.** Tier 0 means the answer conflicts with something the presenter said
earlier — that is what `contradiction` charges. Tier 1 means a document refutes it — that
is `false_fact`. The model mirrors a self-contradiction into *both* `fact_checks` and
`consistency_flags`, so `scoring.py:70` filters tier 0 out of the `false_fact` count to
avoid billing one statement twice.

Finally, `delta = max(-2, min(2, delta))`.

## Why the clamp exists

The clamp is authored rubric policy, not an arithmetic necessity. It is specified in
`2-scoring-and-drift.md` and `docs/superpowers/specs/2026-07-17-airtight-poc-design.md:108`:
"rows are summed and clamped to the -2 to +2 range." Four reasons:

1. **The bound equals the widest single row.** The rubric's extremes are `dodge` at -2 and
   `evidence_backed` at +2. Clamping there means no *combination* of behaviors can outweigh
   the worst or best *single* behavior. Rows combine to describe a turn, not to stack.
2. **It preserves red-line severity ordering.** A red line is the maximum penalty: -2 plus a
   permanent cap. Unclamped, three tier-1 false facts would be -3, so ordinary sloppiness
   would outscore crossing a hard limit.
3. **The meter is a nudge tally.** One number, 0-100, starting at 50, over roughly a dozen
   turns. A bounded per-turn step keeps a single answer from swinging it and keeps the final
   figure a running tally of behaviors rather than a magnitude contest.
4. **The schema encodes the one exception.** `support_delta: int = Field(ge=-3, le=2)`
   (`server/app/schemas/scoring.py:39`). The -3 floor is reachable only through
   `over_limit`, which is applied *after* the clamp because it is an objective length
   measurement, not a rubric judgment.

## 4. The persona reacts, and still cannot touch the number

`server/app/pipeline/reaction.py` receives the finished score and writes an in-character
reply that *describes* it. Persona voice changes wording only. A contracting officer and a
technical evaluator phrase their reactions completely differently and grade identically,
because neither one computes the grade.

## 5. Two post-hoc adjustments

**Length penalty.** `apply_limit_penalty` (`scoring.py:107-134`) runs after the reaction
and after the clamp, which is why the persisted `support_delta` bottoms out at -3 rather
than -2. It is deliberately hidden from the model — the reaction is written before the
penalty lands, so the persona cannot editorialize about it.

**Meter.** `apply_to_meter` (`scoring.py:137-154`):

```python
new = max(0, min(100, current + delta))
if already_capped or capped:
    new = min(new, cap_ceiling)   # 25, authored on the red_line row
```

Every persona starts at 50. The cap is sticky: once red-lined, that persona never recovers
for the remainder of the session.

## A worked example

An answer dodges the main question and states three facts the RFP refutes:

```
extraction:  dodges                = [deflection]
             fact_checks           = [3 x refuted, tier 1]

dodge            -2     fires once
false_fact       -3     fires three times
                 ----
raw sum          -5
clamp            -2
meter         50 - 2 = 48
```

## What the transcript now shows

`matched_rows` stays a deduplicated list, but each row now carries its application
count in `row_counts`, and the pre-clamp semantic sum rides along in
`raw_support_delta`. The worked example above renders as:

```
[-2 Max · from -5]  [Approach Cited]  [False Fact x3]
```

Three readings: `x3` is the application count (three refuted tier-1 facts, three
charges), `Max` says the turn is at the rubric's floor, and `from -5` says two
further points were absorbed by the clamp. A row carries no count when it is charged
once per answer; the count is applications, not spans.

The after-action report groups to match: one card per (turn, row), carrying every
quote that fed it, badged with `support_value * count`. Card totals now sum to the
turn delta.

The drawer discloses the rules that decide how rows combine — red line first and
alone, then sum and clamp, `false_fact` per fact, `evidence_backed` over
`approach_cited`, `contradiction` and `false_fact` split by tier, `over_limit`
after the clamp. All of it authored in `rubric.yaml` and served through
`GET /content/rubric`; none of it hardcoded in the UI.

The scoring math did not change: `support_delta`, `matched_rows`, the meter, and
`tests/golden/cases.yaml` are all untouched.

See `docs/plans/scoring-legibility.md` and
`docs/superpowers/plans/2026-08-01-scoring-legibility-implementation.md`.
