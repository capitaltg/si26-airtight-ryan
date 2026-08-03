"""Persona editor API coverage.

Every test that writes runs against a temp copy of the content store: the
writer resolves ``settings.content_dir`` at call time, so monkeypatching the
settings object redirects both the write and the reload.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

STORE = Path(__file__).resolve().parent.parent / "app" / "content" / "store"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway copy of the content store, wired in as the live one."""
    copy = tmp_path / "store"
    shutil.copytree(STORE, copy)
    monkeypatch.setattr(settings, "content_dir", copy)
    return copy


@pytest.fixture
def client(store: Path) -> Iterator[TestClient]:
    # `with` runs the lifespan, which now reads settings.content_dir at call
    # time, so app.state.content is loaded from the temp copy.
    with TestClient(app) as c:
        yield c


def test_reload_content_swaps_the_bundle_on_app_state(
    client: TestClient, store: Path
) -> None:
    from app.api.deps import reload_content

    before = app.state.content
    persona = store / "personas" / "contracting_officer.md"
    persona.write_text(
        persona.read_text().replace("display_name: Marcus", "display_name: Mira")
    )

    after = reload_content(app)

    assert after is not before, "reload must swap the reference, not mutate in place"
    assert app.state.content is after
    assert after.personas["contracting_officer"].display_name == "Mira"
    assert before.personas["contracting_officer"].display_name == "Marcus"


def test_list_returns_all_three_in_turn_order(client: TestClient) -> None:
    r = client.get("/content/personas")

    assert r.status_code == 200
    body = r.json()
    assert [p["id"] for p in body] == [
        "technical_evaluator",
        "contracting_officer",
        "program_rep",
    ]


def test_list_includes_locked_fields_and_the_customized_flag(client: TestClient) -> None:
    marcus = next(
        p
        for p in client.get("/content/personas").json()
        if p["id"] == "contracting_officer"
    )

    assert marcus["display_name"] == "Marcus"
    assert marcus["priorities"] == [
        "compliance_security",
        "cost_realism",
        "past_performance",
    ]
    assert marcus["rubric_version"] == 1
    assert marcus["polly_voice_id"] == "Matthew"
    assert marcus["is_customized"] is False
    assert marcus["exemplars"][0]["persona"] == "contracting_officer"


def test_list_reports_a_hand_edited_persona_as_customized(
    client: TestClient, store: Path
) -> None:
    from app.api.deps import reload_content

    persona = store / "personas" / "contracting_officer.md"
    persona.write_text(
        persona.read_text().replace("display_name: Marcus", "display_name: Mira")
    )
    reload_content(app)

    marcus = next(
        p
        for p in client.get("/content/personas").json()
        if p["id"] == "contracting_officer"
    )
    assert marcus["is_customized"] is True


def a_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "display_name": "Mira",
        "intro": "Mira Alvarez, contracting officer on this acquisition.",
        "voice": "Clipped and procedural.",
        "demographics": "Contracting officer with warrant authority.",
        "values": ["compliance with the RFP"],
        "wants": ["answers that stay inside the PWS"],
        "non_negotiables": ["do not promise work outside the PWS"],
        "polly_voice_id": "Joanna",
        "exemplars": [
            {
                "user": "Firm-fixed price, 28 FTE.",
                "support_delta": 2,
                "note": "Backed.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_save_returns_the_updated_persona(client: TestClient) -> None:
    r = client.put("/content/personas/contracting_officer", json=a_payload())

    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Mira"
    assert body["polly_voice_id"] == "Joanna"
    assert body["is_customized"] is True
    assert body["exemplars"] == [
        {
            "persona": "contracting_officer",
            "user": "Firm-fixed price, 28 FTE.",
            "support_delta": 2,
            "note": "Backed.",
        }
    ]


def test_a_saved_persona_shows_up_on_the_next_get(client: TestClient) -> None:
    client.put("/content/personas/contracting_officer", json=a_payload())

    marcus = next(
        p
        for p in client.get("/content/personas").json()
        if p["id"] == "contracting_officer"
    )
    assert marcus["display_name"] == "Mira"
    assert marcus["is_customized"] is True


def test_save_reloads_the_content_on_app_state(client: TestClient) -> None:
    before = app.state.content

    client.put("/content/personas/contracting_officer", json=a_payload())

    assert app.state.content is not before
    assert app.state.content.personas["contracting_officer"].display_name == "Mira"


def test_reload_failure_rolls_back_saved_bytes_and_app_state(
    client: TestClient, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import personas as personas_api

    path = store / "personas" / "contracting_officer.md"
    before_bytes = path.read_bytes()
    before_content = app.state.content

    def fail_reload(application: FastAPI) -> None:
        application.state.content = object()
        raise RuntimeError("reload failed")

    monkeypatch.setattr(personas_api, "reload_content", fail_reload)

    with pytest.raises(RuntimeError, match="reload failed"):
        client.put("/content/personas/contracting_officer", json=a_payload())

    assert path.read_bytes() == before_bytes
    assert app.state.content is before_content


def test_save_ignores_locked_fields_in_the_payload(client: TestClient) -> None:
    r = client.put(
        "/content/personas/contracting_officer",
        json=a_payload(id="impostor", priorities=["risk"], rubric_version=99),
    )

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "contracting_officer"
    assert body["priorities"] == [
        "compliance_security",
        "cost_realism",
        "past_performance",
    ]
    assert body["rubric_version"] == 1


def test_an_out_of_range_support_delta_is_a_422(
    client: TestClient, store: Path
) -> None:
    path = store / "personas" / "contracting_officer.md"
    before = path.read_bytes()

    r = client.put(
        "/content/personas/contracting_officer",
        json=a_payload(exemplars=[{"user": "u", "support_delta": 5, "note": "n"}]),
    )

    assert r.status_code == 422
    locs = [error["loc"] for error in r.json()["detail"]]
    assert ["body", "exemplars", 0, "support_delta"] in locs
    assert path.read_bytes() == before, "a rejected save must not touch the file"


def test_an_empty_intro_is_a_422(client: TestClient) -> None:
    r = client.put("/content/personas/contracting_officer", json=a_payload(intro=""))

    assert r.status_code == 422
    locs = [error["loc"] for error in r.json()["detail"]]
    assert ["body", "intro"] in locs


def test_saving_an_unknown_persona_is_a_404(client: TestClient) -> None:
    r = client.put("/content/personas/nobody", json=a_payload())
    assert r.status_code == 404


def test_reset_restores_the_shipped_persona(client: TestClient, store: Path) -> None:
    path = store / "personas" / "contracting_officer.md"
    default = store / "personas" / "defaults" / "contracting_officer.md"
    client.put("/content/personas/contracting_officer", json=a_payload())
    assert path.read_bytes() != default.read_bytes()

    r = client.post("/content/personas/contracting_officer/reset")

    assert r.status_code == 200
    assert r.json()["display_name"] == "Marcus"
    assert r.json()["is_customized"] is False
    assert path.read_bytes() == default.read_bytes()


def test_reset_reloads_the_content_on_app_state(client: TestClient) -> None:
    client.put("/content/personas/contracting_officer", json=a_payload())
    assert app.state.content.personas["contracting_officer"].display_name == "Mira"

    client.post("/content/personas/contracting_officer/reset")

    assert app.state.content.personas["contracting_officer"].display_name == "Marcus"


def test_resetting_an_unknown_persona_is_a_404(client: TestClient) -> None:
    assert client.post("/content/personas/nobody/reset").status_code == 404
