import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_bedrock_client, get_db, get_session_factory
from app.content.loader import Content
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
        assert content.rubric.version == 1


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

    def react(self, prompt: str, *, max_tokens: int = 1024) -> str:
        return "Strong on the technical approach; keep drilling staffing specifics."


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_bedrock_client] = _FakeClient
    # The SSE endpoint opens its own session off the factory (own worker thread),
    # so point it at the same in-memory engine the request sessions use.
    app.dependency_overrides[get_session_factory] = lambda: factory
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


def test_unknown_session_is_404(client: TestClient) -> None:
    r = client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_content_rubric_is_disclosed(client: TestClient) -> None:
    r = client.get("/content/rubric")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert "cap_ceiling" not in body  # the cap now rides inside the red_line row
    assert len(body["rows"]) == 7
    red_line = next(row for row in body["rows"] if row["id"] == "red_line")
    assert red_line["cap"] == 25
    assert all(row["cap"] is None for row in body["rows"] if row["id"] != "red_line")
    assert len(body["concerns"]) == 8
    assert all(c["red_lines"] for c in body["concerns"])
