"""Write-side helpers for the file-backed persona store.

The editor changes the same markdown files loaded at startup. Locked fields
always come from the current file, and every merged definition validates before
the file changes.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from app.config import settings
from app.content.loader import YAML_FENCE, load_persona
from app.schemas.content import PersonaDefinition, PersonaUpdate

__all__ = [
    "default_path",
    "is_customized",
    "live_path",
    "render_persona_file",
    "reset_persona",
    "save_persona",
]


def _root(content_dir: Path | None) -> Path:
    """Resolve at call time so tests and configured reloads share a store."""
    return (content_dir if content_dir is not None else settings.content_dir) / "personas"


def live_path(persona_id: str, content_dir: Path | None = None) -> Path:
    """Return the live persona path for ``persona_id``."""
    return _root(content_dir) / f"{persona_id}.md"


def default_path(persona_id: str, content_dir: Path | None = None) -> Path:
    """Return the frozen default persona path for ``persona_id``."""
    return _root(content_dir) / "defaults" / f"{persona_id}.md"


def _exemplar_block(exemplars: list[dict[str, Any]]) -> str:
    block = yaml.safe_dump(
        {"exemplars": exemplars},
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=88,
    )
    return f"```yaml\n{block}```"


def _replace_exemplars(body: str, exemplars: list[dict[str, Any]]) -> str:
    """Replace the fenced exemplar block without changing surrounding prose."""
    fence = _exemplar_block(exemplars)
    if YAML_FENCE.search(body) is not None:
        return YAML_FENCE.sub(lambda _: fence, body, count=1)
    return f"{body.rstrip(chr(10))}\n\n{fence}\n"


def render_persona_file(
    path: Path, persona_id: str, update: PersonaUpdate
) -> tuple[str, PersonaDefinition]:
    """Merge editable content onto a live persona, without writing it.

    The existing frontmatter owns locked fields. Validation happens before this
    function returns file text, so callers cannot persist an invalid merge.
    """
    post = frontmatter.load(path)
    metadata: dict[str, Any] = dict(post.metadata)
    metadata.update(update.model_dump(exclude={"exemplars"}))

    exemplars: list[dict[str, Any]] = [
        {"persona": persona_id, **exemplar.model_dump()} for exemplar in update.exemplars
    ]
    definition = PersonaDefinition.model_validate({**metadata, "exemplars": exemplars})

    body = _replace_exemplars(post.content, exemplars)
    text = frontmatter.dumps(frontmatter.Post(body, **metadata))
    return (text if text.endswith("\n") else text + "\n"), definition


def save_persona(
    persona_id: str, update: PersonaUpdate, content_dir: Path | None = None
) -> PersonaDefinition:
    """Validate and save editable content for one persona."""
    path = live_path(persona_id, content_dir)
    text, definition = render_persona_file(path, persona_id, update)
    path.write_text(text, encoding="utf-8")
    return definition


def reset_persona(persona_id: str, content_dir: Path | None = None) -> PersonaDefinition:
    """Restore the frozen file bytes, then parse the restored persona."""
    source = default_path(persona_id, content_dir)
    if not source.is_file():
        raise FileNotFoundError(f"missing frozen default: {source}")
    destination = live_path(persona_id, content_dir)
    shutil.copyfile(source, destination)
    return load_persona(destination)


def is_customized(persona_id: str, content_dir: Path | None = None) -> bool:
    """Whether live and frozen parsed persona definitions differ."""
    default = default_path(persona_id, content_dir)
    if not default.is_file():
        return False
    return load_persona(live_path(persona_id, content_dir)) != load_persona(default)
