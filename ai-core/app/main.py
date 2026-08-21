"""Pulsar-KKDS AI Core — inference ve açıklanabilirlik servisi.

MDR notu: Bu servis yalnızca karar destek çıktısı üretir; nihai klinik
karar hekim onayına (human-in-the-loop) tabidir.
"""
from __future__ import annotations

import base64

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .nlp import analyze_epikriz
from .schemas import (
    FusionRequest,
    FusionResponse,
    HealthResponse,
    NlpResponse,
    TokenAttributionOut,
    VisionResponse,
    FindingOut,
)
from .vision import FINDING_LABELS, analyze_image, produce_cam_overlay

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "application/dicom", "application/octet-stream"}

app = FastAPI(title="Pulsar-KKDS AI Core", version="0.2.0")

# Lazy singleton model yuvası (torch checkpoint varsa doldurulur).
_MODEL_HOLDER: dict = {"model": None, "target_layers": None}


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="ai-core",
        models="loaded" if _MODEL_HOLDER["model"] else "heuristic-engine",
        xai_backend="grad-cam" if _MODEL_HOLDER["model"] else "energy-saliency",
    )


def _validate_upload(file: UploadFile, data: bytes) -> None:
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Görüntü 10MB sınırını aşıyor")
    if file.content_type and file.content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"Desteklenmeyen içerik tipi: {file.content_type}")


@app.post("/v1/vision/analyze", response_model=VisionResponse, tags=["vision"])
async def vision_analyze(
    image: UploadFile = File(...),
    modality: str = Form("CR"),
) -> VisionResponse:
    data = await image.read()
    _validate_upload(image, data)

    result = analyze_image(data, modality=modality)
    cam_b64, _heat = produce_cam_overlay(data, model=_MODEL_HOLDER["model"],
                                         target_layers=_MODEL_HOLDER["target_layers"])

    findings = [
        FindingOut(
            label=label,
            probability=result["probabilities"].get(label, 0.0),
            cam_image_b64=cam_b64,
            top_regions=result["top_regions"],
        )
        for label in FINDING_LABELS
    ]
    return VisionResponse(
        findings=findings,
        risk_score=result["risk_score"],
        features=result["features"],
        xai_method="grad-cam" if _MODEL_HOLDER["model"] else "energy-saliency+grid-attribution",
    )


@app.post("/v1/nlp/analyze", response_model=NlpResponse, tags=["nlp"])
async def nlp_analyze(payload: dict) -> NlpResponse:
    text = (payload or {}).get("text", "")
    if not text:
        raise HTTPException(400, "'text' alanı zorunlu")
    if len(text) > 20000:
        raise HTTPException(413, "Metin 20.000 karakteri aşıyor")
    result = analyze_epikriz(text)
    return NlpResponse(
        urgency=result["urgency"],
        urgency_score=result["urgency_score"],
        confidence=result["confidence"],
        highlighted_tokens=[TokenAttributionOut(**t) for t in result["highlighted_tokens"]],
        rationale=result["rationale"],
    )


@app.post("/v1/fusion", response_model=FusionResponse, tags=["fusion"])
async def fusion(payload: FusionRequest) -> FusionResponse:
    """Görsel + metin skorlarını birleştirir (ağırlıklı füzyon + gerekçe)."""
    w_vision, w_nlp = 0.6, 0.4
    fused = round(w_vision * payload.vision_risk_score + w_nlp * payload.nlp_urgency_score, 1)
    urgency = "düşük" if fused < 35 else ("orta" if fused < 65 else "yüksek")

    parts = []
    if payload.vision_top_findings:
        parts.append("Görüntüde öne çıkan bulgular: " + ", ".join(payload.vision_top_findings[:3]))
    if payload.nlp_rationale:
        parts.append(f"Epikriz: {payload.nlp_rationale}")
    parts.append(f"Füzyon skoru: görüntü %{w_vision*100:.0f} + epikriz %{w_nlp*100:.0f} ağırlıkla hesaplandı.")

    return FusionResponse(
        fused_risk_score=fused,
        urgency=urgency,
        rationale=" | ".join(parts),
        weights={"vision": w_vision, "nlp": w_nlp},
    )
