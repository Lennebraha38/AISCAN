"""Uygulama ayarları."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from os import getenv
from pathlib import Path

_DEFAULT_JWT_SECRET = "dev-secret-change-me"
_DEFAULT_ANON_SALT = "pulsar-kkds-salt"

# Uretimde kesinlikle kabul edilmeyecek bilinen/zayif degerler.
_WEAK_SECRETS = {
    "",
    _DEFAULT_JWT_SECRET,
    _DEFAULT_ANON_SALT,
    "replace-with-a-long-random-secret",
    "change-me",
    "changeme",
    "secret",
    "password",
    "pulsar-kkds",
}

# Bu ortamlarda zayif varsayilanlar tolere edilir (yerel gelistirme/test).
_DEV_ENVS = {"development", "dev", "local", "test", "testing", "ci"}


def _load_dotenv() -> None:
    """Kucuk, bagimliliksiz .env yukleyici.

    Gercek ortam degiskenleri her zaman kazanir (setdefault semantigi);
    dosya yoksa sessizce gecilir.
    """
    root = Path(__file__).resolve().parents[3]
    candidates = [
        Path.cwd() / ".env",
        root / ".env",                      # repo koku
        Path(__file__).resolve().parents[2] / ".env",  # backend/
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue
        break


_load_dotenv()


def _parse_cors_origins() -> list[str]:
    raw = getenv("CORS_ORIGINS", "")
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(o) for o in parsed]
        except json.JSONDecodeError:
            # Virgulle ayrilmis basit liste de kabul edilir.
            return [o.strip() for o in raw.split(",") if o.strip()]
    # Vercel + localhost varsayimlari
    return [
        "http://localhost:3000",
        "https://pulsar-kkds.vercel.app",
        "https://pulsar-kkds-*.vercel.app",
    ]


def _env_int(name: str, default: int) -> int:
    raw = getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} sayisal bir deger olmali: {raw!r}") from exc


def _env_bool(name: str, default: bool = False) -> bool:
    raw = getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Pulsar-KKDS API"
    environment: str = getenv("PULSAR_ENV", getenv("ENV", "development")).strip().lower()
    database_url: str = getenv(
        "DATABASE_URL", "sqlite:///./pulsar-dev.db"
    )
    jwt_secret: str = getenv("JWT_SECRET", _DEFAULT_JWT_SECRET)
    jwt_algorithm: str = getenv("JWT_ALGORITHM", "HS256")
    access_token_minutes: int = _env_int(
        "ACCESS_TOKEN_MINUTES", _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    )
    refresh_token_days: int = _env_int("REFRESH_TOKEN_DAYS", 7)
    ai_core_url: str = getenv("AI_CORE_URL", "http://ai-core:8001")
    anon_salt: str = getenv("ANON_SALT", _DEFAULT_ANON_SALT)
    ecg_upload_dir: str = getenv("ECG_UPLOAD_DIR", "./data/ecg_uploads")
    # auto|on|off — pgvector kullanilip kullanilmayacagi (string; "auto" karar).
    use_pgvector: str = getenv("USE_PGVECTOR", "auto")
    pii_reject_enabled: bool = True
    # Yalnizca guvenilir bir reverse proxy arkasinda True yapin; aksi halde
    # X-Forwarded-For basligi spoof edilerek audit IP'si sahtelenebilir.
    trust_forwarded_for: bool = _env_bool("TRUST_FORWARDED_FOR", False)
    cors_origins: list[str] = field(
        default_factory=lambda: _parse_cors_origins()
    )

    @property
    def is_development(self) -> bool:
        return self.environment in _DEV_ENVS

    def getenv(self, name: str) -> str | None:
        return getenv(name)


settings = Settings()


def validate_security_settings(cfg: Settings | None = None) -> None:
    """Zayif varsayilan secret'larla uretime cikisi ENGELLER.

    Uretim (development/test disi) ortamda JWT_SECRET ve ANON_SALT zorunlu
    ve yeterince uzun olmalidir; aksi halde uygulama baslatilmaz. Boylece
    bilinen varsayilan anahtarla token imzalanmasi (dolayisiyla admin token
    taklidi) mumkun olmaz.
    """
    cfg = cfg or settings
    if cfg.is_development:
        return
    problems: list[str] = []
    if cfg.jwt_secret in _WEAK_SECRETS or len(cfg.jwt_secret) < 32:
        problems.append("JWT_SECRET (en az 32 karakter rastgele deger)")
    if cfg.anon_salt in _WEAK_SECRETS or len(cfg.anon_salt) < 16:
        problems.append("ANON_SALT (en az 16 karakter rastgele deger)")
    if problems:
        raise RuntimeError(
            "Guvenli olmayan varsayilan secret(lar) tespit edildi: "
            + ", ".join(problems)
            + ". Bunlari ortam degiskeniyle tanimlayin (PULSAR_ENV="
            + cfg.environment
            + "). Yerel gelistirme icin PULSAR_ENV=development ayarlayin."
        )
