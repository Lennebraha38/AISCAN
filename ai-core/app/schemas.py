"""AI Core Pydantic şemaları."""
from __future__ import annotations

from pydantic import BaseModel, Field


class FindingOut(BaseModel):
    label: str
    probability: float
    cam_image_b64: str | None = None
    top_regions: list[dict] = Field(default_factory=list)


class VisionResponse(BaseModel):
    findings: list[FindingOut]
    risk_score: float
    features: dict = Field(default_factory=dict)
    xai_method: str


class TokenAttributionOut(BaseModel):
    text: str
    start: int
    end: int
    score: float
    negated: bool


class NlpResponse(BaseModel):
    urgency: str
    urgency_score: int
    confidence: float
    highlighted_tokens: list[TokenAttributionOut]
    rationale: str


class FusionRequest(BaseModel):
    vision_risk_score: float = Field(ge=0, le=100)
    nlp_urgency_score: int = Field(ge=0, le=100)
    vision_top_findings: list[str] = Field(default_factory=list)
    nlp_rationale: str = ""


class FusionResponse(BaseModel):
    fused_risk_score: float
    urgency: str
    rationale: str
    weights: dict[str, float]


class HealthResponse(BaseModel):
    status: str
    service: str
    models: str
    xai_backend: str
