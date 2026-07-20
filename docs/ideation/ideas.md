# CTG Capstone Ideas — AI-First, Video-Leaning, Government-Adjacent

_Four AI-first capstone concepts for an individual builder, each demo-able in ~1 month._

**Framing.** These are scoped for one person to build and demo in roughly a month. Every
idea is **AI-first** (the AI does the core work, not a bolt-on), leans into **video editing**,
and sits **adjacent to government** — civic transparency, public records, policy comms,
public-sector training — without requiring access to a real government system or an ATO. The
common technical spine is: transcription → LLM reasoning over the transcript/frames →
programmatic video assembly. Build that spine once and three of the four fall out of it.

**A note on "buildable in a month."** The heavy lifting (speech-to-text, LLM APIs, face/PII
detection, headless video rendering) is all available off the shelf. The capstone's real work
is the *judgment layer* — deciding what to cut, what to flag, how to frame — plus a clean UI
and one polished demo. That's the honest scope, and it's achievable.

---

## Idea 1 — CLIPGOV

_An AI that turns three-hour public meetings into shareable highlight clips._

### Target user
Public-affairs and communications staff at local governments, agencies, and civic/advocacy
organizations — plus civic journalists — who need to get the substance of long, tedious
public meetings in front of an audience quickly.

### Problem
City council meetings, agency town halls, school board sessions, and congressional hearings
are recorded in full and dumped onto YouTube or a public portal as one unbroken multi-hour
video. Almost no one watches. The moments that matter — a heated exchange, a vote, a public
comment that lands — are buried with no way to find or share them. Comms teams don't have an
editor's hours to scrub the footage, so transparency dies of boredom.

### MVP features
- **Ingest**: paste a YouTube/public-portal URL or upload a file; auto-transcribe with speaker
  diarization and timestamps.
- **Topic segmentation**: LLM breaks the meeting into agenda-item chapters with titles and
  time ranges, and marks votes, motions, and public-comment turns.
- **Highlight detection**: ranks moments by "shareability" signals (sentiment swings,
  audience reaction, decisive language, named entities/dollar figures) and proposes a
  90-second highlight reel plus 3–5 standalone social clips.
- **One-click assembly**: renders selected clips with burned-in captions, a title card, and
  a speaker lower-third, in vertical (social) and horizontal (web) aspect ratios.
- **Human-in-the-loop trim**: a simple timeline where the user nudges in/out points before
  export.

### Personas
- **Dana, city comms officer** — solo communications person for a mid-size city. Goal: post a
  clip within an hour of a meeting ending. Frustration: she can transcribe or she can edit,
  but not both before the news cycle moves on.
- **Marcus, civic-beat reporter** — covers five municipalities. Goal: find the one newsworthy
  exchange in a four-hour session without watching all four hours. Frustration: no index, no
  search, just a scrubber.
- **Priya, advocacy organizer** — needs a shareable "look what they said about our issue"
  clip for a campaign. Goal: pull the 40 seconds that prove her point, captioned and ready
  for Instagram. Frustration: editing tools assume she's a video pro.

### What the demo shows
Drop in a real 3-hour city council video (freely available). Watch it get chaptered by agenda
item in ~2 minutes, then produce a captioned 90-second highlight reel and three vertical
social clips — one of them a public-comment moment the AI flagged on its own. End on the
timeline, nudge an out-point, and re-export. The "wow" is going from an unwatched wall of
video to publish-ready clips with zero manual scrubbing.

---

## Idea 2 — REDACT

_AI-assisted redaction and release editing for public-records video._

### Target user
FOIA / public-records officers, agency legal teams, and police records units who are legally
required to release footage (bodycam, surveillance, meeting recordings) but must first redact
faces, license plates, on-screen PII, and audible personal information.

### Problem
Public-records law says the footage must come out; privacy law says faces and PII must be
blurred first. Today that's frame-by-frame manual work in professional editing software — an
officer scrubbing an hour of bodycam blurring every bystander's face. It's slow, expensive,
error-prone, and the backlog is a genuine, well-documented government pain point. A missed
face is a privacy violation; an over-redaction is a transparency failure.

### MVP features
- **Auto-detect**: run face detection, license-plate detection, and on-screen text/PII
  detection (OCR + LLM classification) across every frame; track each detection across time so
  a face stays blurred as it moves.
- **Audio PII**: transcribe and flag spoken names, addresses, SSNs, phone numbers for audio
  bleeping.
- **Review queue**: present detections as a reviewable list ("Face #3, appears 0:12–1:40");
  the human approves, rejects, or adds a missed region — the tool never releases anything
  unreviewed.
- **Apply & export**: render blur/pixelate on approved regions and bleeps on approved audio,
  with a burned-in or sidecar **redaction log** (what was redacted, where, and the cited
  exemption) for the release record.

### Personas
- **Officer Reyes, records unit** — clears bodycam release requests. Goal: turn a 45-minute
  clip in under an hour instead of a full day. Frustration: manual frame-by-frame blurring is
  soul-crushing and one slip is a lawsuit.
- **Lena, agency FOIA analyst** — juggles a redaction backlog against statutory deadlines.
  Goal: cut turnaround time and produce a defensible log. Frustration: no audit trail means
  every release is a leap of faith.
- **Sam, oversight-org paralegal** — requests footage and receives it late or over-redacted.
  Goal (secondary/adversarial persona for framing): faster, *consistent* redaction that
  doesn't black out the whole frame "to be safe."

### What the demo shows
Load a clip with several bystanders and a visible license plate. Watch the AI find and *track*
each face across motion, flag a spoken phone number in the audio, and list everything in a
review queue. Reject one false positive, approve the rest, add one region the AI missed, then
export the redacted video with an auto-generated redaction log. The "wow" is watching a blur
stay locked to a face as the camera pans — the thing that takes a human editor an hour.

---

## Idea 3 — EXPLAINER

_Turn a dense policy or regulation document into a short narrated explainer video._

### Target user
Agency public-information offices, HR/benefits communicators, and program-training teams who
have to explain a rule change, a new regulation, or a policy memo to employees or the public —
and know that nobody reads the PDF.

### Problem
Government communicates in dense prose: a benefits change, an updated regulation, a new
compliance requirement lands as a multi-page memo. The audience won't read it, so the message
doesn't land, and the info office doesn't have a motion-graphics team to make a video. The gap
between "we published it" and "people understood it" is enormous.

### MVP features
- **Doc → script**: upload a policy doc; LLM extracts the key points and drafts a tight,
  plain-language narration script (with a reading-level target and a "what changed / what you
  need to do" structure), fully editable.
- **Storyboard**: auto-segment the script into scenes, each with a suggested visual — a
  key stat, a bulleted takeaway, a simple icon/diagram, or a callout of the exact clause.
- **Voiceover + captions**: generate TTS narration (multiple voices) and synced,
  508-style captions.
- **Motion assembly**: render scenes as clean animated slides (title, text builds, highlighted
  numbers) timed to the narration, into a finished MP4.
- **Guardrail**: every on-screen claim links back to the source line in the document, so the
  explainer can be fact-checked against what it's explaining.

### Personas
- **Grace, benefits communications lead** — has to announce an open-enrollment change to
  10,000 employees. Goal: a 90-second "here's what's changing and what to do" video by Friday.
  Frustration: her only tools are email and a PDF, and open rates are dismal.
- **Tomás, agency public-info officer** — must explain a new regulation to the public. Goal:
  something shareable and accurate that a non-expert understands. Frustration: legal wants
  precision, the public wants plain English, and he's stuck between them with no video budget.
- **Aisha, program trainer** — onboards contractors to a compliance requirement. Goal: a
  reusable explainer she can drop into a training module. Frustration: rebuilding slides by
  hand every time the rule updates.

### What the demo shows
Upload a real, dense policy PDF (e.g., a public benefits-change notice or a FAR clause). In
one pass, watch it become an editable plain-language script, then a storyboard, then a
finished ~75-second narrated video with captions and animated key numbers — each claim traceable
back to its source line. Tweak one script sentence and re-render that scene. The "wow" is
watching an unreadable memo become a video an actual human would watch, with a built-in
accuracy trail.

---

## Idea 4 — WALKTHROUGH

_Screen recording in, polished training tutorial out._

### Target user
Government-contractor delivery teams and agency training staff who capture "how to use this
arcane internal system" knowledge — the tribal knowledge that lives in one senior person's
head and walks out the door when they leave.

### Problem
Public-sector systems are notoriously clunky, and the knowledge of how to actually use them is
undocumented. When someone finally records a screen walkthrough, it's a raw, unedited, um-filled
20-minute video with sensitive fields visible on screen and no structure. Turning that into a
real tutorial is editing work nobody has time for, so it never happens and the knowledge stays
trapped.

### MVP features
- **Ingest screen capture + narration**: transcribe the voiceover with timestamps.
- **Auto-clean**: detect and cut silences, long pauses, and filler ("um," "uh," restarts) to
  tighten the raw take.
- **Chapter + step detection**: LLM segments the walkthrough into named steps ("Step 3: submit
  the form") and generates chapter markers and a written step-by-step summary alongside the video.
- **On-screen redaction**: detect and blur sensitive fields (PII, credentials, record numbers)
  via OCR + classification — same tracking engine as REDACT.
- **Callouts**: auto-add zoom/highlight callouts on the region where each click or key action
  happens, timed to the narration.
- **Export**: finished tutorial video plus a synced written quick-reference guide.

### Personas
- **Ken, departing senior analyst** — knows the legacy system cold and retires in a month.
  Goal: record what's in his head once and have it turned into something usable. Frustration:
  he'll narrate a walkthrough, but he won't edit it — and unedited, it's useless.
- **Bianca, delivery-team lead** — onboards new contractors onto a client system every quarter.
  Goal: a library of clean, chaptered tutorials instead of live shoulder-surfing. Frustration:
  raw recordings have client PII on screen and can't be shared as-is.
- **Nate, new hire** — dropped into an unfamiliar system on day one. Goal (beneficiary persona):
  a searchable, step-by-step tutorial he can pause and follow. Frustration: today his "training"
  is a 20-minute unedited video with no chapters.

### What the demo shows
Feed in a raw, rambling screen-recording walkthrough of some clunky web app. Watch it get
de-ummed and tightened, auto-chaptered into named steps, with a visible account number blurred
automatically and click-highlight callouts added. Out comes a clean tutorial plus a written
step-by-step guide generated from the same narration. The "wow" is the before/after: a
20-minute raw take becomes an 8-minute structured, redacted, callout-annotated tutorial with a
companion doc — knowledge capture that would otherwise never get made.

---

## How they relate (and how to choose)

All four share a spine: **transcribe → reason with an LLM → assemble video programmatically.**

- **CLIPGOV** and **REDACT** work on *existing* footage (find/cut, find/blur).
- **EXPLAINER** *generates* footage from a document.
- **WALKTHROUGH** *cleans and structures* a raw recording.

**REDACT** has the clearest, most defensible government pain point and the most striking demo
(a blur locked to a moving face) — strongest if you want undeniable relevance. **EXPLAINER**
has the biggest visual "wow" and the widest audience — strongest if you want a polished,
productizable showcase. **CLIPGOV** is the easiest to source demo data for (endless free public
footage) and the most fun. **WALKTHROUGH** reuses REDACT's redaction engine, so building both
as a pair is a credible stretch goal.

If forced to pick one to build first: **CLIPGOV** — lowest data-access friction, and it
exercises every part of the shared spine, so whatever you learn transfers directly to the
other three.
