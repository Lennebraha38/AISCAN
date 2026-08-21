"""Türkçe klinik metinler için PII tespit desenleri."""
from __future__ import annotations

import re


def tc_kimlik_gecerli(num: str) -> bool:
    """11 haneli TC Kimlik No doğrulama (resmi checksum algoritması)."""
    if not re.fullmatch(r"[1-9][0-9]{10}", num):
        return False
    d = [int(c) for c in num]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    if (odd * 7 - even) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


# (tip, derlenmiş desen, öncelik) — küçük öncelik önce uygulanır.
PATTERNS: list[tuple[str, re.Pattern, int]] = [
    ("TC_KIMLIK",
     re.compile(r"(?:T\.?C\.?\s*Kimlik\s*(?:No|Numarası)?\s*[:=]?\s*)(\d{11})|\b([1-9]\d{10})\b"),
     0),
    ("PASAPORT",
     re.compile(r"\b(?:[A-Z]{1,2}\d{7,8}|U\+[A-Z]\d{7})\b"),
     1),
    ("IBAN",
     re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b"),
     1),
    ("EPOSTA",
     re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
     1),
    ("TELEFON",
     re.compile(
         r"(?:\+90|0090|0)?[\s.(]*5\d{2}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b"
         r"|\b0\d{3}[\s]-?\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b"
     ),
     2),
    ("PLAKA",
     re.compile(r"\b\d{2}\s?(?:[A-Z]|[A-Z]{2,3})\s?\d{2,4}\b"),
     3),
]

# Bağlam duyarlı doğum tarihi: "doğum tarihi 01.01.1980", "D.T.: 01/01/1980"
DOB_CONTEXT = re.compile(
    r"(?:d(?:o|ö)[gğ](?:u|ü)m\s*t(?:a)r[ii]h[iı]|d\.?t\.?)\s*[:=]?\s*"
    r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{8})",
    re.IGNORECASE,
)

GENEL_TARIH = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")

# Kurum adı: hastane/klinik/poliklinik içeren ifadeler
KURUM = re.compile(
    r"\b[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ.]*(?:\s+(?:ve|ile|[A-ZÇĞİÖŞÜ][\wçğıöşü]*))*"
    r"\s+(?:Devlet\s+)?(?:Hastanesi|Hastane[sıi]|Medikal\s*Merkez|Tıp\s*Merkezi|"
    r"Poliklini[iğ]|Göz\s*Hastalıkları\s*Merkezi)\b"
    r"|\b[A-ZÇĞİÖŞÜ][\wçğıöşü]*\s+Üniversitesi\s+Tıp\s+Fakültesi(?:\s+Hastanesi)?\b",
)

# Adres: mahalle/cadde/sokak kalıpları
ADRES = re.compile(
    r"\b[A-ZÇĞİÖŞÜ][\wçğıöşü]*(?:\s+[A-ZÇĞİÖŞÜ]?[\wçğıöşü.]*)*"
    r"\s+(?:Mah(?:allesi)?\.?|Cad(?:desi)?\.?|Sok(?:ağı)?\.?)"
    r"(?:\s*,?\s*(?:No\s*:?\s*\d+[/\w]*|Kat\s*:?\s*\d+|Daire\s*:?\s*\d+))*",
)

# Unvanlı kişi adları: "Op. Dr. Ahmet Yılmaz", "Prof.Dr. Ayşe Demir"
UNVANLAR = (
    r"(?:Prof(?:\.|\.)?\s*Dr\.?|Do[cç]\.\s*Dr\.?|Op\.\s*Dr\.?|Uz(?:m)?\.\s*Dr\.?|"
    r"Dr\.?|[Dd]oktor|Hasta|Sn\.?)"
)
KISI_ADI_UNVANLU = re.compile(
    UNVANLAR + r"\s+([A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+){1,2})"
)
# BÜYÜK HARF ad soyad: "AHMET YILMAZ"
KISI_ADI_BUYUK = re.compile(r"\b([A-ZÇĞİÖŞÜ]{2,}(?:\s+[A-ZÇĞİÖŞÜ]{2,}){1,2})\b")
