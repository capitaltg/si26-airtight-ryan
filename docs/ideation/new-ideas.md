# CTG capstone ideas (AI-first, video-leaning, govcon-adjacent)

A shortlist for a one-month, solo-buildable capstone using Claude Code and Claude Opus 4.8. It mixes three new concepts with refined versions of the two strongest ideas from `ideas.md`. All are govcon-adjacent, meaning government-flavored but none needs a real government system or an ATO. They also follow the same buildable pattern:

> capture / transcribe, then LLM reasoning (Claude Opus 4.8, structured output), then programmatic video assembly (ffmpeg / MoviePy / Remotion)

Each one ships a small `EVALUATION.md` golden set to show quality, not just a demo.

If I had to pick, I'd build **PitchCut** as releasability-aware retargeting: one internal video recut into a version each audience is cleared and needs to see, with an audit log of what was removed. It's original because it's govcon (need-to-know is an axis generic tools don't touch), it reuses Airtight's detect-then-apply-rules approach, and it demos well. **OralsTape** is the fallback if you want the tightest tie to CTG's orals work.

---

## How to pick

| Idea | Video flavor | Govcon tie | Demo wow | Build risk |
|------|--------------|-----------|----------|-----------|
| ⭐ **PitchCut** | Releasability retargeting + redaction | High (releasable cut per audience + audit log) | High | Medium |
| ⭐ **OralsTape** | Video analysis + reel | High (orals) | High | Medium |
| **AccessReel** | Processing / accessibility | High (508 is law) | Medium | Medium |
| **CLIPGOV** | Public-record video | Medium | Medium | Low (free data) |
| **BriefReel** | Generative / explainer | Medium | Highest | Med to high |

---

## 1. PitchCut: releasability-aware retargeting (one source video, one version per cleared audience) *(NEW, recommended)*

**One-liner:** PitchCut takes one internal video and produces audience-specific cuts, where each audience is defined by what it is allowed and needs to see. It removes PII, CUI, and need-to-know content according to a releasability policy you define, and it logs exactly what was cut and why.

- **Target user:** Public-affairs, security/FOIA, and program teams at a govcon firm or agency who have one internal recording (a briefing, demo, or walkthrough) that has to go outward, to the public, a coalition partner, or a less-cleared team, but can't be released as-is.
- **Problem:** The original contains PII, CUI/FOUO, internal system details, or need-to-know material. Making a releasable version today means a person watches the whole thing and scrubs it by hand. That's slow, easy to get wrong, and leaves no record of what was removed. So the video either doesn't get shared or gets shared unsafely.
- **What makes it original (and govcon, not generic):** In a normal company, audiences differ by how much they understand. In government, audiences differ by what they're allowed and need to see: clearance, need-to-know, markings, releasability, FOIA. Generic repurposing tools don't touch that axis. Comprehension-simplification (shorten, reorder, add plain-language captions) can sit on top, but releasability is the part that's hard to copy.
- **How it works (the pipeline):**
  1. Transcribe with word-level timestamps (Whisper).
  2. Detect sensitive spans. PII goes through Presidio/NER (names, SSNs, emails, locations). Policy categories (CUI/FOUO, personnel, cost figures, system architecture, security controls) go through Claude, which classifies each span against a releasability policy you supply.
  3. Apply the audience policy. Each audience profile is a ruleset, for example "public release: remove all PII and CUI" or "coalition partner: remove US-only caveated content." Code applies the frozen rules to the detected spans and decides keep, cut, or mute.
  4. Execute. Cut or mute the span in the audio and redact the caption text. As a stretch, blur faces or on-screen text (OCR) in the video.
  5. Human review gate. Everything flagged goes to a review queue, and a person approves or overrides before anything exports. Nothing releases automatically.
  6. Export and audit log. You get a marked releasable cut plus a report listing every removed span: its timestamp, what it was, which rule triggered it, and for which audience.
- **Is it feasible?** Yes, for a one-month build, if you hold the scope. The MVP is transcript and audio-level releasability: detect, apply policy, cut or mute, then audit plus review queue. Those are off-the-shelf pieces you assemble rather than invent. Visual redaction (face blur, on-screen-text OCR with frame tracking) is the stretch: cutting a whole segment is easy, but tracking a region across frames is the hard part, so keep it optional. Two constraints actually help you here. The tool is assistive, not authoritative: it proposes cuts and a human authorizes release. And it can't know real classification, which is fine, because releasability is applying a policy, not guessing. Demo it on public or unclassified footage seeded with synthetic PII/CUI markings, so you never need real sensitive data.
- **What the demo shows:** Upload one internal briefing, pick "audience: public-affairs release," then "audience: coalition partner," and get two different releasable cuts, plus a side-by-side audit report showing what each one removed and which rule fired.
- **Why recommended:** It's original because it's govcon. Need-to-know and releasability are things generic tools don't handle, and it's a real, recurring task. It reuses the same shape as Airtight (the model detects, code applies the frozen policy and owns the audit trail, a human authorizes), and it absorbs the old REDACT idea. It also answers "how does it help them" plainly: a shareable version in minutes, with proof of what came out.

## 2. OralsTape: AI delivery coach for oral-presentation practice *(NEW, strong runner-up)*

- **Target user:** Proposal teams rehearsing federal orals. This sits next to the Airtight thesis but is a different product: it analyzes video rather than scoring answers.
- **Problem:** Teams rehearse but get no objective read on delivery: pace, filler, time spent per required topic, and whether they actually answered the question.
- **MVP features:** Record or upload a practice run, transcribe it, and have Claude analyze words per minute and pacing, filler-word density, time spent per required topic against the plan, and whether each Q&A turn answered the question. The output is a delivery scorecard plus an auto-assembled reel of the weakest moments, with a jump cut to each flagged spot and a caption naming the issue.
- **What the demo shows:** Upload a practice answer, get a scorecard, and with one click produce a "watch your 5 worst moments" reel.
- **Why strong:** Tightest CTG tie (orals), reuses the existing domain thesis, and the weak-moments reel is a good demo.

## 3. AccessReel: Section 508 accessibility pipeline for government video *(NEW)*

- **Target user:** Any agency or contractor publishing video, which by law has to meet Section 508 accessibility.
- **Problem:** 508-compliant captions, an audio-description track, and a compliance record are all required, tedious to produce, and often skipped or done badly.
- **MVP features:** Upload a video and get accurate captions with speaker labels, an AI-generated audio-description script for the visual-only moments with a TTS track mixed into the gaps, and a 508 compliance report covering what was checked, what passed, and what gaps remain. Code owns the compliance checklist; Claude writes the language.
- **What the demo shows:** A raw clip goes in, and out come a captioned video, a described-audio version, and a one-page compliance report.
- **Why interesting:** The clearest real government pain and the most obviously sellable of the set, and it's genuinely different from the existing ideas.

## 4. CLIPGOV: public meeting to captioned highlight clips *(REFINED from `ideas.md`)*

- **Target user:** Public-affairs and government-relations staff, plus journalists tracking city councils, boards, and federal hearings.
- **Problem:** Decisions are buried inside multi-hour meeting recordings that nobody has time to watch.
- **MVP features:** Ingest a long public-meeting video (there's plenty of free footage), transcribe and auto-chapter it by agenda item, detect the moments worth clipping (votes, motions, notable exchanges), and assemble captioned, social-ready clips with title cards in one click.
- **What the demo shows:** A three-hour council video turns into a set of 30-to-60-second captioned clips ("Council votes 5-2 on...") in minutes.
- **Why keep:** The lowest data friction of the set. You can build and demo it without any sensitive footage.

## 5. BriefReel: proposal or policy doc to narrated explainer video *(REFINED from EXPLAINER)*

- **Target user:** Capture teams and program offices that need to get a capability, solution, or policy across quickly.
- **Problem:** Dense one-pagers and executive summaries don't travel well. A short video does, but making one is expensive.
- **MVP features:** A document goes in, and Claude drafts a tight script and storyboard with source-line traceability, so every claim maps back to a line in the doc. Then TTS narration, captions, and simple motion graphics get assembled programmatically (Remotion or MoviePy).
- **What the demo shows:** Paste a one-page capability summary and get a roughly 60-second narrated, captioned explainer video with the source citations shown on screen.
- **Why keep:** The biggest visual payoff, and the generative flavor rounds out the set.

---

## Shared tech stack

- **Reasoning:** Claude Opus 4.8 (`claude-opus-4-8`) via the Anthropic Python SDK, at temperature 0 with structured outputs. Claude decides what to keep, cut, or say; deterministic code owns the actual edits and any scoring.
- **Transcription:** Whisper (or an equivalent ASR) for word-level timestamps, which is what transcript-driven editing runs on.
- **Detection and redaction (PitchCut, AccessReel):** Presidio or spaCy NER for PII, Claude for classifying policy categories against a defined ruleset, and Tesseract or PaddleOCR plus face detection for the optional visual-redaction stretch.
- **Video assembly:** ffmpeg and MoviePy for cuts, captions, and mutes; Remotion for the motion-graphics and generative output (BriefReel).
- **App shell:** React front end, FastAPI back end.
- **Proof deliverable:** `EVALUATION.md`, a set of 15 to 20 hand-graded golden examples (for instance, "did the cut keep the right spans?" or "did the audio description match the frame?") that shows the quality rather than relying on the demo alone.

## Recommendation

Lead with PitchCut for the best fit against the video-editing interest and the strongest product and demo. Fall back to OralsTape if you want the closest tie to CTG's orals work. Both are single-builder, realistic in a month, and demo well.
