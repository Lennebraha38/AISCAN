"""SQLAlchemy modelleri.

KVKK notu: studies tablosunda HİÇBİR kişisel veri kolonu yoktur; yalnız
istemcide üretilmiş `anon_study_hash` saklanır.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # admin|hekim|radyolog|asistan
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="reviewer")


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    anon_study_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    modality: Mapped[str] = mapped_column(String(8), default="CR")
    image_count: Mapped[int] = mapped_column(Integer, default=1)
    masked_epikriz: Mapped[str | None] = mapped_column(Text, nullable=True)
    anonymization_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="study")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    vision_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    nlp_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fusion_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    # MDR human-in-the-loop: analiz hekim onayı olmadan kesinleşmez.
    status: Mapped[str] = mapped_column(String(20), default="PENDING_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    study: Mapped[Study] = relationship(back_populates="analyses")
    decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="analysis")
    embedding: Mapped["CaseEmbedding | None"] = relationship(back_populates="analysis", uselist=False)


class ReviewDecision(Base):
    """Hekim Onay Log'u — append-only klinik karar kaydı."""

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(10))  # APPROVED|REJECTED
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analysis: Mapped[Analysis] = relationship(back_populates="decisions")
    reviewer: Mapped[User] = relationship(back_populates="decisions")


class AuditLog(Base):
    """Değiştirilemez işlem kaydı (UPDATE/DELETE DB trigger'ı ile engellenir)."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseEmbedding(Base):
    """pgvector benzer vaka arama gömmeleri (postgres'te vector(768))."""

    __tablename__ = "case_embeddings"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id"), primary_key=True
    )
    embedding_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(80), default="pulsar-fusion-v1")

    analysis: Mapped[Analysis] = relationship(back_populates="embedding")


IMMUTABLE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION prevent_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs tablosu append-onlydir: % yasak', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_logs_immutable
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
"""


def make_engine(database_url: str):
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )


def init_db(engine) -> None:
    """Tabloları oluşturur; postgres ise audit immutability trigger'ını ekler."""
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            exists = conn.exec_driver_sql(
                "SELECT 1 FROM pg_trigger WHERE tgname='audit_logs_immutable'"
            ).fetchone()
            if not exists:
                conn.exec_driver_sql(IMMUTABLE_TRIGGER_SQL)


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def _block_audit_mutation(mapper, connection, target):  # pragma: no cover
    raise RuntimeError("audit_logs append-only: güncelleme/silme yasak (KVKK md.12)")
