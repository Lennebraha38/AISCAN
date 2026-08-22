"""AI Core HTTP istemcisi."""
from __future__ import annotations

import httpx

from ..core.config import settings


class AICoreError(RuntimeError):
    pass


def call_vision_analyze(image_bytes: bytes, filename: str, content_type: str,
                        modality: str) -> dict:
    try:
        resp = httpx.post(
            f"{settings.ai_core_url}/v1/vision/analyze",
            files={"image": (filename, image_bytes, content_type)},
            data={"modality": modality},
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise AICoreError(f"AI Core erişilemiyor: {exc}") from exc
    if resp.status_code != 200:
        raise AICoreError(f"AI Core hata döndürdü: {resp.status_code}")
    return resp.json()


def call_nlp_analyze(text: str) -> dict:
    try:
        resp = httpx.post(
            f"{settings.ai_core_url}/v1/nlp/analyze",
            json={"text": text},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise AICoreError(f"AI Core erişilemiyor: {exc}") from exc
    if resp.status_code != 200:
        raise AICoreError(f"AI Core hata döndürdü: {resp.status_code}")
    return resp.json()


def call_ecg_analyze(mat_b64: str) -> dict:
    """12 derivasyonlu EKG (.mat base64) analiz isteği."""
    try:
        resp = httpx.post(
            f"{settings.ai_core_url}/v1/ecg/analyze",
            json={"mat_b64": mat_b64, "fs": 500},
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise AICoreError(f"AI Core erişilemiyor: {exc}") from exc
    if resp.status_code != 200:
        raise AICoreError(f"AI Core hata döndürdü: {resp.status_code}")
    return resp.json()


def call_fusion(vision_risk: float, nlp_score: int, top_findings: list[str],
                nlp_rationale: str) -> dict:
    try:
        resp = httpx.post(
            f"{settings.ai_core_url}/v1/fusion",
            json={
                "vision_risk_score": vision_risk,
                "nlp_urgency_score": nlp_score,
                "vision_top_findings": top_findings,
                "nlp_rationale": nlp_rationale,
            },
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise AICoreError(f"AI Core erişilemiyor: {exc}") from exc
    if resp.status_code != 200:
        raise AICoreError(f"AI Core hata döndürdü: {resp.status_code}")
    return resp.json()
