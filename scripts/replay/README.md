# Session replay

Replay canned rehearsal sessions against a running Airtight API — no browser, no
copy-paste. Useful for demoing the engine, watching a full session play out, or
re-running the same inputs repeatedly.

`../replay_session.py` is a **pure HTTP client**. It hits the same endpoints the
UI does (`POST /sessions`, `/answer`, `/clarify`) and never touches server code —
the scoring engine runs exactly as it does for a real user.

## Run

Bring the stack up, then run a scenario:

```sh
cd e2e && npm run stack:up          # or run the local dev servers
python3 scripts/replay_session.py scripts/replay/scenario-mixed.json
python3 scripts/replay_session.py --all
python3 scripts/replay_session.py --all --repeat 5      # each scenario 5x
python3 scripts/replay_session.py scripts/replay/scenario-mixed.json --report
```

Point at a non-default API with `--base-url` or `AIRTIGHT_API_URL`.

## Scenarios

| file                          | what it exercises                                                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `scenario-mixed.json`         | a believable full rehearsal: a clarify, clean passes, a coverage-gap follow-up that recovers, an over-claim, a concern that closes failed        |
| `scenario-contradiction.json` | Tier-0 `contradiction`: four conflicts between two things the presenter said, on facts absent from the RFP and proposal so nothing else can fire |
| `scenario-acknowledged-revision.json` | the mirror of the above: the same four-conflict shape, but each flip names the old position, the new one, and why it changed, so rubric v4 pays `acknowledged_revision` at 0 instead of charging `contradiction` |
| `scenario-false-fact.json`    | Tier-1 `false_fact`: six claims refutable against the RFP or written proposal, chosen to stay off the authored red lines                         |
| `scenario-custom-dana.json`   | full agenda with a temporary technical-evaluator customization                                                                             |
| `scenario-custom-marcus.json` | full agenda with a temporary contracting-officer customization                                                                            |
| `scenario-custom-priya.json`  | full agenda with a temporary program-representative customization                                                                          |

A scenario may declare `"expect_rows": ["contradiction"]` — the rubric rows that
must fire somewhere in the run. Row ids come from
[`rubric.yaml`](../../server/app/content/store/rubric.yaml); `consistency_check.py`
treats an expected row that never fires as a failure, so a scenario that drifts
into testing nothing says so instead of passing quietly.

`scenario-contradiction.json` and `scenario-acknowledged-revision.json` are meant
to be read together. Both plant Tier-0 conflicts between two things the presenter
said, on facts absent from both documents; the only difference is whether the
presenter explains the flip. Run them back to back and the rubric v4 split — a
concealed change charged as `contradiction`, an explained one recorded as
`acknowledged_revision` at 0 — is the whole delta between the two runs.

The revision fixture was written from the authored rules, not transcribed from a
recorded run, so it carries no observed-behaviour note. Run it against a live
stack before trusting any specific row or meter in it.

## Consistency check

`../consistency_check.py` replays a scenario N times and diffs the runs turn by
turn — prompt, answer sent, matched rows and their counts, the full delta
arithmetic, meter, capped, concern status, reply, rationale — plus the final
meters. Session ids and timestamps are excluded; they are supposed to differ.

"The full delta arithmetic" is four numbers, not one, because three separate
reductions sit between the summed rubric rows and the number that reaches the
meter. Two runs that arrive at the same `support_delta` by different routes have
diverged, so each is compared on its own:

| field               | what it is                                                                                                             |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `raw_support_delta` | the matched rows summed, before anything is applied                                                                    |
| `support_delta`     | the number persisted to the meter, after all three reductions                                                          |
| `integrity_ceiling` | whether a rubric v4 ceiling row (`false_fact`, `contradiction`) held the turn at or below 0                            |
| `limit`             | the measured length, its threshold, and the over-limit penalty — the reason a long answer can reach -3                 |

`integrity_ceiling` is the one field the runner derives rather than reads: the
engine computes it but the API does not return it, and the clamped raw sum
sitting above the semantic delta identifies it exactly. The play-by-play spells
each reduction out in place, e.g. `delta=+0 (held to +0 by the integrity
ceiling)`.

```sh
python3 scripts/consistency_check.py scripts/replay/scenario-contradiction.json
python3 scripts/consistency_check.py --all --runs 3 --quiet
python3 scripts/consistency_check.py scripts/replay/scenario-false-fact.json --no-cache
python3 scripts/consistency_check.py scripts/replay/scenario-custom-dana.json --compare-baseline
```

The repeat-run modes test two different things:

- **default (cache on).** Run 1 populates `model_response_cache`; later runs
  replay it. A pass means the request bytes hash identically across separate
  sessions — the guarantee [`app/bedrock/cache.py`](../../server/app/bedrock/cache.py)
  actually makes. A failure means the prompt drifted and the cache stopped
  hitting. This does **not** test the model; every call after run 1 is a replay.
  Free after the first run.
- **`--no-cache`.** Truncates `model_response_cache` between runs, so every run
  makes real Bedrock calls. This is the temperature-0 stability test from
  [docs/ideation/2-scoring-and-drift.md](../../docs/ideation/2-scoring-and-drift.md):
  a turn that swings is an unanchored case wanting an exemplar. Costs a full
  session of Sonnet calls per run. Override the truncate with `--reset-cmd` if
  your Postgres isn't the compose one.

For repeat-run modes, exit code is 0 only if every run agreed and every expected
row fired. Baseline comparison is observational, so differences do not make it
fail. The pure comparison logic is unit-tested in
[`server/tests/test_consistency_check.py`](../../server/tests/test_consistency_check.py).

`--compare-baseline` requires a scenario with a nonempty `personas` object. It
snapshots each targeted live persona, resets those IDs to shipped defaults,
uses the same scripted initial answer for each concern against the defaults,
then runs them with temporary overrides applied from that default state.
Follow-up delivery stays adaptive. It restores all pre-comparison live
snapshots afterward, including on failure. Score changes are observations from
different validated extraction facts, not failures. Reactions are always
compared too. This mode runs exactly one shipped-default/customized pair, so it
cannot be combined with `--no-cache` or a non-default `--runs` value. A
successful command reports that each baseline comparison completed; it does
not claim that the two runs reproduced identically.

## Why scenarios are keyed by concern

The engine walks a **fixed agenda**, one owner per concern:

| #   | concern             | persona             |
| --- | ------------------- | ------------------- |
| 1   | technical_approach  | technical_evaluator |
| 2   | key_personnel       | technical_evaluator |
| 3   | transition          | technical_evaluator |
| 4   | risk                | technical_evaluator |
| 5   | compliance_security | contracting_officer |
| 6   | cost_realism        | contracting_officer |
| 7   | past_performance    | contracting_officer |
| 8   | operational_impact  | program_rep         |

A scenario supplies one answer **per concern**; the runner feeds whichever answer
matches the concern the engine says is active. This is why it can't just be a flat
list of answers — the worked "sessions" in `docs/examples/example-sessions.md` are
curated _slices_ of specific concern interactions, not contiguous runnable
sessions.

## Scenario format

```json
{
  "name": "Mixed realistic run",
  "notes": ["optional lines printed before the run"],
  "concerns": {
    "technical_approach": {
      "clarify": ["optional clarifying question asked (not scored) before answering"],
      "answer": "first-attempt presenter response (required)",
      "followup": "response used if the engine presses a same-concern follow-up"
    }
  }
}
```

- `answer` — required; the first scored response for that concern.
- `followup` — used when the engine returns a follow-up prompt on the same
  concern. Omit it and the runner resends `answer` (with a warning).
- `clarify` — optional list of clarifying questions; asked once, before the first
  answer, exercising the non-scored `/clarify` path.

The exact classification and meter for each turn are decided **live by the
engine** — a scenario shapes the inputs, not the outcome.

## Temporary persona customization

A scenario can include one or more evaluator overrides. The runner snapshots the
current persona, applies only editable fields through the content API, runs the
rehearsal, then restores that snapshot even if the replay fails. If an override
omits `exemplars`, the runner carries the snapshot's complete exemplar set into
the apply request instead of clearing it.

```json
"personas": {
  "technical_evaluator": {
    "display_name": "Mara",
    "intro": "Mara Velez, senior technical evaluator. I'll press on testable architecture and controlled migration.",
    "voice": "Direct and architecture-first.",
    "values": ["operationally testable architecture"],
    "wants": ["named integration and migration controls"],
    "non_negotiables": ["do not trade migration safety for speed"],
    "polly_voice_id": "Ruth",
    "exemplars": [{"user": "...", "support_delta": 2, "note": "..."}]
  }
}
```

Allowed fields are `display_name`, `intro`, `voice`, `demographics`, `values`,
`wants`, `non_negotiables`, `polly_voice_id`, and `exemplars`. IDs, priorities,
and rubric versions stay fixed. Each custom fixture includes all eight concern
answers because the agenda does not change with a reskinned evaluator.

Persona customization changes shared, file-backed content for the duration of a
run. Do not run these scenarios concurrently with another customized replay or
any persona-writing activity. The runner restores its prior snapshot, but a
second writer can otherwise be overwritten by that restoration.

## Persona-discriminator fixtures

The three custom fixtures send the same scripted initial answer for each concern
to their shipped-default and customized runs. Follow-up delivery is adaptive.
Their target-concern answers deliberately withhold proof that the temporary
persona emphasizes. A score change or a reaction-only change is useful evidence;
neither result is guaranteed.
