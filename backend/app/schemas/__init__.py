"""Pydantic şemaları (API sözleşmeleri)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime


class StudyCreate(BaseModel):
    """Yalnız anonimleştirilmiş veri kabul edilir."""

    anon_study_hash: str = Field(min_length=32, max_length=64)
    modality: str = "CR"
    image_count: int = 1
    masked_epikriz: str | None = None
    anonymization_report: dict | None = None


class StudyOut(BaseModel):
    id: str
    anon_study_hash: str
    modality: str
    image_count: int
    created_at: datetime
    has_epikriz: bool


class AnalysisOut(BaseModel):
    id: str
    study_id: str
    status: str
    fusion_risk_score: float
    vision_result: dict | None
    nlp_result: dict | None
    created_at: datetime
    decided_at: datetime | None


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    note: str | None = None


class DecisionOut(BaseModel):
    id: str
    analysis_id: str
    reviewer_id: str
    decision: str
    note: str | None
    decided_at: datetime


class SimilarCaseOut(BaseModel):
    analysis_id: str
    fusion_risk_score: float
    status: str
    similarity: float


class AuditLogOut(BaseModel):
    id: str
    user_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    data_hash: str | None
    ip: str | None
    created_at: datetime
