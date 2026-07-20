# Airtight: project pitch

_A one-page pitch synthesizing the four planning docs, built to be talked through with a reviewer. Detail lives in [1-overview.md](1-overview.md) (product), [2-scoring-and-drift.md](2-scoring-and-drift.md) (scoring), [3-spec.md](3-spec.md) (build), and [4-chatbot-comparison.md](4-chatbot-comparison.md) (why not a chatbot)._

---

## In one line

Airtight is a flight simulator for the federal orals hot seat: proposal teams rehearse the live evaluator Q&A as many times as they need, and get a defensible score on what they actually said.

---

## The problem

- A growing share of federal contracts are won or lost in an oral presentation and live Q&A, not on the slides.
- The people in the hot seat are technical leads and program managers. They are experts in the work, not trained to handle a panel probing for weaknesses.
- One weak stretch can sink a bid worth millions: an answer that waffles, over-promises outside the solicitation, or contradicts the written proposal.
- Today's prep is a "gold team" mock panel: senior colleagues role-play evaluators once or twice before the deadline. It is expensive, it depends on who is in the room, and it walks out the door when the bid closes.
- Nobody gets to run the hard questions ten times until the answers are tight.

---

## What it does

- The presenter faces three calibrated evaluator personas: a technical evaluator, a contracting officer, and a program or end-user representative. Each pushes its own concerns and its own red lines.
- The presenter answers in their own words, the persona reacts in character, and a readiness meter moves. Try again, tighter, and watch it respond.
- Scoring reads against a fixed reference: the RFP (the government's written solicitation) and the team's own written proposal. Drift out of scope, over-commit, or contradict the proposal, and it costs points.
- It ends with an after-action report that ties every point of the score back to the presenter's exact words.

---

## What makes it stand out

Four things set Airtight apart from "just prompt a chatbot."

### 1. The proposal data never leaves a boundary the buyer already trusts

- A live proposal holds win themes, pricing, named key personnel, and sometimes CUI (controlled unclassified information). None of it can be pasted into a public chatbot, so for this buyer security decides whether the tool gets in the door at all.
- Airtight runs on AWS Bedrock, which hosts the AI model inside the customer's own AWS account and region. Prompts and proposal text are not used to train the model and are not shared with the model provider, and no consumer app in the middle keeps transcripts.
- Data is encrypted in transit and at rest, and calls can run over a private network (VPC) endpoint that never touches the public internet.
- In AWS GovCloud (US), the government cloud region, it sits under FedRAMP High, the government's high-security accreditation and the same environment the customer already runs federal work in. Airtight fits their existing accreditation rather than forcing a new one.

### 2. The evaluator personas do not drift

- Over a long chat, an AI persona slides into generic helpfulness. A helpful "evaluator" makes the whole rehearsal worthless, so holding character is a real engineering problem.
- Airtight rebuilds each persona from its file every turn, so it never leans on the model to remember who it is.
- Red lines are enforced as hard caps on the meter, not stated preferences the presenter can talk past.
- The voice is anchored with worked examples and the model runs at temperature 0 (no randomness in its output), so the persona at turn 30 is the same one from turn 1.

### 3. Code owns the score, so the grade is defensible

- A proposal shop will not accept a black-box grade. Their first question is "scored how, and can you defend it?"
- Every turn runs three steps: the model extracts quote-backed facts (answered, dodged, backed with specifics, contradicted the proposal), then code applies a frozen, version-tagged rubric, then the persona reacts to the number that was already computed.
- Because the number is a lookup plus arithmetic over the extraction, running the same answer twice scores it the same both times. A chatbot re-guesses the grade in the same breath as the reply; Airtight computes it.
- Every point traces to a rubric row and a quoted span, so the after-action report can be read and challenged line by line. Nothing about the grade has to be taken on faith.

### 4. Voice chat makes the rehearsal real (the priority stretch goal)

- Orals are spoken. Typing lets a presenter quietly edit away the rambling, filler, and freezing that only show up out loud, which is the exact skill the real panel is testing.
- The goal right after the POC is to let the presenter speak to the persona and hear it push back live, interruptions and all.
- Voice is only an input adapter: speech becomes a transcript, and the same scoring pipeline runs on that transcript. The transcript is shown to the presenter and the audio is kept, so the audit stays honest even when a word is misheard.
- The speech stack is AWS-native (Amazon Nova Sonic, or Amazon Transcribe plus Polly), so voice stays inside the same secure boundary as everything else.

---

## Who it's for, and the ROI

- Government contractors competing on orals-required bids, from large primes to mid-size firms whose survival depends on their win rate.
- The buyer is whoever owns proposal outcomes: a capture or proposal manager on a live pursuit, or a proposal center.
- The budget is B&P (bid and proposal) money on a pursuit that is live right now. It is urgent and already being spent to win, so Airtight rides it as pursuit prep instead of waiting on a slow training decision.
- One lost orals is one lost award worth millions, so the tool pays for itself against a single win.

---

## How it's sold

- **Land per pursuit, expand to a subscription.** Sell one team on one live bid first (this matches how B&P money is allocated), then expand to the proposal center that supports every pursuit, and later an enterprise tier.
- **Price against the award.** A five-figure price is a rounding error against a multi-million bid, so anchor on the value of a win, not on per-seat SaaS comps.
- **Reach buyers through CTG's network and APMP** (the proposal-management trade org), and make "defensibility" the public message.
- **Near-term the sellable unit is a CTG-delivered service** that configures Airtight for a client's specific pursuit, and becomes self-serve software as RFP ingestion matures.

---

## The first version (the proof of concept, or POC)

Deliberately narrow, sized to prove the core rather than ship a platform:

- **One solicitation:** a five-year task order to modernize and operate a federal legacy case-management system (cloud migration, 24x7 operations, security accreditation (ATO), incumbent transition), chosen because it exercises every rubric row.
- **Three personas:** technical evaluator (Dana), contracting officer (Marcus), and program/end-user representative (Priya), authored up front.
- **Eight frozen concerns** and a **disclosed rubric**, shown rather than hidden, because a team only trusts a grade it can read and challenge.
- **An auditable after-action report.**
- **Out of scope for now:** arbitrary RFP ingestion, portfolio dashboards, multi-presenter mode, and integrations. Voice is out of the POC too, but it is the top of the roadmap.

---

## Why CTG

CTG knows how orals and evaluations actually work. That domain knowledge is exactly what the personas and the rubric have to encode to be credible, and it is why this gets built here instead of by a generic AI shop.

---

## Open questions for the reviewer

- **Meter normalization.** The score is currently path- and length-dependent (a 78 after 4 turns is not the same as a 78 after 20). Decide whether to normalize per turn before building.
- **Red-line detection and cap value.** How a crossed red line reaches the extraction (the judge output schema does not yet name a red-line field), and the numeric meaning of the sticky cap it triggers.
- **AWS accreditation.** Text path confirmed (July 2026): Bedrock is FedRAMP High in AWS GovCloud (US), both regions, with Claude authorized under FedRAMP High and DoD IL4/5 (Claude Sonnet 4.5 named explicitly). Pin the cited model version, since the authorized matrix changes. Still to confirm: the voice services (Nova Sonic may lag GovCloud; Transcribe and Polly are the more likely fallback), a post-POC item.
