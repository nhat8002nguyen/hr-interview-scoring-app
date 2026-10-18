from pydantic_settings import SettingsConfigDict

from iam import JwtSettings


class Settings(JwtSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@api-db:5432/talotrace"
    candidate_web_origin: str = "http://localhost:3001"
    cors_origins: list[str] = []
    scoring_workers: int = 2
    scoring_max_attempts: int = 3
    scoring_lease_timeout_seconds: int = 300
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    audio_storage_dir: str = "/tmp/talotrace-audio"
    seed_hr_email: str = "hr@talotrace.ai"
    seed_hr_password: str = "change-me"
