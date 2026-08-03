"""Unit tests for temporary persona customization in the replay runner."""

from __future__ import annotations

import pytest


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
