from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_bedrock_client, get_db
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
        prompt: str,
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


def test_unknown_session_is_404(client: TestClient) -> None:
    r = client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_content_rubric_is_disclosed(client: TestClient) -> None:
    r = client.get("/content/rubric")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["cap_ceiling"] == 25
    assert len(body["rows"]) == 7
    assert len(body["concerns"]) == 8
    assert all(c["red_lines"] for c in body["concerns"])
