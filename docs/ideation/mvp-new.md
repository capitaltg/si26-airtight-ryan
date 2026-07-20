# Stumped: one-month MVP

_An AI practice simulator for governing under pressure. This is the scope one developer can build in about a month. The whole thing lives or dies on one question: can an LLM grade a political exchange in a way that feels fair, reads clearly, and repeats the same way every time?_

---

## What it is

You play an elected official in a one-on-one meeting with a constituent. The constituent is an AI persona with its own values and priorities. You answer their concerns in your own words. The app scores each answer by how much it moved that persona's support.

The loop, per turn:

1. The persona raises a concern in character.
2. You type an answer.
3. One LLM call extracts what you actually said, then reacts in character and moves a support meter.

That's it. No separate "grader" handing out 1 to 5 stars behind the scenes. The persona's reaction *is* the score.

## What ships in v1

- One scenario: a single constituent, one conversation thread.
- Three tunable personas (for contrast: a fixed-income retiree, a young renter, a small-business owner).
- Persona-as-judge scoring with a fixed rubric (below).
- A support meter (0 to 100) plus a per-turn rationale that quotes your own words back to you.
- One difficulty: "skeptical but fair."
- An end-of-session scorecard.
- A golden set of 15 to 20 hand-graded exchanges that prove the scoring holds up.

Out of scope: town-hall mode, media-interview mode, open-web fact checking, cross-session history, classroom tools. These extend the core later. They don't help if the core scoring is weak, so v1 spends its budget there.

---

## The core scoring mechanic

Each user turn is one structured LLM call. It returns two blocks, in order:

- **`extraction`** (objective, auditable). What claims you made, which sub-questions you covered, whether you dodged, consistency against earlier turns, fact verdicts. Every field cites a quote from your answer. If the model can't quote your words for a claim, the claim doesn't exist.
- **`persona_reaction`** (subjective, character-driven). What the persona says back, a `support_delta` from -2 to +2, and a one-sentence rationale.

Keeping extraction and valence separate is the whole trick. Extraction is where determinism comes from. Valence is where the persona's personality comes from. Mix them and you get scores nobody can defend.

```json
{
  "extraction": {
    "claims": [
      { "text": "back a 5% annual rent cap", "type": "commitment",
        "backing": "specified", "span": "I'll back a 5% annual rent-cap ordinance" }
    ],
    "sub_question_coverage": [
      { "id": "policy",   "addressed": "full",    "span": "a 5% annual rent-cap ordinance" },
      { "id": "timeline", "addressed": "partial", "span": "next session" },
      { "id": "cost",     "addressed": "none",    "span": null }
    ],
    "dodges": [
      { "sub_question_id": "cost", "type": "non_commitment",
        "evidence": "named the concern but no funding source" }
    ],
    "conciseness": { "word_count": 58, "filler_ratio": 0.07, "density": 0.8 },
    "consistency_flags": [],
    "fact_checks": []
  },
  "persona_reaction": {
    "in_character_reply": "A cap is something, but who pays to enforce it? You skipped that.",
    "support_delta": 1,
    "rationale": "Named a real policy, but ducked the cost question I care about."
  }
}
```

Because every input to the rationale is already extracted and labeled, writing the rationale is trivial and it can never contradict the number.

### What gets extracted

| Signal | How it's computed |
|---|---|
| Conciseness | Word count, filler ratio, and reading level in code. Claim density (`claims / sentences`) from the extraction. |
| Responsiveness | Per sub-question: `full` / `partial` / `none`, with a quoted span or it's marked `none`. |
| Dodges | A mismatch between what a sub-question required and what you delivered. Typed: topic-switch, non-commitment, deflection, pure-affect, filibuster. |
| Commitment backing | `bare` (no mechanism), `specified` (names a policy), `backed` (adds funding or a timeline). A `backed` claim must quote the words that supply the mechanism. |
| Fact checks | Only for empirical claims. Tier 0: contradicts your own earlier turns. Tier 1: contradicts the scenario fact sheet. Tier 2 (open web) is deferred. |

---

## The fixed rubric

This is the part you asked for directly: run the same exchange twice and get the same result.

An LLM will never be bit-for-bit deterministic, but you can pin down everything that decides the grade so that repeats land in the same place. Four things do that work:

1. **The delta is a lookup, not a vibe.** The rubric below maps extracted conditions to a support delta. The model isn't asked "how did that feel?" It's asked "which row does this answer match?" Same extraction in, same row out.
2. **Temperature 0 and a fixed seed.** Greedy decoding on the judge call. No sampling variance to average out.
3. **A frozen, versioned rubric.** The rubric text lives in the system prompt with a `rubric_version` tag. Change it and you bump the version and re-run the golden set. Nothing about grading drifts silently between sessions.
4. **Structured output.** The schema forces the exact `extraction` plus `persona_reaction` shape, so there's no free-text parsing where variation sneaks in.

The rubric for "skeptical but fair," applied against the concern's `what_would_satisfy` target:

| Condition (from extraction) | Delta |
|---|---|
| Crosses a persona non-negotiable | -2 and cap the meter |
| Dodge on the core ask (any dodge type) | -2 |
| Bare commitment, or pure reassurance | 0 |
| Refuted empirical claim | -1 (persona also challenges it in character) |
| Contradicts an earlier turn | -1 |
| Specified commitment that covers the core ask | +1 |
| Backed commitment covering the core ask plus timeline or cost | +2 |

The persona's `voice` changes the wording of `in_character_reply`. It never changes the delta. That split is why two personas can phrase their reactions completely differently and still grade the same craft the same way.

**How you know it works: the consistency test.** Run every golden-set exchange three times at temperature 0. The delta should be identical, or off by 1 at most. Anything that swings by 2 is an unanchored case: add an exemplar for it and re-run. The rubric is the contract; this test is the proof the model honors it.

---

## Personas: template and drift control

A persona is a markdown file with frontmatter, loaded from the repo at startup and parsed with `python-frontmatter`. The frontmatter holds structured fields. The body holds hand-written exemplar exchanges. This same file is the character card, the tuning surface, and the drift guard.

```markdown
---
id: young_renter
display_name: "Maya, 27, renter"
voice: "direct, a little impatient, allergic to political hedging"
demographics: "Rents a one-bedroom, works retail, priced out of her own neighborhood."
values:
  - "housing should be affordable to the people who work here"
wants:                      # what would win her over
  - "a concrete rent policy with a number attached"
  - "someone who treats renting as permanent, not a phase"
priorities:                 # concrete issues she raises, in order
  - rent_burden
  - eviction_protection
non_negotiables:            # hard limits, no answer talks her past these
  - "dismisses renters as temporary or unserious"
rubric_version: 1
---

## Exemplars

- persona: "Rents keep climbing. What are you actually going to do?"
  user: "I hear you, housing is tough for everyone right now."
  support_delta: -1
  note: "Pure affect, no commitment. Bare sympathy reads as a dodge to her."

- persona: "Rents keep climbing. What are you actually going to do?"
  user: "I'll back a 5% annual cap, funded by a vacancy tax, next session."
  support_delta: 2
  note: "Backed commitment: policy, funding, and timeline. Hits her want directly."
```

### Keeping personas in character

Drift is when the persona slowly forgets who it is: the retiree starts talking like the renter, red lines soften, the voice flattens. Four guards, cheapest first:

1. **Re-inject the full card every turn.** Don't trust the persona to "stay" in context across a long chat. The system prompt is rebuilt each turn from the markdown file, so the character is stated fresh on every call. This is the single biggest drift fix and it's free.
2. **Non-negotiables are hard caps, not suggestions.** They cap the meter (see the scorecard). A persona that has been argued across a red line can't climb back out of "skeptical," which stops the model from being sweet-talked out of character.
3. **Exemplars anchor the voice.** The 2 or 3 exemplar replies in the body show tone as well as scoring. The model copies the register, not just the logic.
4. **Optional self-check field.** Add `character_consistent: bool` to the output and require the reply to rest on a stated value or priority. If it comes back false in testing, that's your drift alarm. Leave it out of the shipped output if it bloats the call.

Temperature 0 helps here too: a stable voice is a low-variance voice.

---

## Tuning a persona (preferences, desires, wants)

You wanted users to shape the persona, not just take the presets as-is. Keep it constrained so it stays MVP-sized and can't produce an incoherent character.

The user edits three fields of a preset through a small form before the session starts. Each maps straight onto the template:

| Form field | Template field | Effect |
|---|---|---|
| "What does this person want from you?" | `wants` | Sets the target `what_would_satisfy` grades against. |
| "What do they care about most?" | `priorities` | Reorders the concerns they'll raise. |
| "What will they never accept?" | `non_negotiables` | Adds a hard cap the meter can't cross. |

The form writes the same markdown or frontmatter the presets use, so tuned personas and built-in ones run through one identical code path. No separate schema, no separate loader.

Two rules keep this honest:

- **Tuning changes the target, never the rubric.** A user can make Maya want stronger tenant protections. They can't make the grader easier. The delta table stays frozen; only `what_would_satisfy` moves. So "fine-tune the persona" never becomes "fine-tune my own grade."
- **Editing a preset bumps its `rubric_version` context, not the rubric itself.** The tuned persona is a new character card. Re-run a couple of golden exchanges against it before trusting the scores.

This is a deliberately narrow slice of the full "bring your own persona" vision. Arbitrary user uploads, schema validation, and untrusted-input handling stay out of v1.

---

## Data model, in brief

Three objects at three moments. "Persona" means only the first.

| Object | When it exists | Who writes it |
|---|---|---|
| Persona definition | Authored ahead, static all session | You (or a user, via the tuning form) |
| Concern object | Emitted when the persona raises a concern | The model |
| Judge output | Produced after each user turn | The model |

The concern object is what everything downstream grades against, so grades stay consistent instead of impressionistic:

```json
{
  "concern_id": "rent_burden",
  "core_ask": "What will you concretely do about rising rents?",
  "sub_questions": [
    { "id": "policy",   "text": "What specific policy?", "requires": "commitment" },
    { "id": "timeline", "text": "When?",                 "requires": "commitment" },
    { "id": "cost",     "text": "Who pays?",             "requires": "fact_or_commitment" }
  ],
  "red_lines": ["dismisses renters' concerns as unrealistic"],
  "what_would_satisfy": "A named policy plus a rough timeline, even if imperfect."
}
```

Tagging each sub-question with `requires` turns dodge detection into a lookup: a `commitment`-requiring question answered with no extracted commitment is a non-commitment dodge, flagged automatically.

Session state (held outside the judge call): the running list of your claims for Tier-0 consistency, the turn history, and cumulative support per persona.

---

## The scorecard

During the meeting the user sees only the support meter drifting. Everything else waits for the end, so the numbers never turn the roleplay into a game of watching a counter.

**Reputation meter (the headline).** One number, 0 to 100, for how much this constituent backs you. Everyone starts at 50. Each turn's reaction moves it by a fixed step, clamped to 0 and 100. Crossing a non-negotiable caps it inside a range no matter how well the rest went. Labels: 0 to 20 hostile, 21 to 40 skeptical, 41 to 60 undecided, 61 to 80 leaning your way, 81 to 100 won over.

**Why it moved (three stats).** All read straight off the extraction, so they can't disagree with the number: concern coverage (share of their questions you answered), questions dodged, and answers that were concise and substantive.

**Question by question.** Every concern they raised, whether you answered / half-answered / dodged it, and the exact words that served as your answer. Cheap to build since the data already exists. First thing to cut if the UI runs long.

**Moments that mattered.** The two or three turns with the biggest swings, each with the persona's one-line reason.

```
-- Scorecard: your meeting with Maya, 27, renter --------------

  REPUTATION    62 / 100   leaning your way
                started 50, +12 over 5 turns

  Why it moved
    Concern coverage       70%     (7 of 10, counting half-answers)
    Questions dodged        2 of 5
    Answered concisely      3 of 5

  Question by question
    What's your policy on rents?   answered   "a 5% annual rent cap"
    By when?                       half       "next session"
    Who pays for it?               dodged     (no funding named)

  Moments that mattered
    +  "You gave me a real number instead of a promise."
    -  "You ducked who actually pays for it."
----------------------------------------------------------------
```

The two dials (meter step size, and where the "concise" bar sits) are tuned against the golden set until the scorecard agrees with a fair human grader. Until then the numbers are provisional.

---

## Fairness evaluation

The main evidence that the scoring is trustworthy. It needs real time in the schedule.

1. **Golden set.** 15 to 20 exchanges, delta graded by hand before the model sees them. Mix easy cases (a clear dodge is -2) and hard ones (technically correct but tone-deaf).
2. **Consistency test.** Each exchange three times at temperature 0. Delta stable, off by 1 at most. Swings of 2 mean an unanchored case: add an exemplar.
3. **Bias probe.** Show the same well-structured answer to a left-leaning and a right-leaning persona. The support outcome can differ; the craft (specific vs. vague, engages vs. ignores) must be rewarded either way. Document where it fails.

Deliverable: a short `EVALUATION.md` with the golden set, the consistency numbers, and the bias findings.

---

## Stack

A small React client talking to a Python API, one Claude call per turn.

- **Frontend:** React plus TypeScript, Vite, Tailwind. A chat thread, a support meter, the scorecard, and the persona-tuning form. Light state (Zustand or a reducer).
- **Backend:** FastAPI. Endpoints to start a session, post a turn, fetch the scorecard. Pydantic models are the home for the concern object and the judge output, so one schema validates the model's response and serializes the API response. The deterministic conciseness metrics live here in code, next to the model call.
- **Model:** Claude Opus 4.8 (`claude-opus-4-8`) through the Anthropic Python SDK, temperature 0, structured outputs (`client.messages.parse()` with a Pydantic model). The persona card, its red lines, the rubric, and the exemplars go in the system prompt; the conversation goes in the messages. Haiku 4.5 is fine for mechanical sub-tasks, but the judging wants the strongest model.
- **Personas and scenario data:** markdown or frontmatter files, parsed at startup. Same format the tuning form writes.
- **Persistence:** DynamoDB keyed by user and session (SQLite behind the same interface for local dev).
- **Hosting:** static React on S3 plus CloudFront; FastAPI on Lambda behind API Gateway (via Mangum). API key in Secrets Manager, read at cold start, never committed.

Per turn: the client posts an answer, FastAPI computes the conciseness signals, calls Opus for the structured judgment, writes it to DynamoDB, and returns the reply plus delta and rationale.

---

## Voice (stretch)

Not core, but architect for it from day one. The first skill this tool builds is thinking on your feet under pressure, and typing lets you edit yourself into a polished answer you'd never say out loud. Speaking removes that safety net.

It's an I/O layer, not a rearchitecture: speech in, transcribe, run the existing judge pipeline unchanged, speak the reply out. Build so the transcript is the interface and voice is a pluggable wrapper. Keep it out of Weeks 1 to 3 for two reasons: the fairness evaluation has to run on text (if speech-to-text mishears you, you can't tell whether the persona reacted to what you said or what the transcriber heard), and latency stacks up fast (transcription plus synthesis on top of the judge call can hit five to ten seconds of dead air).

Cheap path (a weekend): the browser Web Speech API, no backend, no per-call cost, robotic voices, spotty outside Chromium. Good path (a few days): Whisper for transcription plus a quality TTS API, with a distinct voice per persona, which reinforces the character concept and demos well.

---

## Four-week build plan

| Week | Focus | Done when |
|---|---|---|
| 1 | Spike the core call plus one persona. One structured persona-as-judge call returning reply, delta, and rationale. Hard-code everything. | A 5-turn terminal conversation with roughly right deltas. |
| 2 | Get scoring right on one persona. Build the golden set, add exemplar anchors, freeze the rubric, run the consistency test, tune the prompt. | The consistency test passes and you could defend the grades to a skeptic. |
| 3 | Three personas, tuning form, minimal UI. Author the three presets in the markdown template, build the chat UI, support meter, scorecard, and the tuning form. | Three personas hold character, the UI shows running support and rationales, and a user can retune a preset. |
| 4 | Evaluation write-up and demo polish. Run the bias probe, write `EVALUATION.md`, polish the one demo path, rehearse. | The demo runs end to end and `EVALUATION.md` is written. |

If Week 2 runs long, drop to two personas before cutting evaluation work. The evaluation is the project.

---

## What the demo shows

1. Open a meeting with Maya, the young renter. She raises housing costs.
2. Give a vague, reassuring answer. Support drops: "You didn't give me anything concrete about rent."
3. Give a specific, backed answer. Support rises, and the rationale cites the number.
4. Switch to the small-business owner and give that same pro-renter answer. His support moves the other way: one input, two personas, opposite directions.
5. Retune Maya through the form to care more about eviction protection, replay a turn, and watch the target shift while the rubric stays put.
6. End the session and open `EVALUATION.md`: the consistency numbers and bias probe are the evidence that the grade is earned, not arbitrary.

---

## Summary

One scenario, three tunable personas, one difficulty, one scoring call built around a frozen rubric, and a written fairness evaluation. The rubric plus temperature 0 plus anchored exemplars is what makes a repeated exchange reproduce. The markdown character card, re-injected every turn with non-negotiables as hard caps, is what keeps personas in character. The tuning form lets users shape what a persona wants without touching how it grades. Everything else in the full vision extends this core rather than replacing it.
