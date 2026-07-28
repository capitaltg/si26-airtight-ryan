"""Every image that runs the API must install ffmpeg, because `to_pcm16`
shells out to it (see `app/voice/audio.py`) and a missing binary turns every
voice answer into an opaque 422 "Could not transcribe the recording".

This is a text check on the Dockerfiles rather than a runtime check, precisely
because the runtime check can't work: `test_voice_audio.py` skips itself when
ffmpeg isn't on PATH, so on a machine (or in a container) without ffmpeg the
whole suite still goes green. That's how the dev image shipped without it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Both images run the FastAPI app: the first serves it in deployment, the
# second is where it's run interactively during development.
_DOCKERFILES = [
    _REPO_ROOT / "server" / "Dockerfile",
    _REPO_ROOT / ".devcontainer" / "Dockerfile",
]


@pytest.mark.parametrize("dockerfile", _DOCKERFILES, ids=lambda p: str(p.name))
def test_dockerfile_installs_ffmpeg(dockerfile: Path) -> None:
    assert dockerfile.exists(), f"{dockerfile} is missing"
    assert "ffmpeg" in dockerfile.read_text(), (
        f"{dockerfile.relative_to(_REPO_ROOT)} does not install ffmpeg; "
        "voice answers will fail to decode in that image"
    )
