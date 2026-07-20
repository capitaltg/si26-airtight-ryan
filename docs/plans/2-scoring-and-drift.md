# How Airtight scores answers and keeps personas in character

_How the app scores an answer and keeps a persona in character. For what Airtight is, the problem it solves, and who it's for, see [1-overview.md](1-overview.md). This doc explains the logic, not the code._

---

## Part 1: performance scoring

### The one idea to start with

Three things happen when the app scores an answer, and they happen in a fixed order. First the model reads the user's answer and classifies it into quote-backed facts: what got answered, what got dodged, what was promised. Then deterministic code (not the model) turns those facts into a support change against a frozen rubric, the fixed scoring rules. Last, the persona reacts in character to that result. When the technical evaluator says "that staffing plan is concrete, I'm more convinced," the words describe the number the code already produced; they don't set it.

The point is that the number has exactly one owner, code reading the extraction, so it's reproducible and auditable. The reaction is generated with that number already in hand, so the words and the meter can't disagree.

### One turn, three steps

Every time the user answers, the turn moves through three steps, in order:

1. **Extraction (model, objective).** What did the user actually say? The model pulls out their claims, checks which of the persona's questions got answered, flags dodges, and quotes the exact words for each. If it can't quote the user's words for a claim, the claim doesn't count.
2. **Scoring (code, deterministic).** Code matches the extraction against the frozen rubric and computes the support change from -2 to +2. No model runs here.
3. **Reaction (model, subjective).** Given who this persona is *and the support change just computed*, how do they react? This produces the reply the user reads.

The middle step is the important part. Extraction is the same for everyone and can be audited line by line; scoring is pure arithmetic anyone can replay; only the reaction carries personality. The model classifies and speaks, but it never owns the number. If you let one model call do all three at once, you get scores nobody can defend.

(Whether extraction and reaction are one model call or two is an implementation choice. The one hard requirement is that the reaction runs *after* the score, so the persona's words can never contradict the meter.)

### What "extraction" looks for

| Signal | Plain-English question |
|---|---|
| Coverage | Did they answer each thing the evaluator asked, half-answer it, or skip it? |
| Dodges | Did an answer look like an answer but avoid the question? (changed the subject, committed to nothing, deflected to someone else, answered with enthusiasm instead of substance, or buried it in words) |
| Commitment backing | Was a claim about the approach unsubstantiated, tied to a concrete approach element, or backed by staffing, schedule, or past performance? |
| Conciseness | Was it dense and direct, or padded with filler? |
| Facts | Did an empirical claim contradict the RFP, the team's written proposal, or an earlier answer? |

Each of these is a quote-backed lookup rather than a subjective judgment, which is what makes it repeatable.

### Turning signals into a support change

Code turns the extraction into a support change against a fixed rubric. Nobody is asked "how did that feel?"; the rubric asks "which rows does this answer match?"

| What the answer did | Support change |
|---|---|
| Crossed a persona's hard limit | -2, and caps the meter |
| Dodged the main question | -2 |
| Unsubstantiated claim, or generic reassurance | 0 |
| Stated a fact that turned out false | -1 |
| Contradicted an earlier answer or the written proposal | -1 |
| Cited a concrete, compliant piece of the approach that answers the ask | +1 |
| Backed it with specific staffing, schedule, or past-performance evidence | +2 |

Rows combine; the answer doesn't just pick one. A single answer can cite a concrete approach element (+1) and contradict the written proposal (-1) at the same time. The rule: a crossed hard limit fires first and caps the meter regardless of everything else; otherwise the remaining rows are summed and clamped to the -2 to +2 range.

The persona's voice changes how the reply is worded. It never changes which rows the answer lands in, because the persona doesn't compute the rows at all; code does. That's why a contracting officer and a technical evaluator can phrase their reactions completely differently and still grade the same craft the same way.

### Why the same answer scores consistently

People usually ask this first. The number itself is never produced by the model, so the only thing that has to stay stable is the extraction the number is computed from:

- The grade is deterministic code: a lookup against the frozen rubric. Identical extractions always produce an identical number.
- That moves the reproducibility problem off the number and onto classification: the model only has to sort the answer into small enums (addressed: full/partial/none, backing: bare/specified/backed), which it does far more stably than inventing a score.
- The model runs at temperature 0. Temperature is a setting on the model call that controls randomness: at 0 the model always picks its most likely next word instead of sampling from the options, so repeats stay stable.
- The rubric is frozen and version-tagged. Changing it is a deliberate act, not silent drift.
- The extraction is forced into a fixed structure, so there's no loose text where variation creeps in.

We hold it with a golden-set regression test: run 15 to 20 hand-graded example exchanges three times each and confirm the extraction (and therefore the score) barely moves. Anything that swings gets a new worked example added until it settles, and the golden set runs again on every change so a regression shows up before it ships. The claim is controlled and regression-tested behavior, not a promise of bit-identical output on every call.

### How the user sees it

One meter, 0 to 100, starting at 50. Each answer nudges it. Cross a persona's hard limit and it gets capped no matter how well the rest went. At the end, three plain stats explain the number (how much got answered, how much got dodged, how concise the answers were), all read straight off the extraction so they can never contradict the meter.

### What the number means, and what it doesn't

The meter starts at 50 and each answer nudges it up or down. So the final number is a running tally of rubric-matched behaviors, not a percentage or a grade in the usual sense.

Reading the number, with examples:

- **50 is the neutral baseline.** You start here. A session that ends near 50 means your answers, on balance, neither won the evaluator over nor lost them: every gain was offset by a dodge, an unsubstantiated claim, or a wobble. It does not mean "average compared to other users"; it means net-zero against the rubric.
- **Below 50 (say, 34) is net-negative.** More of what the rubric penalizes than rewards: dodged the main question, made unsubstantiated claims, contradicted an earlier answer, or stated something the RFP (the government's written solicitation) or the team's written proposal refutes. A very low or floored score (say, 12) usually means a hard limit was crossed, which caps the meter no matter how well the rest went.
- **Above 50 (say, 78) is net-positive, with no red line crossed.** Your answers cited concrete, compliant approach elements, backed them with staffing, schedule, or past performance, covered the evaluator's question, and stayed concise and consistent more often than not. Higher just means more of that, sustained across the session.

What any score does claim:

- It is a tally of rubric-matched behaviors, computed by code from your quoted words, for one scenario, one persona set, one rubric version.
- It is ordinal: higher is better-handled per the rubric. 78 beats 64 beats 50.
- A mid or high score certifies no non-negotiable was crossed, because crossing one caps the meter low.
- Every point traces to a specific quote and rubric row, so it is defensible line by line.

What no score claims:

- Not a probability of real-world success. 78 is not "78% chance the real session goes well."
- Not a percentage or a percentile. 78 is not "78% correct" and not "better than 78% of other users."
- Not a factual-accuracy grade beyond the scenario. Facts are checked against the RFP, the written proposal, and your own earlier answers, not the open web.
- Not general communication skill. It scores answering craft as the rubric defines it, not tone, empathy, charisma, or delivery. A warm answer that dodges still scores like a dodge.
- Not comparable across scenarios, personas, or rubric versions. A 78 here is not the same measurement as a 78 somewhere else.
- Not the persona's literal feelings. The number comes from code; the persona's warmth or coldness is flavor generated after the number, not the source of it.

Two caveats worth stating out loud:

- It is path- and length-dependent. A 78 after 4 turns and a 78 after 20 turns are not the same amount of performance, because each turn nudges from 50. (Open question: whether to normalize per turn.)
- The three headline stats summarize the number, they do not fully derive it. Red lines, commitment backing, contradictions, and fact errors also move the meter.

---

## Part 2: keeping personas in character

### The problem

Over a long conversation, an AI persona tends to drift. The contracting officer slowly starts talking like the technical evaluator, the hard limits soften, the distinct voice flattens into generic helpfulness. If that happens, the whole exercise falls apart, because the user is no longer practicing against a real, consistent person.

### The persona is a markdown file

Each persona is one file: who they are, how they talk, what they value, what would win them over, and what they will never accept. The same file also holds two or three worked examples showing the persona reacting to good and bad answers.

That single file is the character definition, the scoring anchor, and the drift guard all at once.

### Four guardrails, cheapest first

1. **Rehydrate the versioned contract every turn.** The persona is a versioned evaluator contract, not something the model is trusted to "remember" across a long chat. Before each answer, the prompt is rebuilt from that file plus the structured session state, so the character is declared fresh on every single call. This one fix does most of the work and costs nothing.
2. **Hard limits are enforced in code, not suggested.** Each persona has red lines. Crossing one caps the support meter in code, so the model can't be sweet-talked into abandoning the character. The limit has a real consequence, so the model holds it.
3. **Worked examples anchor the voice.** The two or three examples in the file show tone, not just scoring. The model copies the register (blunt, anxious, folksy) as well as the logic.
4. **A golden-set regression test.** The same golden set that guards scoring also checks persona behavior: a change that lets a character soften its red lines or slide toward generic helpfulness shows up as a regression before it ships. A runtime self-check flag (does the reply rest on one of the persona's stated values?) gives an early warning during a session.

Running at temperature 0 helps here too: a low-randomness voice is a stable voice.

### The one-sentence version

We score with deterministic code against a frozen rubric, reading only the model's quote-backed extraction of the answer, so grades are consistent and always tied to the user's actual words; the evaluator then reacts in character to that result. We hold the character steady by re-declaring the persona from a markdown file on every turn and making its red lines cap the score, so it can't quietly drift out of character.

---

## Part 3: technical reference (the objects)

Three objects do the work, and they exist at three different moments. "Persona" means only the first one. The other two are produced by the model during play.

| Object | When it exists | Who writes it |
|---|---|---|
| Persona definition | Authored ahead of time, static all session | A human (a markdown file, or the tuning form) |
| Concern object | Emitted when the persona raises a concern | The model |
| Judge output | Produced after each user turn | The model |

### Persona definition

The only object a human writes. A markdown file with frontmatter, loaded at startup. Frontmatter holds the structured fields; the body holds the exemplars.

| Property | Type | Notes |
|---|---|---|
| `id` | string | Stable slug, e.g. `technical_evaluator`. Key in session state and the scorecard. |
| `display_name` | string | What the UI shows, e.g. "Dana, technical evaluator." |
| `voice` | string | How they talk (blunt, anxious, folksy). Keeps `in_character_reply` in character. |
| `demographics` | string | Who they are: age, housing, work, neighborhood. Free text. |
| `values` | string[] | What they care about in principle. |
| `wants` | string[] | What would win them over. Feeds the concern's `what_would_satisfy`. Editable in the tuning form. |
| `priorities` | string[] | The concrete issues they raise, in order. Seeds the concerns. Editable in the tuning form. |
| `non_negotiables` | string[] | Hard limits that hold all session. Crossing one caps the meter. Editable in the tuning form. |
| `rubric_version` | int | Which frozen rubric this persona was validated against. |
| `exemplars` | object[] | 2 to 3 worked examples in the body: `{ persona, user, support_delta, note }`. The anchors that make scoring consistent. |

### Concern object

Emitted when the persona raises a concern. Everything downstream grades the user's answer against this object rather than against free text.

| Property | Type | Notes |
|---|---|---|
| `concern_id` | string | Stable handle, e.g. `key_personnel`. |
| `core_ask` | string | One sentence: what the persona wants answered. |
| `sub_questions` | object[] | The concern broken into checkable pieces (below). |
| `red_lines` | string[] | What would anger them on this concern. Scoped to the concern, unlike `non_negotiables`. |
| `what_would_satisfy` | string | The answer that would move support up. The target the answer is graded against. |

Each `sub_questions` entry:

| Property | Type | Notes |
|---|---|---|
| `id` | string | e.g. `approach`, `staffing`, `schedule`. Referenced by coverage and dodges. |
| `text` | string | The human-readable question. |
| `requires` | enum | `commitment` \| `fact` \| `fact_or_commitment`. What kind of answer counts. Turns dodge detection into a lookup. |

### Judge output (per turn)

One object per user turn, in two blocks. `extraction` is objective and quote-grounded (auditable). `persona_reaction` is subjective (character-driven).

`extraction.claims[]` (the distinct claims in the answer):

| Property | Type | Notes |
|---|---|---|
| `text` | string | The claim, normalized. |
| `type` | enum | `empirical_checkable` \| `commitment` \| `value_opinion` \| `rhetorical`. Only the first is fact-checked. |
| `backing` | enum \| null | Only when `type` is `commitment`: `bare` \| `specified` \| `backed`. `null` otherwise. |
| `span` | string | Exact quote from the answer that supports the claim. |

`extraction.sub_question_coverage[]` (one per concern sub-question):

| Property | Type | Notes |
|---|---|---|
| `id` | string | Matches a `sub_questions[].id`. |
| `addressed` | enum | `full` \| `partial` \| `none`. For a commitment-requiring question, backing maps to this: `backed` = full, `specified` = partial, `bare` = none. |
| `span` | string \| null | Quote that addresses it, or `null`. |

`extraction.dodges[]` (mismatches between what a sub-question required and what was delivered):

| Property | Type | Notes |
|---|---|---|
| `sub_question_id` | string | Which sub-question was dodged. |
| `type` | enum | `topic_switch` \| `non_commitment` \| `deflection` \| `pure_affect` \| `filibuster`. |
| `evidence` | string | One phrase naming why it counts as a dodge. |

`extraction.conciseness` (object):

| Property | Type | Notes |
|---|---|---|
| `word_count` | int | Computed in code. |
| `filler_ratio` | float | 0 to 1. Filler tokens over total, from a small lexicon. Computed in code. |
| `density` | float | `substantive_claims / sentences`. From the extraction. |

`extraction.consistency_flags[]` (Tier-0 contradictions against earlier turns):

| Property | Type | Notes |
|---|---|---|
| `conflicts_with_turn` | int | Index of the earlier turn it contradicts. |
| `detail` | string | The contradiction in one sentence. |

`extraction.fact_checks[]` (only for `empirical_checkable` claims):

| Property | Type | Notes |
|---|---|---|
| `claim` | string | The empirical claim being checked. |
| `tier` | int | `0` consistency \| `1` RFP and written proposal \| `2` open web (deferred). |
| `verdict` | enum | `supported` \| `refuted` \| `unverifiable`. |
| `source` | string | What the verdict rests on, e.g. `rfp: PWS requires 24x7 on-site coverage`. |

`persona_reaction` (the subjective block):

| Property | Type | Notes |
|---|---|---|
| `in_character_reply` | string | What the persona says back. This is the conversation. Written after the delta is computed, so it can react to the actual result. |
| `rationale` | string | One sentence tying the reaction to the specific thing the user said. |

The support change itself is **not** in this block. It's computed by code and lives in the score output below.

### Score output (per turn)

Produced by the scoring step, not the model call. Code reads the extraction, applies the rubric, then applies the result to the meter.

| Property | Type | Notes |
|---|---|---|
| `support_delta` | int | -2 to +2. The rubric result for this turn. |
| `matched_rows` | string[] | Which rubric rows fired, e.g. `["approach_backed", "contradiction"]`. Makes the number auditable and feeds the reaction. |
| `capped` | bool | True when a hard limit was crossed, forcing -2 and capping the meter. |

### Session state (bookkeeping, not returned by the judge call)

Held per session outside the model call:

| Field | Type | Notes |
|---|---|---|
| Running claim list | object[] | The user's claims and commitments so far. Feeds Tier-0 consistency. |
| Turn history | object[] | Each turn's answer and judge output. |
| Cumulative support | map | Support per persona (0 to 100). Rendered as the meter, rolled up into the scorecard. |
| Concern status | map | Per concern: open, partial, satisfied, or dodged. Keeps the persona from re-raising a settled concern. |
| Versions | object | The frozen `rubric_version` and active persona `id`s, so scores stay interpretable and reproducible. |

### What survives a long session

The per-turn model call is built from static documents (the persona file, the RFP, the written proposal, the rubric) reloaded fresh, plus the structured session state above. It is never built from the full running transcript. That is what makes a long rehearsal safe to compress: the turn was never a function of the whole conversation, so summarizing or dropping old chat costs nothing.

What must survive exactly, as structured data and never as a prose summary:

- **The support meter and any cap flags.** A number and a sticky boolean. Summarizing them is meaningless, and a cap once applied stays applied.
- **The claim ledger, with verbatim spans.** Tier-0 consistency compares each new answer against earlier claims, so the exact earlier claim and its quote must persist. A summary would drop the specific wording needed to catch a contradiction.
- **The per-turn audit records, with verbatim quotes.** The after-action report ties every point back to exact words, and quotes cannot be rebuilt from a summary, so each turn's extraction and score output are kept verbatim.
- **Concern status.** Which concerns have been raised and whether each is open, partial, satisfied, or dodged, so coverage stays correct and the persona does not re-raise a settled concern.
- **Version tags.** The frozen rubric version and the persona ids, so the score stays interpretable and reproducible.

Static references (persona definitions, the RFP, the written proposal, the rubric) survive trivially: they are reloaded every turn rather than remembered, which is also anti-drift guardrail 1.

The trap to avoid is summarizing the conversation and feeding the summary back. Prose summarization is lossy in exactly the three places the product's credibility lives: the number, contradiction detection, and the audit trail.

### What is computed where

| Layer | Produces |
|---|---|
| Model (extraction) | Everything in `extraction`. |
| Code (no model) | `word_count`, `filler_ratio`, the meter arithmetic, and the rubric lookup that turns the extraction into the `score output` (`support_delta`, `matched_rows`, `capped`). |
| Model (reaction) | The `persona_reaction` block (`in_character_reply` and `rationale`), generated after the score. |
