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
import os
import re
from dataclasses import dataclass, field

from pii_nlp.masker import contains_pii, mask

_FIELD_RE = re.compile(r"^#\s*(Age|Sex|Dx|Rx|Hx|Sx)\s*:\s*(.*)$", re.IGNORECASE)
_ANY_FIELD_RE = re.compile(r"^#\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*)$")
_FREE_TEXT_FIELDS = {"rx", "hx", "sx"}
# Değeri doğrudan PHI sayılan, tanınan başlık alan adları (küçük harf).
_PHI_FIELD_NAMES = {
    "patientname", "patient", "patientid", "name", "id", "dob", "birthdate",
    "birth", "birthday", "birthname", "comments", "comment", "address",
    "hospital", "institution", "institutionname", "physician", "doctor",
    "mrn", "lastname", "firstname", "surname", "ssn", "accession",
    "accessionnumber", "phone", "telephone", "email", "tc", "tcno",
    "gender",
}
# Alan adı bu parçalardan birini içeriyorsa PHI alanı sayılır.
_PHI_FIELD_HINTS = (
    "patient", "physician", "doctor", "mrn", "dob", "birthdate", "birth",
    "ssn", "accession", "address", "institution", "hospital",
)


def _bilinen_phi_alani(name: str) -> bool:
    """Alan adı bilinen bir PHI alanına benziyorsa True döner."""
    n = name.lower()
    return n in _PHI_FIELD_NAMES or any(h in n for h in _PHI_FIELD_HINTS)


def _resolve_salt(salt: str | None) -> str:
    """Salt'ı çöz: açık değer yoksa ANON_SALT ortam değişkeni; yoksa hata."""
    resolved = salt if salt else os.getenv("ANON_SALT")
    if not resolved:
        raise ValueError("ANON_SALT (veya açık salt) zorunludur")
    return resolved


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


def deidentify_hea(content: str, salt: str | None = None) -> HeaDeidentResult:
    """WFDB .hea metnini KVKK uyumlu hale getirir."""
    salt = _resolve_salt(salt)
    out_lines: list[str] = []
    findings: list[Finding] = []
    pseudonym: str | None = None
    pseudonyms: dict[str, str] = {}

    for raw in content.splitlines():
        line = raw.rstrip("\n")
        if not line.startswith("#"):
            # teknik satir: ilk token kayit adi (.hea) veya <ad>.mat referansi
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                first = stripped.split()[0]
                m_rec = re.match(r"^([A-Za-z0-9][A-Za-z0-9_-]*?)(\.mat)?$", first)
                if m_rec:
                    rec_id = m_rec.group(1)
                    if rec_id not in pseudonyms:
                        new_id = _pseudonym(rec_id, salt)
                        pseudonyms[rec_id] = new_id
                        if pseudonym is None:
                            pseudonym = new_id
                        findings.append(
                            Finding("record_id", "hash", f"{rec_id} -> {new_id}")
                        )
                    line = line.replace(rec_id, pseudonyms[rec_id], 1)
            out_lines.append(line)
            continue

        m = _FIELD_RE.match(line)
        if m:
            name, value = m.group(1), m.group(2).strip()
            key = name.lower()
            if key == "age":
                if value.isdigit():
                    band = _age_band(int(value))
                    out_lines.append(f"#Age: {band}")
                    findings.append(Finding("Age", "band", f"{value} -> {band}"))
                else:
                    findings.append(Finding("Age", "remove", value))
            elif key == "sex":
                findings.append(Finding("Sex", "remove", value))
            elif key in _FREE_TEXT_FIELDS:
                if value and contains_pii(value):
                    res = mask(value, mask_dates=True)
                    out_lines.append(f"#{name}: {res.masked_text}")
                    findings.append(Finding(name, "mask", f"{len(res.findings)} PII bulundu"))
                else:
                    out_lines.append(line)
            else:  # Dx korunur (analiz icin sart)
                out_lines.append(line)
            continue

        # Taninmayan "# Alan: deger" satirlari: PHI ise kaldir, degilse maskele.
        am = _ANY_FIELD_RE.match(line)
        if am:
            name, value = am.group(1), am.group(2).strip()
            if _bilinen_phi_alani(name):
                findings.append(Finding(name, "remove", value))
                continue
            if value and contains_pii(value):
                res = mask(value, mask_dates=True)
                out_lines.append(f"#{name}: {res.masked_text}")
                findings.append(Finding(name, "mask", f"{len(res.findings)} PII bulundu"))
            else:
                out_lines.append(line)
            continue

        # Serbest "# yorum" satiri: PII tasiyorsa maskele, yoksa koru.
        # Sinyal tanim satirlari (# ile baslamaz) korunur; aksi halde WFDB
        # bicimi (or. taban tarih alani) bozulur.
        if line.lstrip().startswith("#") and contains_pii(line):
            res = mask(line, mask_dates=True)
            out_lines.append(res.masked_text)
            findings.append(Finding("comment", "mask", f"{len(res.findings)} PII bulundu"))
        else:
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
