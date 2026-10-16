"""Kimlik doğrulama endpoint'leri."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.deps import client_ip, get_current_user, get_db
from ...core.ratelimit import rate_limit
from ...core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from ...models import User
from ...schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
    UserCreateRequest,
    UserOut,
)
from ...services.audit import write_audit

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# Refresh token yalnizca bu HttpOnly cerezde tasinir; govdede/JS'te tutulmaz.
REFRESH_COOKIE = "pulsar_refresh"
REFRESH_COOKIE_PATH = "/v1/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Refresh token'i HttpOnly + Secure + SameSite cerez olarak yazar."""
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_token_days * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response,
          db: Session = Depends(get_db)) -> TokenResponse:
    # Brute-force koruması (IP başına dakikada 30 deneme).
    rate_limit(request, "login", 30, 60)
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        write_audit(db, user_id=None, action="LOGIN_FAILED", entity_type="user",
                    entity_id=payload.email[:32], ip=client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-posta veya şifre hatalı")
    _set_refresh_cookie(response, create_refresh_token(user.id, user.role, user.token_version))
    write_audit(db, user_id=user.id, action="LOGIN", entity_type="user",
                entity_id=user.id, ip=client_ip(request))
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.token_version),
        role=user.role,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response,
            payload: RefreshRequest | None = None,
            db: Session = Depends(get_db)) -> TokenResponse:
    """Erişim token'ını yeniler.

    Refresh token birincil olarak `pulsar_refresh` HttpOnly çerezinden okunur;
    geriye dönük uyumluluk için gövdeden de kabul edilir. Her yenilemede token
    döndürülür (rotation): yeni refresh token yine çereze yazılır.
    """
    token = request.cookies.get(REFRESH_COOKIE) or (payload.refresh_token if payload else None)
    claims = decode_token(token) if token else None
    if not claims or claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz refresh token")
    user = db.get(User, claims["sub"])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kullanıcı bulunamadı")
    if int(claims.get("tv", 0)) != int(getattr(user, "token_version", 0) or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token geçersiz kılınmış")
    _set_refresh_cookie(response, create_refresh_token(user.id, user.role, user.token_version))
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.token_version),
        role=user.role,
    )


@router.post("/logout", status_code=200)
def logout(response: Response) -> dict:
    """Refresh çerezini temizler (istemci tarafı token'ı da silmelidir)."""
    _clear_refresh_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, role=user.role, created_at=user.created_at)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreateRequest,
                admin: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> UserOut:
    """Yeni kullanıcı açma. Şifre yalnız istek gövdesinde taşınır (URL/log'a düşmez)."""
    if admin.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Yalnız admin kullanıcı açabilir")
    role = payload.role.lower().strip()
    if role not in ("admin", "hekim", "radyolog", "asistan"):
        raise HTTPException(422, "Geçersiz rol")
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "Bu e-posta kayıtlı")
    if len(payload.password) < 8:
        raise HTTPException(422, "Şifre en az 8 karakter olmalı")
    user = User(email=email, password_hash=hash_password(payload.password), role=role)
    db.add(user)
    db.flush()
    write_audit(db, user_id=admin.id, action="USER_CREATED", entity_type="user",
                entity_id=user.id)
    return UserOut(id=user.id, email=user.email, role=user.role, created_at=user.created_at)


@router.post("/password", status_code=200)
def change_password(payload: PasswordChangeRequest,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    """Kullanıcının kendi şifresini değiştirmesi (eski şifre doğrulanır)."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Mevcut şifre hatalı")
    if len(payload.new_password) < 8:
        raise HTTPException(422, "Yeni şifre en az 8 karakter olmalı")
    user.password_hash = hash_password(payload.new_password)
    # Eski access/refresh token'ları geçersiz kıl.
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    write_audit(db, user_id=user.id, action="PASSWORD_CHANGED", entity_type="user",
                entity_id=user.id)
    return {"status": "ok"}
