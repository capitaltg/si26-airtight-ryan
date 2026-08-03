"""Unit tests for temporary persona customization in the replay runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPLAY_DIR = Path(__file__).resolve().parents[2] / "scripts" / "replay"
EXPECTED_CONCERNS = {
    "technical_approach",
    "key_personnel",
    "transition",
    "risk",
    "compliance_security",
    "cost_realism",
    "past_performance",
    "operational_impact",
}


@pytest.mark.parametrize(
    "filename,persona_id",
    [
        ("scenario-custom-dana.json", "technical_evaluator"),
        ("scenario-custom-marcus.json", "contracting_officer"),
        ("scenario-custom-priya.json", "program_rep"),
    ],
)
def test_custom_persona_scenarios_define_one_editable_persona(
    filename: str, persona_id: str
) -> None:
    """Each customized fixture changes one evaluator, not its locked identity."""
    scenario = json.loads((REPLAY_DIR / filename).read_text())

    assert set(scenario["personas"]) == {persona_id}
    assert set(scenario["concerns"]) == EXPECTED_CONCERNS
    assert not {"id", "priorities", "rubric_version"} & set(scenario["personas"][persona_id])


def test_persona_update_omits_locked_and_server_owned_fields() -> None:
    """Only editable persona content reaches the update endpoint."""
    from replay_session import persona_update

    update = persona_update(
        {
            "id": "technical_evaluator",
            "display_name": "Mara",
            "priorities": ["risk"],
            "rubric_version": 99,
            "is_customized": True,
            "exemplars": [
                {
                    "persona": "technical_evaluator",
                    "user": "x",
                    "support_delta": 1,
                    "note": "n",
                }
            ],
        }
    )

    assert update == {
        "display_name": "Mara",
        "exemplars": [{"user": "x", "support_delta": 1, "note": "n"}],
    }


def test_replay_with_personas_restores_snapshot_when_replay_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each successfully customized persona is restored when the replay fails."""
    from replay_session import replay_with_personas

    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "replay_session._get",
        lambda *_: [
            {
                "id": "technical_evaluator",
                "display_name": "Dana",
                "exemplars": [],
            }
        ],
    )
    monkeypatch.setattr(
        "replay_session._put",
        lambda _base, path, body: calls.append((path, body)) or {},
    )
    monkeypatch.setattr(
        "replay_session.replay",
        lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        replay_with_personas(
            "http://api",
            {"personas": {"technical_evaluator": {"display_name": "Mara"}}},
            True,
            False,
        )

    assert calls == [
        ("/content/personas/technical_evaluator", {"display_name": "Mara"}),
        (
            "/content/personas/technical_evaluator",
            {"display_name": "Dana", "exemplars": []},
        ),
    ]


def test_replay_with_personas_bypasses_persona_api_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Baseline replays must not make an unnecessary persona API request."""
    from replay_session import replay_with_personas

    monkeypatch.setattr(
        "replay_session._get",
        lambda *_: pytest.fail("persona API must not be called"),
    )
    sentinel = {"name": "baseline"}
    monkeypatch.setattr("replay_session.replay", lambda *_: sentinel)

    assert replay_with_personas("http://api", {"concerns": {}}, True, False) == sentinel


def test_replay_with_personas_attempts_every_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed restore must not prevent restoration of an earlier persona."""
    from replay_session import replay_with_personas

    calls: list[str] = []
    monkeypatch.setattr(
        "replay_session._get",
        lambda *_: [
            {"id": "technical_evaluator", "display_name": "Dana"},
            {"id": "contracting_officer", "display_name": "Marcus"},
        ],
    )

    def put(_base: str, path: str, _body: dict) -> dict:
        calls.append(path)
        if len(calls) == 3:
            raise RuntimeError("restore failed")
        return {}

    monkeypatch.setattr("replay_session._put", put)
    monkeypatch.setattr("replay_session.replay", lambda *_: {"name": "run"})

    with pytest.raises(RuntimeError, match="restore failed"):
        replay_with_personas(
            "http://api",
            {"personas": {"technical_evaluator": {}, "contracting_officer": {}}},
            True,
            False,
        )

    assert calls == [
        "/content/personas/technical_evaluator",
        "/content/personas/contracting_officer",
        "/content/personas/contracting_officer",
        "/content/personas/technical_evaluator",
    ]


def test_replay_with_personas_preserves_replay_error_when_restore_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay failure remains primary when cleanup also reports a failure."""
    from replay_session import replay_with_personas

    calls = 0
    monkeypatch.setattr(
        "replay_session._get",
        lambda *_: [{"id": "technical_evaluator", "display_name": "Dana"}],
    )

    def put(*_args: object) -> dict:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("restore failed")
        return {}

    monkeypatch.setattr("replay_session._put", put)
    monkeypatch.setattr(
        "replay_session.replay",
        lambda *_: (_ for _ in ()).throw(RuntimeError("replay failed")),
    )

    with pytest.raises(RuntimeError, match="replay failed") as caught:
        replay_with_personas(
            "http://api",
            {"personas": {"technical_evaluator": {}}},
            True,
            False,
        )

    assert caught.value.__notes__ == ["restore failed: restore failed"]
