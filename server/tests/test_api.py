from fastapi.testclient import TestClient

from app.content.loader import Content
from app.main import app


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
