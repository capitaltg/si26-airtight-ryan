"""Write-side helpers for the file-backed persona store.

The editor changes the same markdown files loaded at startup. Locked fields
always come from the current file, and every merged definition validates before
the file changes.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from app.config import settings
from app.content.loader import YAML_FENCE, load_persona, parse_persona
from app.schemas.content import PersonaDefinition, PersonaUpdate

__all__ = [
    "default_path",
    "is_customized",
    "live_path",
    "render_persona_file",
    "reset_persona",
    "restore_persona_bytes",
    "save_persona",
    "slug_id",
]

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slug_id(text: str, taken: set[str]) -> str:
    """A stable, readable id for a newly added non-negotiable.

    Only ever used for an entry the editor created without one. An existing entry
    keeps its authored id, so rewording never repoints a stored finding.
    """
    base = _SLUG_STRIP.sub("_", text.strip().lower()).strip("_")[:48] or "non_negotiable"
    candidate, suffix = base, 2
    while candidate in taken:
        candidate, suffix = f"{base}_{suffix}", suffix + 1
    return candidate


def _resolve_non_negotiables(update: PersonaUpdate) -> list[dict[str, str]]:
    """Fill in an id for every incoming entry that lacks one."""
    taken = {nn.id for nn in update.non_negotiables if nn.id}
    resolved: list[dict[str, str]] = []
    for nn in update.non_negotiables:
        identifier = nn.id or slug_id(nn.text, taken)
        taken.add(identifier)
        resolved.append({"id": identifier, "text": nn.text})
    return resolved


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
    metadata["non_negotiables"] = _resolve_non_negotiables(update)

    exemplars: list[dict[str, Any]] = [
        {"persona": persona_id, **exemplar.model_dump()} for exemplar in update.exemplars
    ]
    definition = PersonaDefinition.model_validate({**metadata, "exemplars": exemplars})

    body = _replace_exemplars(post.content, exemplars)
    text = frontmatter.dumps(frontmatter.Post(body, **metadata))
    text = text if text.endswith("\n") else text + "\n"
    round_tripped = parse_persona(text)
    if round_tripped != definition:
        raise ValueError("rendered persona does not round-trip to the merged definition")
    return text, round_tripped


def _atomic_write_bytes(destination: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as candidate:
            candidate.write(content)
            candidate.flush()
            os.fsync(candidate.fileno())
        shutil.copymode(destination, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def save_persona(
    persona_id: str, update: PersonaUpdate, content_dir: Path | None = None
) -> PersonaDefinition:
    """Validate and save editable content for one persona."""
    path = live_path(persona_id, content_dir)
    text, definition = render_persona_file(path, persona_id, update)
    _atomic_write_bytes(path, text.encode("utf-8"))
    return definition


def restore_persona_bytes(
    persona_id: str, content: bytes, content_dir: Path | None = None
) -> None:
    """Atomically restore previously validated live persona bytes."""
    _atomic_write_bytes(live_path(persona_id, content_dir), content)


def reset_persona(persona_id: str, content_dir: Path | None = None) -> PersonaDefinition:
    """Validate and atomically restore the frozen file bytes."""
    source = default_path(persona_id, content_dir)
    if not source.is_file():
        raise FileNotFoundError(f"missing frozen default: {source}")
    destination = live_path(persona_id, content_dir)
    persona = load_persona(source)
    if persona.id != persona_id:
        raise ValueError(f"frozen default id {persona.id!r} does not match {persona_id!r}")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        shutil.copymode(destination, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return persona


def is_customized(persona_id: str, content_dir: Path | None = None) -> bool:
    """Whether live and frozen parsed persona definitions differ."""
    default = default_path(persona_id, content_dir)
    if not default.is_file():
        raise FileNotFoundError(f"missing frozen default: {default}")
    return load_persona(live_path(persona_id, content_dir)) != load_persona(default)
