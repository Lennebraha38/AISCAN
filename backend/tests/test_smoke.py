"""Smoke tests for backend API (Pulsar-KKDS).

Bu testler gerçek modellere ve güvenlik yardımcılarına karşı çalışır.
Harici servis (PostgreSQL, Redis) gerektirmez; SQLite in-memory kullanır.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Test ortamı: token'lar deterministik ve bağımsız olsun.
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Analysis,
    AuditLog,
    Base,
    ReviewDecision,
    Study,
    User,
    init_db,
    make_engine,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import settings


def _new_db():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, SessionLocal()


def test_password_hashing():
    """PBKDF2-SHA256 hash + doğrulama."""
    pwd = "test-password-123"
    hashed = hash_password(pwd)
    assert hashed != pwd  # açık metin değil
    assert hashed.startswith("pbkdf2$")
    assert verify_password(pwd, hashed)
    assert not verify_password("wrong-password", hashed)
    assert not verify_password(pwd, "bozuk-hash")
    # Aynı şifre iki kez hash'lenince farklı salt -> farklı çıktı
    assert hash_password(pwd) != hashed
    print("[OK] test_password_hashing")


def test_jwt_roundtrip():
    """JWT üret / çöz, tip ve roller doğru mu."""
    user_id = "u" * 32
    token = create_access_token(user_id, "hekim")
    assert isinstance(token, str) and token.startswith("eyJ")  # JWT format

    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["role"] == "hekim"
    assert payload["type"] == "access"

    refresh = create_refresh_token(user_id, "radyolog")
    rp = decode_token(refresh)
    assert rp is not None and rp["type"] == "refresh"

    # Bozuk token -> None
    assert decode_token("eyJhbGciOiJIUzI1NiJ9.bozuk.imza") is None
    print("[OK] test_jwt_roundtrip")


def test_database_init_and_user():
    """init_db tabloları oluşturur; User CRUD çalışır."""
    _engine, db = _new_db()
    user = User(
        email="hekim@pulsar.demo",
        password_hash=hash_password("gizli123"),
        role="hekim",
    )
    db.add(user)
    db.commit()

    found = db.query(User).filter(User.email == "hekim@pulsar.demo").first()
    assert found is not None
    assert found.role == "hekim"
    assert found.id  # otomatik uuid hex
    assert verify_password("gizli123", found.password_hash)
    db.close()
    print("[OK] test_database_init_and_user")


def test_study_creation_ecg_meta():
    """EKG çalışması: PII içermeyen anon hash + teknik meta."""
    _engine, db = _new_db()
    study = Study(
        anon_study_hash="abc123def456",
        modality="ECG",
        ecg_meta={"fs": 500, "leads": 12, "duration_sec": 10},
    )
    db.add(study)
    db.commit()

    found = db.query(Study).filter(Study.anon_study_hash == "abc123def456").first()
    assert found is not None
    assert found.modality == "ECG"
    assert found.ecg_meta["leads"] == 12
    assert found.image_count == 1  # varsayılan
    # KVKK: masked_epikriz PII taşımaz (None olabilir)
    assert found.masked_epikriz is None
    db.close()
    print("[OK] test_study_creation_ecg_meta")


def test_analysis_human_in_the_loop():
    """MDR: analiz PENDING_REVIEW başlar, hekim kararı ile kesinleşir."""
    _engine, db = _new_db()
    user = User(email="dr@pulsar.demo", password_hash=hash_password("x"), role="hekim")
    db.add(user)
    db.commit()

    study = Study(anon_study_hash="hash-htl", modality="ECG")
    db.add(study)
    db.commit()

    analysis = Analysis(
        study_id=study.id,
        ecg_result={"superclass": "arrhythmia", "confidence": 0.87},
        fusion_risk_score=72.0,
    )
    db.add(analysis)
    db.commit()

    # AI çıktısı tek başına kesinleşmez
    assert analysis.status == "PENDING_REVIEW"
    assert analysis.decided_at is None

    decision = ReviewDecision(
        analysis_id=analysis.id,
        reviewer_id=user.id,
        decision="APPROVED",
        note="Normal EKG, onaylandı",
    )
    db.add(decision)
    analysis.status = "APPROVED"
    from datetime import datetime, timezone

    analysis.decided_at = datetime.now(timezone.utc)
    db.commit()

    db.refresh(analysis)
    assert analysis.status == "APPROVED"
    assert analysis.decided_at is not None
    assert len(analysis.decisions) == 1
    assert analysis.decisions[0].decision == "APPROVED"
    db.close()
    print("[OK] test_analysis_human_in_the_loop")


def test_audit_log_append_only():
    """audit_logs UPDATE/DELETE ORM seviyesinde engellenir (KVKK md.12)."""
    _engine, db = _new_db()
    audit = AuditLog(
        user_id="u1",
        action="TEST_ACTION",
        entity_type="test",
        entity_id="123",
        ip="127.0.0.1",
    )
    db.add(audit)
    db.commit()
    audit_id = audit.id

    import pytest

    # UPDATE engellenir
    audit.action = "MODIFIED"
    with pytest.raises(RuntimeError):
        db.commit()
    db.rollback()

    # DELETE engellenir
    audit_row = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    db.delete(audit_row)
    with pytest.raises(RuntimeError):
        db.commit()
    db.rollback()

    # Kayıt hâlâ yerinde
    still = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    assert still is not None
    assert still.action == "TEST_ACTION"
    db.close()
    print("[OK] test_audit_log_append_only")


def test_health_endpoint():
    """Uygulama ayağa kalkar ve /health 200 döner."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "backend"
    print("[OK] test_health_endpoint")


def test_model_defaults():
    """Varsayılanlar güvenli mi (status, fusion_risk_score)."""
    _engine, db = _new_db()
    study = Study(anon_study_hash="h-defaults")
    db.add(study)
    db.commit()
    analysis = Analysis(study_id=study.id)
    db.add(analysis)
    db.commit()
    assert analysis.status == "PENDING_REVIEW"
    assert analysis.fusion_risk_score == 0.0
    db.close()
    print("[OK] test_model_defaults")


if __name__ == "__main__":
    test_password_hashing()
    test_jwt_roundtrip()
    test_database_init_and_user()
    test_study_creation_ecg_meta()
    test_analysis_human_in_the_loop()
    test_audit_log_append_only()
    test_health_endpoint()
    test_model_defaults()
    print("\n[OK] All backend smoke tests passed!")
