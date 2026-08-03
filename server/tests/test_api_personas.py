"""Persona editor API coverage.

Every test that writes runs against a temp copy of the content store: the
writer resolves ``settings.content_dir`` at call time, so monkeypatching the
settings object redirects both the write and the reload.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
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
