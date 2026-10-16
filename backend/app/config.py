from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings read from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env")

    database_url: str = "postgresql://tank:tank@localhost:5432/tankdb"
    chunk_words: int = 180     # target words per chunk
    chunk_overlap: int = 30    # words repeated between neighbouring chunks


settings = Settings()
