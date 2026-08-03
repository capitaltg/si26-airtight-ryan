"""Write-side persona store coverage: frozen defaults, merge, reset."""

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.content.loader import load_content
from app.schemas.content import PersonaDefinition, PersonaUpdate

STORE = Path(__file__).resolve().parent.parent / "app" / "content" / "store"
PERSONAS = STORE / "personas"
DEFAULTS = PERSONAS / "defaults"

PERSONA_IDS = ("contracting_officer", "program_rep", "technical_evaluator")


def test_every_persona_has_a_frozen_default() -> None:
    assert DEFAULTS.is_dir(), "the frozen defaults directory is missing"
    assert {p.stem for p in DEFAULTS.glob("*.md")} == set(PERSONA_IDS)


def test_each_default_is_a_valid_persona_whose_id_matches_its_filename() -> None:
    import frontmatter

    for persona_id in PERSONA_IDS:
        post = frontmatter.load(DEFAULTS / f"{persona_id}.md")
        data = dict(post.metadata)
        data["exemplars"] = []
        persona = PersonaDefinition.model_validate(data)
        assert persona.id == persona_id


def test_defaults_are_invisible_to_the_loader() -> None:
    # `personas_dir.glob("*.md")` is non-recursive, so the frozen copies must not
    # show up as a second set of personas. Three personas, not six.
    content = load_content()
    assert len(content.personas) == 3
    assert set(content.personas) == set(PERSONA_IDS)


def test_loader_publishes_the_persona_file_conventions() -> None:
    """The writer rewrites the same fenced block the loader reads, so both must
    come from one definition rather than two copies that can drift."""
    from app.content.loader import YAML_FENCE, load_persona

    persona = load_persona(PERSONAS / "contracting_officer.md")
    assert persona.id == "contracting_officer"
    assert persona.exemplars, "exemplars come from the fenced yaml block"
    assert YAML_FENCE.search("```yaml\nexemplars: []\n```") is not None


@pytest.fixture
def store(tmp_path: Path) -> Path:
    copy = tmp_path / "store"
    shutil.copytree(STORE, copy)
    return copy


def an_update(**overrides: object) -> PersonaUpdate:
    """A full, valid editable payload for contracting_officer."""
    data: dict[str, object] = {
        "display_name": "Mira",
        "intro": "Mira Alvarez, contracting officer on this acquisition.",
        "voice": "Clipped and procedural.",
        "demographics": "Contracting officer with warrant authority.",
        "values": ["compliance with the RFP"],
        "wants": ["answers that stay inside the PWS"],
        "non_negotiables": ["do not promise work outside the PWS"],
        "polly_voice_id": "Joanna",
        "exemplars": [{"user": "Firm-fixed price, 28 FTE.", "support_delta": 2, "note": "Backed."}],
    }
    data.update(overrides)
    return PersonaUpdate.model_validate(data)


def test_save_persists_the_editable_fields(store: Path) -> None:
    from app.content.loader import load_persona
    from app.content.persona_writer import live_path, save_persona

    saved = save_persona("contracting_officer", an_update(), store)

    assert saved.display_name == "Mira"
    assert saved.polly_voice_id == "Joanna"
    reread = load_persona(live_path("contracting_officer", store))
    assert reread.display_name == "Mira"
    assert reread.values == ["compliance with the RFP"]


def test_save_keeps_the_locked_fields(store: Path) -> None:
    from app.content.loader import load_persona
    from app.content.persona_writer import live_path, save_persona

    before = load_persona(live_path("contracting_officer", store))
    save_persona("contracting_officer", an_update(), store)
    after = load_persona(live_path("contracting_officer", store))

    assert after.id == before.id
    assert after.priorities == before.priorities
    assert after.rubric_version == before.rubric_version


def test_smuggled_locked_fields_are_ignored_not_rejected(store: Path) -> None:
    from app.content.loader import load_persona
    from app.content.persona_writer import live_path, save_persona

    payload = PersonaUpdate.model_validate(
        {
            **an_update().model_dump(),
            "id": "impostor",
            "priorities": ["risk"],
            "rubric_version": 99,
        }
    )
    save_persona("contracting_officer", payload, store)

    after = load_persona(live_path("contracting_officer", store))
    assert after.id == "contracting_officer"
    assert after.priorities == ["compliance_security", "cost_realism", "past_performance"]
    assert after.rubric_version == 1


def test_save_preserves_the_body_prose(store: Path) -> None:
    from app.content.persona_writer import live_path, save_persona

    save_persona("contracting_officer", an_update(), store)

    text = live_path("contracting_officer", store).read_text()
    assert "# Marcus, Contracting Officer" in text
    assert "Marcus rewards discipline." in text


def test_save_stamps_the_persona_on_every_exemplar(store: Path) -> None:
    from app.content.loader import load_persona
    from app.content.persona_writer import live_path, save_persona

    saved = save_persona("contracting_officer", an_update(), store)

    assert [e.persona for e in saved.exemplars] == ["contracting_officer"]
    reread = load_persona(live_path("contracting_officer", store))
    assert [e.persona for e in reread.exemplars] == ["contracting_officer"]
    assert reread.exemplars[0].support_delta == 2


def test_save_round_trips_an_empty_exemplar_list(store: Path) -> None:
    from app.content.loader import load_persona
    from app.content.persona_writer import live_path, save_persona

    save_persona("contracting_officer", an_update(exemplars=[]), store)

    assert load_persona(live_path("contracting_officer", store)).exemplars == []


def test_save_round_trips_an_exemplar_with_literal_fence_text(store: Path) -> None:
    from app.content.loader import load_persona
    from app.content.persona_writer import live_path, save_persona

    saved = save_persona(
        "contracting_officer",
        an_update(
            exemplars=[
                {"user": "First line\n```\nLast line", "support_delta": 2, "note": "Backed."}
            ]
        ),
        store,
    )

    assert load_persona(live_path("contracting_officer", store)) == saved


def test_an_invalid_merge_raises_and_leaves_the_file_untouched(store: Path) -> None:
    from app.content.persona_writer import live_path, save_persona

    path = live_path("contracting_officer", store)
    before = path.read_bytes()
    with pytest.raises(ValidationError):
        save_persona("contracting_officer", an_update(intro=""), store)

    assert path.read_bytes() == before


def test_reset_restores_the_default_bytes_exactly(store: Path) -> None:
    from app.content.persona_writer import default_path, live_path, reset_persona, save_persona

    path = live_path("contracting_officer", store)
    save_persona("contracting_officer", an_update(), store)
    assert path.read_bytes() != default_path("contracting_officer", store).read_bytes()

    restored = reset_persona("contracting_officer", store)

    assert path.read_bytes() == default_path("contracting_officer", store).read_bytes()
    assert restored.display_name == "Marcus"


def test_malformed_default_leaves_the_live_persona_untouched(store: Path) -> None:
    from app.content.persona_writer import default_path, live_path, reset_persona

    default_path("contracting_officer", store).write_text("---\nid: contracting_officer\n---\n")
    live = live_path("contracting_officer", store)
    before = live.read_bytes()

    with pytest.raises(ValidationError):
        reset_persona("contracting_officer", store)

    assert live.read_bytes() == before


def test_interrupted_reset_copy_leaves_the_live_persona_untouched(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.content import persona_writer

    live = persona_writer.live_path("contracting_officer", store)
    before = live.read_bytes()

    def interrupt_copy(_source: Path, destination: Path) -> None:
        Path(destination).write_bytes(b"partial copy")
        raise OSError("copy interrupted")

    monkeypatch.setattr(persona_writer.shutil, "copyfile", interrupt_copy)

    with pytest.raises(OSError, match="copy interrupted"):
        persona_writer.reset_persona("contracting_officer", store)

    assert live.read_bytes() == before


def test_is_customized_tracks_save_and_reset(store: Path) -> None:
    from app.content.persona_writer import is_customized, reset_persona, save_persona

    assert is_customized("contracting_officer", store) is False
    save_persona("contracting_officer", an_update(), store)
    assert is_customized("contracting_officer", store) is True
    reset_persona("contracting_officer", store)
    assert is_customized("contracting_officer", store) is False


def test_is_customized_raises_when_the_frozen_default_is_missing(store: Path) -> None:
    from app.content.persona_writer import default_path, is_customized

    default_path("contracting_officer", store).unlink()

    with pytest.raises(FileNotFoundError):
        is_customized("contracting_officer", store)


def test_saving_identical_content_is_not_a_customization(store: Path) -> None:
    """The customization flag compares parsed personas, not YAML bytes."""
    from app.content.loader import load_persona
    from app.content.persona_writer import is_customized, live_path, save_persona

    current = load_persona(live_path("contracting_officer", store))
    unchanged = PersonaUpdate.model_validate(
        {
            **current.model_dump(exclude={"id", "priorities", "rubric_version", "exemplars"}),
            "exemplars": [e.model_dump(exclude={"persona"}) for e in current.exemplars],
        }
    )
    save_persona("contracting_officer", unchanged, store)

    assert is_customized("contracting_officer", store) is False
