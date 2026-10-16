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


# ---------------------------------------------------------------------------
# Güvenlik regresyon testleri: IDOR, token iptali, rate limit, XFF, audit kalıcılığı
# ---------------------------------------------------------------------------


def _admin_headers(client: TestClient) -> dict:
    return _login(client, "admin@test.demo")


def _create_user(client: TestClient, admin: dict, email: str, password: str, role: str):
    r = client.post("/v1/auth/users",
                    json={"email": email, "password": password, "role": role},
                    headers=admin)
    # Aynı oturumda tekrar oluşturulursa 409 dönebilir; ikisi de kabul.
    assert r.status_code in (201, 409), r.text
    return r


def test_study_idor_is_enforced_by_role(client, asistan, hekim):
    """IDOR: broad-access olmayan rol yalnız kendi çalışmasını görür; hekim tümüne erişir."""
    admin = _admin_headers(client)
    _create_user(client, admin, "asistan2@test.demo", "test-pass-123", "asistan")
    asistan2 = _login(client, "asistan2@test.demo")

    a_study = _create_study(client, asistan, anon_hash="c" * 64)
    assert a_study.status_code == 201, a_study.text
    a_id = a_study.json()["id"]

    b_study = _create_study(client, asistan2, anon_hash="d" * 64)
    assert b_study.status_code == 201, b_study.text
    b_id = b_study.json()["id"]

    # Nesne düzeyi: asistan yalnız kendi çalışmasına erişebilir.
    assert client.get(f"/v1/studies/{b_id}", headers=asistan).status_code == 403
    assert client.get(f"/v1/studies/{a_id}", headers=asistan2).status_code == 403
    # broad-access rol (hekim) inceleme amacıyla erişebilir.
    assert client.get(f"/v1/studies/{b_id}", headers=hekim).status_code == 200

    # Liste düzeyi: her asistan yalnız kendi kayıtlarını görür.
    a_ids = {s["id"] for s in client.get("/v1/studies", headers=asistan).json()}
    b_ids = {s["id"] for s in client.get("/v1/studies", headers=asistan2).json()}
    assert a_id in a_ids and b_id not in a_ids
    assert b_id in b_ids and a_id not in b_ids


def test_password_change_invalidates_old_tokens(client):
    """token_version: şifre değişince eski access/refresh token'lar 401 olur."""
    admin = _admin_headers(client)
    _create_user(client, admin, "pwuser@test.demo", "test-pass-123", "hekim")

    tokens = client.post("/v1/auth/login",
                         json={"email": "pwuser@test.demo", "password": "test-pass-123"}).json()
    old_access = {"Authorization": f"Bearer {tokens['access_token']}"}
    old_refresh = tokens["refresh_token"]
    assert client.get("/v1/auth/me", headers=old_access).status_code == 200

    ch = client.post("/v1/auth/password",
                     json={"current_password": "test-pass-123", "new_password": "yeni-parola-456"},
                     headers=old_access)
    assert ch.status_code == 200, ch.text

    # Eski token'lar artık geçersiz kılınmış.
    assert client.get("/v1/auth/me", headers=old_access).status_code == 401
    assert client.post("/v1/auth/refresh",
                       json={"refresh_token": old_refresh}).status_code == 401
    # Yeni şifreyle giriş çalışır.
    assert client.post("/v1/auth/login",
                       json={"email": "pwuser@test.demo", "password": "yeni-parola-456"}).status_code == 200


def test_rate_limit_raises_429_after_limit():
    """Sabit-pencere hız sınırlayıcı limiti aşınca 429 üretir."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.core.ratelimit import rate_limit

    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.50"))
    name = f"unit-{uuid.uuid4().hex[:8]}"
    for _ in range(3):
        rate_limit(req, name, 3, 60)
    with pytest.raises(HTTPException) as ei:
        rate_limit(req, name, 3, 60)
    assert ei.value.status_code == 429


def test_client_ip_ignores_xff_unless_trusted(monkeypatch):
    """XFF yalnız TRUST_FORWARDED_FOR=1 iken dikkate alınır (audit IP spoof koruması)."""
    import dataclasses
    from types import SimpleNamespace

    from app.core import deps
    from app.core.config import settings

    req = SimpleNamespace(headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"},
                          client=SimpleNamespace(host="203.0.113.7"))

    monkeypatch.setattr(deps, "settings", dataclasses.replace(settings, trust_forwarded_for=False))
    assert deps.client_ip(req) == "203.0.113.7"  # spoof edilen başlık yok sayılır

    monkeypatch.setattr(deps, "settings", dataclasses.replace(settings, trust_forwarded_for=True))
    assert deps.client_ip(req) == "9.9.9.9"  # güvenilir proxy arkasında ilk adres

    req2 = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.8"))
    assert deps.client_ip(req2) == "203.0.113.8"  # başlık yoksa gerçek IP


def test_failed_login_is_committed_to_audit(client):
    """get_db HTTPException yolunda da commit etmeli: LOGIN_FAILED kaydı kalıcı olur."""
    client.post("/v1/auth/login", json={"email": "admin@test.demo", "password": "yanlis-sifre"})
    admin = _admin_headers(client)
    actions = {row["action"] for row in client.get("/v1/audit/logs", headers=admin).json()}
    assert "LOGIN_FAILED" in actions


def test_pii_rejection_is_committed_to_audit(client, hekim):
    """get_db HTTPException yolunda da commit etmeli: PII_REJECTED kaydı kalıcı olur."""
    r = _create_study(client, hekim, masked_epikriz="Kimlik 10000000146 ile başvurdu.")
    assert r.status_code == 422
    admin = _admin_headers(client)
    actions = {row["action"] for row in client.get("/v1/audit/logs", headers=admin).json()}
    assert "PII_REJECTED" in actions
