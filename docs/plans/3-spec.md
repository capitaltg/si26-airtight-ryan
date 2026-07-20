# Airtight: build spec

_The implementation spec: the proof-of-concept (POC) scenario, the evaluator personas, the concern bank, and (still to come) schemas, flow, and stack. For what the product is and who it's for see [1-overview.md](1-overview.md); for how scoring and anti-drift work see [2-scoring-and-drift.md](2-scoring-and-drift.md)._

Scope is bounded by the POC section in [1-overview.md](1-overview.md): one solicitation, three personas, six to eight frozen concerns, a disclosed rubric, and an auditable after-action report.

---

## The POC scenario

One representative solicitation (the government's written request for proposals), authored once and frozen for the POC.

**Solicitation:** a five-year task order to modernize and operate a federal agency's legacy case-management system. The work includes migrating the system to the cloud, standing up 24x7 operations and maintenance, meeting the agency's security and ATO (authority to operate) requirements, and taking over from the incumbent (the contractor currently doing the work) without disrupting daily operations. The award is best-value tradeoff, meaning the government weighs price against technical merit rather than just picking the lowest bidder. The team presents its technical approach in a live oral proposal and then answers a government evaluation panel's questions.

We picked this scenario because it exercises every rubric row and every red line: technical feasibility, staffing, transition risk, cost realism, compliance, and operational impact all come up naturally.

Two fixed reference documents back the fact-checking (the "fact sheet" in [2-scoring-and-drift.md](2-scoring-and-drift.md)):

- **The RFP / PWS** (the government's written solicitation; PWS is the performance work statement). What the government asked for, including scope boundaries and mandatory requirements.
- **The team's written proposal.** What the vendor already committed to in writing. Answers that contradict it lose points.

---

## The three evaluator personas

Each persona is one markdown file (fields per the persona definition in [2-scoring-and-drift.md](2-scoring-and-drift.md) Part 3). Drafts below.

### 1. Technical evaluator (Dana)

- **voice:** precise, probing, unimpressed by buzzwords. Asks follow-ups until an answer is concrete.
- **values:** technical feasibility, staffing depth, honest risk awareness.
- **wants:** a concrete architecture, named key personnel with relevant experience, a credible transition plan.
- **priorities (concerns raised):** technical approach, key personnel, transition and schedule, risk.
- **non_negotiables:** don't hand-wave the migration; don't propose staff who don't meet the labor-category qualifications; don't claim a capability the team can't substantiate.

### 2. Contracting officer (Marcus)

- **voice:** formal and careful, listening for anything that deviates from the solicitation or creates contractual risk.
- **values:** compliance with the RFP, realistic pricing, no scope creep.
- **wants:** answers that stay inside the PWS, acknowledgment of terms and constraints, no gratuitous promises.
- **priorities (concerns raised):** compliance and security, cost realism, scope discipline.
- **non_negotiables:** don't promise work outside the PWS; don't commit to prices or terms not in the proposal; don't disparage the incumbent or competitors.

### 3. Program / end-user representative (Priya)

- **voice:** practical, focused on "what does this mean for my users and my operations."
- **values:** continuity of operations, user experience, responsive support.
- **wants:** assurance the transition won't break daily work, a clear support model, real change-management thinking.
- **priorities (concerns raised):** operational impact, support and SLAs, transition experience.
- **non_negotiables:** don't dismiss operational continuity; don't over-promise a zero-risk cutover; don't ignore end-user needs.

---

## The concern bank (eight frozen concerns)

Each concern follows the concern object in [2-scoring-and-drift.md](2-scoring-and-drift.md). `requires` controls dodge detection: `commitment`, `fact`, or `fact_or_commitment`.

| concern_id | Raised by | core_ask | requires |
|---|---|---|---|
| `technical_approach` | Dana | "Walk us through the architecture for the modernized system and why it is feasible." | fact_or_commitment |
| `key_personnel` | Dana | "Your proposed program manager: what is their relevant experience, and are they committed to this effort?" | fact |
| `transition` | Dana, Priya | "How do you take over from the incumbent without disrupting operations, and on what schedule?" | commitment |
| `past_performance` | Dana, Marcus | "Where have you done work of this size and complexity, and what was the outcome?" | fact |
| `cost_realism` | Marcus | "Your staffing looks lean for this scope. How is this priced realistically?" | fact_or_commitment |
| `compliance_security` | Marcus | "How do you meet the security and ATO requirements in the PWS?" | fact_or_commitment |
| `operational_impact` | Priya | "What does cutover day look like for my end users, and what is your support model?" | commitment |
| `risk` | Dana | "What is the biggest risk in your approach, and how do you mitigate it?" | commitment |

Each concern still needs its `sub_questions`, `red_lines`, and `what_would_satisfy` filled in and calibrated against the exemplars. That calibration work is the next step.

---

## Still to write

- **Schemas.** Turn the object tables in [2-scoring-and-drift.md](2-scoring-and-drift.md) Part 3 (persona, concern, judge output, score output, session state) into concrete schemas.
- **Per-turn call flow.** The extraction call (the model reads the answer and labels it with quotes), the code scoring step, the reaction call, and where the RFP and written proposal are injected.
- **Scoring code.** The rubric lookup, the row-combination rule, and the meter arithmetic.
- **Persona file format.** Frontmatter fields plus the exemplar body, with the three personas above as the first instances.
- **Stack.** Runtime, model, storage for session state, and how the RFP and proposal are loaded.

### Open design questions

- **Meter normalization.** The score is currently path- and length-dependent (see [2-scoring-and-drift.md](2-scoring-and-drift.md), "What the number means"). Decide whether to normalize per turn before building.
- **Rubric disclosure.** The POC promises a disclosed rubric. Confirm how and where it is shown to the user.

---

## Post-POC: real-time voice

Voice is out of POC scope but is the top post-POC priority (rationale in [1-overview.md](1-overview.md), "Where it goes next"). Speccing the seam now so the POC build does not paint it into a corner.

**Architecture: adapters around an unchanged core.** Voice wraps the existing pipeline with a speech-to-text stage on the way in and a text-to-speech stage on the way out. The scored core does not change. Only the input to extraction changes: it comes from a transcript instead of a text box.

```
text   = speech_to_text(audio)    # NEW: input adapter, before extraction
facts  = model(text, persona)     # unchanged
score  = apply_rubric(facts)      # unchanged: code owns the number
reply  = model(facts, score)      # unchanged
speak(text_to_speech(reply))      # NEW: output adapter, after the number is locked
```

**The transcript is the scored artifact.** Extraction, quotes, and the audit all run on the transcript, exactly as in the text version. To keep the audit honest under transcription error:

- Show the transcript to the presenter each turn (what the scorer heard).
- Persist the audio alongside the transcript so a disputed quoted span can be checked against the recording.
- Treat a low-confidence transcription as a data-quality signal, not a scored dodge (see open questions).

**Stack additions (AWS-native, same boundary).** Keep voice inside the same AWS account and region as the rest of the app (the security boundary in [1-overview.md](1-overview.md), "Where the data lives"):

- **Amazon Nova Sonic** for low-latency speech-to-speech, or
- **Amazon Transcribe** (speech-to-text) plus **Amazon Polly** (text-to-speech) as separate, more mature components when you want the transcript and the reply voice decoupled.

No third-party voice vendor, and no data leaving the accredited boundary.

### Open voice design questions

- **GovCloud availability.** Confirm the chosen voice service is available in AWS GovCloud (US), the isolated AWS region for US government workloads, under the same authorization as the text path before committing. Nova Sonic is newer and may lag; Transcribe and Polly are the more likely fallback.
- **Low-confidence transcription.** Define the threshold and the behavior: re-prompt the presenter, mark the turn unscored, or score it with a visible confidence flag.
- **Barge-in and interruptions.** Whether a persona can interrupt or be interrupted mid-utterance, and how that maps onto the turn boundary the scorer assumes.
- **Latency budget.** The end-to-end target, speech in to persona voice out, that keeps the rehearsal feeling live.
