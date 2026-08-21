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


def get_db(request: Request) -> Generator[Session, None, None]:
    session: Session = request.app.state.SessionLocal()
    try:
        yield session
        session.commit()
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


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
