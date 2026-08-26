"""Hasta PDF raporu ureticisi — kesinlesmemis analizler icin de calisir.

Bu rapor; bulgulari, riski, tani hipotezini ve karar durumunu tek PDF'te
toplar. Karar oncesi/bilgi amacli kullanilir; karar sonrasi resmi rapor
icin report_pdf.render_report kullanilir.
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

_DV = "/root/projeler/pulsar-kkds/backend/app/static/DejaVuSans.ttf"
_DVB = "/root/projeler/pulsar-kkds/backend/app/static/DejaVuSans-Bold.ttf"
_TTF = False
try:
    pdfmetrics.registerFont(TTFont("DVS", _DV))
    pdfmetrics.registerFont(TTFont("DVSB", _DVB))
    _TTF = True
except Exception:
    pass

F = "Helvetica"
FB = "Helvetica-Bold"


def patient_report(study: dict, analysis: dict) -> bytes:
    """Tek hasta raporu PDF'ini bayt olarak uretir."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x = 48
    y = H - 48

    def fnt(bold=False):
        if _TTF:
            return FB if bold else F
        return ("Helvetica-Bold" if bold else "Helvetica")

    def sz(pt):
        c.setFont(fnt(), pt)

    # --- Baslik ---
    c.setFont(fnt(True), 18)
    c.setFillColorRGB(0.13, 0.24, 0.55)
    c.drawString(x, y, "Pulsar-KKDS Hasta Raporu")
    y -= 22
    c.setFont(fnt(), 9)
    c.setFillColorRGB(0.42, 0.45, 0.52)
    c.drawString(x, y, "Yapay zeka destekli karar destek sistemi — bilgilendirme amacli cikti")
    y -= 20
    c.setStrokeColorRGB(0.8, 0.82, 0.88)
    c.line(x, y, W - x, y)
    y -= 18

    # --- Calisma Bilgileri ---
    def row(label, value, bold_v=False):
        nonlocal y
        c.setFont(fnt(), 9)
        c.setFillColorRGB(0.42, 0.45, 0.52)
        c.drawString(x, y, label)
        c.setFont(fnt(bold_v))
        c.setFillColorRGB(0.13, 0.24, 0.55)
        c.drawString(x + 120, y, str(value or "-"))
        y -= 16

    row("Calisma ID:", study.get("anon_study_hash", "-")[:16] + "...")
    row("Modalite:", study.get("modality", "-"))
    row("Tarih:", str(study.get("created_at", "-"))[:19])
    row("Analiz ID:", analysis.get("id", "-")[:16] + "...")
    y -= 6

    # --- Karar Durumu ---
    status = analysis.get("status", "BILINMIYOR")
    status_tr = {
        "PENDING_REVIEW": "Bekleyen Karar",
        "APPROVED": "Onaylandi",
        "REJECTED": "Reddedildi",
    }.get(status, status)
    status_color = {
        "APPROVED": (0.12, 0.56, 0.31),
        "REJECTED": (0.75, 0.22, 0.17),
    }.get(status, (0.72, 0.48, 0.16))

    c.setFont(fnt(True), 10)
    c.setFillColorRGB(0.13, 0.24, 0.55)
    c.drawString(x, y, "Karar Durumu:")
    c.setFont(fnt(True), 10)
    c.setFillColorRGB(*status_color)
    c.drawString(x + 100, y, status_tr.upper())
    y -= 20

    # --- Fuzon Risk ---
    risk = analysis.get("fusion_risk_score", 0)
    c.setFont(fnt(True), 10)
    c.setFillColorRGB(0.13, 0.24, 0.55)
    c.drawString(x, y, "Fuzon Risk Skoru:")
    c.setFont(fnt(True), 12)
    rc = (0.75, 0.22, 0.17) if risk >= 65 else (0.72, 0.48, 0.16) if risk >= 35 else (0.12, 0.56, 0.31)
    c.setFillColorRGB(*rc)
    c.drawString(x + 130, y, f"{risk:.1f} / 100")
    y -= 24

    # Risk cubugu
    bar_w = W - 2 * x
    bar_h = 10
    c.setFillColorRGB(0.9, 0.91, 0.94)
    c.roundRect(x, y, bar_w, bar_h, 4, fill=1, stroke=0)
    fill_w = max(0, min(bar_w, bar_w * risk / 100))
    c.setFillColorRGB(*rc)
    c.roundRect(x, y, fill_w, bar_h, 4, fill=1, stroke=0)
    y -= 24

    # --- Bulgular ---
    c.setFont(fnt(True), 11)
    c.setFillColorRGB(0.13, 0.24, 0.55)
    c.drawString(x, y, "Tespit Edilen Bulgular")
    y -= 18

    vr = analysis.get("vision_result") or {}
    findings = [f for f in vr.get("findings", []) if isinstance(f, dict)]
    sorted_f = sorted(findings, key=lambda f: f.get("probability", 0), reverse=True)
    meaningful = [f for f in sorted_f if f.get("probability", 0) >= 0.05]

    if meaningful:
        for f in meaningful:
            if y < 120:
                c.showPage()
                y = H - 48
            prob = f.get("probability", 0)
            pcolor = (0.75, 0.22, 0.17) if prob > 0.5 else (0.14, 0.34, 0.84)
            c.setFont(fnt(), 10)
            c.setFillColorRGB(0.13, 0.24, 0.55)
            c.drawString(x + 8, y, f.get("label", "?"))
            c.setFillColorRGB(*pcolor)
            c.setFont(fnt(True), 10)
            c.drawString(x + 200, y, f"{prob*100:.1f}%")
            y -= 4
            bar_x = x + 8
            bar_inner_w = 280
            c.setFillColorRGB(0.9, 0.91, 0.94)
            c.roundRect(bar_x, y, bar_inner_w, 6, 3, fill=1, stroke=0)
            c.setFillColorRGB(*pcolor)
            c.roundRect(bar_x, y, max(2, bar_inner_w * prob), 6, 3, fill=1, stroke=0)
            y -= 16
    else:
        c.setFont(fnt(), 10)
        c.setFillColorRGB(0.54, 0.58, 0.67)
        c.drawString(x + 8, y, "Belirgin bulgu saptanmadi")
        y -= 16

    y -= 8

    # --- EKG ---
    ecg = analysis.get("ecg_result") or {}
    if ecg:
        y -= 4
        c.setFont(fnt(True), 11)
        c.setFillColorRGB(0.13, 0.24, 0.55)
        c.drawString(x, y, "EKG Analizi")
        y -= 18
        sc = ecg.get("superclass", "-")
        conf = ecg.get("confidence", 0)
        hr = ecg.get("heart_rate_bpm")
        c.setFont(fnt(), 10)
        c.drawString(x + 8, y, f"Sinif: {sc.upper()}  |  Guven: {conf*100:.0f}%" +
                     (f"  |  Nabiz: {hr:.0f} bpm" if hr else ""))
        y -= 16
        if ecg.get("rationale"):
            c.setFont(fnt(), 9)
            c.setFillColorRGB(0.42, 0.45, 0.52)
            rationale = ecg["rationale"][:200]
            c.drawString(x + 8, y, rationale)
            y -= 14

    # --- Karar Notu ---
    decisions = analysis.get("decisions", [])
    if decisions:
        y -= 8
        c.setFont(fnt(True), 11)
        c.setFillColorRGB(0.13, 0.24, 0.55)
        c.drawString(x, y, "Hekim Kararlari")
        y -= 18
        for d in decisions:
            if y < 120:
                c.showPage()
                y = H - 48
            dc = d.get("decision", "-")
            dc_tr = "ONAY" if dc == "APPROVED" else "RED" if dc == "REJECTED" else dc
            dc_color = (0.12, 0.56, 0.31) if dc == "APPROVED" else (0.75, 0.22, 0.17)
            c.setFont(fnt(), 9)
            c.setFillColorRGB(*dc_color)
            c.drawString(x + 8, y, f"[{dc_tr}]")
            c.setFillColorRGB(0.13, 0.24, 0.55)
            c.setFont(fnt(), 9)
            c.drawString(x + 50, y, str(d.get("note", ""))[:120])
            y -= 14

    # --- Alt Bilgi ---
    if y < 100:
        c.showPage()
        y = H - 48

    y -= 10
    c.setStrokeColorRGB(0.8, 0.82, 0.88)
    c.line(x, y, W - x, y)
    y -= 16

    aid = analysis.get("id", "")
    dec = decisions[0] if decisions else {}
    dec_at = str(dec.get("decided_at", ""))
    code = hashlib.sha256(f"{aid}|{dec_at}".encode()).hexdigest()[:16].upper() if dec_at and dec_at != "None" else "BILINMIYOR"

    qrw = QrCodeWidget(f"PULSAR-KKDS:{code}")
    qb = qrw.getBounds()
    qsize = 60
    qd = Drawing(qsize, qsize, transform=[qsize / qb[2], 0, 0, qsize / qb[3], 0, 0])
    qd.add(qrw)
    qd.drawOn(c, W - x - qsize, y - qsize + 8)

    c.setFont(fnt(), 8)
    c.setFillColorRGB(0.42, 0.45, 0.52)
    c.drawString(x, y, "Bu cikti yapay zeka destekli KARAR DESTEK aracidir; nihai klinik karar")
    y -= 11
    c.drawString(x, y, "hekim sorumlulugundadir (MDR human-in-the-loop). KVKK geregi veriler anonimdir.")
    y -= 14
    c.setFont(fnt(), 9)
    c.setFillColorRGB(0.13, 0.24, 0.55)
    c.drawString(x, y, f"Dogrulama kodu: {code}")

    c.save()
    return buf.getvalue()
