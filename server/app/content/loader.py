"""Load and validate the authored POC content at startup.

Content is version-tagged and file-based (anti-drift guardrail #1): a PWS, a
synthetic written proposal, three evaluator personas, an eight-concern bank, and a
scoring rubric. Everything is validated into the schemas in
``app.schemas.content`` here, so a malformed file fails loud at startup rather than
silently degrading a later prompt.

Persona exemplar convention
----------------------------
Each ``personas/*.md`` file carries the scalar and list ``PersonaDefinition`` fields
in its YAML frontmatter. The hand-graded exemplars live in the markdown body inside a
single fenced ``yaml`` block whose one top-level key is ``exemplars``. The loader
extracts that block, parses it, and merges the list into the frontmatter before
validation. Keep this shape uniform across all three persona files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from app.config import settings
from app.schemas.content import Concern, PersonaDefinition, Rubric

# Matches the single ```yaml ... ``` fenced block in a persona body.
_YAML_FENCE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class Content:
    """The validated authored-content bundle stashed on ``app.state.content``."""

    rfp_text: str
    proposal_text: str
    personas: dict[str, PersonaDefinition]
    concerns: dict[str, Concern]
    rubric: Rubric


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"missing content file: {path}")
    return path.read_text(encoding="utf-8")


def _parse_exemplars(body: str) -> list[dict[str, Any]]:
    match = _YAML_FENCE.search(body)
    if match is None:
        return []
    block = yaml.safe_load(match.group(1)) or {}
    return list(block.get("exemplars", []))


def _load_persona(path: Path) -> PersonaDefinition:
    post = frontmatter.load(path)
    data: dict[str, Any] = dict(post.metadata)
    data["exemplars"] = _parse_exemplars(post.content)
    return PersonaDefinition.model_validate(data)


def _load_personas(personas_dir: Path) -> dict[str, PersonaDefinition]:
    if not personas_dir.is_dir():
        raise FileNotFoundError(f"missing personas directory: {personas_dir}")
    personas = [_load_persona(p) for p in sorted(personas_dir.glob("*.md"))]
    return {persona.id: persona for persona in personas}


def _load_concerns(path: Path) -> dict[str, Concern]:
    raw = yaml.safe_load(_read_text(path)) or []
    concerns = [Concern.model_validate(item) for item in raw]
    return {concern.concern_id: concern for concern in concerns}


def _load_rubric(path: Path) -> Rubric:
    return Rubric.model_validate(yaml.safe_load(_read_text(path)))


def load_content(content_dir: Path = settings.content_dir) -> Content:
    """Load, validate, and return the authored content bundle.

    Any missing file, parse error, or ``pydantic.ValidationError`` propagates so the
    app fails fast at startup instead of running on partial content.
    """
    return Content(
        rfp_text=_read_text(content_dir / "rfp_pws.md"),
        proposal_text=_read_text(content_dir / "written_proposal.md"),
        personas=_load_personas(content_dir / "personas"),
        concerns=_load_concerns(content_dir / "concerns.yaml"),
        rubric=_load_rubric(content_dir / "rubric.yaml"),
    )
