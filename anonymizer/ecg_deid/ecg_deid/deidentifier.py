"""Pulsar-KKDS EKG/WFDB basligi (.hea) anonimlestirme.

KVKK uyumu: PhysioNet tarzi WFDB .hea basliklari hasta verisi tasir:
    #Age: 85        -> yasi dogrudan verir (quasi-identifier)
    #Sex: Male      -> quasi-identifier
    #Rx/#Hx/#Sx     -> serbest metin; PII tasıyabilir
Kayit adi (JS00001) kurum icin hasta numarasidir -> pseudonymize.

Strateji (k-anonimlik):
    - Kayit adi  : SHA256(salt+deger)[0:16] pseudonym
    - #Age       : on yillik banda indirgenir ("50-59") veya kaldirilir
    - #Sex       : kaldirilir (DICOM cleaner ile tutarli)
    - #Dx        : korunur (analiz icin sart - saglik verisi olarak
                   yalnizca anonimlestirilmis kayit baglamiyla saklanir)
    - #Rx/#Hx/#Sx: pii_nlp maskesinden gecirilir
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from pii_nlp.masker import contains_pii, mask

_AGE_RE = re.compile(r"^#Age:\s*(\d+)\s*$")
_FIELD_RE = re.compile(r"^#(Age|Sex|Dx|Rx|Hx|Sx):(.*)$")
_FREE_TEXT_FIELDS = {"Rx", "Hx", "Sx"}


@dataclass
class Finding:
    field_name: str
    action: str
    detail: str = ""


@dataclass
class HeaDeidentResult:
    content: str
    pseudonym: str | None
    findings: list[Finding] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return all(f.action != "leak" for f in self.findings)


def _pseudonym(value: str, salt: str) -> str:
    return hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:16]


def _age_band(age: int) -> str:
    lo = (age // 10) * 10
    return f"{lo}-{lo + 9}"


def deidentify_hea(content: str, salt: str = "pulsar-kkds") -> HeaDeidentResult:
    """WFDB .hea metnini KVKK uyumlu hale getirir."""
    out_lines: list[str] = []
    findings: list[Finding] = []
    pseudonym: str | None = None
    original_id: str | None = None

    for raw in content.splitlines():
        line = raw.rstrip("\n")
        if not line.startswith("#"):
            # teknik satir: ilk token kayit adi (.hea) veya <ad>.mat referansi
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                first = stripped.split()[0]
                m_rec = re.match(r"^([A-Za-z]{2}\d{5})(\.mat)?$", first)
                if m_rec:
                    if original_id is None:
                        original_id = m_rec.group(1)
                        new_id = _pseudonym(original_id, salt)
                        pseudonym = new_id
                        findings.append(
                            Finding("record_id", "hash", f"{original_id} -> {new_id}")
                        )
                    line = line.replace(original_id, pseudonym or "", 1)
            out_lines.append(line)
            continue

        m = _FIELD_RE.match(line)
        if not m:
            out_lines.append(line)
            continue

        name, value = m.group(1), m.group(2).strip()
        if name == "Age":
            am = _AGE_RE.match(f"#Age: {value}")
            if am:
                band = _age_band(int(am.group(1)))
                out_lines.append(f"#Age: {band}")
                findings.append(Finding("Age", "band", f"{value} -> {band}"))
            else:
                findings.append(Finding("Age", "remove", value))
        elif name == "Sex":
            findings.append(Finding("Sex", "remove", value))
        elif name in _FREE_TEXT_FIELDS:
            if value and contains_pii(value):
                res = mask(value)
                out_lines.append(f"#{name}: {res.masked_text}")
                findings.append(Finding(name, "mask", f"{len(res.findings)} PII bulundu"))
            else:
                out_lines.append(line)
        else:  # Dx ve digerleri korunur
            out_lines.append(line)

    result = HeaDeidentResult(
        content="\n".join(out_lines) + ("\n" if content.endswith("\n") else ""),
        pseudonym=pseudonym,
        findings=findings,
    )

    # sizinti taramasi: son metinde hala PII var mi?
    for i, ln in enumerate(result.content.splitlines()):
        if ln.startswith("#") and contains_pii(ln):
            result.findings.append(Finding(f"line{i}", "leak", ln[:60]))
    return result


def scan_hea_leaks(content: str) -> list[str]:
    """Anonimlestirilmis .hea icerisinde kalan PII satirlarini dondurur."""
    return [ln for ln in content.splitlines() if ln.startswith("#") and contains_pii(ln)]
