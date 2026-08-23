"""Pulsar-KKDS AI Core — inference ve açıklanabilirlik servisi.

MDR notu: Bu servis yalnızca karar destek çıktısı üretir; nihai klinik
karar hekim onayına (human-in-the-loop) tabidir.
"""
from __future__ import annotations

import base64

import numpy as np
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
    EcgAnalyzeRequest,
    EcgAnalyzeResponse,
)
from .vision import FINDING_LABELS, analyze_image
from .vision.cam import render_base_image, render_finding_overlay
from .ecg.inference import get_analyzer

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
        models=f"ecg:{get_analyzer().backend} + vision:"
        + ("loaded" if _MODEL_HOLDER["model"] else "heuristic-engine"),
        xai_backend="grad-cam" if _MODEL_HOLDER["model"] or get_analyzer().model is not None
        else "energy-saliency",
    )


@app.post("/v1/ecg/analyze", response_model=EcgAnalyzeResponse, tags=["ecg"])
async def ecg_analyze(payload: EcgAnalyzeRequest) -> EcgAnalyzeResponse:
    """12 derivasyonlu EKG analizi: ust sinif + guven + XAI haritalari.

    Girdi: base64 .mat dosyasi veya dogrudan 12xN sinyal matrisi.
    Cikti, hekim onayi icin viewer'a tasinir; tek basina tanı DEGILDIR.
    """
    analyzer = get_analyzer()
    if payload.mat_b64:
        try:
            signal, fs = analyzer.decode_mat(payload.mat_b64)
        except Exception as exc:
            raise HTTPException(422, f".mat cozumleme hatasi: {exc}") from exc
    elif payload.signal:
        try:
            signal = np.asarray(payload.signal, dtype=np.float64)
        except ValueError as exc:
            raise HTTPException(422, "sinyal matrisi okunamadi") from exc
        if signal.ndim != 2 or signal.shape[0] != 12:
            raise HTTPException(422, "12 derivasyon bekleniyor (ilk boyut=12)")
        if signal.size > 12 * 50000:
            raise HTTPException(413, "sinyal cok buyuk (max 12x50000)")
        fs = int(payload.fs)
    else:
        raise HTTPException(400, "'mat_b64' veya 'signal' alanlarindan biri zorunlu")

    result = analyzer.analyze_signal(signal, fs)
    return EcgAnalyzeResponse(
        superclass=result["superclass"],
        superclass_index=result["superclass_index"],
        confidence=result["confidence"],
        probabilities=result["probabilities"],
        grad_cam=result["grad_cam"],
        lead_saliency=result["lead_saliency"],
        heart_rate_bpm=result.get("heart_rate_bpm"),
        backend=result["backend"],
        xai_method=result["xai_method"],
        rationale=result.get("rationale", ""),
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

    # Her bulgu KENDI mekânsal imzasindan uretilmis ayri overlay tasiyor;
    # backend bunlari DB'de saklar, API yanitlarindan soyar ve /cam ile
    # tek tek lazy-load eder. Ayrica 'temiz goruntu' icin taban PNG doner.
    findings = []
    for label in FINDING_LABELS:
        p = result["probabilities"].get(label, 0.0)
        cam_b64, cam_empty = render_finding_overlay(data, label, modality=modality, probability=p)
        findings.append(
            FindingOut(
                label=label,
                probability=p,
                cam_image_b64=cam_b64,
                cam_empty=cam_empty,
                top_regions=result["top_regions"],
            )
        )
    return VisionResponse(
        findings=findings,
        risk_score=result["risk_score"],
        features=result["features"],
        xai_method="grad-cam" if _MODEL_HOLDER["model"] else "finding-saliency (bulgu-bazlı)",
        base_image_b64=render_base_image(data, modality=modality),
        modality=modality,
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
