import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_bedrock_client, get_db, get_session_factory
from app.bedrock.cache import CacheKeyInput
from app.content.loader import Content
from app.db import repo
from app.db.models import Base
from app.main import app
from app.schemas.extraction import (
    Addressed,
    Backing,
    Claim,
    ClaimType,
    Extraction,
    SubQuestionCoverage,
)
from app.schemas.reaction import PersonaReaction


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_app_boots_with_content_on_state():
    # `with` runs the lifespan, so content is loaded onto app.state.
    with TestClient(app) as client:
        client.get("/health")
        content = app.state.content
        assert isinstance(content, Content)
        assert len(content.personas) == 3
        assert len(content.concerns) == 8
        assert content.rubric.version == 2


class _FakeClient:
    """Returns a backed, fully-covering extraction for the first concern and a
    canned reaction — enough for one green answer round-trip."""

    def extract(
        self,
        content: str | list,
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> BaseModel:
        if content_schema is Extraction:
            return Extraction(
                claims=[
                    Claim(
                        text="Named architecture with committed leads.",
                        type=ClaimType.commitment,
                        backing=Backing.backed,
                        span="named components, FedRAMP host, three integrations",
                    )
                ],
                sub_question_coverage=[
                    SubQuestionCoverage(id="architecture", addressed=Addressed.full, span="x"),
                    SubQuestionCoverage(id="hosting", addressed=Addressed.full, span="x"),
                    SubQuestionCoverage(id="integrations", addressed=Addressed.full, span="x"),
                ],
            )
        return PersonaReaction(in_character_reply="Concrete. Good.", rationale="+2 backed.")

    def react(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        cache_key: CacheKeyInput | None = None,
    ) -> str:
        return "Strong on the technical approach; keep drilling staffing specifics."


class _PartialClient(_FakeClient):
    """Covers one sub-question only, so the concern goes `partial` and earns a
    follow-up on the same concern."""

    def extract(self, content, *, content_schema, tool_name, max_tokens=4096, cache_key=None):
        if content_schema is Extraction:
            return Extraction(
                sub_question_coverage=[
                    SubQuestionCoverage(id="architecture", addressed=Addressed.full, span="x")
                ]
            )
        return super().extract(
            content,
            content_schema=content_schema,
            tool_name=tool_name,
            max_tokens=max_tokens,
            cache_key=cache_key,
        )


@pytest.fixture
def db_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(db_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def _get_db() -> Iterator[Session]:
        db = db_factory()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_bedrock_client] = _FakeClient
    # The SSE endpoint opens its own session off the factory (own worker thread),
    # so point it at the same in-memory engine the request sessions use.
    app.dependency_overrides[get_session_factory] = lambda: db_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_session_returns_first_prompt(client: TestClient) -> None:
    r = client.post("/sessions")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "active"
    assert len(body["meters"]) == 3
    assert all(m["support"] == 50 for m in body["meters"])
    assert body["prompt"]["persona_id"] == "technical_evaluator"
    assert body["prompt"]["concern_id"] == "technical_approach"
    assert body["done"] is False


def test_answer_round_trip_moves_meter_and_advances(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]

    r = client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Concrete. Good."
    assert body["support_delta"] == 2
    assert body["meter"] == 52
    assert body["capped"] is False
    assert body["concern_status"] == "satisfied"
    assert body["next_prompt"]["concern_id"] == "key_personnel"
    assert body["done"] is False


def _collect_sse(response) -> list[dict]:
    """Parse `data: {json}` SSE frames from a streamed response into dicts."""
    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


def test_answer_stream_emits_stages_then_result(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]

    with client.stream(
        "POST",
        f"/sessions/{session_id}/answer/stream",
        json={"answer": "Here is the architecture."},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _collect_sse(r)

    # Stages arrive in pipeline order, then exactly one result frame closes it.
    stages = [e["stage"] for e in events if "stage" in e]
    assert stages == ["extracting", "scoring", "reacting"]
    results = [e["result"] for e in events if "result" in e]
    assert len(results) == 1
    body = results[0]
    # The result frame matches the /answer contract exactly.
    assert body["reply"] == "Concrete. Good."
    assert body["support_delta"] == 2
    assert body["meter"] == 52
    assert body["concern_status"] == "satisfied"
    assert body["next_prompt"]["concern_id"] == "key_personnel"
    # Dana already introduced herself on the first turn, so her next prompt
    # (still hers — key_personnel is her second priority) carries no intro.
    assert body["next_prompt"]["intro"] is None
    assert body["done"] is False

    # The turn was persisted: a follow-up read reflects the advanced state.
    state = client.get(f"/sessions/{session_id}").json()
    assert state["concern_status"]["technical_approach"] == "satisfied"
    assert state["prompt"]["concern_id"] == "key_personnel"


def test_answer_stream_after_done_emits_error(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    # Drive every concern to a terminal state so the next submit has no open concern.
    for _ in range(20):
        state = client.get(f"/sessions/{session_id}").json()
        if state["done"]:
            break
        client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})
    assert client.get(f"/sessions/{session_id}").json()["done"] is True

    with client.stream(
        "POST", f"/sessions/{session_id}/answer/stream", json={"answer": "late answer"}
    ) as r:
        events = _collect_sse(r)

    assert any("error" in e for e in events)
    assert not any("result" in e for e in events)


def test_report_is_code_rendered_with_labeled_narrative(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})

    r = client.get(f"/sessions/{session_id}/report")
    assert r.status_code == 200
    body = r.json()

    # rate stats lead; the one backed answer satisfied its concern
    assert body["rate_stats"]["total_turns"] == 1
    assert body["rate_stats"]["concerns_satisfied"] == 1
    # the backed commitment is a scored finding carrying its verbatim span
    assert len(body["findings"]) == 1
    assert body["findings"][0]["rubric_row"] == "evidence_backed"
    assert body["findings"][0]["span"]
    # the narrative sits under a "Not scored" header
    assert body["narrative"]["scored"] is False
    assert body["narrative"]["header"] == "Not scored"
    assert body["narrative"]["text"]


def test_clarify_does_not_move_meter_and_keeps_prompt(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    before = client.get(f"/sessions/{session_id}").json()

    r = client.post(f"/sessions/{session_id}/clarify", json={"question": "What do you mean?"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert body["remaining"] == 1
    # unchanged active prompt echoed back
    assert body["prompt"]["concern_id"] == before["prompt"]["concern_id"]

    # meter and agenda untouched after the clarification
    after = client.get(f"/sessions/{session_id}").json()
    assert after["meters"] == before["meters"]
    assert after["prompt"]["concern_id"] == before["prompt"]["concern_id"]
    assert after["concern_status"] == before["concern_status"]


def test_clarify_cap_returns_429(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]

    first = client.post(f"/sessions/{session_id}/clarify", json={"question": "q1"})
    assert first.json()["remaining"] == 1
    second = client.post(f"/sessions/{session_id}/clarify", json={"question": "q2"})
    assert second.json()["remaining"] == 0
    third = client.post(f"/sessions/{session_id}/clarify", json={"question": "q3"})
    assert third.status_code == 429


def test_report_lists_clarifications(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/clarify", json={"question": "Which vehicle?"})

    body = client.get(f"/sessions/{session_id}/report").json()
    assert len(body["clarifications"]) == 1
    assert body["clarifications"][0]["question"] == "Which vehicle?"
    assert body["clarifications"][0]["reply"]


def test_report_never_leaks_a_persona_intro(client: TestClient) -> None:
    """The intro is derived state shown only above a persona's first prompt —
    never persisted, and never part of the after-action report."""
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})
    client.post(
        f"/sessions/{session_id}/answer", json={"answer": "Three named services, FedRAMP host."}
    )

    r = client.get(f"/sessions/{session_id}/report")
    assert r.status_code == 200
    dana_intro = client.app.state.content.personas["technical_evaluator"].intro
    assert dana_intro not in r.text


def test_unknown_session_is_404(client: TestClient) -> None:
    r = client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_content_rubric_is_disclosed(client: TestClient) -> None:
    r = client.get("/content/rubric")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 2
    assert "cap_ceiling" not in body  # the cap now rides inside the red_line row
    assert len(body["rows"]) == 8
    red_line = next(row for row in body["rows"] if row["id"] == "red_line")
    assert red_line["cap"] == 25
    assert all(row["cap"] is None for row in body["rows"] if row["id"] != "red_line")
    assert len(body["concerns"]) == 8
    assert all(c["red_lines"] for c in body["concerns"])


def test_content_tangent_limits_are_disclosed(client: TestClient) -> None:
    response = client.get("/content/tangent-limits")

    assert response.status_code == 200
    assert response.json() == {
        "text": {"warning": 225.0, "limit": 300.0, "unit": "words"},
        "voice": {"warning": 45.0, "limit": 60.0, "unit": "seconds"},
        "penalty": -1,
    }


def test_create_session_prompt_carries_the_opening_intro(client: TestClient) -> None:
    body = client.post("/sessions").json()
    expected = client.app.state.content.personas["technical_evaluator"].intro

    assert body["prompt"]["persona_id"] == "technical_evaluator"
    assert body["prompt"]["intro"] == expected
    # The intro is its own field — it never leaks into the question text.
    assert expected not in body["prompt"]["prompt"]


def test_prompt_carries_the_persona_display_name(client: TestClient) -> None:
    """The header renders a name next to the role label, so the DTO ships
    `display_name` alongside `persona_id` rather than making the frontend
    look it up some other way."""
    body = client.post("/sessions").json()
    persona = client.app.state.content.personas["technical_evaluator"]

    assert body["prompt"]["display_name"] == persona.display_name


def test_get_session_before_answering_still_shows_the_intro(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    reloaded = client.get(f"/sessions/{session_id}").json()

    expected = client.app.state.content.personas["technical_evaluator"].intro
    assert reloaded["prompt"]["intro"] == expected


def test_next_prompt_intro_is_null_once_the_persona_has_spoken(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    body = client.post(
        f"/sessions/{session_id}/answer", json={"answer": "Three named services, FedRAMP host."}
    ).json()

    assert body["next_prompt"]["persona_id"] == "technical_evaluator"
    assert body["next_prompt"]["intro"] is None


def test_prompt_text_is_the_bare_question(client: TestClient) -> None:
    """The DTO already ships `persona_id`, and both surfaces that render a
    question turn that into a header, so a name in the text is a duplicate the
    presenter reads twice."""
    body = client.post("/sessions").json()
    content = client.app.state.content
    persona = content.personas["technical_evaluator"]

    assert body["prompt"]["prompt"] == content.concerns["technical_approach"].core_ask
    assert not body["prompt"]["prompt"].startswith(persona.display_name)


def test_handoff_prompt_carries_the_incoming_personas_intro(client: TestClient) -> None:
    """Both handoffs in the session — technical_evaluator -> contracting_officer
    and contracting_officer -> program_rep — carry the incoming persona's own
    intro exactly once, on their first prompt only."""
    session_id = client.post("/sessions").json()["id"]
    intros = {
        pid: persona.intro for pid, persona in client.app.state.content.personas.items()
    }

    handoffs = []
    for _ in range(30):
        body = client.post(
            f"/sessions/{session_id}/answer", json={"answer": "Here is the answer."}
        ).json()
        nxt = body["next_prompt"]
        if body["done"] or nxt is None:
            break
        if nxt["intro"] is not None:
            handoffs.append(nxt)
        if len(handoffs) >= 2:
            break

    assert len(handoffs) >= 2, "never reached both handoffs"
    first_handoff, second_handoff = handoffs[0], handoffs[1]
    assert first_handoff["persona_id"] == "contracting_officer"
    assert first_handoff["intro"] == intros["contracting_officer"]
    assert first_handoff["is_follow_up"] is False
    assert second_handoff["persona_id"] == "program_rep"
    assert second_handoff["intro"] == intros["program_rep"]
    assert second_handoff["is_follow_up"] is False


def test_clarify_echoes_the_active_prompt_with_its_intro(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    body = client.post(
        f"/sessions/{session_id}/clarify", json={"question": "Do you mean the target state?"}
    ).json()

    expected = client.app.state.content.personas["technical_evaluator"].intro
    # A clarification persists no turn, so the intro is still owed and still shown.
    assert body["prompt"]["intro"] == expected


def _drive_to_done(client: TestClient, session_id: str) -> None:
    """Answer until the agenda is exhausted. `_FakeClient` returns coverage for
    the first concern's sub-question ids only, so that concern satisfies in one
    turn and each of the other seven takes its follow-up and then closes as
    dodged: 15 turns, one satisfied concern."""
    for _ in range(20):
        if client.get(f"/sessions/{session_id}").json()["done"]:
            return
        client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})
    raise AssertionError("session never finished")


def test_finishing_a_session_archives_it(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    _drive_to_done(client, session_id)

    history = client.get("/sessions/history")
    assert history.status_code == 200
    ids = [row["id"] for row in history.json()]
    assert session_id in ids


def test_ending_a_session_archives_it(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]

    r = client.post(f"/sessions/{session_id}/end")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ended"
    # `done` reflects `archived_at`, not just whether the agenda happened to be
    # exhausted — a freshly-created session has plenty of open concerns, but
    # ending it is still terminal, and the response body itself must say so
    # rather than requiring a follow-up GET to find out.
    assert body["done"] is True

    assert [row["id"] for row in client.get("/sessions/history").json()] == [session_id]


def test_ending_twice_keeps_the_first_archive(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/end")
    first = client.get("/sessions/history").json()[0]["archived_at"]

    client.post(f"/sessions/{session_id}/end")

    rows = client.get("/sessions/history").json()
    assert len(rows) == 1
    assert rows[0]["archived_at"] == first


def test_streaming_answer_archives_on_done(client: TestClient) -> None:
    """Every turn goes over SSE, so the turn that finishes the rehearsal is a
    streaming one. The archive runs in that endpoint's worker thread, before its
    commit, so the terminal frame already reflects an archived session."""
    session_id = client.post("/sessions").json()["id"]
    for _ in range(20):
        with client.stream(
            "POST",
            f"/sessions/{session_id}/answer/stream",
            json={"answer": "Here is the architecture."},
        ) as r:
            events = _collect_sse(r)
        result = next(e["result"] for e in events if "result" in e)
        if result["done"]:
            break
    else:
        raise AssertionError("session never finished")

    assert [row["id"] for row in client.get("/sessions/history").json()] == [session_id]


def test_answer_after_end_returns_409(client: TestClient) -> None:
    """`/end` on a rehearsal with concerns still open archives it without
    exhausting the agenda, so `orchestrator.submit_answer` alone would happily
    keep scoring it — the archived check is what has to stop this."""
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/end")

    r = client.post(f"/sessions/{session_id}/answer", json={"answer": "late answer"})
    assert r.status_code == 409


def test_answer_stream_after_end_emits_error(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/end")

    with client.stream(
        "POST", f"/sessions/{session_id}/answer/stream", json={"answer": "late answer"}
    ) as r:
        events = _collect_sse(r)

    assert any("error" in e for e in events)
    assert not any("result" in e for e in events)


def test_clarify_after_end_returns_409(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/end")

    r = client.post(f"/sessions/{session_id}/clarify", json={"question": "late question?"})
    assert r.status_code == 409


class _ExplodingReactClient(_FakeClient):
    """Extraction still works; only the narrative call fails."""

    def react(self, prompt, *, max_tokens=1024, cache_key=None) -> str:
        raise RuntimeError("bedrock unavailable")


def test_report_is_readable_when_the_snapshot_failed(client: TestClient) -> None:
    client.app.dependency_overrides[get_bedrock_client] = _ExplodingReactClient
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/end")
    # Back to the working client so the on-demand fallback can build a report.
    client.app.dependency_overrides[get_bedrock_client] = _FakeClient

    r = client.get(f"/sessions/{session_id}/report")
    assert r.status_code == 200
    first = r.json()
    assert first["narrative"]["scored"] is False

    # The rebuild above must have been backfilled onto the session: a second
    # read against a client that fails any narrative call still succeeds and
    # returns byte-identical content, proving it was served from the
    # now-populated snapshot rather than rebuilt again.
    client.app.dependency_overrides[get_bedrock_client] = _RaisingReactClient
    second = client.get(f"/sessions/{session_id}/report")
    assert second.status_code == 200
    assert second.json() == first


class _RaisingReactClient(_FakeClient):
    """Fails if anything asks it for a narrative. Proves the snapshot is served
    without a model call."""

    def react(self, prompt, *, max_tokens=1024, cache_key=None) -> str:
        raise AssertionError("the archived report must not call the model")


def test_archived_report_is_served_from_the_snapshot(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/end")
    snapshot = client.get(f"/sessions/{session_id}/report").json()

    client.app.dependency_overrides[get_bedrock_client] = _RaisingReactClient
    again = client.get(f"/sessions/{session_id}/report").json()

    assert again == snapshot


def test_report_survives_a_stored_snapshot_that_no_longer_matches_the_schema(
    client: TestClient,
) -> None:
    """A schema change after archiving (a new required field, a rename) leaves
    an old snapshot un-parseable. There's no migration path for opaque stored
    JSON, so the endpoint must self-heal by rebuilding rather than 500ing on
    data it can no longer recover."""
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/end")

    session_factory = client.app.dependency_overrides[get_session_factory]()
    with session_factory() as db:
        session = repo.get_session(db, uuid.UUID(session_id))
        assert session is not None
        session.report_json = {"not": "a valid report"}
        db.commit()

    r = client.get(f"/sessions/{session_id}/report")
    assert r.status_code == 200
    assert r.json()["narrative"]["scored"] is False


def test_history_lists_newest_first_with_summary_fields(client: TestClient) -> None:
    first = client.post("/sessions").json()["id"]
    _drive_to_done(client, first)
    second = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{second}/end")

    rows = client.get("/sessions/history").json()

    assert [row["id"] for row in rows] == [second, first]
    finished = rows[1]
    assert finished["status"] == "complete"
    # Counted from the rows, so compare against the rows rather than hardcoding
    # what `_FakeClient` happens to produce.
    transcript = client.get(f"/sessions/{first}/transcript").json()["turns"]
    assert finished["turn_count"] == len(transcript) > 0
    assert finished["concerns_total"] == 8
    assert finished["concerns_satisfied"] == 1  # see `_drive_to_done`
    assert len(finished["meters"]) == 3
    assert rows[0]["status"] == "ended"
    assert rows[0]["turn_count"] == 0
    assert rows[0]["archived_at"] is not None


def test_history_excludes_a_live_session(client: TestClient) -> None:
    live = client.post("/sessions").json()["id"]

    rows = client.get("/sessions/history").json()

    assert live not in [row["id"] for row in rows]
    assert rows == []


def test_history_caps_at_five(client: TestClient) -> None:
    for _ in range(7):
        session_id = client.post("/sessions").json()["id"]
        client.post(f"/sessions/{session_id}/end")

    assert len(client.get("/sessions/history").json()) == 5


def test_history_route_wins_over_the_session_id_route(client: TestClient) -> None:
    """Declared after GET /sessions/{session_id}, "history" would be parsed as a
    UUID path parameter and 422 instead."""
    r = client.get("/sessions/history")

    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_creating_a_session_prunes_beyond_the_keep_limit(client: TestClient) -> None:
    finished = []
    for _ in range(6):
        session_id = client.post("/sessions").json()["id"]
        client.post(f"/sessions/{session_id}/end")
        finished.append(session_id)

    # The seventh create prunes the oldest archived session.
    client.post("/sessions")

    ids = [row["id"] for row in client.get("/sessions/history").json()]
    assert finished[0] not in ids
    assert len(ids) == 5


def test_transcript_returns_the_prompt_as_asked(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]
    asked = client.get(f"/sessions/{session_id}").json()["prompt"]
    client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})

    turns = client.get(f"/sessions/{session_id}/transcript").json()["turns"]

    assert len(turns) == 1
    turn = turns[0]
    assert turn["prompt"] == asked["prompt"]
    assert turn["intro"] == asked["intro"]
    assert turn["display_name"] == asked["display_name"]
    assert turn["persona_id"] == "technical_evaluator"
    assert turn["concern_id"] == "technical_approach"
    assert turn["is_follow_up"] is False
    assert turn["answer"] == "Here is the architecture."
    assert turn["reply"] == "Concrete. Good."
    assert turn["rationale"] == "+2 backed."
    assert turn["support_delta"] == 2
    assert turn["scored"] is True
    assert turn["transcript"] is None


def test_transcript_interleaves_clarifications_and_marks_them_unscored(
    client: TestClient,
) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/clarify", json={"question": "Which boundary?"})
    client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})

    turns = client.get(f"/sessions/{session_id}/transcript").json()["turns"]

    assert [t["scored"] for t in turns] == [False, True]
    clarification = turns[0]
    assert clarification["answer"] == "Which boundary?"
    assert clarification["rationale"] == ""
    assert clarification["support_delta"] == 0
    assert clarification["matched_rows"] == []
    assert clarification["capped"] is False
    # Asked against the active prompt, which is the same one the scored turn answered.
    assert clarification["prompt"] == turns[1]["prompt"]


def test_transcript_marks_a_second_turn_on_one_concern_as_a_follow_up(
    client: TestClient,
) -> None:
    session_id = client.post("/sessions").json()["id"]
    # `_PartialClient` covers only one sub-question, so the first concern earns a
    # same-concern follow-up instead of satisfying.
    client.app.dependency_overrides[get_bedrock_client] = _PartialClient
    for _ in range(2):
        client.post(f"/sessions/{session_id}/answer", json={"answer": "Partly there."})

    turns = client.get(f"/sessions/{session_id}/transcript").json()["turns"]

    assert turns[0]["concern_id"] == turns[1]["concern_id"]
    assert turns[0]["is_follow_up"] is False
    assert turns[1]["is_follow_up"] is True


def test_transcript_falls_back_to_the_core_ask_for_a_pre_migration_turn(
    client: TestClient, db_factory
) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.post(f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."})
    # Simulate a row written before migration 0006.
    with db_factory() as db:
        turn = repo.get_turns(db, uuid.UUID(session_id))[0]
        turn.prompt = None
        turn.prompt_intro = None
        db.commit()

    turn = client.get(f"/sessions/{session_id}/transcript").json()["turns"][0]

    assert turn["prompt"] == app.state.content.concerns["technical_approach"].core_ask
    assert turn["intro"] is None


def test_transcript_works_on_a_live_session(client: TestClient) -> None:
    session_id = client.post("/sessions").json()["id"]

    assert client.get(f"/sessions/{session_id}/transcript").json() == {"turns": []}
