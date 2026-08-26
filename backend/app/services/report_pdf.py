"""Onaylanmis analiz raporunu PDF olarak uretir (reportlab + DejaVu TTF).

Rapor; calisma, bulgular, fuzyon riski, NLP aciliyeti ve hekim kararini
icerir. Dogrulama kodu = sha256(analysis_id | decided_at)[:16] olup
PDF'te QR olarak da basilir; GET /v1/verify/{kod} ile saglanabilir.
"""
from __future__ import annotations

import hashlib
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DVS", f"{_FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVSB", f"{_FONT_DIR}/DejaVuSans-Bold.ttf"))


def verification_code(analysis_id: str, decided_at) -> str:
    raw = f"{analysis_id}|{decided_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


def _fmt_dt(dt) -> str:
    try:
        return dt.strftime("%d.%m.%Y %H:%M UTC")
    except Exception:
        return str(dt)


def render_report(analysis: dict, study: dict) -> bytes:
    """analysis: id/status/fusion_risk_score/vision_result/nlp_result/ecg_result/
    decided_at/decisions;  study: anon_study_hash/modality/created_at."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x, y = 50, H - 60

    def line(txt, size=10, bold=False, dy=18, color=(0.1, 0.12, 0.2)):
        nonlocal y
        c.setFont("DVSB" if bold else "DVS", size)
        c.setFillColorRGB(*color)
        c.drawString(x, y, txt)
        y -= dy

    # Baslik bandı
    c.setFillColorRGB(0.13, 0.24, 0.55)
    c.rect(0, H - 42, W, 42, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("DVSB", 15)
    c.drawString(x, H - 28, "PULSAR-KKDS · Yapay Zeka Destekli Karar Destek Raporu")
    y = H - 75

    code = verification_code(analysis["id"], analysis.get("decided_at"))
    status = analysis["status"]
    approved = status == "APPROVED"
    sband = (0.85, 0.30, 0.25) if not approved else (0.12, 0.55, 0.31)
    line(f"RAPOR DURUMU: {'KESINLESTI (HEKIM ONAYLI)' if approved else 'REDDEDILDI'}",
         12, True, 20, sband)
    line(f"Dogrulama kodu: {code}", 11, True, 22)

    line("ÇALIŞMA BİLGİLERİ", 11, True, 20)
    line(f"Anonim çalışma no : {str(study.get('anon_study_hash'))[:24]}…")
    line(f"Modalite / tarih : {study.get('modality')} · {_fmt_dt(study.get('created_at'))}")
    line(f"Analiz kimliği   : {analysis['id']}", dy=22)

    # Risk
    risk = float(analysis.get("fusion_risk_score") or 0)
    band = "DÜŞÜK" if risk < 35 else ("ORTA" if risk < 65 else "YÜKSEK")
    rcol = (0.12, 0.55, 0.31) if risk < 35 else ((0.72, 0.47, 0.12) if risk < 65 else (0.80, 0.20, 0.16))
    line("FÜZYON RISK SKORU", 11, True, 20)
    c.setFillColorRGB(*rcol)
    c.setFont("DVSB", 26)
    c.drawString(x, y - 6, f"{risk:.1f} / 100")
    c.setFont("DVSB", 13)
    c.drawString(x + 150, y, f"({band})")
    y -= 40

    # Bulgular
    vr = analysis.get("vision_result") or {}
    findings = [f for f in (vr.get("findings") or []) if isinstance(f, dict)]
    if findings:
        line("GÖRÜNTÜ BULGULARI (olasılık)", 11, True, 20)
        findings.sort(key=lambda f: -(f.get("probability") or 0))
        for f in findings[:7]:
            p = (f.get("probability") or 0) * 100
            bar_len = int(p / 5)
            c.setFont("DVS", 10)
            c.setFillColorRGB(0.1, 0.12, 0.2)
            c.drawString(x + 8, y, str(f.get("label")))
            c.setFillColorRGB(0.78, 0.80, 0.86)
            c.rect(x + 190, y - 2, 180, 9, fill=1, stroke=0)
            c.setFillColorRGB(*rcol)
            c.rect(x + 190, y - 2, max(bar_len, 2), 9, fill=1, stroke=0)
            c.setFillColorRGB(0.1, 0.12, 0.2)
            c.setFont("DVS", 9)
            c.drawString(x + 378, y, f"%{p:.1f}")
            y -= 16
        y -= 6

    nr = analysis.get("nlp_result") or {}
    if nr:
        line("EPKRIZ ANALİZİ", 11, True, 20)
        urg = str(nr.get("urgency"))
        ucol = {"yüksek": (0.80, 0.20, 0.16), "orta": (0.72, 0.47, 0.12)}.get(urg, (0.12, 0.55, 0.31))
        c.setFillColorRGB(*ucol)
        c.setFont("DVSB", 10)
        c.drawString(x + 8, y, f"Aciliyet: {urg.upper()} ({nr.get('urgency_score')}/100)")
        y -= 16
        rationale = str(nr.get("rationale") or "")
        c.setFont("DVS", 9.5)
        while len(rationale) > 95:
            cut = rationale.rfind(" ", 0, 95)
            cut = cut if cut > 0 else 95
            c.drawString(x + 8, y, rationale[:cut])
            rationale = rationale[cut:].lstrip()
            y -= 13
        c.drawString(x + 8, y, rationale)
        y -= 20

    er = analysis.get("ecg_result") or {}
    if er and er.get("superclass"):
        line("EKG ANALİZİ", 11, True, 20)
        conf = (er.get("confidence") or 0) * 100
        c.setFont("DVS", 10)
        c.drawString(x + 8, y, f"Sınıf: {er.get('superclass')} · güven %{conf:.1f}")
        y -= 20

    # Karar
    decs = analysis.get("decisions") or []
    line("HEKİM KARARI", 11, True, 20)
    if decs:
        d = decs[-1]
        c.setFont("DVS", 10)
        c.setFillColorRGB(*sband)
        c.drawString(x + 8, y,
                     f"{d['decision']} · {_fmt_dt(d.get('decided_at'))}")
        c.setFillColorRGB(0.35, 0.38, 0.45)
        c.setFont("DVS", 9)
        c.drawString(x + 250, y, f"gözden geçiren: {str(d.get('reviewer_id'))[:8]}…")
        y -= 15
        note = d.get("note") or ""
        if note:
            c.setFont("DVS", 9.5)
            c.setFillColorRGB(0.1, 0.12, 0.2)
            c.drawString(x + 8, y, f"Not: {note[:110]}")
            y -= 15
    else:
        c.setFont("DVS", 10)
        c.drawString(x + 8, y, "Karar bekleniyor")
        y -= 15
    y -= 14

    c.setStrokeColorRGB(0.8, 0.82, 0.88)
    c.line(x, y, W - x, y)
    y -= 16
    # QR: dogrulama kodunu telefonla okutulabilir yapar
    qrw = QrCodeWidget(f"PULSAR-KKDS:{code}")
    qb = qrw.getBounds()
    qsize = 74
    qd = Drawing(qsize, qsize, transform=[qsize / qb[2], 0, 0, qsize / qb[3], 0, 0])
    qd.add(qrw)
    qd.drawOn(c, W - x - qsize, y - qsize + 10)
    c.setFont("DVS", 8.5)
    c.setFillColorRGB(0.42, 0.45, 0.52)
    c.drawString(x, y, "Bu çıktı yapay zeka destekli bir KARAR DESTEK aracıdır; nihai klinik karar ve")
    y -= 12
    c.drawString(x, y, "sorumluluk onaylayan hekime aittir (MDR human-in-the-loop). KVKK gereği veriler anonimdir.")
    y -= 14
    c.setFont("DVS", 9)
    c.drawString(x, y, "QR'daki kodu GET /v1/verify/{kod} ucundan sorgularak raporun özgünlüğünü doğrulayabilirsiniz.")
    y -= 14
    c.setFont("DVSB", 9)
    c.setFillColorRGB(0.13, 0.24, 0.55)
    c.drawString(x, y, f"Doğrulama kodu: {code}")

    c.showPage()
    c.save()
    return buf.getvalue()
