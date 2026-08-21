"""Türkçe epikriz metinleri için PII maskeleme.

KVKK gereği metin, sunucuya gönderilmeden önce istemci tarafında maskelenir.
Maskelenen tür etiketi korunur (ör. [TC_KIMLIK]) böylece aşağı akış NLP
modeli bağlamı yitirmez.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .patterns import (
    ADRES,
    DOB_CONTEXT,
    GENEL_TARIH,
    KISI_ADI_BUYUK,
    KISI_ADI_UNVANLU,
    KURUM,
    PATTERNS,
    tc_kimlik_gecerli,
)

LABELS = {
    "TC_KIMLIK": "[TC_KIMLIK]",
    "PASAPORT": "[PASAPORT]",
    "IBAN": "[IBAN]",
    "EPOSTA": "[EPOSTA]",
    "TELEFON": "[TELEFON]",
    "PLAKA": "[PLAKA]",
    "TARIH": "[TARIH]",
    "KISI_ADI": "[KISI_ADI]",
    "KURUM": "[KURUM]",
    "ADRES": "[ADRES]",
}


@dataclass
class Finding:
    type: str
    start: int
    end: int
    value: str
    label: str

    def to_dict(self) -> dict:
        return {"type": self.type, "start": self.start,
                "end": self.end, "label": self.label}


@dataclass
class MaskResult:
    masked_text: str
    findings: list[Finding] = field(default_factory=list)
    original_length: int = 0

    def to_dict(self) -> dict:
        return {
            "masked_text": self.masked_text,
            "findings": [f.to_dict() for f in self.findings],
            "pii_count": len(self.findings),
        }


def _collect(text: str, mask_dates: bool) -> list[Finding]:
    raw: list[tuple[int, int, str, str]] = []  # (start, end, type, value)

    for m in DOB_CONTEXT.finditer(text):
        value_start = m.start(1)
        raw.append((value_start, m.end(1), "TARIH", m.group(1)))

    for ptype, pattern, _prio in PATTERNS:
        for m in pattern.finditer(text):
            value = next((g for g in m.groups() if g), m.group(0))
            start = m.start() if not m.groups() else m.start(1) if value == m.group(1) else m.start()
            # TC grubu yakalandıysa checksum doğrula; geçersizse yine de işaretle.
            if ptype == "TC_KIMLIK":
                digits = re.sub(r"\D", "", value)
                if len(digits) != 11:
                    continue
            raw.append((start, m.end(), ptype, value))

    if mask_dates:
        for m in GENEL_TARIH.finditer(text):
            if any(s <= m.start() < e for s, e, *_ in raw):
                continue
            raw.append((m.start(), m.end(), "TARIH", m.group(0)))

    for m in KURUM.finditer(text):
        raw.append((m.start(), m.end(), "KURUM", m.group(0)))
    for m in ADRES.finditer(text):
        raw.append((m.start(), m.end(), "ADRES", m.group(0)))
    for m in KISI_ADI_UNVANLU.finditer(text):
        raw.append((m.start(), m.end(), "KISI_ADI", m.group(0)))
    for m in KISI_ADI_BUYUK.finditer(text):
        if any(s <= m.start() < e for s, e, *_ in raw):
            continue
        raw.append((m.start(), m.end(), "KISI_ADI", m.group(0)))

    # Örtüşenleri ele: önce başlangıç, sonra uzunluk.
    raw.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    picked: list[tuple[int, int, str, str]] = []
    last_end = -1
    for s, e, t, v in raw:
        if s >= last_end:
            picked.append((s, e, t, v))
            last_end = e
    return [Finding(t, s, e, v, LABELS[t]) for s, e, t, v in picked]


def mask(text: str, mask_dates: bool = False) -> MaskResult:
    """Metindeki PII'yi maskeler.

    Dönüş: MaskResult(masked_text, findings[span bilgili], original_length)
    """
    findings = _collect(text, mask_dates)
    out = text
    for f in reversed(findings):
        out = out[:f.start] + f.label + out[f.end:]
    return MaskResult(masked_text=out, findings=findings, original_length=len(text))


def contains_pii(text: str) -> bool:
    """Defans-in-depth kontrolü: sunucu tarafı da bunu çağırabilir."""
    return bool(_collect(text, mask_dates=False))
