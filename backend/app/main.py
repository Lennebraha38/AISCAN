"""Pulsar-KKDS SaaS API.

MDR (EU 2017/745) notu: bu servis SaMD hedefli bir karar destek prototipinin
backend'idir; AI cikitisi hekim onayi olmadan kesinlesmez. Onaylanmis bir
tibbi cihaz degildir (bkz. docs/SINIRLAMALAR.md).
"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core.config import settings, validate_security_settings
from .models import init_db, make_engine
from .api.v1 import analyses, audit, auth, studies

from datetime import datetime, timezone, timedelta

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="KVKK ilkeleri gozetilerek tasarlanmis, SaMD hedefli multimodal karar destek prototipi",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Büyük JSON yanıtlarını (analiz, sinyal) sıkıştırır.
app.add_middleware(GZipMiddleware, minimum_size=1024)

engine = make_engine(settings.database_url)


@app.on_event("startup")
def startup() -> None:
    import logging

    # Uretim ortaminda bilinen/zayif secret ile baslatmayi REDDET.
    validate_security_settings()
    if settings.is_development:
        logging.getLogger("uvicorn.error").warning(
            "PULSAR_ENV=development: zayif JWT_SECRET/ANON_SALT varsayilanlari "
            "kabul ediliyor. Uretimde PULSAR_ENV=production + guclu secret verin."
        )
    if settings.database_url.startswith("sqlite"):
        logging.getLogger("uvicorn.error").warning(
            "SQLite kullaniliyor: coklu instance / yuksek yazma yuku icin PostgreSQL onerilir."
        )
    init_db(engine)
    from sqlalchemy.orm import sessionmaker

    app.state.engine = engine
    app.state.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "service": "backend"}


@app.get("/v1/dashboard/stats", tags=["dashboard"])
def dashboard_stats(user=Depends(auth.get_current_user)):
    """Son 24 saatin analiz istatistikleri ve bekleyen onay sayisi."""
    from .models import Analysis
    from sqlalchemy.orm import Session as S

    db = app.state.SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = db.query(Analysis).filter(Analysis.created_at >= since).all()
        total = db.query(Analysis).count()
        pending = db.query(Analysis).filter(Analysis.status == "PENDING_REVIEW").count()
        approved_24h = sum(1 for a in recent if a.status == "APPROVED")
        rejected_24h = sum(1 for a in recent if a.status == "REJECTED")
        high_risk_24h = sum(1 for a in recent if (a.fusion_risk_score or 0) >= 65)
        return {
            "total_analyses": total,
            "pending_reviews": pending,
            "last_24h": {
                "total": len(recent),
                "approved": approved_24h,
                "rejected": rejected_24h,
                "high_risk": high_risk_24h,
            },
        }
    finally:
        db.close()


app.include_router(auth.router)
app.include_router(studies.router)
app.include_router(analyses.router)
app.include_router(audit.router)
from .api.v1 import verify as verify_router  # noqa: E402
from .api.v1 import notifications as notif_router  # noqa: E402

app.include_router(verify_router.router)
app.include_router(notif_router.router)
