from pathlib import Path

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


settings = Settings()
