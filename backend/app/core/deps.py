"""Ortak FastAPI dependency'leri: DB oturumu, kimlik, rol kontrolü."""
from __future__ import annotations

from typing import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..models import User
from .config import settings
from .security import decode_token

ROLES = ("admin", "hekim", "radyolog", "asistan")
# MDR human-in-the-loop: yalnız hekim/radyolog nihai karar verebilir.
DECISION_ROLES = ("hekim", "radyolog")
# İnceleme/rapor için tüm kayıtlara erişebilen roller.
BROAD_ACCESS_ROLES = ("admin", "hekim", "radyolog")


def get_db(request: Request) -> Generator[Session, None, None]:
    session: Session = request.app.state.SessionLocal()
    try:
        yield session
        session.commit()
    except HTTPException:
        # Denetim kayıtları (LOGIN_FAILED, PII_REJECTED) HTTPException ile
        # birlikte atılır; bunları geri almak yerine commit ederek KORU
        # (KVKK md.12 append-only denetim). Bu yollarda başka yarım yazma yok.
        session.commit()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kimlik başlığı eksik")
    payload = decode_token(auth.removeprefix("Bearer ").strip())
    if not payload or payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz veya süresi dolmuş token")
    user = db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kullanıcı bulunamadı")
    # Şifre değiştiyse eski token'lar (eski token_version) geçersizdir.
    if int(payload.get("tv", 0)) != int(getattr(user, "token_version", 0) or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum geçersiz kılınmış")
    return user


def require_role(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Bu işlem için gerekli rol: {' veya '.join(roles)}",
            )
        return user

    return checker


def can_access_study(user: User, study) -> bool:
    """Nesne düzeyinde yetki (IDOR koruması).

    admin/hekim/radyolog inceleme amacıyla tüm kayıtlara erişebilir;
    asistan yalnızca kendi oluşturduğu çalışmaları görebilir.
    """
    if user.role in BROAD_ACCESS_ROLES:
        return True
    return study is not None and study.created_by_id == user.id


def client_ip(request: Request) -> str | None:
    """İstemci IP'si.

    X-Forwarded-For yalnızca güvenilir proxy arkasında (TRUST_FORWARDED_FOR=1)
    dikkate alınır; aksi halde başlık spoof edilerek audit IP'si sahtelenebilir.
    """
    if settings.trust_forwarded_for:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            first = fwd.split(",")[0].strip()
            if first:
                return first[:64]
    return request.client.host if request.client else None
