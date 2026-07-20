# Stumped: One-Month MVP

_An AI practice simulator for governing under pressure. This document scopes a first release that one developer can build in about a month. The central question it has to answer: can an LLM grade a political exchange in a way that feels fair, legible, and consistent?_

---

## What it is

A role-play simulator where the user acts as an elected representative fielding questions,
complaints, and pushback from AI constituent personas, then gets scored on how well they
handled it. The loop is:

- **Setup.** The user plays an elected official or candidate, dropped into a scenario (for the
  MVP, a one-on-one constituent meeting).
- **Personas.** AI-driven constituent personas, each with distinct demographics, values, and
  priorities, raise real concerns and push back in character.
- **Loop.** The user responds in their own words; the app scores the exchange and reports how
  it shifted that persona's support.

## The problem it addresses

Governing means every position pleases some constituents and alienates others; there is no
answer that satisfies everyone. Most people never feel that tension until they are in the room,
and there is no low-stakes way to practice it. Stumped lets users feel it first-hand, and
builds three skills in a repeatable setting:

- **Thinking on your feet** under pressure and pushback.
- **Clear, direct communication** that acknowledges a concern before answering it.
- **Charitable engagement** with views the user disagrees with.

## Who it's for

- **Practitioners.** First-time or local candidates and campaign volunteers rehearsing
  constituent meetings and town halls; advocacy and community organizers practicing persuasion
  across disagreement.
- **Education.** Civics and poli-sci classrooms (high school through college), debate programs,
  and student government.

## The full vision (what the MVP scopes down from)

The complete product includes:

- **Grounded persona library** with distinct demographics, values, and priorities, each
  consistent in character across a session, plus a template so teachers or campaign staff can
  author their own.
- **Scenario modes:** one-on-one meeting, town hall (many personas at once), and hostile media
  interview, each with its own pacing and difficulty curve.
- **Performance scoring** on clarity, persuasiveness, and responsiveness (did the user address
  the concern or dodge it), a consistency check across the session, and a per-persona
  support-shift readout with rationale.
- **Adjustable difficulty**, a live **conflicting-interests dashboard** showing how gaining one
  group's approval costs another's, and **progress tracking** across sessions.

This is more than one developer can build in a month. The rest of this document describes the
reduced scope for the first release.

---

## Scope and goal

For the first release, the priority is confidence in the core loop rather than breadth of
features: a single conversation, scored in a way that holds up. If the scoring is fair and
legible on one scenario, the remaining features (town hall, dashboards, custom personas) are
extensions of something that already works. If the scoring is weak, those features do not help.

The success criterion is a quality claim rather than a feature count:

> A user has a one-on-one exchange with a constituent persona, and both the persona's reaction
> and the feedback feel earned: the user can point to why their support went up or down, and a
> skeptical observer would agree the grading was fair.

---

## What's in scope

- **One scenario mode: one-on-one meeting.** Single persona, single conversation thread. No
  concurrency, no town hall.
- **Three personas.** Enough to show contrast (for example, a fixed-income retiree, a young
  renter, and a small-business owner) while keeping each one tuned well.
- **Persona-as-its-own-judge scoring.** The persona reacts in character, and its reaction is
  the score. There is no separate external grader assigning abstract 1-5 ratings. (Described in
  the next section.)
- **Support-shift readout with a line-level rationale.** After each user turn: a delta (-2 to
  +2) and one sentence tying it to the specific thing the user said.
- **One difficulty level: "skeptical but fair."** Neither friendly nor adversarial. It is the
  most useful single setting and the one where fairness is hardest to get right.
- **End-of-session scorecard.** A roll-up showing final support per persona and the two or
  three moments that moved it most. No cross-session history or trends.
- **A written evaluation harness.** 15-20 hand-graded exemplar exchanges the developer scores,
  used both to anchor the model's judgment and to regression-test it. This is a deliverable in
  its own right: the evidence that the scoring works.

---

## Out of scope for the first release

These are deliberately excluded. Listing them keeps the scope explicit rather than open-ended.

- Town hall / multi-persona mode
- Hostile media interview mode
- Conflicting-interests dashboard
- Adjustable difficulty (friendly / adversarial tiers)
- User-facing custom-persona import (the upload UI, schema validation, and handling untrusted
  input). The persona format itself is in scope: the three presets are authored in a simple
  Markdown/frontmatter persona file and loaded from the repo, which covers most of the future
  import feature. What is deferred is letting an outside user bring their own.
- Cross-session progress tracking and analytics
- Classroom tools (assignments, grading review)
- Persuasiveness as a separate score (folded into the persona's reaction instead)
- Consistency check across turns (a V1.1 refinement; the persona reacting badly to a reversal
  already covers most of it)

---

## Stretch: voice interaction

Not in the core scope, but worth designing for from day one. The user speaks their answer
aloud and the persona replies in a spoken voice, so the practice becomes verbal instead of
typed.

Why it fits the product: the first skill this tool sets out to build is "thinking on your feet
under pressure" (see _The problem it addresses_). Typing quietly undercuts that. You can pause,
backspace, and edit yourself into a polished answer you would never produce out loud. Speaking
removes the safety net, which is closer to the real thing being rehearsed. So voice is arguably
core to the purpose rather than a cosmetic add-on.

Why it is still a stretch and not core scope:

- **It is an I/O layer, not a rearchitecture, which is the good news.** The loop stays text
  underneath: **speech in -> transcribe -> the existing judge pipeline, unchanged -> persona
  reply -> speak it out.** The scoring engine, the concern object, and the structured judge call
  do not change. Voice bolts onto the two ends. Build the app so the transcript is the interface
  and voice is a pluggable wrapper, and adding it later is cheap.
- **Validate scoring on text first.** The whole project rests on whether the scoring is fair,
  legible, and consistent. If speech-to-text mishears the user, the fairness evaluation can no
  longer tell whether the persona reacted to what the user _said_ or to what the transcriber
  _heard_. That confound is why the golden set and the consistency test should run on text, with
  voice added only once the text scoring holds up.
- **Latency is the real risk.** A turn already takes a few seconds for the judge call. Stack
  transcription plus speech synthesis on top and a turn can reach five to ten seconds of dead
  air, which is exactly what kills a "think on your feet" exercise. Truly conversational,
  real-time voice (barge-in, voice-activity detection, streaming) solves this but is a large
  scope-add that would swallow the month.

Recommended sequencing: architect for voice from the start, keep it out of Weeks 1-3, and add it
in Week 4 as demo polish or as a fast-follow after the MVP.

### Two implementation paths

- **Cheap path (roughly a weekend): browser-native Web Speech API.** `SpeechRecognition` for
  speech-to-text and `SpeechSynthesis` for text-to-speech run in the browser with no backend and
  no per-call cost. Good enough to prove the loop. Downsides: robotic voices, uneven support
  outside Chromium browsers (Safari and Firefox are spotty), and little control over quality.
- **Good path (roughly three to five days): dedicated speech-to-text plus text-to-speech APIs.**
  Transcribe with Whisper (or a real-time provider), synthesize with a high-quality voice API.
  The strong fit here is giving each persona a _distinct voice_ (the retiree, the young renter,
  and the small-business owner each sound different), which reinforces the persona concept and
  makes a memorable demo. Costs more and adds a backend hop, but the quality gap is large.

### Resources

Speech-to-text:

- Browser Web Speech API (`SpeechRecognition`): MDN docs,
  https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition
- OpenAI speech-to-text (Whisper / `gpt-4o-transcribe`):
  https://platform.openai.com/docs/guides/speech-to-text
- Deepgram (fast streaming STT): https://developers.deepgram.com/docs
- AssemblyAI: https://www.assemblyai.com/docs

Text-to-speech:

- Browser Web Speech API (`SpeechSynthesis`): MDN docs,
  https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis
- ElevenLabs (best-in-class voices, easy per-persona voice assignment):
  https://elevenlabs.io/docs/api-reference/text-to-speech
- OpenAI text-to-speech (`gpt-4o-mini-tts`, `tts-1`):
  https://platform.openai.com/docs/guides/text-to-speech
- Cartesia (low-latency streaming TTS): https://docs.cartesia.ai

Real-time / conversational (only if you commit to the harder low-latency version):

- OpenAI Realtime API (single-socket speech-to-speech):
  https://platform.openai.com/docs/guides/realtime
- Pipecat (open-source voice-agent pipeline framework): https://docs.pipecat.ai
- LiveKit Agents (WebRTC transport plus turn-taking): https://docs.livekit.io/agents

A pragmatic first step: wire the Web Speech API into the existing chat UI behind a "voice"
toggle so the text transcript still drives scoring, then swap in Whisper plus ElevenLabs only if
the demo warrants the extra quality.

---

## The core scoring mechanic

The scoring rests on one design decision worth stating up front. Instead of a hidden grader
assigning "persuasiveness: 4/5," each user turn triggers a single structured LLM call in the
persona's voice that returns:

1. `in_character_reply`: what the persona says back (this is the conversation).
2. `support_delta`: an integer from -2 to +2 for how the last answer moved this persona's
   support.
3. `rationale`: one sentence naming the specific thing the user said that caused the shift
   ("You gave a concrete number on the rent cap instead of a vague promise, so I trust you
   more").
4. `concern_addressed`: whether the answer engaged this persona's stated concern or dodged it
   (boolean plus which sub-concern).

Why this approach rather than a separate grader:

- Legibility. The rationale is not a separate explanation of a black-box number; it is the
  reason the number exists, so the persona and the score cannot disagree.
- Fairness comes from the persona's values, not the model's politics. The delta measures
  whether the answer moved this specific character given their priorities, not whether it was a
  good answer in the abstract. That reduces, though does not eliminate, the model's own lean.
- One call rather than two, which is simpler to build and cheaper to run, with no drift between
  what the persona said and how it was graded.

The persona prompt carries two or three hand-written exemplar exchanges showing what a -2, a 0,
and a +2 answer look like for that persona. Consistency comes from these concrete anchors rather
than from instructing the model to be consistent.

Each persona also has explicit non-negotiables ("I will never support a plan that raises my
property taxes, no matter how well you argue it"). These keep a persona from being talked into
anything and hold it in character.

---

## How the metrics are computed

Conciseness, responsiveness, non-dodginess, and fact-checking are all detected underneath the
persona's reaction. Two principles hold it together:

1. **Separate extraction from judgment.** First extract the objective structure (what claims
   were made, which sub-questions were touched, quoted spans, consistency, fact verdicts); this
   part is auditable and consistent. Then the persona applies subjective valence (given my
   values and red lines, do I like this?). Mixing the two is where arbitrary, hard-to-defend
   scores come from. Extraction can be audited; valence is character-driven and is meant to be
   subjective.
2. **Every judgment cites a span.** Require a quote for any claim about the user's answer. If
   the model cannot cite the user's words, treat the thing as not present.

### The concern object

When a persona raises a concern, that generation step also emits a structured concern object.
Everything downstream scores the user's answer against this object rather than against free
text, which keeps grades consistent rather than impressionistic.

```json
{
  "concern_id": "rent_burden",
  "core_ask": "What will you concretely do about rising rents?",
  "sub_questions": [
    { "id": "policy",   "text": "What specific policy?",       "requires": "commitment" },
    { "id": "timeline", "text": "When?",                        "requires": "commitment" },
    { "id": "cost",     "text": "Who pays / what's the cost?",  "requires": "fact_or_commitment" }
  ],
  "red_lines": ["dismisses renters' concerns as unrealistic"],
  "what_would_satisfy": "A named policy plus a rough timeline, even if imperfect."
}
```

Tagging each sub-question with `requires` (a `commitment`, a `fact`, or either) is what turns
dodge detection into a lookup rather than a judgment call. `fact_or_commitment` is a gradient,
not a coin flip: a hard figure earns full credit, a substantiated (`backed`) commitment earns
partial, and a bare promise counts as a soft dodge. Commitment backing is defined in section 5.

### 1. Conciseness

Conciseness here means information density, not brevity. It has two parts:

- **Deterministic sisgnals (computed in code, no LLM):** word and sentence count, Flesch reading
  level, and a filler/hedge ratio drawn from a small lexicon ("to be honest," "at the end of
  the day," "I think," qualifier stacking, repetition).
- **Density signal (one LLM extraction):** extract the distinct claims and commitments in the
  answer, then compute `density ~= substantive_claims / sentences`. A six-sentence answer with
  four real commitments scores well; a two-sentence answer that is pure reassurance scores
poorly. Report `density` and `filler_ratio`, both traceable to spans.

### 2. Responsiveness

For each `sub_question`, one judgment: `{ addressed: full | partial | none, span: "<quote>" | null }`.

- Score is the weighted fraction addressed.
- The judge must quote the exact span that addresses each sub-question, or mark it `none`. If
  it cannot cite the user's words, the sub-question was not addressed. This prevents the model
  from claiming a question was answered when it was not.
- For a sub-question that `requires` a commitment, `addressed` tracks how backed that commitment
  is (see section 5): a `backed` commitment counts as `full`, a `specified` one as `partial`,
  and a `bare` promise as `none`. A promise with no substance behind it does not count as
  answering the question.

### 3. Non-dodginess

Dodging looks like an answer but is not. A single yes/no judgment is too coarse, so classify by
type:

| Dodge type | Signature |
|---|---|
| **Topic-switch** | Answers an easier, different question |
| **Non-commitment** | Acknowledges the concern, promises nothing concrete |
| **Deflection** | Blames someone else / "that's not my department" |
| **Pure affect** | Empathy words, zero content |
| **Filibuster** | Many words, no extractable claim |

Detection reuses the machinery above. For each sub-question you already know (a) whether it was
addressed and (b) whether its `requires` field demands a commitment or a fact. A dodge is a
mismatch between what the sub-question required and what the extracted claim delivered. For
example, `addressed: partial, span exists, requires: commitment, but no commitment claim
extracted` is a non-commitment dodge, flagged automatically.

### 4. Fact-checking

The first step is claim classification. Most of what a user says is not a factual claim; it is
a commitment, a value, or rhetoric. Classify every extracted claim as
`{ empirical_checkable, commitment, value_opinion, rhetorical }` and only fact-check the first
category. This also prevents the app from fact-checking opinions, which would be inappropriate
for a civics tool. Claims typed `commitment` carry one extra field, a `backing` level, since a
promise's worth depends on the substance behind it (section 5); the other types do not.

There are three tiers of increasing difficulty and risk:

- **Tier 0: internal consistency (in scope, best return on effort).** Rather than checking
  against the world, check the user against their own earlier statements. Keep a running list
  of their claims and commitments for the session and flag contradictions ("Earlier you
  promised no new taxes; that plan needs one"). No external data is required, and it provides
  the session consistency check from the full vision.
- **Tier 1: closed-world / scenario-grounded (in scope if time allows).** Give each scenario a
  curated fact sheet (real district budget, crime, and housing figures from public sources such
  as the Census ACS, BLS, and Ballotpedia). Check empirical claims against that fact sheet only,
  via retrieval over a small trusted corpus or by including it directly in context. Bounded and
  verifiable, with no dependence on the model's own world knowledge.
- **Tier 2: open-world (deferred to V1.1).** Extract check-worthy claims, retrieve evidence from
  the web, then classify as supported, refuted, or unverifiable. Workable but slow and
  expensive, and it brings the model's own biases and knowledge cutoff into a political
  application. Deferred to a later release.

Fact-checking can also happen in character. Rather than an out-of-band flag, a well-informed
persona challenges the dubious claim directly: "Actually, the budget office says that bill does
not do that." This is more engaging and works naturally when the persona has access to the same
fact sheet.

### 5. Commitment backing

A commitment is only worth as much as the substance behind it. "I'll fix the rent problem" and
"I'll back a 5% cap, funded by a vacancy tax, introduced next session" are both commitments, but
they should not score the same. Treating any promise as equal is what lets a vague, agreeable
answer earn credit it did not earn. So every claim typed `commitment` also carries a `backing`
level:

| Backing | Signature | Example |
|---|---|---|
| **`bare`** | A promise with no mechanism, number, or timeline | "I'll take care of rents." |
| **`specified`** | Names a concrete policy or action, but nothing behind it | "I'll back a 5% annual rent cap." |
| **`backed`** | Adds a mechanism, funding source, or timeline that makes it plausible | "...funded by a vacancy tax, introduced next session." |

Backing is extracted from spans like everything else: a `backed` commitment must cite the words
that supply the mechanism or the number, or it drops to `specified`. This is what gives the
persona something to be skeptical about. At the one difficulty setting, "skeptical but fair," a
constituent hears a `bare` promise and barely moves ("I've heard promises before"); a `backed`
one moves them meaningfully. The support delta reflects the backing level rather than rewarding
the mere presence of a promise. This keeps the discount character-driven — a realistic voter
discounting cheap talk — rather than a hard-coded rule in the extraction layer.

Note what backing is *not*. It measures whether a commitment is substantiated in the room, not
whether it will be *kept*: a single meeting has no later turn to verify follow-through, so true
promise-keeping is out of scope. Within a session, Tier-0 consistency catches only
self-contradiction ("earlier you promised no new taxes"); real cross-session accountability
belongs to the full vision, where a persona remembers what you told them last time. Backing is
also not truthfulness — a `backed` commitment can still rest on a false figure, which is what
fact-checking is for.

### The structured-output contract

The per-turn judge call returns the objective extraction first, then the persona's valence.
Everything in the extraction block is span-grounded and auditable; only the last block is
subjective.

```json
{
  "extraction": {
    "claims": [
      { "text": "I'll back a 5% annual rent-cap ordinance",
        "type": "commitment",
        "backing": "specified",
        "span": "I'll back a 5% annual rent-cap ordinance" }
    ],
    "sub_question_coverage": [
      { "id": "policy",   "addressed": "full",    "span": "a 5% annual rent-cap ordinance" },
      { "id": "timeline", "addressed": "partial", "span": "next session" },
      { "id": "cost",     "addressed": "none",    "span": null }
    ],
    "dodges": [
      { "sub_question_id": "cost", "type": "non_commitment",
        "evidence": "acknowledged cost concern but named no funding source" }
    ],
    "conciseness": { "word_count": 58, "filler_ratio": 0.07, "density": 0.8 },
    "consistency_flags": [
      { "conflicts_with_turn": 2,
        "detail": "Turn 2 promised no new taxes; a rent-cap enforcement body needs funding." }
    ],
    "fact_checks": [
      { "claim": "rents rose 40% last year", "tier": 1, "verdict": "refuted",
        "source": "scenario_fact_sheet: rents +12% YoY" }
    ]
  },
  "persona_reaction": {
    "in_character_reply": "A cap is something, but who pays to enforce it? You dodged that.",
    "support_delta": 1,
    "rationale": "Named a concrete policy (good), but ducked the cost question I care about."
  }
}
```

Because every input to the `rationale` is already grounded and labeled, generating it is
straightforward. Conciseness fields come partly from code (`word_count`, `filler_ratio`) and
partly from the extraction (`density`); everything else is a single structured LLM call per turn.

---

## Data model reference

The design uses three distinct objects that live at three different moments. Keeping them
separate is the key to reading the rest of this document: the word "persona" refers only to the
first one; the other two are produced by the model during play.

| Object | When it exists | Who creates it |
|---|---|---|
| **Persona definition** | Authored ahead of time, static all session | You, by hand (a Markdown/frontmatter file) |
| **Concern object** | Emitted when the persona raises a concern | The model |
| **Judge output** | Produced after each user turn | The model |

### 1. Persona definition

The only object you author yourself. A Markdown file with frontmatter, loaded from the repo at
startup and parsed with `python-frontmatter`. The frontmatter holds the structured fields; the
Markdown body holds the hand-written exemplar exchanges.

| Property | Type | Values / notes |
|---|---|---|
| `id` | string | Stable slug, e.g. `young_renter`. Used as a key in session state and the scorecard. |
| `display_name` | string | What the UI shows, e.g. "Maya, 27, renter." |
| `demographics` | string | Who they are: age, housing status, work, neighborhood. Free text. |
| `values` | string[] | What they care about in principle ("housing should be affordable to work here"). |
| `priorities` | string[] | The concrete issues they will actually raise, in rough order. Seeds the concerns. |
| `non_negotiables` | string[] | Persona-level red lines that hold across the whole session ("I will never support a plan that raises my property taxes"). Distinct from a concern's `red_lines`, which are scoped to one concern. |
| `voice` | string | Optional. How they talk (blunt, anxious, folksy), so the `in_character_reply` stays in character. |
| `exemplars` | object[] | 2-3 hand-written examples in the Markdown body. Each is `{ persona_message, user_reply, support_delta, note }` showing what a -2, a 0, and a +2 answer look like for this persona. These are the anchors that make scoring consistent. |

The scenario fact sheet (real district figures for Tier-1 fact-checking) is authored the same
way but is scenario-level, shared by every persona in a scenario, rather than a persona field.

### 2. Concern object

Emitted by the model when the persona raises a concern. Everything downstream scores the user's
answer against this object rather than against free text.

| Property | Type | Values / notes |
|---|---|---|
| `concern_id` | string | Stable handle for the concern, e.g. `rent_burden`. |
| `core_ask` | string | One-sentence version of what the persona wants answered. |
| `sub_questions` | object[] | The concern broken into checkable pieces (see below). |
| `red_lines` | string[] | Things that would anger the persona *on this concern* ("dismisses renters' concerns as unrealistic"). Concern-scoped, unlike the persona's `non_negotiables`. |
| `what_would_satisfy` | string | Plain-language description of the answer that would move support up ("a named policy plus a rough timeline, even if imperfect"). The target the answer is graded against. |

Each entry in `sub_questions`:

| Property | Type | Values / notes |
|---|---|---|
| `id` | string | e.g. `policy`, `timeline`, `cost`. Referenced by `sub_question_coverage` and `dodges`. |
| `text` | string | The human-readable question. |
| `requires` | enum | `commitment` \| `fact` \| `fact_or_commitment`. What kind of answer counts. `fact_or_commitment` is a gradient (a hard figure = full, a `backed` commitment = partial, a bare promise = soft dodge). |

### 3. Judge output (per turn)

One object per user turn, in two blocks. The `extraction` block is objective and span-grounded
(auditable); the `persona_reaction` block is subjective (character-driven).

**`extraction.claims[]`** — the distinct claims and commitments in the answer.

| Property | Type | Values / notes |
|---|---|---|
| `text` | string | The claim, normalized. |
| `type` | enum | `empirical_checkable` \| `commitment` \| `value_opinion` \| `rhetorical`. Only `empirical_checkable` is fact-checked. |
| `backing` | enum \| null | Present only when `type` is `commitment`: `bare` \| `specified` \| `backed`. How substantiated the promise is (section 5). `null` for other types. |
| `span` | string | Exact quote from the user's answer that supports the claim. |

**`extraction.sub_question_coverage[]`** — one entry per concern sub-question.

| Property | Type | Values / notes |
|---|---|---|
| `id` | string | Matches a `sub_questions[].id` from the concern object. |
| `addressed` | enum | `full` \| `partial` \| `none`. For a commitment-requiring sub-question this tracks backing: `backed` = full, `specified` = partial, `bare` = none. |
| `span` | string \| null | Quote that addresses it, or `null` if `none`. |

**`extraction.dodges[]`** — mismatches between what a sub-question required and what was delivered.

| Property | Type | Values / notes |
|---|---|---|
| `sub_question_id` | string | Which sub-question was dodged. |
| `type` | enum | `topic_switch` \| `non_commitment` \| `deflection` \| `pure_affect` \| `filibuster`. |
| `evidence` | string | One phrase naming why it counts as a dodge. |

**`extraction.conciseness`** — object.

| Property | Type | Values / notes |
|---|---|---|
| `word_count` | integer | Computed in code. |
| `filler_ratio` | float | 0-1. Filler/hedge tokens over total, from a small lexicon. Computed in code. |
| `density` | float | `substantive_claims / sentences`. From the extraction. |

**`extraction.consistency_flags[]`** — Tier-0 contradictions against earlier turns.

| Property | Type | Values / notes |
|---|---|---|
| `conflicts_with_turn` | integer | Index of the earlier turn it contradicts. |
| `detail` | string | The contradiction in one sentence. |

**`extraction.fact_checks[]`** — only for `empirical_checkable` claims.

| Property | Type | Values / notes |
|---|---|---|
| `claim` | string | The empirical claim being checked. |
| `tier` | integer | `0` (consistency) \| `1` (scenario fact sheet) \| `2` (open-world, V1.1). |
| `verdict` | enum | `supported` \| `refuted` \| `unverifiable`. |
| `source` | string | What the verdict rests on, e.g. `scenario_fact_sheet: rents +12% YoY`. |

**`persona_reaction`** — the subjective block.

| Property | Type | Values / notes |
|---|---|---|
| `in_character_reply` | string | What the persona says back. This is the conversation. |
| `support_delta` | integer | -2 to +2. How this answer moved this persona's support. |
| `rationale` | string | One sentence tying the delta to the specific thing the user said. |

### Session state (bookkeeping)

Held per session, not returned by the judge call: the running list of the user's claims and
commitments (feeds Tier-0 consistency), the turn history, and cumulative support per persona
(rendered as the support meter and rolled up into the end-of-session scorecard). How per-turn
support accumulates into the bounded reputation meter is defined in the next section.

---

## How the score is shown to the user

Everything the user sees about how they did lives on one screen at the end of the meeting. While
the conversation is in progress, only the support meter is visible, drifting up or down as the
constituent reacts. The stats, the breakdown, and the highlights all wait until the meeting ends,
so the numbers never distract from the roleplay or turn it into a game of watching a score tick.

### The reputation meter (the headline)

The headline is a single number from 0 to 100: how much this constituent backs you by the end of
the meeting. It is the persona's own standing toward you, not an abstract grade — the same
reaction that drove the conversation, added up.

Everyone starts at 50, undecided. After each answer the constituent forms one of five reactions —
hurt you a lot, hurt you a little, no change, helped you a little, helped you a lot — and the
meter moves by a fixed amount per step, never dropping below 0 or rising above 100. How big that
step is is a dial set during the fairness evaluation: tuned so a full meeting of good and bad
answers lands the meter somewhere that feels earned, rather than letting one great line win
everything or leaving the needle stuck.

The number carries a plain-language label so it reads as a feeling rather than a test score:

| Range | Label |
|---|---|
| 0-20 | hostile |
| 21-40 | skeptical |
| 41-60 | undecided |
| 61-80 | leaning your way |
| 81-100 | won over |

Crossing one of the persona's non-negotiables caps the meter — for example, it cannot climb out
of the skeptical range no matter how well the rest of the meeting went. This is how the "cannot
be talked into anything" rule from the persona definition shows up on screen.

### Why it moved (the craft stats)

Beneath the number, three stats explain where it came from. None of them is a new score; each is
read straight off what the judge already extracted each turn, so the explanation and the number
can never disagree.

- **Concern coverage.** How much of what the constituent actually asked got answered. Each
  question they raised counts as fully answered, half-answered, or not answered, and this is the
  share that got covered.
- **Questions dodged.** How many of their questions you sidestepped — answered a different one,
  promised nothing concrete, deflected onto someone else, offered pure sympathy, or buried it in
  words.
- **Answered concisely.** How many of your answers were dense and direct rather than padded. An
  answer clears this bar when it actually says something (real commitments or facts, not
  reassurance) and stays free of filler and hedging. Where exactly that bar sits is a dial tuned
  during the evaluation, the same way the meter's step size is.

### The question-by-question breakdown

A table listing every question the constituent raised and how you handled it — answered,
half-answered, or dodged — with the exact words of yours that served as the answer, or a note
that nothing did.

This is worth including because it costs almost nothing to build. The app already records, for
every question, whether it was addressed and the quote that addressed it, so rendering the
breakdown is displaying data that already exists rather than grading anything new. If the
interface work runs long, this is the first thing to drop: the meter and the three stats above
carry the scorecard on their own.

### The moments that mattered

Two or three turns that moved the meter most, each shown with the constituent's one-line reason.
These come straight from the turns with the biggest swings and give the user the highlights
without replaying the whole transcript.

### What it looks like

```
-- Scorecard: your meeting with Maya, 27, renter --------------

  REPUTATION    62 / 100   leaning your way
                started 50, +12 over 5 turns

  Why it moved
    Concern coverage       70%     (7 of 10, counting half-answers)
    Questions dodged        2 of 5
    Answered concisely      3 of 5

  Question by question
    What's your policy on rents?    answered    "a 5% annual rent cap"
    By when?                        half        "next session"
    Who pays for it?                dodged      (no funding named)

  Moments that mattered
    +  "You gave me a real number instead of a promise."
    -  "You ducked who actually pays for it."

----------------------------------------------------------------
```

### Setting the two dials

Both dials — how big a step each reaction moves the meter, and where the "concise" bar sits — are
set the same way as everything else in the scoring: against the hand-graded golden set in the
fairness evaluation. Pick a sensible starting value, then adjust until the scorecard agrees with a
fair human grader. Until that tuning happens, the numbers are provisional.

For the builder: the meter is each turn's support reaction (`support_delta`) scaled by the step
size and clamped to 0-100; coverage, dodges, and conciseness read from the turn's
`sub_question_coverage`, `dodges`, and `conciseness` fields; the breakdown is each question's
`addressed` value plus its `span`; the moments are the turns with the largest `support_delta`. All
of these are defined in the Data model reference above — the scorecard renders them and computes
nothing new.

---

## Fairness evaluation

This is the main evidence that the scoring is trustworthy, and it needs real time in the
schedule.

1. **Golden set.** Write 15-20 exchanges (persona message plus user response) and grade the
   support-delta by hand before running them through the model. Include easy cases (a clear
   dodge scores -2) and hard ones (a technically correct but tone-deaf answer).
2. **Consistency test.** Run each exchange three times at low temperature. The delta should be
   stable (0, occasionally 1 off). Flag anything that swings by 2 or more as an unanchored case
   and add an exemplar for it.
3. **Bias probe.** Take a handful of value-neutral quality signals (specific versus vague,
   acknowledges the concern versus ignores it) and confirm they are rewarded regardless of which
   ideological direction the answer leans. Present the same well-structured answer to a
   left-leaning and a right-leaning persona and check that both grade the craft fairly even
   when the support outcome differs. Document what you find, including where it fails.

Deliverable: a short `EVALUATION.md` containing the golden set, the consistency numbers, and the
bias findings.

---

## Technical stack

The app is a small web client talking to a Python API, with one Claude call per turn doing the
judging. None of it requires a real government system, so the whole thing runs on ordinary web
infrastructure.

- **Frontend: React and TypeScript.** A single-page app built with Vite. The UI is small: a chat
  thread, a per-persona support meter, and the end-of-session scorecard. Keep state in React with
  a light store (Zustand or a reducer) rather than a heavier framework. Tailwind keeps the styling
  in the markup and the build simple.
- **Backend: FastAPI (Python).** A few endpoints: start a session, post a user turn, fetch the
  scorecard. FastAPI's Pydantic models are the natural home for the concern object and the judge's
  structured output defined above, so one schema both validates the model's response and serializes
  the API response. Python also keeps the deterministic conciseness metrics (word count, filler
  ratio, reading level) next to the model call.
- **The model: Claude Opus 4.8.** Each turn is one call to `claude-opus-4-8` through the Anthropic
  Python SDK. Use structured outputs (`client.messages.parse()` with a Pydantic model, or
  `output_config.format` with a JSON schema) so the judge call is forced to return the exact
  `extraction` plus `persona_reaction` shape instead of free text the app has to parse. The persona
  definition, its red lines, and the scoring exemplars go in the system prompt; the running
  conversation goes in the messages. Claude Haiku 4.5 is available as a cheaper option for
  development or for the purely mechanical sub-tasks, but the judging quality the project rests on
  wants the strongest model.
- **Personas and scenario data: Markdown files in the repo.** Each preset is a Markdown/frontmatter
  file (values, priorities, red lines, exemplars, and the scenario fact sheet), parsed at startup
  with `python-frontmatter`. This is the same format the future import feature reuses.
- **Persistence: DynamoDB.** Session history (turns, deltas, scorecard) keyed by user and session.
  DynamoDB is serverless and pairs cleanly with a Lambda backend; for local development, SQLite
  behind the same repository interface works with no AWS setup.
- **Hosting: AWS.** The built React app is static files on S3, served through CloudFront. The
  FastAPI app runs on AWS Lambda behind API Gateway (via Mangum), which scales to zero and costs
  almost nothing for a demo. The Anthropic API key lives in AWS Secrets Manager and is read at cold
  start, never committed. A per-turn call takes a few seconds, well within Lambda's timeout; a
  loading state covers it for the MVP, and streaming the persona's reply token by token is a later
  refinement. If an always-on container is easier to reason about, AWS App Runner runs the same
  FastAPI image with no code changes.

Putting it together: the React client sends a turn to FastAPI; FastAPI computes the deterministic
conciseness signals, calls Claude Opus 4.8 for the structured judgment, writes the result to
DynamoDB, and returns the persona's reply along with the support delta and rationale for the client
to render.

---

## Four-week build plan

| Week | Focus | Done when |
|------|-------|-----------|
| **1** | **Spike the core call plus one persona.** Get the single structured persona-as-judge call returning reply, delta, and rationale for one persona. Hard-code everything. | You can have a 5-turn conversation in the terminal and the deltas are roughly right. |
| **2** | **Get scoring quality right on one persona.** Build the golden set, add exemplar anchors, run the consistency test, and tune the prompt until deltas are stable and rationales are specific. | The consistency test passes on one persona, and you could defend the grades to a skeptic. |
| **3** | **Generalize to three personas plus a minimal UI.** Define a Markdown/frontmatter persona format (values, priorities, red lines, scoring exemplars) and author the three presets in it, loaded from the repo. Build a basic chat UI, support meter, and end-of-session scorecard. | Three distinct personas each hold character, and the UI shows running support and rationales. |
| **4** | **Evaluation write-up plus demo polish.** Run the bias probe, write `EVALUATION.md`, polish the one demo path, and rehearse. | The demo runs end to end and `EVALUATION.md` is written. |

**If Week 2 runs long:** drop to two personas before cutting the evaluation work. The evaluation
is the core of the project; the third persona is optional.

---

## What the demo shows

1. Open a one-on-one with the young-renter persona. She raises housing costs.
2. Give a vague, reassuring answer. Her support goes down, and the rationale reads: "You didn't
   give me anything concrete about rent."
3. Give a specific, committed answer. Support goes up, and the rationale cites the specific
   number.
4. Switch to the small-business owner and give that same pro-renter answer. His support moves
   the other way: the same input moves two personas in opposite directions.
5. End the session; the scorecard shows final support per persona and the two lines that moved
   it most.
6. Open `EVALUATION.md` and show the consistency numbers and bias probe as evidence that the
   grading is fair rather than arbitrary.

---

## Summary

One scenario mode, three personas, one difficulty level, a single scoring mechanic built
carefully, and a written fairness evaluation. That is a month of work that produces a working
demo and a concrete answer to a hard question. The later phases of the full vision extend this
core rather than replace it.
