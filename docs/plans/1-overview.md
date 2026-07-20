# Airtight: what it is, the problem, and who it's for

_The plain-language overview: what the product does, the problem it solves, who buys it, and why they care. The scoring and anti-drift mechanics live in [2-scoring-and-drift.md](2-scoring-and-drift.md); the build spec is [3-spec.md](3-spec.md)._

---

## The one-line version

Airtight is a rehearsal environment where federal-contracting proposal teams practice the live question-and-answer of an "oral proposal" against realistic AI evaluator characters, and get scored on what they actually said, with a grade they can defend.

Think of it as a flight simulator for the orals hot seat, where you can't rewind the questions once the evaluators start asking.

---

## The problem

A growing share of US federal contracts are decided by an oral presentation. The vendor team presents its approach, then answers questions from a government evaluation panel, live. The award often turns on that Q&A, not the slides.

The people in the hot seat are technical leads and program managers. They are experts in the work, but they are not trained to handle a panel probing for weaknesses. One weak stretch of Q&A can sink a pursuit worth millions: an answer that waffles, over-promises something outside the solicitation (the government's written request), or contradicts what the team already wrote in its proposal.

### How teams prepare today

The standard prep is a "gold team" mock panel: senior colleagues role-play the evaluators and grill the presenters. It works, but it is expensive and thin. It burns the time of the most senior people in the company, it happens once or twice before the deadline, its quality depends entirely on who is in the room, and the moment the bid closes it all walks out the door.

Nobody gets to run the hard questions ten times until the answers are tight.

---

## What Airtight does

Airtight lets a proposal team rehearse the orals Q&A as many times as they need, before the real panel.

The presenter faces calibrated evaluator characters (we call them personas): a technical evaluator, a contracting officer, and a program or end-user representative. Each one pushes on its own concerns and its own red lines. The presenter answers in their own words, the persona reacts in character, and a readiness meter moves. Run it again, try a tighter answer, watch the meter respond.

The scoring reads against a fixed reference: the RFP (the government's written solicitation) and the team's own written proposal. An answer that drifts out of scope, over-commits, or contradicts the submitted proposal is caught and costs points. At the end, the presenter gets an after-action report that ties every point of the score back to their exact words, defensible line by line.

How the score is produced, and how each evaluator persona is kept from drifting out of character over a long session, is in [2-scoring-and-drift.md](2-scoring-and-drift.md).

---

## Who it's for

Airtight is sold to government contractors that compete on orals-required bids, from large primes down to the mid-size firms whose survival depends on their win rate. That is the beachhead, and the section after this one shows why it is not the ceiling.

**The economic buyer** is whoever owns proposal outcomes: a capture manager or proposal manager on a specific pursuit, or the proposal center (sometimes a "proposal center of excellence") that supports pursuits across the company.

**The budget** is B&P (bid and proposal) money, the funds allocated to pursuing a specific bid. That matters. B&P is time-boxed and urgent, and it is money the firm is already spending to win the bid. Airtight is not a nice-to-have training line item. It is prep for a deal that is live right now.

**Why they care:** one lost orals is one lost award, often worth millions. A tool that makes the Q&A tighter, that any presenter can drill against on their own schedule, and that hands senior staff their gold-team hours back, pays for itself against a single win. Across a pipeline of pursuits, it makes orals readiness consistent instead of dependent on who happened to run the last mock panel.

### The general shape of the problem

Federal orals is one instance of a pattern. It helps to see the pattern directly, because it tells you which other markets are real and which only look similar.

A scenario fits Airtight when three things are true:

1. **An expert panel probes you for weakness, live.** Not a friendly audience. Someone whose job is to find the hole in your answer while you are standing there.
2. **There is a fixed reference to grade against.** A rubric (the fixed scoring rules), plus your own prior written record: the proposal, the brief, the filing, the dissertation, last quarter's guidance. Contradicting your own record is the fatal move, and because the record is fixed, code can check for it.
3. **Prep today is a scarce, expensive human mock panel.** Senior people role-play the examiner once or twice, and the value leaves the building when they do.

If you think of it as software, the shape is one you already know: one engine, many configs. The scoring engine, the persona machinery, and the anti-drift guardrails do not change. A vertical is a config: its rubric, its persona files, its reference documents. Federal orals is the reference implementation we build first.

### Where else the same engine runs

These all satisfy the three traits, so the "code owns the number, traced to your exact words" design carries over with no redesign:

- **Legal: oral argument and moot court.** An attorney rehearses appellate argument against a hot bench. The reference is the record and their own brief, and contradicting the brief mid-argument sinks the case. Deposition prep and expert-witness cross fit the same mold.
- **Academic: thesis or viva defense.** A PhD candidate defends against a committee hunting for holes. The reference is their own dissertation. "You claimed X in chapter 4 but just said Y" is exactly the drift the scorer catches.
- **Corporate: earnings-call and investor Q&A.** An executive or investor-relations lead faces analysts. The reference is prior guidance and the 10-K, and contradicting old guidance carries real regulatory risk. High stakes, recurring, well funded.
- **Public sector: congressional or regulatory testimony.** A witness holds a position against a hostile panel. The reference is prior written testimony and the submitted record.

A second tier still runs the same rehearsal loop but grades against a standard rather than a document you wrote, so the self-contradiction hook is weaker: medical oral boards, commercial sales and security due-diligence grilling, consulting case interviews, and crisis-comms or media training. These are real markets with a slightly different pitch.

The takeaway for the build: none of this asks for new core machinery, only new configs. That is the argument for getting the engine and the config boundary right in the POC, even while we ship a single vertical.

---

## Why CTG, and why AI

The hard part was never building a chatbot that role-plays an evaluator. The hard part is scoring the practice in a way a buyer trusts. A proposal shop that lives on win themes and evaluation criteria will not accept a black-box grade. They will ask "scored how, and can you defend it?"

Airtight's design answers that. Every point traces to the presenter's actual words, checked against the RFP and the written proposal, and computed by deterministic code rather than an AI's judgment in the moment. The model reads and reacts; the number is owned by auditable code. That defensibility is what makes this a serious tool rather than a demo.

CTG's footing in the govcon (government contracting) world is the reason to build it here. The company knows how orals and evaluations actually work, which is exactly the domain knowledge the personas and the rubric have to encode to be credible.

---

## Why not just prompt a chatbot?

This is the first question anyone asks. Short version: a chatbot *improvises* the grade; Airtight *calculates* it.

The difference is which part of the system decides the number, the model or plain code:

- **The model** is good at *understanding* text and bad at being *consistent*. Ask it the same thing twice and you can get two different answers.
- **Code** has no opinion, but the same input always gives the same output.

A chatbot writes the reply and picks the number in one shot:

```
reply, score = model(answer, rubric, persona)   # model decides everything
```

Airtight takes the number out of the model's hands and gives it to code:

```
facts = model(answer, persona)   # model ONLY classifies into a checklist
score = apply_rubric(facts)      # plain code: deterministic, replayable
reply = model(facts, score)      # persona reacts AFTER the number is locked
```

The model still does what it's good at: reading your answer, filling out a checklist of quote-backed facts (answered, dodged, backed with specifics, contradicted the proposal), and talking in character. It never touches the number.

That one move is what a chatbot can't match, no matter how you prompt it:

| | Chatbot | Airtight |
|---|---|---|
| Same answer, same score? | No. It re-guesses each time. | Controlled. `apply_rubric()` is deterministic, and the classification it reads is regression-tested. |
| Bends to flattery or arguing? | Yes. Say "come on, that was good" and it caves. | No. The number comes from the checklist, not a mood. |
| Can it show its work? | No. It invents a story for "why 72?" after the fact. | Yes. The score *is* the rubric rows that fired plus your quoted words. |

**"But what if I paste the rubric and persona files into the prompt?"** That changes what the model *reads*, not who *computes*. It's still `model(...)` doing the scoring by feel while it writes the reply. The rubric file is the same, but a chatbot re-improvises how to apply it every turn instead of running it. A prompt can only add instructions for the model to follow. It can't remove the model from a step, because the prompt is the model doing the step. Airtight's trick is subtraction, and you can't prompt your way to subtraction.

**"But what if I tell it to follow the rubric exactly and not make assumptions?"** That's an instruction, not a mechanism. It's like a `# please be deterministic` comment above a function that isn't. It can't fix two things. First, the rubric says how many points a dodge costs, but never whether this answer dodged. That call is left to the reader, so the model makes it fresh, and differently, every time. Second, "don't assume" is impossible here: scoring a freeform answer *is* interpreting it, so there's no assumption-free version to ask for. Airtight doesn't tell the model to stop interpreting. It shrinks the interpretation to picking one of a few labels (`full/partial/none`) with a required quote, then hands the math to code.

**"Then let it chat and score once at the end?"** Worse. Now the model grades a long conversation from fuzzy memory in one guess. It over-weights the last few turns, misses contradictions (catching "full-time in turn 4, half-time in turn 15" needs turn 4's exact words, which a summary drops), and can't cite specifics. It also kills the practice loop (the meter moving *as you answer*) and lets the persona drift out of character over the unscored chat.

Same rubric, same personas either way. The only difference is that the number is *generated* in a chatbot and *computed* in Airtight. That's the exact thing a buyer needs to be able to defend.

---

## Where the data lives: security and privacy

A proposal shop asks two questions of any new tool. The first is the one we keep answering: scored how, and can you defend it? The second is quieter and just as fatal if you get it wrong: where does our data go?

The data in play is some of the most sensitive a contractor owns. A live proposal holds win themes, pricing, staffing plans, named key personnel, and sometimes controlled unclassified information (CUI). None of it can be pasted into a public chatbot, whatever the model quality. So for this buyer "just use ChatGPT" fails twice: once on scoring, and once before that, on data handling. The security answer decides whether you get in the door at all.

Airtight is built on AWS Bedrock, an AWS service for running AI foundation models inside your own AWS account, which is what lets the data answer be short and credible:

- **The data stays in the customer's boundary.** Inference runs in the customer's own AWS account and region. Prompts, proposal text, and answers are not used to train the underlying model and are not shared with the model provider. There is no consumer app in the middle collecting transcripts.
- **Frontier-model quality without the consumer-app exposure.** Bedrock serves the same class of frontier models a team would reach for on the open internet (including Anthropic's Claude), but the prompt and proposal never leave the customer's boundary and never reach the model provider. So the choice is not "good model but risky data path" versus "safe but weak"; it is the same model quality with the data path the buyer can actually clear.
- **It is encrypted and can stay off the public internet.** Data is encrypted in transit and at rest, with support for customer-managed KMS keys, and calls can run over a private VPC endpoint so traffic never crosses the open internet.
- **It targets a boundary federal buyers already run.** Bedrock is available in AWS GovCloud (US), the US government cloud region, where the service carries FedRAMP High authorization, the same class of environment the customer already runs federal workloads in. That gives Airtight a credible path to accreditation inside a program the buyer already has rather than a separate one to stand up. Airtight still earns its own authorization to operate; the platform's FedRAMP High status is the starting posture, not a grant that makes the app accredited on day one.

The practical version for a developer: there is no separate data plane to secure. Airtight is an application sitting on top of the customer's Bedrock, so it inherits the account's IAM, KMS, VPC, logging, and region controls instead of inventing its own. The audit trail the scoring already produces, every point tied to a quoted span and a rubric row, lives inside that same governed environment.

This is the second half of what protects the product. The first half is a score you can defend. The second is that you can defend it without your proposal ever leaving a boundary you are already cleared to use.

---

## The ROI line

The product costs a rounding error against a single lost award. It turns a scarce, once-or-twice gold-team rehearsal into unlimited on-demand practice, gives senior staff their time back, and makes readiness consistent across every pursuit in the pipeline.

---

## How to market it

One idea drives all of this: **sell it as prep for a deal that's live right now, not as training.** Training competes for a slow training budget and a "someday" decision. Pursuit prep rides B&P money that's already allocated to a specific bid and already being spent to win it. Same product, far less friction to the first dollar.

The pitch is the ROI line above, said out loud: one lost orals is one lost award worth millions, so a tool that makes the Q&A tighter pays for itself against a single win.

Where to actually reach the buyer:

- **Start inside CTG's network.** CTG already lives in this world and knows how orals and evaluations work. That credibility, plus a first real client from CTG's orbit, is the wedge. A win story from a team the buyer respects sells better than any ad.
- **Go where proposal people gather.** APMP (the Association of Proposal Management Professionals) is the trade home of the exact buyer: capture managers and proposal centers. Conferences, local chapters, and content aimed at them.
- **Land one pursuit, then expand to the proposal center.** Sell one team on one bid first. If it helps them win, the proposal center that supports *every* pursuit becomes the next, bigger sale.
- **Make "defensibility" the public message.** The buyer's first objection is "scored how, and can you defend it?" Explaining our auditable scoring in public is both marketing and a competitive advantage. It answers the objection before it's asked. (The scoring design that backs this claim is in [2-scoring-and-drift.md](2-scoring-and-drift.md).)

---

## How to monetize it

The way B&P money works points to a natural progression: **start with per-pursuit pricing, expand to a subscription.**

- **Land: per-pursuit pack.** A firm buys Airtight for one live solicitation. This matches how the money is allocated (B&P against a specific bid), so it's the easiest first dollar to get. This is the wedge.
- **Expand: annual subscription.** Once a firm runs several orals bids a year, the pitch shifts to consistency across the whole pipeline, sold per proposal center or per seat. This is predictable recurring revenue for us.
- **Later: enterprise tier.** Large primes with dedicated proposal centers, plus everything the POC deliberately punts: arbitrary RFP ingestion, portfolio dashboards, team analytics, integrations. Highest price, longest sales cycle.

Two things worth knowing as a developer building this:

1. **Price against the award, not against our costs.** The bid is worth millions, so even a five-figure price per pursuit is a rounding error to the buyer. We anchor on the value of a win, not on per-seat SaaS comparisons or what it costs us to run.
2. **Real per-pursuit revenue needs per-pursuit setup, which the POC doesn't do yet.** Charging a client for *their* bid means ingesting *their* RFP and *their* proposal to author the personas and concerns, and that's explicitly out of POC scope (see below). So near-term the sellable unit is likely a CTG-delivered service (CTG configures Airtight for a client's specific pursuit) that becomes self-serve software as RFP ingestion matures. Good news for the build: we don't have to solve arbitrary RFP ingestion to earn the first revenue.

---

## What the first version is (the POC)

The proof of concept is deliberately narrow. It is sized to prove the core idea, not to ship a platform:

- **One solicitation.** A single, representative RFP with a defined evaluation focus, not an RFP ingestion engine.
- **Three evaluator personas.** The technical evaluator, the contracting officer, and the program or end-user representative, authored ahead of time.
- **Six to eight frozen concerns.** A fixed bank drawn from that solicitation (technical approach, key personnel, past performance, transition and schedule, risk, cost realism, compliance), written and calibrated up front, not generated on the fly.
- **A disclosed scoring rubric.** The rubric is shown to the user, not hidden. A proposal team will only trust a grade they can read and challenge.
- **An auditable after-action report.** At the end of a session the presenter gets a report that ties every point of the score back to their own words and to the RFP or proposal, defensible line by line.

Everything else waits. Uploading an arbitrary RFP to auto-generate personas and concerns, portfolio dashboards and team analytics, multi-presenter live team mode, and integrations are all out of scope for the POC. They are real features for later, not part of proving the core. Real-time voice is out of scope for the POC too, but it is a different kind of "later," so it gets its own section below.

---

## Where it goes next: real-time voice

The POC is text: the presenter types answers, the persona replies in text, the meter moves. That is the right first build, because it proves the scoring defensibility at the lowest cost. But it is not the finished product, and the single most important thing after the POC is voice.

Voice is a priority, not a garnish. Orals are spoken. The real hot seat is a person answering out loud, under time pressure, with no backspace. A lot of what sinks a presenter only exists in speech: rambling past the question, filler and hedging, freezing on a hard follow-up, a tone that reads as evasive. Typing lets the presenter quietly edit all of that away, which means text rehearsal trains a skill next to the one being tested rather than the one being tested. Voice is what makes "flight simulator for the hot seat" literal: the presenter speaks to the persona and hears it push back in real time, interruptions and all.

It is a stretch goal only in sequencing, not in importance. Text first proves the hard part, a defensible number, without paying for real-time audio latency, cost, and transcription accuracy up front.

**Does voice break the scoring defensibility?** No, as long as it is built as an input method rather than a new scorer. Only one stage is added:

```
audio = microphone_capture()      # NEW
text  = speech_to_text(audio)     # NEW: the only added stage
facts = model(text, persona)      # unchanged
score = apply_rubric(facts)       # unchanged: still plain code
```

The transcript is the canonical scored artifact, the same text the extraction and the deterministic scorer already consume. The one new risk is transcription error: if speech-to-text mishears a word, the quote in the audit is quoting the transcript, not the audio. The fix is to make the transcript visible (the presenter sees what was heard) and to keep the audio so a disputed quote can be checked against the recording. The number is still computed by code over the transcript, exactly as in the text version.

**Does voice break the security boundary?** No. A real-time speech stack on AWS keeps it inside the same account and region as the rest of the app: Amazon Nova Sonic for low-latency speech-to-speech, or Amazon Transcribe plus Polly if you want the transcript and the reply voice as separate, more mature pieces. Either way there is no third-party voice vendor and no data leaving the boundary the security section already described.

So voice is sequenced after the POC, but it is the top priority after launch. It is the difference between practicing the test and practicing something that resembles it.
