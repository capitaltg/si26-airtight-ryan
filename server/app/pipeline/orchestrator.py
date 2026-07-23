"""Turn orchestrator — the code-driven control loop (task 10).

The loop is pure Python. The model classifies (extraction) and reacts; it never
selects the concern, decides a follow-up, or ends the session. That keeps the
control flow deterministic and auditable, matching the moat: code owns the
number *and* the agenda.

Agenda
------
The turn order is a fixed walk: for each persona in ``PERSONA_ORDER``, take its
authored ``priorities`` in order. The first persona to claim a concern owns it,
so overlapping priorities (``transition``, ``risk``) dedupe to one owner and the
eight concerns spread across the three personas without repeats.

Follow-ups and termination
--------------------------
A concern gets at most ``MAX_TURNS_PER_CONCERN`` turns (one follow-up). A turn
that fully covers the concern (and isn't a dodge) satisfies it and advances; a
dodge or partial answer on the first attempt earns a same-concern follow-up; a
crossed red line is a terminal failure. Once every concern is terminal the
session is complete — the turn cap guarantees the loop halts.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

from sqlalchemy.orm import Session

from app.content.loader import Content
from app.db import repo
from app.db.models import RehearsalSession, Turn
from app.pipeline.extraction import run_extraction
from app.pipeline.reaction import run_clarification, run_reaction
from app.pipeline.scoring import apply_to_meter, score_turn
from app.schemas.content import Concern, PersonaDefinition
from app.schemas.extraction import Addressed, Extraction
from app.schemas.reaction import PersonaReaction

logger = logging.getLogger(__name__)

# Fixed persona turn order. The walk below depends on it to assign each concern a
# single owner; changing it changes which persona presses overlapping concerns.
PERSONA_ORDER = ("technical_evaluator", "contracting_officer", "program_rep")

SCENARIO_VERSION = "poc-v1"
MAX_TURNS_PER_CONCERN = 2  # first ask + one follow-up

# Guard against dodging disguised as questions: a free no-score channel would
# otherwise let a presenter stall a concern indefinitely.
MAX_CLARIFICATIONS_PER_CONCERN = 2

# Non-terminal statuses: the concern still needs a turn (subject to the turn cap).
_OPEN = "open"
_PARTIAL = "partial"
_SATISFIED = "satisfied"
_DODGED = "dodged"


class SessionComplete(RuntimeError):
    """Raised when an answer is submitted to a session with no open concern."""


class ClarificationCapReached(RuntimeError):
    """Raised when a concern has already used its clarification allowance."""


@dataclass(frozen=True)
class Assignment:
    """Who asks what next, and whether it's a repeat press on the same concern."""

    persona: PersonaDefinition
    concern: Concern
    prompt: str
    is_follow_up: bool


@dataclass(frozen=True)
class TurnResult:
    """Everything the API needs to render a turn and the next prompt."""

    turn: Turn
    reaction: PersonaReaction
    persona_id: str
    concern_id: str
    concern_status: str
    support_delta: int
    matched_rows: list[str]
    meter: int
    capped: bool
    next: Assignment | None
    done: bool


@dataclass(frozen=True)
class ClarificationResult:
    """A non-scored clarification exchange and the (unchanged) active prompt."""

    persona_id: str
    concern_id: str
    question: str
    reply: str
    remaining: int  # clarifications left on this concern
    prompt: Assignment  # unchanged active prompt, echoed back


def _persona_order(content: Content) -> list[str]:
    return [pid for pid in PERSONA_ORDER if pid in content.personas]


def _agenda(content: Content, persona_ids: list[str]) -> list[tuple[str, str]]:
    """Ordered ``(persona_id, concern_id)`` pairs; first owner wins each concern."""
    seen: set[str] = set()
    agenda: list[tuple[str, str]] = []
    for pid in persona_ids:
        persona = content.personas.get(pid)
        if persona is None:
            continue
        for cid in persona.priorities:
            if cid in content.concerns and cid not in seen:
                seen.add(cid)
                agenda.append((pid, cid))
    return agenda


def _needs_turn(status: str, turns_on_concern: int) -> bool:
    if status == _OPEN:
        return True
    return status == _PARTIAL and turns_on_concern < MAX_TURNS_PER_CONCERN


def _coverage_state(concern: Concern, extraction: Extraction) -> str:
    """"full" if every sub-question is fully addressed, "some" if any is
    touched, else "none"."""
    required = [sq.id for sq in concern.sub_questions]
    by_id = {c.id: c.addressed for c in extraction.sub_question_coverage}
    full = sum(1 for rid in required if by_id.get(rid) is Addressed.full)
    touched = sum(
        1 for rid in required if by_id.get(rid) in (Addressed.full, Addressed.partial)
    )
    if required and full == len(required):
        return "full"
    return "some" if touched else "none"


def _next_status(concern: Concern, extraction: Extraction, attempts: int) -> str:
    """Concern status after a turn. ``attempts`` includes the turn just scored."""
    # A crossed red line is a terminal failure regardless of coverage.
    if extraction.red_line_hits:
        return _DODGED
    is_dodge = bool(extraction.dodges)
    coverage = _coverage_state(concern, extraction)
    if coverage == "full" and not is_dodge:
        return _SATISFIED
    if attempts >= MAX_TURNS_PER_CONCERN:
        # Follow-ups exhausted: close it out. A dodge or no coverage is a failure;
        # partial coverage gets partial credit and moves on.
        return _DODGED if (is_dodge or coverage == "none") else _SATISFIED
    return _PARTIAL  # first attempt fell short → press once more on the same concern


def _core_prompt(persona: PersonaDefinition, concern: Concern) -> str:
    return f"{persona.display_name}: {concern.core_ask}"


def _follow_up_prompt(concern: Concern, last: Extraction) -> str:
    by_id = {c.id: c.addressed for c in last.sub_question_coverage}
    uncovered = [sq for sq in concern.sub_questions if by_id.get(sq.id) is not Addressed.full]
    detail = " ".join(sq.text for sq in uncovered) or concern.core_ask
    return f"Let's stay on this. That didn't fully land. {detail}"


def _last_extraction_on(turns: list[Turn], concern_id: str) -> Extraction | None:
    for turn in reversed(turns):
        if turn.concern_id == concern_id:
            return Extraction.model_validate(turn.extraction_json)
    return None


def start_session(db: Session, content: Content) -> RehearsalSession:
    """Create a session with every persona meter at 50 and every concern open."""
    persona_ids = _persona_order(content)
    session = repo.create_session(
        db,
        scenario_version=SCENARIO_VERSION,
        rubric_version=content.rubric.version,
        persona_ids=persona_ids,
    )
    for pid in persona_ids:
        repo.upsert_meter(db, session_id=session.id, persona_id=pid, support=50, capped=False)
    for _, cid in _agenda(content, persona_ids):
        repo.set_concern_status(db, session_id=session.id, concern_id=cid, status=_OPEN)
    db.flush()
    return session


def next_concern(
    db: Session, content: Content, session: RehearsalSession
) -> Assignment | None:
    """The next concern that still needs a turn, in agenda order, or ``None``."""
    statuses = repo.get_concern_statuses(db, session.id)
    turns = repo.get_turns(db, session.id)
    counts = Counter(turn.concern_id for turn in turns)

    for pid, cid in _agenda(content, list(session.persona_ids)):
        status = statuses.get(cid, _OPEN)
        if not _needs_turn(status, counts[cid]):
            continue
        persona = content.personas[pid]
        concern = content.concerns[cid]
        if counts[cid] == 0:
            return Assignment(persona, concern, _core_prompt(persona, concern), False)
        last = _last_extraction_on(turns, cid)
        prompt = _follow_up_prompt(concern, last) if last else _core_prompt(persona, concern)
        return Assignment(persona, concern, prompt, True)
    return None


def submit_answer_events(
    db: Session,
    content: Content,
    client: object,
    session: RehearsalSession,
    answer: str,
) -> Iterator[dict[str, object]]:
    """Run one turn, yielding stage-progress events around the same pipeline.

    This is the single source of truth for a turn. It yields ``{"stage": ...}``
    at the three natural boundaries (extracting → scoring → reacting) and, as its
    final action after persist/advance, ``{"result": TurnResult(...)}``. The
    thin ``submit_answer`` driver below drains it, so behavior is byte-identical
    to the pre-streaming pipeline; scoring and the DB writes are untouched.
    """
    current = next_concern(db, content, session)
    if current is None:
        raise SessionComplete("no open concern; the session is already complete")
    persona, concern = current.persona, current.concern

    prior_claims = repo.get_claims(db, session.id)
    yield {"stage": "extracting"}
    extraction_start = time.perf_counter()
    extraction = run_extraction(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=prior_claims,
        client=client,  # type: ignore[arg-type]
    ).extraction
    logger.info(
        "extraction (%s) took %.0f ms",
        persona.id,
        (time.perf_counter() - extraction_start) * 1000,
    )

    yield {"stage": "scoring"}
    score = score_turn(extraction, content.rubric)

    meter_row = repo.get_meter(db, session.id, persona.id)
    current_support = meter_row.support if meter_row is not None else 50
    already_capped = meter_row.capped if meter_row is not None else False
    new_meter, capped = apply_to_meter(
        current_support,
        score.support_delta,
        score.capped,
        content.rubric.cap_ceiling,
        already_capped,
    )

    # Reaction runs only after the number is locked; it can never move it.
    yield {"stage": "reacting"}
    reaction_start = time.perf_counter()
    reaction = run_reaction(
        persona=persona,
        concern=concern,
        extraction=extraction,
        score=score,
        client=client,  # type: ignore[arg-type]
    )
    logger.info(
        "reaction (%s) took %.0f ms",
        persona.id,
        (time.perf_counter() - reaction_start) * 1000,
    )

    turn_index = len(repo.get_turns(db, session.id))
    turn = repo.append_turn(
        db,
        session_id=session.id,
        turn_index=turn_index,
        persona_id=persona.id,
        concern_id=concern.concern_id,
        user_answer=answer,
        extraction=extraction,
        score=score,
        reaction=reaction,
    )
    repo.append_claims(
        db, session_id=session.id, turn_index=turn_index, claims=extraction.claims
    )
    repo.upsert_meter(
        db, session_id=session.id, persona_id=persona.id, support=new_meter, capped=capped
    )

    # Includes the turn just appended, so a first answer has attempts == 1.
    attempts = sum(
        1 for t in repo.get_turns(db, session.id) if t.concern_id == concern.concern_id
    )
    status = _next_status(concern, extraction, attempts)
    repo.set_concern_status(
        db, session_id=session.id, concern_id=concern.concern_id, status=status
    )
    db.flush()

    following = next_concern(db, content, session)
    done = following is None
    if done and session.status != "complete":
        session.status = "complete"
        db.flush()

    yield {
        "result": TurnResult(
            turn=turn,
            reaction=reaction,
            persona_id=persona.id,
            concern_id=concern.concern_id,
            concern_status=status,
            support_delta=score.support_delta,
            matched_rows=score.matched_rows,
            meter=new_meter,
            capped=capped,
            next=following,
            done=done,
        )
    }


def submit_answer(
    db: Session,
    content: Content,
    client: object,
    session: RehearsalSession,
    answer: str,
) -> TurnResult:
    """Run one turn: extract → score → persist → meter → react → advance.

    Thin driver over :func:`submit_answer_events`: it drains the generator and
    returns the terminal ``result`` event, keeping the synchronous JSON contract
    (``POST /answer``) unchanged. Concern selection is code-driven; the model is
    invoked only for extraction and reaction, and the score is locked before the
    reaction runs.
    """
    result: TurnResult | None = None
    for ev in submit_answer_events(db, content, client, session, answer):
        if "result" in ev:
            result = cast(TurnResult, ev["result"])
    assert result is not None  # the generator always yields a terminal result
    return result


def ask_clarification(
    db: Session,
    content: Content,
    client: object,
    session: RehearsalSession,
    question: str,
) -> ClarificationResult:
    """Answer a clarifying question without scoring the turn.

    None of the scored-path side effects run: no extraction, no ``score_turn``,
    no meter change, no claim-ledger append, no concern-status write, and no
    ``append_turn``. ``next_concern`` is read-only, so re-reading the active
    concern does not advance the agenda; the row is stored in ``clarifications``,
    not ``turns``, so it cannot count as an attempt. The same prompt stays active
    afterward — the presenter still owes a real answer to it.
    """
    current = next_concern(db, content, session)
    if current is None:
        raise SessionComplete("no open concern; the session is already complete")
    concern_id = current.concern.concern_id

    used = repo.count_clarifications(db, session.id, concern_id)
    if used >= MAX_CLARIFICATIONS_PER_CONCERN:
        raise ClarificationCapReached(
            f"clarification cap ({MAX_CLARIFICATIONS_PER_CONCERN}) reached on "
            f"concern {concern_id}"
        )

    reply = run_clarification(
        persona=current.persona,
        concern=current.concern,
        question=question,
        client=client,  # type: ignore[arg-type]
    )
    repo.append_clarification(
        db,
        session_id=session.id,
        concern_id=concern_id,
        persona_id=current.persona.id,
        seq=used,
        question=question,
        reply=reply,
    )
    db.flush()

    return ClarificationResult(
        persona_id=current.persona.id,
        concern_id=concern_id,
        question=question,
        reply=reply,
        remaining=MAX_CLARIFICATIONS_PER_CONCERN - used - 1,
        prompt=current,
    )
