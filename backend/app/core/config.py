"""Uygulama ayarları."""
from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv


@dataclass(frozen=True)
class Settings:
    app_name: str = "Pulsar-KKDS API"
    database_url: str = getenv(
        "DATABASE_URL", "sqlite:///./pulsar-dev.db"
    )
    jwt_secret: str = getenv("JWT_SECRET", "dev-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(getenv("ACCESS_TOKEN_MINUTES", "30"))
    refresh_token_days: int = int(getenv("REFRESH_TOKEN_DAYS", "7"))
    ai_core_url: str = getenv("AI_CORE_URL", "http://ai-core:8001")
    anon_salt: str = getenv("ANON_SALT", "pulsar-kkds-salt")
    use_pgvector: bool = getenv("USE_PGVECTOR", "auto")  # auto|on|off
    pii_reject_enabled: bool = True
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])


settings = Settings()
