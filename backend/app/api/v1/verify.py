"""Rapor dogrulama ucunun kamuya acik sorgusu (kimlik gerektirmez).

QR icindeki kod tasyan herkes raporun gercekte sisteme kesinlesip
kesinlesmedigini ogrenebilir; kod yuksek entropilidir ve baska veri
sizdirir. KVKK acisindan kisisel veri icermez.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...core.deps import get_db
from ...core.ratelimit import rate_limit
from ...models import Analysis
from ...services.report_pdf import verification_code

router = APIRouter(prefix="/v1/verify", tags=["system"])


@router.get("/{code}")
def verify(code: str, request: Request, db: Session = Depends(get_db)) -> dict:
    # Kimlik gerektirmeyen uç: tüm tabloyu tarayabildiği için hız sınırlanır
    # (kaynak tüketimi / numaralandırma saldırısını azaltır).
    rate_limit(request, "verify", 60, 60)
    code = (code or "").strip().upper().removeprefix("PULSAR-KKDS:")
    if len(code) != 16:
        return {"valid": False, "reason": "kod biçimi hatalı"}
    for a in db.query(Analysis).filter(
        Analysis.status.in_(("APPROVED", "REJECTED"))
    ):
        if not a.decided_at:
            continue
        if verification_code(a.id, a.decided_at) == code:
            return {
                "valid": True,
                "analysis_id": a.id,
                "status": a.status,
                "decided_at": a.decided_at.isoformat(),
                "fusion_risk_score": a.fusion_risk_score,
            }
    return {"valid": False, "reason": "bu kodla kesinleşmiş rapor bulunamadı"}
