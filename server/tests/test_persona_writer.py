"""Write-side persona store coverage: frozen defaults, merge, reset."""

from pathlib import Path

from app.content.loader import load_content
from app.schemas.content import PersonaDefinition

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
