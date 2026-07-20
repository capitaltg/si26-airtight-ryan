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
    # cap_ceiling must be an int; a string fails validation
    rubric.write_text(rubric.read_text().replace("cap_ceiling: 25", "cap_ceiling: high"))
    with pytest.raises(ValidationError):
        load_content(store)


def test_missing_file_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(STORE, store)
    (store / "rubric.yaml").unlink()
    with pytest.raises(FileNotFoundError):
        load_content(store)
