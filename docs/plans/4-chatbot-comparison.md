# What a chatbot can and can't do (and where Airtight begins)

_Airtight lets a federal-contracting proposal team rehearse the live question-and-answer of an "oral proposal" (the part of some US government bids where the vendor team presents and then answers a government panel's questions live) against AI evaluator characters, and get a score they can defend. This doc tests whether a normal chatbot can do the same, across every setup a user could build, including pasting in the scoring rubric and the evaluator personas. For what Airtight is, see [1-overview.md](1-overview.md); for how scoring and anti-drift work, see [2-scoring-and-drift.md](2-scoring-and-drift.md); for the build spec, see [3-spec.md](3-spec.md)._

The first objection anyone raises is "why not just prompt a chatbot?" The short answer is in [1-overview.md](1-overview.md). This doc is the long version: every chatbot setup tested against every capability, so the line between what a prompt can do and what it cannot is spelled out rather than asserted.

---

## The boundary: what counts as "a normal chatbot"

The test needs a hard definition first.

**A normal chatbot** is a conversational LLM (ChatGPT, Claude.ai, a Custom GPT, a Project) where the user supplies text, files, and instructions, and the model replies. It includes pasting in the rubric and personas, custom instructions, knowledge files, and telling the model to output structured JSON. It excludes deterministic code the user wrote running between model calls, an external store that holds state outside the model, and an orchestration layer that forces a fixed pipeline.

Add those three and it stops being a chatbot: it becomes an application, and that application is Airtight. The one edge case, a chatbot with a code interpreter, is tested below.

---

## The configurations tested

Each row adds capability to the one above it.

| ID | Configuration |
|---|---|
| **C0** | Bare: "role-play a federal evaluator and grade me 0 to 100" |
| **C1** | C0 plus the persona markdown pasted in (or as a Custom GPT / Project knowledge file) |
| **C2** | C1 plus the frozen rubric pasted in |
| **C3** | C2 plus "extract the labels first (answered / dodged / backed / contradicted) with quotes, then apply the rubric" |
| **C4** | C3 plus "output JSON, keep a running score, restate the persona every turn, don't make assumptions" |
| **C5** | C4 plus the chatbot has a code interpreter or tool it can choose to call |
| **APP** | Airtight: model call constrained to extraction, then code scores, then a separate reaction call, with external structured state |

---

## Master capability matrix

Yes = reliable by construction: guaranteed by code where the property is code-owned (the arithmetic, the sticky cap, the audit trail), and regression-tested against a golden set where it rests on the model's classification. Approx = works sometimes, no guarantee. No = not achievable in that configuration.

| Capability | C0 | C1 | C2 | C3 | C4 | C5 | APP |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Role-play persona voice | Approx | Yes | Yes | Yes | Yes | Yes | Yes |
| Raise the frozen concerns | No | Yes | Yes | Yes | Yes | Yes | Yes |
| React in character | Approx | Yes | Yes | Yes | Yes | Yes | Yes |
| Produce an extraction (labels plus quoted spans) | No | Approx | Approx | Yes | Yes | Yes | Yes |
| Produce a plausible score | Approx | Approx | Approx | Approx | Approx | Approx | Yes |
| **Same answer produces same score (determinism)** | No | No | No | No | Approx | Approx | Yes |
| **Combination rule correct every time (cap-first, sum, clamp)** | No | No | No | Approx | Approx | Approx | Yes |
| **Number provably bound to the extraction** | No | No | No | No | No | Approx | Yes |
| No number/reply contamination | No | No | No | No | Approx | Approx | Yes |
| Persona held in character over a long session | No | Approx | Approx | Approx | Approx | Approx | Yes |
| **Red lines enforced as hard caps** | No | No | Approx | Approx | Approx | Approx | Yes |
| **Sticky cap invariant (stays capped all session)** | No | No | No | No | Approx | Approx | Yes |
| Drift-free running meter across turns | No | No | No | No | Approx | Approx | Yes |
| **Verbatim claim retention for contradiction checks (long session)** | No | No | No | No | Approx | Approx | Yes |
| No re-litigating past turns | No | No | No | No | No | Approx | Yes |
| Auditable, replayable score (matched_rows guaranteed to match the number) | No | No | No | No | No | Approx | Yes |
| Recompute old sessions under a new rubric version | No | No | No | No | No | Approx | Yes |
| Rubric frozen and version-tagged as enforced data (not suggestion text) | No | No | No | No | No | Approx | Yes |
| Scorer unit-testable in isolation (no model) | No | No | No | No | No | Approx | Yes |

The bold rows never reach Yes in any chatbot column, and that set of properties is what the product is.

---

## What a chatbot genuinely can do

To be fair, from C1 to C4 a chatbot is genuinely good at several things:

- **Role-play and in-character reactions.** This is pure generation, which is what chatbots are best at. Doc 2 concedes it directly: "the hard part was never building a chatbot that role-plays an evaluator."
- **Extraction.** Extraction here means the model reads an answer and labels it (answered, dodged, backed, contradicted) with the quotes that support each label. Given the "extract first, with quotes" instruction (C3 and up), it produces those labels reasonably well and reasonably stably, because doc 2's own insight applies: sorting an answer into a few fixed categories is something the model "does far more stably than inventing a score." Classification is the part the model is reliable at, chatbot or app.
- **A plausible score and a plausible explanation.** On a single early turn its number is often correct. It goes wrong unpredictably, and that is the issue: correctness is neither guaranteed nor reproducible.

So a C4 chatbot makes a convincing demo, which is why "just use a chatbot" is tempting. The demo is also a trap, because it shows the easy part and hides the part Airtight exists to guarantee.

---

## What no chatbot configuration can do, case by case

### Case: user pastes the rubric (C2)

Pasting in the rubric, the fixed scoring rules, changes what the model reads but not who does the computing. The model still applies the rules by feel while it writes the reply, treating the rubric as text to interpret loosely instead of a procedure to run. It is the same rubric file the app uses, but the chatbot re-improvises how to apply it every turn, so "same rubric" does not mean "same scoring."

### Case: user pastes the personas (C1)

Pasting in the personas, the AI evaluator characters, gets you their voice and their concerns. It does not get you the anti-drift guarantee. Doc 2's guardrail is that the persona is rebuilt from its file every turn and that "red lines," the answers an evaluator will not accept, carry a hard mechanical consequence: they cap the running score. In a chat the persona text persists, but the growing transcript still pulls the model toward generic helpfulness, and a red line stays a stated preference the model can be talked past rather than an enforced cap. That is why holding the persona in character over a long session is Approx, not Yes.

### Case: "extract first, then score" (C3)

This is the smartest chatbot move, and it does improve the extraction. But the number still comes out of the same generation, so it stays non-binding: the model can label an answer a dodge and still hand out a generous score, because nothing forces the number to follow the labels. The audit claim that every point traces to a rubric row is not guaranteed, because the model wrote the number instead of computing it by looking up the labels.

### Case: "keep a running tally, restate persona, don't assume" (C4)

Each of these instructions asks the model to behave a certain way without giving it the machinery to comply.

- Running tally: the score lives as text the model re-reads and rewrites every turn, so it drifts like a game of telephone. No persistent variable exists to hold it.
- Restate persona: this helps, but it does not stop the transcript from accumulating and it enforces nothing.
- Don't assume: impossible for this task, because scoring freeform prose is interpreting it. There is no assumption-free classification to ask for.
- Long session: the context window truncates and summarizes, so the verbatim turn-4 wording you need to catch a turn-15 contradiction is gone. Doc 2 names this trap exactly: summarizing the conversation and feeding it back is "lossy in exactly the three places the product's credibility lives: the number, contradiction detection, and the audit trail." The sticky cap ("a cap once applied stays applied") is an invariant a transcript cannot enforce.

### Case: chatbot with a code interpreter or tool (C5)

This is the only real edge case, and it splits two ways. A code interpreter is a sandbox where the model can run code it writes.

- If the model chooses when to call the scoring code and feeds it the labels, orchestration is still governed by the model. It can skip the call, pass the wrong arguments, or route them badly. The guarantees stay Approx rather than Yes, because deterministic code does not help when a non-deterministic model decides whether and how to invoke it.
- If you force the pipeline (always extract, always call the scorer with a fixed schema, run a separate reaction call, persist state outside the model), you now have constrained model calls, code that owns the number, and external state. That is no longer a chatbot: you have rebuilt Airtight. It does not disprove the argument, it concedes it, because you needed code, state, and orchestration to get there.

That is why every C5 cell is Approx and never Yes: a chatbot with tools can approach the app only by turning into the app, at which point it is no longer the thing being compared.

---

## The dividing line

Every capability sorts into two piles.

- **Prompt-shaped (reaches Yes in a chatbot):** role-play, raising concerns, extraction, reacting in character. These amount to reading and talking, and a prompt handles them.
- **Mechanism-shaped (never reaches Yes in a chatbot):** determinism, binding the number to the evidence, a correct combination every time, a drift-free meter, verbatim retention, sticky caps, a replayable audit, versioned recompute, and a unit-testable scorer. These need code, persistent state, and forced orchestration, and they are what the product is.

Only the app can guarantee the second pile, and the reason is structural rather than a matter of prompt quality. A prompt only adds instructions for the model to follow. It cannot take the model out of a step, and it cannot give the model a stable place to keep state. The model is stateless and generative, while the second pile requires something stateful and deterministic.

---

## The other axis: where the data goes

Everything above argues about scoring. There is a prior question the matrix does not measure: can you put your proposal into the thing at all?

For this buyer, often not. The "normal chatbot" defined above is a consumer service (ChatGPT, Claude.ai, a Custom GPT, a Project). Pasting a live proposal into one sends win themes, pricing, key personnel, and sometimes CUI (controlled unclassified information) into a third-party environment the contractor does not own and, for federal work, is usually not accredited to use. That fails before scoring even comes up. It is not a prompt problem, so no configuration from C0 to C5 changes it.

This is a second structural line, orthogonal to the scoring one:

- A consumer chatbot puts the data in the vendor's boundary. Enterprise tiers narrow that (no training on your data, SOC 2 controls), but it is still a separate vendor's environment rather than the customer's own accredited one, and it is not AWS GovCloud under FedRAMP High.
- Airtight runs on AWS Bedrock (AWS's service for running AI models inside your own AWS account) in the customer's own account and region. Prompts and proposal text are not used to train the model and are not shared with the model provider, data is encrypted in transit and at rest, and calls can run over a private VPC endpoint. In AWS GovCloud, the US government cloud region, the Bedrock platform is authorized at FedRAMP High, the same class of environment the customer already runs its federal workloads in; Airtight deploys into that boundary and earns its own authorization there rather than inheriting one automatically. This distinction is the whole point: Bedrock does not swap in a weaker model to earn that boundary. It *reaches* the same frontier models (Claude among them) while keeping the prompt from ever reaching the model provider. The consumer version of that same model, ChatGPT or Claude.ai, is exactly what the buyer cannot use, because the data would land in the vendor's environment rather than because the model is worse. It is the same class of model on a data path the buyer can clear.

So the comparison has a floor under it the matrix does not show. Even where a C5 chatbot could approximate a scoring behavior, this buyer usually cannot put the input into it without breaking its own data-handling rules. Airtight clears that bar by construction, because it is an application on the customer's own Bedrock rather than a conversation on someone else's server.

---

## Verdict

A normal chatbot can convincingly rehearse against a persona and can classify an answer well, but it cannot own the number or the memory. It cannot guarantee that the same answer scores the same, bind the score to its own evidence, hold a drift-free tally, retain verbatim claims across a long session, enforce a sticky cap, or produce a replayable audit. Those are exactly the properties a proposal shop needs in order to trust the grade, and they take code and state rather than a better prompt. The most a chatbot can do is turn itself into Airtight by bolting on code, state, and forced orchestration, which proves the point rather than refuting it. Even that rebuilt version still runs on someone else's server, and a govcon (government contracting) buyer needs the data to stay inside its own accredited boundary before scoring is ever on the table. Airtight meets that on AWS Bedrock, in the customer's own account.
