"""Çalışma (study) endpoint'leri — yalnız anonim veri kabul edilir."""
from __future__ import annotations

import base64
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from ...core.deps import client_ip, get_current_user, get_db
from ...models import Analysis, Study, User
from ...schemas import StudyCreate, StudyOut
from ...services.ai_client import AICoreError, call_ecg_analyze, call_fusion, call_nlp_analyze, call_vision_analyze
from ...services.audit import write_audit
from ...services.embeddings import store_embedding
from ...services.pii_guard import scan_pii

MAX_ECG_BYTES = 5 * 1024 * 1024

router = APIRouter(prefix="/v1/studies", tags=["studies"])


def _study_out(s: Study) -> StudyOut:
    return StudyOut(
        id=s.id,
        anon_study_hash=s.anon_study_hash,
        modality=s.modality,
        image_count=s.image_count,
        created_at=s.created_at,
        has_epikriz=bool(s.masked_epikriz),
    )


@router.post("", response_model=StudyOut, status_code=201)
def create_study(payload: StudyCreate,
                 request: Request,
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> StudyOut:
    # Defans-in-depth: maskelenmiş epikrizde PII yakalanırsa RED.
    if payload.masked_epikriz:
        found = scan_pii(payload.masked_epikriz)
        if found:
            write_audit(db, user_id=user.id, action="PII_REJECTED",
                        entity_type="study", entity_id=payload.anon_study_hash[:32],
                        ip=client_ip(request))
            raise HTTPException(
                422,
                f"Maskelenmemiş PII tespit edildi ({', '.join(found)}). "
                "Veri istemcide anonimleştirilmelidir.",
            )
    if db.query(Study).filter(Study.anon_study_hash == payload.anon_study_hash).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu çalışma zaten kayıtlı")

    study = Study(
        anon_study_hash=payload.anon_study_hash,
        modality=payload.modality.upper()[:8],
        image_count=payload.image_count,
        masked_epikriz=payload.masked_epikriz,
        anonymization_report=payload.anonymization_report,
        ecg_meta=payload.ecg_meta if payload.modality.upper() == "ECG" else None,
        created_by_id=user.id,
    )
    db.add(study)
    db.flush()
    write_audit(db, user_id=user.id, action="STUDY_CREATED", entity_type="study",
                entity_id=study.id, ip=client_ip(request))
    return _study_out(study)


@router.get("")
def list_studies(user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> list[dict]:
    studies = db.query(Study).order_by(Study.created_at.desc()).limit(100).all()
    return [_study_out(s).model_dump() for s in studies]


@router.post("/{study_id}/analyze", status_code=202)
async def analyze_study(study_id: str,
                  request: Request,
                  image: UploadFile | None = File(None),
                  signal_file: UploadFile | None = File(None),
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    study = db.get(Study, study_id)
    if not study:
        raise HTTPException(404, "Çalışma bulunamadı")

    vision_result = nlp_result = ecg_result = fusion_result = None
    try:
        if image is not None and image.filename:
            data = await image.read()
            if data:
                content_type = image.content_type or "application/octet-stream"
                vision_result = call_vision_analyze(data, image.filename, content_type,
                                                    study.modality)
        if signal_file is not None and signal_file.filename:
            data = await signal_file.read()
            if data:
                if len(data) > MAX_ECG_BYTES:
                    raise HTTPException(413, "EKG dosyası 5MB sınırını aşıyor")
                if study.modality != "ECG":
                    raise HTTPException(422, "Bu çalışma EKG modality ile oluşturulmamış")
                ecg_result = call_ecg_analyze(base64.b64encode(data).decode("ascii"))
                fname = _store_ecg_file(data)
                ecg_result["_file"] = fname  # viewer sinyal erisim anahtari
        if study.masked_epikriz:
            nlp_result = call_nlp_analyze(study.masked_epikriz)
        if vision_result or nlp_result or ecg_result:
            fusion_result = call_fusion(
                vision_risk=_ecg_or_vision_risk(vision_result, ecg_result),
                nlp_score=(nlp_result or {}).get("urgency_score", 0),
                top_findings=_top_labels(vision_result, ecg_result),
                nlp_rationale=(nlp_result or {}).get("rationale", ""),
            )
    except AICoreError as exc:
        raise HTTPException(503, str(exc)) from exc

    if not vision_result and not nlp_result and not ecg_result:
        raise HTTPException(422, "Analiz için görüntü, EKG sinyali veya epikriz gerekli")

    analysis = Analysis(
        study_id=study.id,
        vision_result=vision_result,
        nlp_result=nlp_result,
        ecg_result=ecg_result,
        fusion_risk_score=(fusion_result or {}).get("fused_risk_score",
                                                    _ecg_or_vision_risk(vision_result, ecg_result)),
        status="PENDING_REVIEW",  # MDR: hekim onayı olmadan kesinleşmez
    )
    db.add(analysis)
    db.flush()
    store_embedding(db, analysis)
    write_audit(db, user_id=user.id, action="ANALYSIS_CREATED", entity_type="analysis",
                entity_id=analysis.id, ip=client_ip(request))
    return {
        "analysis_id": analysis.id,
        "status": analysis.status,
        "fusion_risk_score": analysis.fusion_risk_score,
    }


def _store_ecg_file(data: bytes) -> str:
    """EKG .mat dosyasini diskte saklar; viewer sinyal okumasi icin.

    KVKK notu: dosya istemcide anonimlestirilmis kayitlara aittir; dosya
    adi analiz kimligiyle eslesir, hasta kimligi tasimaz.
    """
    from ...core.config import settings

    updir = Path(settings.ecg_upload_dir)
    updir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.mat"
    (updir / fname).write_bytes(data)
    return fname


def _ecg_or_vision_risk(vision_result: dict | None, ecg_result: dict | None) -> float:
    """EKG varsa risk = (aritmi*0.6 + blok*0.4)*100; yoksa görüntü skoru."""
    if ecg_result:
        p = ecg_result.get("probabilities", {})
        return round(100 * (p.get("arrhythmia", 0.0) * 0.6 + p.get("block", 0.0) * 0.4), 1)
    return (vision_result or {}).get("risk_score", 0.0)


def _top_labels(vision_result: dict | None, ecg_result: dict | None) -> list[str]:
    if ecg_result:
        labels = [ecg_result["superclass"]]
        hr = ecg_result.get("heart_rate_bpm")
        if hr:
            labels.append(f"KHD {hr:.0f} bpm")
        return labels
    return [
        f["label"] for f in sorted(
            (vision_result or {}).get("findings", []),
            key=lambda f: f["probability"], reverse=True)[:3]
        if f["probability"] > 0.5
    ]


@router.get("/{study_id}")
def get_study(study_id: str, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict:
    study = db.get(Study, study_id)
    if not study:
        raise HTTPException(404, "Çalışma bulunamadı")
    out = _study_out(study).model_dump()
    out["analyses"] = [
        {"id": a.id, "status": a.status, "fusion_risk_score": a.fusion_risk_score}
        for a in sorted(study.analyses, key=lambda x: x.created_at, reverse=True)
    ]
    return out
