import re
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.content.loader import Content, load_content
from app.schemas.content import Concern, NonNegotiable, PersonaDefinition, Requires

STORE = Path(__file__).resolve().parent.parent / "app" / "content" / "store"


def test_load_content_returns_full_bundle() -> None:
    content = load_content()
    assert isinstance(content, Content)
    assert len(content.personas) == 3
    assert len(content.concerns) == 8
    assert content.rubric.version == 4
    assert content.rubric.cap_ceiling == 25  # computed from the red_line row's cap


def test_rubric_rows_are_in_non_descending_order() -> None:
    content = load_content()
    values = [row.support_value for row in content.rubric.rows]
    assert values == sorted(values), (
        f"rubric rows must ascend by support_value, got {values}"
    )


def test_rubric_cap_lives_on_the_red_line_row() -> None:
    content = load_content()
    rows = {row.id: row for row in content.rubric.rows}
    # The red line row carries the sticky cap inline.
    assert rows["red_line"].cap == 25
    # No other row caps the meter.
    assert all(row.cap is None for row in content.rubric.rows if row.id != "red_line")
    # The computed ceiling still resolves to 25 for the scoring engine.
    assert content.rubric.cap_ceiling == 25


def test_rubric_discloses_how_rows_combine() -> None:
    content = load_content()
    assert len(content.rubric.combination) >= 6
    joined = " ".join(content.rubric.combination).lower()
    assert "red line" in joined
    assert "-2 to +2" in joined


def test_rows_with_a_combination_caveat_carry_a_note() -> None:
    rows = {row.id: row for row in load_content().rubric.rows}
    assert rows["false_fact"].note is not None
    assert rows["approach_cited"].note is not None
    assert rows["contradiction"].note is not None
    assert rows["over_limit"].note is not None
    assert rows["dodge"].note is None


def test_rubric_without_the_new_fields_still_loads(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    (store / "rubric.yaml").write_text(
        "version: 2\n"
        "rows:\n"
        "  - id: red_line\n"
        "    support_value: -2\n"
        "    cap: 25\n"
        "    description: Crossed a persona hard limit.\n"
        "  - id: over_limit\n"
        "    support_value: -1\n"
        "    description: Answer exceeds the configured limit.\n"
    )
    content = load_content(store)
    assert content.rubric.combination == []
    assert all(row.note is None for row in content.rubric.rows)


def test_texts_and_keys_are_populated() -> None:
    content = load_content()
    assert content.rfp_text.strip()
    assert content.proposal_text.strip()
    assert set(content.personas) == {
        "technical_evaluator",
        "contracting_officer",
        "program_rep",
    }
    assert "technical_approach" in content.concerns
    assert content.personas["technical_evaluator"].exemplars


def test_malformed_persona_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    persona = store / "personas" / "technical_evaluator.md"
    text = persona.read_text()
    # drop the required rubric_version field from the frontmatter
    persona.write_text(text.replace("rubric_version: 1\n", ""))
    with pytest.raises(ValidationError):
        load_content(store)


def test_malformed_rubric_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    rubric = store / "rubric.yaml"
    # a row's cap must be an int; a string fails validation
    rubric.write_text(rubric.read_text().replace("cap: 25", "cap: high"))
    with pytest.raises(ValidationError):
        load_content(store)


def test_red_line_without_a_cap_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    rubric = store / "rubric.yaml"
    # dropping the red_line cap would silently defeat the sticky pin; reject it.
    rubric.write_text(rubric.read_text().replace("    cap: 25\n", ""))
    with pytest.raises(ValidationError):
        load_content(store)


def test_missing_file_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    (store / "rubric.yaml").unlink()
    with pytest.raises(FileNotFoundError):
        load_content(store)


def test_all_personas_have_polly_voice_id() -> None:
    content = load_content()
    for persona in content.personas.values():
        assert persona.polly_voice_id
        assert persona.polly_voice_id.strip()


def test_persona_missing_polly_voice_id_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    persona = store / "personas" / "technical_evaluator.md"
    text = persona.read_text()
    # drop the required polly_voice_id field from the frontmatter
    persona.write_text(text.replace("polly_voice_id: Ruth\n", ""))
    with pytest.raises(ValidationError):
        load_content(store)


def test_all_personas_have_an_intro() -> None:
    content = load_content()
    for persona in content.personas.values():
        assert persona.intro
        assert persona.intro.strip()


def test_intro_names_the_persona() -> None:
    """The intro is where the person introduces themself, so it carries the
    authored first name that the UI's role-based header never shows."""
    content = load_content()
    for persona in content.personas.values():
        assert persona.display_name in persona.intro


def test_persona_missing_intro_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    persona = store / "personas" / "technical_evaluator.md"
    # Drop either a folded or wrapped plain-scalar `intro:` entry.
    stripped = re.sub(r"\nintro:.*\n(?:  .*\n)*", "\n", persona.read_text(), count=1)
    assert "intro:" not in stripped, "the intro block was not removed; fix the pattern"
    persona.write_text(stripped)
    with pytest.raises(ValidationError):
        load_content(store)


def test_persona_empty_intro_raises(tmp_path: Path) -> None:
    """An empty `intro:` key passes the "key is present" check but must still
    fail: a blank intro is exactly as personaless as a missing one."""
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    persona = store / "personas" / "technical_evaluator.md"
    stripped = re.sub(
        r"\nintro:.*\n(?:  .*\n)*", "\nintro: ''\n", persona.read_text(), count=1
    )
    assert "intro: ''" in stripped, "the intro block was not replaced; fix the pattern"
    persona.write_text(stripped)
    with pytest.raises(ValidationError):
        load_content(store)


def test_extraction_fingerprint_is_stable_and_excludes_the_rubric() -> None:
    content = load_content()
    assert len(content.extraction_fingerprint) == 64
    # deterministic across loads
    assert load_content().extraction_fingerprint == content.extraction_fingerprint


def test_extraction_fingerprint_changes_when_a_persona_changes() -> None:
    from app.content.loader import compute_extraction_fingerprint

    content = load_content()
    edited = {
        pid: (
            p.model_copy(
                update={
                    "non_negotiables": [
                        *p.non_negotiables,
                        NonNegotiable(id="new_line", text="new line"),
                    ]
                }
            )
            if pid == "technical_evaluator"
            else p
        )
        for pid, p in content.personas.items()
    }
    changed = compute_extraction_fingerprint(
        rfp_text=content.rfp_text,
        proposal_text=content.proposal_text,
        personas=edited,
        concerns=content.concerns,
    )
    assert changed != content.extraction_fingerprint


def test_red_lines_and_non_negotiables_carry_authored_ids() -> None:
    content = load_content()
    concern = content.concerns["technical_approach"]
    assert [rl.id for rl in concern.red_lines] == ["on_prem_hosting", "unbacked_capability"]
    assert concern.red_lines[0].text.startswith("Proposes on-premises hosting")

    persona = content.personas["contracting_officer"]
    assert [nn.id for nn in persona.non_negotiables] == [
        "no_work_outside_pws",
        "no_off_proposal_terms",
        "no_disparaging_incumbent",
    ]


def test_duplicate_red_line_ids_in_one_concern_fail_validation() -> None:
    with pytest.raises(ValidationError):
        Concern.model_validate(
            {
                "concern_id": "dupes",
                "core_ask": "ask",
                "sub_questions": [],
                "red_lines": [
                    {"id": "same", "text": "first"},
                    {"id": "same", "text": "second"},
                ],
                "what_would_satisfy": "something",
            }
        )


def test_duplicate_non_negotiable_ids_in_one_persona_fail_validation() -> None:
    content = load_content()
    raw = content.personas["program_rep"].model_dump(mode="json")
    raw["non_negotiables"] = [{"id": "same", "text": "a"}, {"id": "same", "text": "b"}]
    with pytest.raises(ValidationError):
        PersonaDefinition.model_validate(raw)


def test_extraction_fingerprint_ignores_the_rubric() -> None:
    from app.content.loader import compute_extraction_fingerprint

    content = load_content()
    same = compute_extraction_fingerprint(
        rfp_text=content.rfp_text,
        proposal_text=content.proposal_text,
        personas=content.personas,
        concerns=content.concerns,
    )
    assert same == content.extraction_fingerprint


def test_naming_a_risk_is_satisfiable_by_a_fact() -> None:
    """`requires` now demotes coverage, so a sub-question asking what is true
    must not demand a commitment. Naming a risk is a statement, not a promise."""
    concern = load_content().concerns["risk"]
    named_risk = next(sq for sq in concern.sub_questions if sq.id == "named_risk")
    assert named_risk.requires is Requires.fact_or_commitment


def test_integrity_rows_carry_a_ceiling() -> None:
    rubric = load_content().rubric
    by_id = {row.id: row for row in rubric.rows}
    assert by_id["false_fact"].ceiling == 0
    assert by_id["contradiction"].ceiling == 0
    assert by_id["acknowledged_revision"].support_value == 0
    assert by_id["acknowledged_revision"].ceiling is None
    # the red line still pins the meter, and the new field did not leak into it
    assert rubric.cap_ceiling == 25


def test_an_integrity_row_without_a_ceiling_is_rejected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    rubric_path = store / "rubric.yaml"
    rubric_path.write_text(rubric_path.read_text().replace("    ceiling: 0\n", "", 1))
    with pytest.raises(ValidationError):
        load_content(store)
