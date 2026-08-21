"""Pulsar-KKDS SaaS API.

MDR (EU 2017/745) notu: bu servis bir Karar Destek Sistemi (SaMD)
backend'idir; AI çıktısı hekim onayı olmadan kesinleşmez.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .models import init_db, make_engine
from .api.v1 import analyses, audit, auth, studies

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="KVKK uyumlu multimodal tıbbi karar destek platformu",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = make_engine(settings.database_url)


@app.on_event("startup")
def startup() -> None:
    init_db(engine)
    from sqlalchemy.orm import sessionmaker

    app.state.engine = engine
    app.state.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "service": "backend"}


app.include_router(auth.router)
app.include_router(studies.router)
app.include_router(analyses.router)
app.include_router(audit.router)
