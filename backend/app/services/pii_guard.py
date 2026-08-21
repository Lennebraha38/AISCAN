"""Defans-in-depth PII tarayıcı.

İstemci zaten anonimleştirir; backend yine de gelen masked_epikriz içinde
PII deseni görürse isteği reddeder (KVKK veri minimizasyonu md.4).
"""
from __future__ import annotations

import re

TC = re.compile(r"\b[1-9]\d{10}\b")
PHONE = re.compile(r"(?:\+90|0090|0)?[\s.(]*5\d{2}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IBAN = re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b")

_PATTERNS = {"TC_KIMLIK": TC, "TELEFON": PHONE, "EPOSTA": EMAIL, "IBAN": IBAN}


def scan_pii(text: str) -> list[str]:
    """Metinde tespit edilen PII türlerini döndürür (boş liste = temiz)."""
    found = []
    for name, pattern in _PATTERNS.items():
        if name == "TC_KIMLIK":
            for m in pattern.finditer(text):
                digits = m.group(0)
                # checksum doğrulaması: yanlış pozitif 11 haneleri ele
                d = [int(c) for c in digits]
                if ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10 == d[9] \
                        and sum(d[:10]) % 10 == d[10]:
                    found.append(name)
                    break
        elif pattern.search(text):
            found.append(name)
    return found
