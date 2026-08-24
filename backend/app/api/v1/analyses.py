"""Analiz ve hekim onay endpoint'leri (MDR human-in-the-loop)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ...core.deps import DECISION_ROLES, client_ip, get_current_user, get_db
from ...models import Analysis, ReviewDecision, Study, User
from ...schemas import AnalysisOut, DecisionOut, DecisionRequest
from ...services.audit import write_audit
from ...services.embeddings import similar_cases
from ...services.report_pdf import render_report

router = APIRouter(prefix="/v1/analyses", tags=["analyses"])


def _strip_cams(vision: dict | None) -> dict | None:
    """Base64 CAM görüntülerini yanıttan çıkarır (payload ~1.8MB → KB'lar)."""
    if not vision:
        return vision
    out = {**vision, "base_image_b64": None}
    out["findings"] = [
        {**f, "cam_image_b64": None} if isinstance(f, dict) else f
        for f in out.get("findings", [])
    ]
    return out


def _analysis_out(a: Analysis) -> AnalysisOut:
    return AnalysisOut(
        id=a.id,
        study_id=a.study_id,
        status=a.status,
        fusion_risk_score=a.fusion_risk_score,
        vision_result=_strip_cams(a.vision_result),
        nlp_result=a.nlp_result,
        ecg_result=a.ecg_result,
        created_at=a.created_at,
        decided_at=a.decided_at,
    )


@router.get("")
def list_analyses(status_filter: str | None = None,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    """Hafif liste projeksiyonu — ağır analiz kolonları (vision/nlp/ecg)
    dökülmez; aksi halde her satır MB'larca base64 taşır.
    Panelde okunabilirlik için modalite ve baskın bulgu etiketi eklenir."""
    q = db.query(Analysis).order_by(Analysis.created_at.desc())
    if status_filter:
        q = q.filter(Analysis.status == status_filter)
    studies = {s.id: s for s in db.query(Study).all()}
    rows = []
    for a in q.limit(100):
        top = None
        vr = a.vision_result or {}
        fnds = [f for f in (vr.get("findings") or []) if isinstance(f, dict)]
        if fnds:
            best = max(fnds, key=lambda f: (f.get("probability") or 0))
            if (best.get("probability") or 0) >= 0.30:
                top = best.get("label")
        er = a.ecg_result or {}
        ecg_label = er.get("superclass") if isinstance(er, dict) else None
        study = studies.get(a.study_id)
        rows.append({
            "id": a.id,
            "study_id": a.study_id,
            "status": a.status,
            "fusion_risk_score": a.fusion_risk_score,
            "created_at": a.created_at.isoformat(),
            "modality": study.modality if study else None,
            "top_finding": top or (f"EKG · {ecg_label}" if ecg_label else None),
        })
    return rows


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str,
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    analysis = db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(404, "Analiz bulunamadı")
    out = _analysis_out(analysis).model_dump()
    out["decisions"] = [
        {
            "decision": d.decision,
            "note": d.note,
            "decided_at": d.decided_at.isoformat(),
            "reviewer_id": d.reviewer_id,
        }
        for d in analysis.decisions
    ]
    return out


@router.get("/{analysis_id}/report.pdf")
def report_pdf(analysis_id: str,
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> Response:
    """Kesinleşmiş analizin resmi PDF raporu (hekim/radyolog/admin).

    Rapor; doğrulama kodu, bulgular, fuzyon riski ve hekim kararını içerir.
    """
    if user.role not in DECISION_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Rapor indirme yetkisi hekim/radyolog/admin'e aittir")
    analysis = db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(404, "Analiz bulunamadı")
    if analysis.status not in ("APPROVED", "REJECTED"):
        raise HTTPException(409, "Analiz henüz kesinleşmedi (hekim kararı bekleniyor)")
    study = db.get(Study, analysis.study_id)
    out = _analysis_out(analysis).model_dump()
    out["decisions"] = [
        {
            "decision": d.decision,
            "note": d.note,
            "decided_at": d.decided_at,
            "reviewer_id": d.reviewer_id,
        }
        for d in analysis.decisions
    ]
    pdf = render_report(out, {
        "anon_study_hash": study.anon_study_hash if study else "-",
        "modality": study.modality if study else "-",
        "created_at": study.created_at if study else None,
    })
    write_audit(db, user_id=user.id, action="REPORT_DOWNLOADED",
                entity_type="analysis", entity_id=analysis.id)
    fname = f"pulsar-rapor-{analysis.id[:8]}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{analysis_id}/cam")
def get_cam(analysis_id: str,
            finding: str | None = None,
            clean: bool = False,
            user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    """CAM overlay'i ayrı ve tek istekle döner (lazy-load).

    ?finding=<label>  → o bulgunun kendi ısı haritası (yoksa ilk mevcut)
    ?clean=true       → bindirmesiz temel görüntü
    """
    analysis = db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(404, "Analiz bulunamadı")
    if not analysis.vision_result:
        # EKG vb. görüntüsüz analiz: ön yüz boş görselle sessizce geçer.
        return {"label": None, "cam_image_b64": "", "empty": True}
    vision = analysis.vision_result

    if clean:
        base_b64 = vision.get("base_image_b64")
        if not base_b64:
            raise HTTPException(404, "Temiz görüntü kayıtlı değil")
        return {
            "label": None,
            "cam_image_b64": base_b64,
            "xai_method": vision.get("xai_method"),
            "empty": False,
        }

    fallback: dict | None = None
    for f in vision.get("findings", []):
        if not isinstance(f, dict) or not f.get("cam_image_b64"):
            continue
        if finding is None or f.get("label") == finding:
            return {
                "label": f.get("label"),
                "cam_image_b64": f["cam_image_b64"],
                "xai_method": vision.get("xai_method"),
                "empty": bool(f.get("cam_empty", False)),
            }
        if fallback is None:
            fallback = f
    if finding is not None and fallback is not None:
        return {
            "label": fallback.get("label"),
            "cam_image_b64": fallback["cam_image_b64"],
            "xai_method": vision.get("xai_method"),
            "requested_label": finding,
            "empty": bool(fallback.get("cam_empty", False)),
        }
    raise HTTPException(404, "Bu analiz için CAM üretilmemiş")


@router.post("/{analysis_id}/decision", response_model=DecisionOut)
def decide(analysis_id: str,
           payload: DecisionRequest,
           request: Request,
           user: User = Depends(get_current_user),
           db: Session = Depends(get_db)) -> DecisionOut:
    """MDR kuralı: yalnız hekim/radyolog nihai karar verebilir; karar
    append-only log'a yazılır ve analiz kesinleşir."""
    if user.role not in DECISION_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Nihai karar yalnız hekim veya radyolog tarafından verilebilir",
        )
    analysis = db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(404, "Analiz bulunamadı")
    if analysis.status != "PENDING_REVIEW":
        raise HTTPException(409, f"Analiz zaten kesinleşmiş: {analysis.status}")

    decision = ReviewDecision(
        analysis_id=analysis.id,
        reviewer_id=user.id,
        decision=payload.decision,
        note=payload.note,
    )
    analysis.status = payload.decision
    analysis.decided_at = datetime.now(timezone.utc)
    db.add(decision)
    db.flush()
    write_audit(db, user_id=user.id, action=f"DECISION_{payload.decision}",
                entity_type="analysis", entity_id=analysis.id, ip=client_ip(request))
    return DecisionOut(
        id=decision.id,
        analysis_id=decision.analysis_id,
        reviewer_id=decision.reviewer_id,
        decision=decision.decision,
        note=decision.note,
        decided_at=decision.decided_at,
    )


@router.get("/{analysis_id}/similar")
def similar(analysis_id: str,
            user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> list[dict]:
    return similar_cases(db, analysis_id)


@router.get("/{analysis_id}/signal")
def get_signal(analysis_id: str,
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    """Saklanan EKG sinyalini viewer icin JSON olarak dondurur.

    Sinyal, kayit bazli z-skor on islemesinden HAM haliyle degil,
    goruntulemeye uygun normalize edilmis sekilde akitilir.
    """
    from ...core.config import settings

    analysis = db.get(Analysis, analysis_id)
    if not analysis or not analysis.ecg_result:
        raise HTTPException(404, "EKG analizi bulunamadı")
    fname = (analysis.ecg_result or {}).get("_file")
    if not fname:
        raise HTTPException(404, "Bu analiz için saklanmış sinyal yok")
    # path traversal korumasi: yalnizca guvenli dosya adi kabul
    safe = Path(fname).name
    fpath = Path(settings.ecg_upload_dir) / safe
    if not fpath.exists():
        raise HTTPException(410, "Sinyal dosyasi bulunamadi")

    from io import BytesIO

    from scipy.io import loadmat

    m = loadmat(BytesIO(fpath.read_bytes()))
    val = m["val"]
    leads = ["I", "II", "III", "aVR", "aVL", "aVF",
             "V1", "V2", "V3", "V4", "V5", "V6"]
    n = min(val.shape[-1], 5000)
    step = max(1, n // 2500)
    sig = [[round(float(v), 3) for v in row[:n:step]] for row in val[:12]]
    return {
        "analysis_id": analysis_id,
        "leads": leads,
        "fs_effective": 500 // step,
        "samples": len(sig[0]),
        "signal": sig,
    }
