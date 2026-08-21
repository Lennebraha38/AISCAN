"""Analiz ve hekim onay endpoint'leri (MDR human-in-the-loop)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...core.deps import DECISION_ROLES, client_ip, get_current_user, get_db
from ...models import Analysis, ReviewDecision, User
from ...schemas import AnalysisOut, DecisionOut, DecisionRequest
from ...services.audit import write_audit
from ...services.embeddings import similar_cases

router = APIRouter(prefix="/v1/analyses", tags=["analyses"])


def _analysis_out(a: Analysis) -> AnalysisOut:
    return AnalysisOut(
        id=a.id,
        study_id=a.study_id,
        status=a.status,
        fusion_risk_score=a.fusion_risk_score,
        vision_result=a.vision_result,
        nlp_result=a.nlp_result,
        created_at=a.created_at,
        decided_at=a.decided_at,
    )


@router.get("")
def list_analyses(status_filter: str | None = None,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(Analysis).order_by(Analysis.created_at.desc())
    if status_filter:
        q = q.filter(Analysis.status == status_filter)
    return [_analysis_out(a).model_dump() for a in q.limit(100)]


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
