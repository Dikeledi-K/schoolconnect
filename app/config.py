"""Application settings, read from environment variables / the .env file.

pydantic-settings matches field names to env vars case-insensitively,
so `database_url` is filled from DATABASE_URL.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database: SQLite locally, Supabase Postgres in production.
    database_url: str = "sqlite:///./schoolconnect.db"

    # AI provider: "rules" (offline, default) | "anthropic" | "gemini"
    llm_provider: str = "rules"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = 15.0

    # If set, write endpoints require the header X-API-Key with this value.
    api_key: str = ""

    # Required to call /jobs/* endpoints (header X-Jobs-Token). Jobs are disabled if empty.
    jobs_token: str = ""

    # Week 6 (POPIA): resolved tickets older than this many days are anonymised by the retention job.
    retention_days: int = 365

    # Week 7: staff passwords (PBKDF2-SHA256). 600 000 follows current OWASP advice;
    # tests use a low value so they stay fast. The count is stored in each hash, so
    # changing it later does not break existing passwords.
    password_hash_iterations: int = 600_000

    # Week 7: notifications. "dry_run" (default) only writes to the outbox table;
    # "smtp" really sends email. SMS / WhatsApp are not supported yet.
    notify_mode: str = "dry_run"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Week 7: shared secret for signed inbound webhooks (email forwarder / WhatsApp gateway).
    # Empty = POST /integrations/inbound-message is disabled.
    inbound_secret: str = ""

    # Comma-separated allowed origins for CORS.
    cors_origins: str = "http://localhost:8501"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so .env is read once. Tests call get_settings.cache_clear() to reload."""
    return Settings()
