"""Backend entegrasyon testleri (T3 DoD kriterleri)."""
from __future__ import annotations

import os
import tempfile
import uuid

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{tempfile.gettempdir()}/pulsar-test-{os.getpid()}-{uuid.uuid4().hex[:8]}.db",
)

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import app, engine
from app.models import Analysis, Study, User, init_db


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    init_db(engine)
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=engine)()
    for email, role in [("admin@test.demo", "admin"), ("hekim@test.demo", "hekim"),
                        ("asistan@test.demo", "asistan")]:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password("test-pass-123"), role=role))
    db.commit()
    yield
    db.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str) -> dict:
    r = client.post("/v1/auth/login", json={"email": email, "password": "test-pass-123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def hekim(client):
    return _login(client, "hekim@test.demo")


@pytest.fixture()
def asistan(client):
    return _login(client, "asistan@test.demo")


ANON_HASH = "a" * 64


def _create_study(client, headers, masked_epikriz=None, anon_hash=ANON_HASH):
    return client.post("/v1/studies", json={
        "anon_study_hash": anon_hash,
        "modality": "CR",
        "masked_epikriz": masked_epikriz,
        "anonymization_report": {"removed": ["PatientName"], "hashed": ["PatientID"]},
    }, headers=headers)


def test_login_and_me(client, hekim):
    r = client.get("/v1/auth/me", headers=hekim)
    assert r.status_code == 200
    assert r.json()["role"] == "hekim"


def test_wrong_password_401(client):
    r = client.post("/v1/auth/login", json={"email": "hekim@test.demo", "password": "yanlis"})
    assert r.status_code == 401


def test_pii_in_request_rejected_422(client, hekim):
    """DoD-1: PII içeren istek 422 döner."""
    r = _create_study(client, hekim,
                      masked_epikriz="Hasta T.C. 10000000146 numaralı kimlikle başvurdu.")
    assert r.status_code == 422
    assert "PII" in r.json()["detail"]


def test_anonymized_study_accepted(client, hekim):
    r = _create_study(client, hekim,
                      masked_epikriz="Akciğerlerde [KISI_ADI] adlı hastada nodül izlendi.")
    assert r.status_code == 201, r.text
    assert r.json()["has_epikriz"] is True


def test_analysis_pending_review_until_decision(client, hekim, asistan, monkeypatch):
    """DoD-2: analiz PENDING_REVIEW doğar; onaysız kesinleşmez. DoD-3: asistan karar veremez."""
    from app.api.v1 import studies as studies_mod

    monkeypatch.setattr(studies_mod, "call_vision_analyze", lambda *a, **k: {
        "findings": [{"label": "Kütle/Nodül", "probability": 0.81, "cam_image_b64": None}],
        "risk_score": 62.5, "features": {}, "xai_method": "energy-saliency",
    })
    monkeypatch.setattr(studies_mod, "call_nlp_analyze", lambda text: {
        "urgency": "yüksek", "urgency_score": 72, "confidence": 0.9,
        "highlighted_tokens": [], "rationale": "nodül vurgusu",
    })
    monkeypatch.setattr(studies_mod, "call_fusion", lambda **k: {
        "fused_risk_score": 66.5, "urgency": "yüksek", "rationale": "füzyon",
        "weights": {"vision": 0.6, "nlp": 0.4},
    })

    study = _create_study(client, hekim, anon_hash="b" * 64)
    assert study.status_code == 201
    sid = study.json()["id"]

    fake_image = {"image": ("x.png", b"\x89PNG-fake", "image/png")}
    r = client.post(f"/v1/studies/{sid}/analyze", files=fake_image, headers=hekim)
    assert r.status_code == 202, r.text
    aid = r.json()["analysis_id"]
    assert r.json()["status"] == "PENDING_REVIEW"

    detail = client.get(f"/v1/analyses/{aid}", headers=hekim).json()
    assert detail["status"] == "PENDING_REVIEW"

    # Asistan kararı reddedilir (MDR human-in-the-loop)
    forbidden = client.post(f"/v1/analyses/{aid}/decision",
                            json={"decision": "APPROVED"}, headers=asistan)
    assert forbidden.status_code == 403

    ok = client.post(f"/v1/analyses/{aid}/decision",
                     json={"decision": "APPROVED", "note": "Bulgularla uyumlu"},
                     headers=hekim)
    assert ok.status_code == 200
    assert ok.json()["decision"] == "APPROVED"

    again = client.post(f"/v1/analyses/{aid}/decision",
                        json={"decision": "REJECTED"}, headers=hekim)
    assert again.status_code == 409


def test_audit_logs_written_and_admin_only(client, hekim, admin_headers=None):
    """DoD-4: her çağrı audit log üretir; loglar yalnız admin'e açık."""
    admin = _login(client, "admin@test.demo")
    logs = client.get("/v1/audit/logs", headers=admin)
    assert logs.status_code == 200
    actions = {row["action"] for row in logs.json()}
    assert "LOGIN" in actions and "STUDY_CREATED" in actions and "DECISION_APPROVED" in actions

    denied = client.get("/v1/audit/logs", headers=hekim)
    assert denied.status_code == 403


def test_similar_cases_endpoint(client, hekim):
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=engine)()
    try:
        approved = (
            db.query(Analysis)
            .filter(Analysis.status == "APPROVED")
            .order_by(Analysis.created_at.desc())
            .first()
        )
    finally:
        db.close()
    if not approved:
        pytest.skip("onaylı analiz yok")
    r = client.get(f"/v1/analyses/{approved.id}/similar", headers=hekim)
    assert r.status_code == 200
    for case in r.json():
        assert set(case) >= {"analysis_id", "similarity", "status"}


def test_unauthenticated_access_blocked(client):
    assert client.get("/v1/studies").status_code == 401
    assert client.get("/v1/audit/logs").status_code == 401
