from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Model is pinned and config-driven. Sonnet 4.5 because it still accepts
    # temperature=0 and is the FedRAMP-High-authorized model in GovCloud.
    # Do NOT swap to a 4.6+/5 model without removing every temperature=0.
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    aws_region: str = "us-east-1"
    database_url: str = "postgresql+psycopg://airtight:airtight@localhost:5432/airtight"
    content_dir: Path = Path(__file__).parent / "content" / "store"

    # Voice settings (Transcribe and Polly) — reuse aws_region above
    transcribe_language_code: str = "en-US"
    transcribe_sample_rate: int = 16000
    polly_engine: str = "neural"
    max_answer_audio_bytes: int = 10 * 1024 * 1024

    text_answer_warning_words: int = 225
    text_answer_limit_words: int = 300
    voice_answer_warning_seconds: float = 45
    voice_answer_limit_seconds: float = 60

    # History retention. `POST /sessions` prunes: it keeps the `history_keep`
    # newest archived sessions and deletes any non-archived session older than
    # the TTL. The TTL is what clears abandoned false starts and their audio
    # blobs; it is time-based rather than "delete other active sessions" so that
    # concurrent e2e runs never delete each other's live session.
    history_keep: int = 5
    abandoned_session_ttl_hours: int = 24

    @model_validator(mode="after")
    def _validate_tangent_limits(self) -> "Settings":
        pairs = (
            (
                "text_answer_warning_words",
                self.text_answer_warning_words,
                "text_answer_limit_words",
                self.text_answer_limit_words,
            ),
            (
                "voice_answer_warning_seconds",
                self.voice_answer_warning_seconds,
                "voice_answer_limit_seconds",
                self.voice_answer_limit_seconds,
            ),
        )
        for warning_name, warning, limit_name, limit in pairs:
            if warning <= 0 or limit <= 0:
                raise ValueError(f"{warning_name} and {limit_name} must be positive")
            if warning >= limit:
                raise ValueError(f"{warning_name} must be less than {limit_name}")
        return self


settings = Settings()
