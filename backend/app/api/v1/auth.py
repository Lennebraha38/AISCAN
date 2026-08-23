"""Kimlik doğrulama endpoint'leri."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...core.deps import client_ip, get_current_user, get_db
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


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        write_audit(db, user_id=None, action="LOGIN_FAILED", entity_type="user",
                    entity_id=payload.email[:32], ip=client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-posta veya şifre hatalı")
    tokens = TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
        role=user.role,
    )
    write_audit(db, user_id=user.id, action="LOGIN", entity_type="user",
                entity_id=user.id, ip=client_ip(request))
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    claims = decode_token(payload.refresh_token)
    if not claims or claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz refresh token")
    user = db.get(User, claims["sub"])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kullanıcı bulunamadı")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
        role=user.role,
    )


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
    write_audit(db, user_id=user.id, action="PASSWORD_CHANGED", entity_type="user",
                entity_id=user.id)
    return {"status": "ok"}
