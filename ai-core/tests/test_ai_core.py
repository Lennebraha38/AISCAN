"""T2.x AI Core testleri: vision, XAI, NLP, fusion."""
from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.nlp import analyze_epikriz
from app.vision.engine import analyze_image, hu_window

client = TestClient(app)


def _png_bytes(seed: int = 7, blob: bool = True) -> bytes:
    rng = np.random.default_rng(seed)
    img = np.full((512, 512), 40, dtype=np.uint8)
    # akciğer benzeri iki karanlık alan
    img[100:400, 80:230] = rng.normal(25, 6, (300, 150)).clip(0, 255).astype(np.uint8)
    img[100:400, 282:432] = rng.normal(25, 6, (300, 150)).clip(0, 255).astype(np.uint8)
    if blob:  # sağ alanda parlak lezyon benzeri kütle
        yy, xx = np.mgrid[0:512, 0:512]
        mask = (yy - 260) ** 2 + (xx - 350) ** 2 < 30 ** 2
        img[mask] = 220
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


def test_health_reports_engine():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "ai-core"
    assert body["xai_backend"] in ("energy-saliency", "grad-cam")


def test_vision_analyze_returns_findings_and_cam():
    r = client.post(
        "/v1/vision/analyze",
        files={"image": ("x.png", _png_bytes(), "image/png")},
        data={"modality": "CR"},
    )
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["risk_score"] <= 100
    labels = [f["label"] for f in body["findings"]]
    assert "Kütle/Nodül" in labels and len(labels) >= 7
    cam = next(f for f in body["findings"] if f["cam_image_b64"])
    raw = base64.b64decode(cam["cam_image_b64"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert body["xai_method"].startswith(("energy-saliency", "grad-cam"))


def test_vision_deterministic():
    a = analyze_image(_png_bytes())
    b = analyze_image(_png_bytes())
    assert a["risk_score"] == b["risk_score"]
    assert a["probabilities"] == b["probabilities"]


def test_hu_windowing():
    arr = np.array([-1400.0, -600.0, 0.0, 500.0])
    out = hu_window(arr, center=-600, width=1500)
    assert out.min() == 0.0 and out.max() <= 1.0
    assert abs(out[1] - 0.5) < 1e-6


def test_nlp_high_risk_epikriz():
    text = "Toraks BT'de sağ alt lobda 8 mm boyutlu nodül saptandı, malignite şüphesi mevcut."
    r = analyze_epikriz(text)
    assert r["urgency"] in ("yüksek", "orta")
    assert r["urgency_score"] > 30
    texts = [t["text"] for t in r["highlighted_tokens"]]
    assert any("nodül" in t.lower() for t in texts)


def test_nlp_negation_lowers_score():
    pos = analyze_epikriz("Akciğerde nodül mevcut.")
    neg = analyze_epikriz("Akciğerde nodül izlenmedi.")
    assert neg["urgency_score"] < pos["urgency_score"]
    tok = next(t for t in neg["highlighted_tokens"] if "nodül" in t["text"].lower())
    assert tok["negated"] is True


def test_nlp_clean_text():
    r = analyze_epikriz("Bilateral akciğer alanları doğaldır.")
    assert r["urgency_score"] <= 35 or r["urgency"] == "düşük"


def test_nlp_api_endpoint():
    r = client.post("/v1/nlp/analyze", json={"text": "Plevral efüzyon izlendi."})
    assert r.status_code == 200
    body = r.json()
    assert body["urgency"] in ("düşük", "orta", "yüksek")
    assert body["rationale"]


def test_fusion():
    r = client.post("/v1/fusion", json={
        "vision_risk_score": 70,
        "nlp_urgency_score": 50,
        "vision_top_findings": ["Kütle/Nodül"],
        "nlp_rationale": "nodül vurgusu",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["fused_risk_score"] == round(0.6 * 70 + 0.4 * 50, 1)
    assert body["weights"]["vision"] == 0.6


def test_upload_rejects_oversize_and_mime():
    big = b"0" * (10 * 1024 * 1024 + 1)
    r = client.post("/v1/vision/analyze",
                    files={"image": ("big.png", big, "image/png")})
    assert r.status_code == 413
    r = client.post("/v1/vision/analyze",
                    files={"image": ("x.txt", b"merhaba", "text/plain")})
    assert r.status_code == 415
