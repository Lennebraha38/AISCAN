"""Gömme üretimi ve benzer vaka arama.

Postgres + pgvector mevcutsa vector tipi kullanılır; aksi halde JSON
kolonunda saklanır ve kosinüs Python tarafında hesaplanır (demo ölçeği).
"""
from __future__ import annotations

import math

from sqlalchemy.orm import Session

from ..models import Analysis, CaseEmbedding

DIM = 768


def build_embedding(analysis: Analysis) -> list[float]:
    """Analiz sonucundan deterministik özellik vektörü üretir."""
    vec = [0.0] * DIM
    vision = analysis.vision_result or {}
    nlp = analysis.nlp_result or {}
    feats: list[float] = [analysis.fusion_risk_score / 100.0]
    for f in vision.get("findings", []):
        feats.append(float(f.get("probability", 0.0)))
    feats.append((nlp.get("urgency_score", 0)) / 100.0)
    for i, v in enumerate(feats[:DIM]):
        vec[i] = round(v, 6)
    return vec


def store_embedding(db: Session, analysis: Analysis) -> None:
    emb = CaseEmbedding(analysis_id=analysis.id, embedding_json=build_embedding(analysis))
    db.add(emb)


def _cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)


def similar_cases(db: Session, analysis_id: str, limit: int = 5) -> list[dict]:
    target = db.get(CaseEmbedding, analysis_id)
    if not target or not target.embedding_json:
        return []
    rows = (
        db.query(CaseEmbedding, Analysis)
        .join(Analysis, Analysis.id == CaseEmbedding.analysis_id)
        .filter(Analysis.status.in_(("APPROVED", "REJECTED")))
        .limit(500)
        .all()
    )
    scored = []
    for emb, analysis in rows:
        if emb.analysis_id == analysis_id:
            continue
        sim = _cosine(target.embedding_json, emb.embedding_json or [])
        scored.append({
            "analysis_id": analysis.id,
            "fusion_risk_score": analysis.fusion_risk_score,
            "status": analysis.status,
            "similarity": round(sim, 4),
        })
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]
