"""Application settings, read from environment variables / the .env file.

pydantic-settings matches field names to env vars case-insensitively,
so `database_url` is filled from DATABASE_URL.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Week 8: "development" (default) or "production". In production the app refuses to start
    # without the secrets that protect it (see check_production_settings below).
    environment: str = "development"

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

    # Week 8: forecast dates that are pre-computed and stored by the nightly job, besides today,
    # so the panel demo (the January 2026 backtest) never computes live on Render's 0.1 CPU.
    forecast_pinned_dates: str = "2025-12-15"

    # Comma-separated allowed origins for CORS.
    cors_origins: str = "http://localhost:8501"

    @property
    def pinned_forecast_dates(self) -> list[str]:
        return [d.strip() for d in self.forecast_pinned_dates.split(",") if d.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


PRODUCTION_MIN_PASSWORD_ITERATIONS = 600_000


def check_production_settings(settings: Settings) -> None:
    """Week 8: fail fast instead of running a public server with the doors open.

    In production an empty API_KEY would let anyone create tickets from scripts, and an empty
    JOBS_TOKEN would switch the scheduled jobs off. Weak password hashing is refused too.
    """
    if settings.environment != "production":
        return
    problems = []
    if not settings.api_key:
        problems.append("API_KEY is empty")
    if not settings.jobs_token:
        problems.append("JOBS_TOKEN is empty")
    if settings.password_hash_iterations < PRODUCTION_MIN_PASSWORD_ITERATIONS:
        problems.append(f"PASSWORD_HASH_ITERATIONS is below {PRODUCTION_MIN_PASSWORD_ITERATIONS}")
    if settings.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL is SQLite (Render's disk is wiped on every restart)")
    if problems:
        raise RuntimeError("Refusing to start with ENVIRONMENT=production: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    """Cached so .env is read once. Tests call get_settings.cache_clear() to reload."""
    return Settings()
