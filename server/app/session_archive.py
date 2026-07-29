"""Turn a finished rehearsal into history.

One entry point. It stamps the session, snapshots the after-action report onto
the row, and drops the voice recordings. Everything else about history is a read
over rows that already existed.

Why snapshot the report but not the transcript: the report's narrative costs a
model call and its scored part is rendered against the *current* content and
rubric files, so a version bump would change an archived report out from under
the presenter. The transcript is already the audit trail (turns and
clarifications, stored verbatim), so re-reading it is free and duplicating it
would be a second source of truth.

The caller owns the transaction. This writes through the session it is handed,
so the endpoint's existing commit boundary commits all of it or none of it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.content.loader import Content
from app.db import repo
from app.db.models import RehearsalSession, Turn
from app.pipeline import orchestrator
from app.report.builder import ReactClient, build_scored_report, render_narrative
from app.schemas.report import Report

logger = logging.getLogger(__name__)


def archive_session(
    db: Session, content: Content, client: ReactClient, session: RehearsalSession
) -> None:
    """Archive ``session`` if it is not already history.

    Idempotent: an already-archived session returns immediately, so re-ending a
    rehearsal never overwrites the stored snapshot with a fresh (and possibly
    different) one.
    """
    if session.archived_at is not None:
        return

    # Derived, not passed: no open concern left means the agenda was exhausted;
    # anything else means the presenter walked away from an unfinished
    # rehearsal. Both are history, and both call sites call this identically.
    exhausted = orchestrator.next_concern(db, content, session) is None
    session.status = "complete" if exhausted else "ended"
    session.archived_at = datetime.now(UTC)

    # The deterministic, code-owned scoring is always safe; only the paid
    # narrative call can fail. Narrow the exception boundary to only wrap the
    # model call, not the DB reads or scoring logic.
    scored = build_scored_report(
        session_id=session.id,
        status=session.status,
        turns=repo.get_turns(db, session.id),
        meters=repo.get_meters(db, session.id),
        concern_statuses=repo.get_concern_statuses(db, session.id),
        content=content,
        clarifications=repo.get_clarifications(db, session.id),
    )

    try:
        narrative = render_narrative(scored, content, client)
        report = Report(**scored.model_dump(), narrative=narrative)
        session.report_json = report.model_dump(mode="json")
    except Exception:
        # Archiving must never fail because a paid call failed. The stamp and the
        # audio drop below still commit, and `GET /report` falls back to building
        # the report on demand.
        logger.exception(
            "report snapshot failed for session %s; archiving without it", session.id
        )

    # Up to `settings.max_answer_audio_bytes` (10 MiB) per voice turn, and five
    # kept sessions would sit on hundreds of MiB. A bulk UPDATE rather than a
    # per-row assignment: `answer_audio` is a deferred column, so touching it
    # through the ORM would load every blob just to null it.
    db.execute(
        update(Turn)
        .where(Turn.session_id == session.id)
        .values(answer_audio=None, answer_audio_content_type=None)
    )
    db.flush()
