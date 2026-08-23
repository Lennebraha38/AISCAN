"""Demo DB'yi sifirlar: 10 farkli goruntu + 3 EKG calismasi olusturur.

Kullanim: .venv/bin/python /tmp/opencode/rebuild_demo.py
"""
import base64
import hashlib
import io
import json
import urllib.request

import numpy as np
from scipy.io import savemat

API = "http://127.0.0.1:8000/v1"
IMG_DIR = "/root/projeler/pulsar-kkds/data/demo_images"
TOKEN = open("/tmp/opencode/tok.txt").read().strip()

CASES = [
    ("cxr-normal.png", "CR", "Rutin kontrol çekimi. Şikâyet yok; akciğer alanları doğal, kardiyotorasik siluet normal sınırlarda."),
    ("cxr-pneumonia.png", "CR", "Ateş, balgam ve yan ağrısı. Sağda yaygın infiltrasyon görülüyor; pnömoni nedeniyle antibiyotik başlandı."),
    ("cxr-pneumothorax.png", "CR", "Ani başlayan göğüs ağrısı ve dispne. Pnömotoraks izleniyor; oksijen desteği ve yakın takip gerekli."),
    ("cxr-tension.png", "CR", "Trakeal sapma, hipotansiyon ve şok bulguları. Gerilme pnömotoraksı; acil dekompresyon yapıldı, göğüs tüpü takıldı."),
    ("cxr-effusion.png", "CR", "Eforla artan dispne, ayakta şişlik. Bilateral plevral efüzyon mevcut; diüretik tedavi düzenlendi, torasentez değerlendiriliyor."),
    ("cxr-atelectasis.png", "CR", "Ameliyat sonrası 2. gün. Sol alt lob atelektazisi gelişti; solunum fizyoterapisi başlandı."),
    ("cxr-mass.png", "CR", "Aylardır süren öksürük ve kilo kaybı. Akciğer kitlesi ve mediyastinal kayma izleniyor; bronşiyal karsinom şüphesi ile BT planlandı."),
    ("cxr-cardiomegaly.png", "CR", "Kalp yetmezliği takibi, efor dispnesi artışı. Konjestyon bulguları mevcut; kardiyoloji konsultasyonu istendi."),
    ("cxr-nodules.png", "CR", "Bilinen nörofibromatozis hastası. Kontrol grafisinde çoklu yuvarlak opasiteler; metastaz-infeksiyon ayrımı için kontrastlı BT planlandı."),
    ("ct-head.png", "CT", "Bilinç bulanıklığı ve baş ağrısı. Kraniyal BT'de kanama şüphesi; nöroşirürji konsultasyonu istendi."),
]


ECG_CASES = [
    ("ecg-normal.mat", {"fs": 500, "leads": 12}, "Rutin kardiyoloji kontrolü. Çarpıntı yok; EKG sinüs ritmi ile uyumlu."),
    ("ecg-afib.mat", {"fs": 500, "leads": 12}, "Palpitasyon ve düzensiz çarpıntı atakları. EKG düzensiz ritim; atriyal fibrilasyona uyumlu bulgular."),
    ("ecg-stemi.mat", {"fs": 500, "leads": 12}, "Göğüste bastırıcı ağrı ve soğuk terleme. Akut miyokard enfarktüsü şüphesi; acil koroner anjiyografi planlandı."),
]


def req(method, path, data=None, files=None):
    url = API + path
    headers = {"Authorization": "Bearer " + TOKEN}
    body = None
    if files:
        boundary = "----pb" + hashlib.md5(path.encode()).hexdigest()[:8]
        parts = []
        for k, v in (data or {}).items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (fname, blob) in files.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fname}\"\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n".encode() + blob + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())


def synth_ecg(kind: str) -> bytes:
    fs = 500
    t_full = np.arange(0, 10, 1 / fs)
    leads_gain = np.array([1.0, 0.9, 0.7, -0.35, 0.5, 0.85, 0.95, 0.75, 0.4, -0.2, 0.55, 0.6])
    sig = np.zeros((12, len(t_full)))

    def beat(t0, rr_next=None):
        n = {}
        n["P"] = 0.10 * np.exp(-((t_full - t0 - 0.00) ** 2) / (2 * 0.018 ** 2))
        qrs = (-0.06 * np.exp(-((t_full - t0 - 0.14) ** 2) / (2 * 0.006 ** 2))
               + 1.05 * np.exp(-((t_full - t0 - 0.16) ** 2) / (2 * 0.0075 ** 2))
               - 0.16 * np.exp(-((t_full - t0 - 0.185) ** 2) / (2 * 0.010 ** 2)))
        st = 0.0
        twave = 0.22 * np.exp(-((t_full - t0 - 0.36) ** 2) / (2 * 0.045 ** 2))
        return n["P"] + qrs + st + twave

    rng = np.random.default_rng(11 if kind == "normal" else 12 if kind == "afib" else 13)
    t = 0.9
    while t < 10:
        if kind == "afib":
            rr = rng.uniform(0.45, 1.35)
        else:
            rr = 0.80 + rng.normal(0, 0.015)
        b = beat(t)
        if kind == "stemi":
            b = b + 0.20 * np.exp(-((t_full - t - 0.26) ** 2) / (2 * 0.09 ** 2))  # ST elevasyonu + hiperakut T
        for li in range(12):
            sig[li] += leads_gain[li] * b
        t += rr
    if kind == "afib":
        fib = 0.025 * np.sin(2 * np.pi * 7 * t_full + rng.uniform(0, 6)) + \
              0.02 * np.sin(2 * np.pi * 5.3 * t_full + rng.uniform(0, 6))
        sig += fib
    sig += rng.normal(0, 0.008, sig.shape)
    buf = io.BytesIO()
    savemat(buf, {"val": sig.astype(np.float64)})
    return buf.getvalue()


def main():
    print("== eski kayitlar siliniyor ==")
    import sqlite3
    con = sqlite3.connect("/root/projeler/pulsar-kkds/data/pulsar.db")
    cur = con.cursor()
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for tb in ["embeddings", "analyses", "studies"]:
        if tb in tables:
            cur.execute(f"DELETE FROM {tb}")
            print("silindi:", tb)
    con.commit()
    con.close()

    print("\n== goruntulu calismalar ==")
    rows = []
    for fname, mod, text in CASES:
        h = hashlib.sha256(("demo-" + fname).encode()).hexdigest()[:48]
        s = req("POST", "/studies", {
            "anon_study_hash": h, "modality": mod, "image_count": 1,
            "masked_epikriz": text,
            "anonymization_report": {"method": "demo-generator", "pii_found": []},
        })
        blob = open(f"{IMG_DIR}/{fname}", "rb").read()
        a = req("POST", f"/studies/{s['id']}/analyze",
                data={"dummy": "1"}, files={"image": (fname, blob)})
        rows.append((fname, mod, a["fusion_risk_score"]))
        print("%-24s %s risk=%s" % (fname, mod, a["fusion_risk_score"]))

    print("\n== EKG calismalari ==")
    for fname, meta, text in ECG_CASES:
        kind = fname.split("-")[1].split(".")[0]
        h = hashlib.sha256(("demo-" + fname).encode()).hexdigest()[:48]
        s = req("POST", "/studies", {
            "anon_study_hash": h, "modality": "ECG", "image_count": 1,
            "masked_epikriz": text, "ecg_meta": meta,
            "anonymization_report": {"method": "demo-generator", "pii_found": []},
        })
        mat = synth_ecg(kind)
        a = req("POST", f"/studies/{s['id']}/analyze",
                data={"dummy": "1"}, files={"signal_file": (fname, mat)})
        rows.append((fname, "ECG", a["fusion_risk_score"]))
        print("%-24s ECG risk=%s" % (fname, a["fusion_risk_score"]))

    print("\n== OZET ==")
    for fname, mod, risk in sorted(rows, key=lambda x: x[2]):
        print("%6.1f  %-4s %s" % (risk, mod, fname))


if __name__ == "__main__":
    main()
