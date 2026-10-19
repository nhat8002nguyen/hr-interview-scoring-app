from typing import Annotated

from pydantic import field_validator
from pydantic_settings import NoDecode, SettingsConfigDict

from iam import JwtSettings


class Settings(JwtSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/talot"
    candidate_web_origin: str = "http://localhost:3001"
    cors_origins: Annotated[list[str], NoDecode] = []
    scoring_workers: int = 2
    scoring_max_attempts: int = 3
    max_answer_submissions: int = 3
    scoring_lease_timeout_seconds: int = 300
    scoring_poll_interval_seconds: float = 2.0
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    audio_storage_dir: str = "/tmp/talotrace-audio"
    seed_hr_email: str = "hr@talotrace.ai"
    seed_hr_password: str = "change-me"
    password_min_length: int = 8

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value
