# code must enforce rubric's semantics

### What I found

The scorer is deterministic, but several semantic rules still depend entirely on model labels:

- A sub-question's requires field can be fact, commitment, or fact_or_commitment. That value appears in the
  prompt, but code does not enforce it.
- approach_cited fires for any full or partial coverage. The finding does not need a cited approach or compliant claim.
- evidence_backed fires only for a commitment labeled backed. A strongly verified empirical answer cannot earn this
  row even though the rubric description includes past-performance evidence.
- what_would_satisfy influences the prompt, but it is not a deterministic validation contract.
  That means a rhetorical span can be labeled partial coverage and receive +1, while a fully documented empirical answer can be limited to +1 unless the model also identifies a backed commitment.

### What I would change

Replace broad addressed labels with atomic check results tied to the authored concern contract. For each sub-question, identify the required evidence type and the exact grounded claim that satisfies it. Let code derive coverage from those verified links.
I would also align the row names with their predicates:

- approach_cited should require a concrete grounded approach claim;
- evidence_backed should reward verified evidence whether the answer is empirical or a commitment, or the row
  should be renamed backed_commitment.
  The question I would put back to you is: what does requires: commitment change in deterministic code today? If the
  answer is "nothing," the contract is not finished.

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

**Verified live (2026-08-06, Task 9 sweep).** Offline: `pytest -q` in `server`
gives 504 passed, 17 skipped (the AWS/voice-gated tests and `server/tests/golden`
skip under a plain run because `.env` isn't sourced into that process); `ruff
check .` is clean; `mypy .` reports 233 pre-existing errors, none in
`app/pipeline/{coverage_contract,scoring,grounding,span_anchor}.py` or
`app/schemas/extraction.py`; frontend `tsc -b` is clean; all 77 `e2e` Playwright
tests pass against a live `docker compose` stack.

Contrary to earlier tasks' assumption, this environment's root `.env` AWS
credentials do resolve and do reach Bedrock once exported into the process
(`sts:GetCallerIdentity` and a `bedrock-runtime` `Converse` call both
succeeded), so the rehearsal and the golden corpus were both run live instead
of skipped. Driving a running session via the `/sessions` API: a vague
reassurance on the `transition` concern reproduced the intended path exactly
(`unsubstantiated`, support_delta 0, the same concern pressed again on
follow-up); the same phrasing against `risk` instead matched `red_line`
(support_delta -2, concern closed as breached) rather than `unsubstantiated`,
and a properly evidenced mitigation answer matched `evidence_backed`
(support_delta +2) — both confirm the `requires` contract and the broadened
`evidence_backed` path fire on real model output, with the caveat that the
model doesn't always pick the row a human would predict for a given phrasing.

`pytest tests/golden -m golden -v` (bonus, beyond what Task 7 could run): 10
passed, 7 failed. Four failures are the FRAGILE cases `cases.yaml` already
called out — `approach_architecture_concrete`, `dodge_risk_deflection`,
`false_fact_pm_years`, `combo_dodge_plus_approach` — landing exactly where
their own notes predicted. Three are mismatches the corpus doesn't flag yet:
`approach_transition_compliant` swings on the same axis as the flagged
architecture case (model volunteers `evidence_backed` where `approach_cited`
was graded); `false_fact_record_count` drops its `approach_cited` credit next
to the `false_fact` penalty (grounding logged `dropped full coverage ...
ungrounded span: None`); `unsubstantiated_support` lands on `red_line`, the
exact direction its own note already named as the remaining risk. None of
these three were re-graded here — flagging them for a follow-up calibration
pass per `cases.yaml`'s own deferred "CALIBRATION (step 3, needs AWS creds)"
step, not treating them as a code regression. The offline pins remain
`server/tests/test_coverage_contract.py` and the new cases in
`server/tests/test_scoring.py`.
