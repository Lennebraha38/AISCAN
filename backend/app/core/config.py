"""Uygulama ayarları."""
from __future__ import annotations

import json

from dataclasses import dataclass, field
from os import getenv


def _parse_cors_origins() -> list[str]:
    raw = getenv("CORS_ORIGINS", "")
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(o) for o in parsed]
        except json.JSONDecodeError:
            pass
    return ["http://localhost:3000"]


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
    ecg_upload_dir: str = getenv("ECG_UPLOAD_DIR", "./data/ecg_uploads")
    use_pgvector: bool = getenv("USE_PGVECTOR", "auto")  # auto|on|off
    pii_reject_enabled: bool = True
    cors_origins: list[str] = field(
        default_factory=lambda: _parse_cors_origins()
    )


settings = Settings()
