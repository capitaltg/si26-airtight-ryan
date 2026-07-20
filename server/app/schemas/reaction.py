"""Per-turn model output — the persona's reply, generated AFTER the number is
locked (spec §5). It describes the already-computed score; it never sets it.
"""

from pydantic import BaseModel


class PersonaReaction(BaseModel):
    in_character_reply: str
    rationale: str
