import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.content.loader import Content, load_content

STORE = Path(__file__).resolve().parent.parent / "app" / "content" / "store"


def test_load_content_returns_full_bundle() -> None:
    content = load_content()
    assert isinstance(content, Content)
    assert len(content.personas) == 3
    assert len(content.concerns) == 8
    assert content.rubric.version == 1
    assert content.rubric.cap_ceiling == 25  # computed from the red_line row's cap


def test_rubric_cap_lives_on_the_red_line_row() -> None:
    content = load_content()
    rows = {row.id: row for row in content.rubric.rows}
    # The red line row carries the sticky cap inline.
    assert rows["red_line"].cap == 25
    # No other row caps the meter.
    assert all(row.cap is None for row in content.rubric.rows if row.id != "red_line")
    # The computed ceiling still resolves to 25 for the scoring engine.
    assert content.rubric.cap_ceiling == 25


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
