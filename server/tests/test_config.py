import pytest
from pydantic import ValidationError

from app.config import Settings


def test_tangent_limit_defaults() -> None:
    settings = Settings()
    assert (settings.text_answer_warning_words, settings.text_answer_limit_words) == (225, 300)
    assert (settings.voice_answer_warning_seconds, settings.voice_answer_limit_seconds) == (90, 120)


@pytest.mark.parametrize(
    "values",
    [
        {"text_answer_warning_words": 0},
        {"text_answer_limit_words": -1},
        {"voice_answer_warning_seconds": 0},
        {"voice_answer_limit_seconds": -1},
        {"text_answer_warning_words": 300, "text_answer_limit_words": 300},
        {"voice_answer_warning_seconds": 120, "voice_answer_limit_seconds": 90},
    ],
)
def test_tangent_limits_must_be_positive_and_ordered(values: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        Settings(**values)
