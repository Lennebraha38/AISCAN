"""SNOMED-CT -> ust sinif haritalama (TEKNOFEST Lise/Kardiyoloji sartnamesi).

Ust siniflar (sartname 3.1):
    0 = normal      (Normal EKG)
    1 = arrhythmia  (Ritim Bozukluklari)
    2 = block       (Iletim Bozukluklari)

Coklu etiket kurali (belgeli tasarim karari):
    Bir kayitta birden fazla hedef sinifa ait kod varsa oncelik sirasi:
        block > arrhythmia > normal
    Gerekce (veri analizi, n=42.625):
        - "aritmi+blok" ortak kayitlar 2.771 adettir; aritmi-onceligi
          altinda blok sinifi yalnizca 174 ornekle kalir ve macro F1
          bu sinifta coler.
        - Blok-onceligi ile blok sinifi 2.983 ornege cikar; bloklar
          (LBBB/RBBB/AVB) QRS morfolojisinde tutarli, modelin
          ogrenmesi kolay isaretlerdir.
        - Kural deterministiktir ve teknik raporda seffaf raporlanir.

Hedef disi kodlar (MI, LVH, STTC vb.) tek baslarina kaydi eler;
ancak kayitta SR varsa ve hedef kod yoksa kayit "normal" sinifina girer.
"""

from __future__ import annotations

from pathlib import Path

SUPERCLASSES = ("normal", "arrhythmia", "block")
# Egitim/inference katmaninin kullandigi takma ad
CLASS_NAMES = SUPERCLASSES

# --- Ritim Bozukluklari (Arrhythmias) ------------------------------------
ARRHYTHMIA_CODES: frozenset[str] = frozenset(
    {
        "164889003",  # AFIB - Atrial Fibrillation
        "164890007",  # AF   - Atrial Flutter
        "713422000",  # AT   - Atrial Tachycardia
        "426761007",  # SVT  - Supraventricular Tachycardia
        "284470004",  # APB  - Atrial Premature Beats
        "251173003",  # ABI  - Atrial Bigeminy
        "17338001",   # VPB  - Ventricular Premature Beat
        "11157007",   # VB   - Ventricular Bigeminy
        "75532003",   # VEB  - Ventricular Escape Beat
        "251180001",  # VET  - Ventricular Escape Trigeminy
        "426995002",  # JEB  - Junctional Escape Beat
        "251164006",  # JPT  - Junctional Premature Beat
        "427393009",  # SA   - Sinus Irregularity
        "426177001",  # SB   - Sinus Bradycardia
        "427084000",  # ST   - Sinus Tachycardia
        "233896004",  # AVNRT
        "233897008",  # AVRT
        "195101003",  # SAAWR / WAVN - Atrial Wandering Rhythm
    }
)

# --- Iletim Bozukluklari (Conduction Blocks) ------------------------------
BLOCK_CODES: frozenset[str] = frozenset(
    {
        "270492004",  # 1AVB  - 1st degree AV block
        "195042002",  # 2AVB  - 2nd degree AV block
        "54016002",   # 2AVB1 - Mobitz type I
        "28189009",   # 2AVB2 - Mobitz type II
        "27885002",   # 3AVB  - 3rd degree AV block
        "233917008",  # AVB   - unspecified AV block
        "164909002",  # LBBB  (+ LBBBB/LFBBB es anlamlilari)
        "59118001",   # RBBB
        "698252002",  # IVB/IDC - Intraventricular block
    }
)

# --- Normal ---------------------------------------------------------------
NORMAL_CODES: frozenset[str] = frozenset(
    {
        "426783006",  # SR - Sinus Rhythm
    }
)

CLASS_TO_INDEX = {name: i for i, name in enumerate(SUPERCLASSES)}
INDEX_TO_CLASS = dict(enumerate(SUPERCLASSES))

# Asama 2 hazirligi: alt tani etiketleri (kesin liste PSR sonrasi duyurulur,
# bu harita hiyerarsik kafa icin iskelet saglar).
SUBCLASS_BY_CODE: dict[str, str] = {
    "164889003": "AFIB",
    "164890007": "AFL",
    "713422000": "AT",
    "426761007": "SVT",
    "284470004": "APB",
    "17338001": "VPB",
    "426177001": "SB",
    "427084000": "STach",
    "427393009": "SA",
    "233896004": "AVNRT",
    "233897008": "AVRT",
    "270492004": "1AVB",
    "195042002": "2AVB",
    "54016002": "2AVB1",
    "28189009": "2AVB2",
    "27885002": "3AVB",
    "164909002": "LBBB",
    "59118001": "RBBB",
    "698252002": "IVCB",
}


def load_snomed_csv(path: str | Path) -> dict[str, str]:
    """ConditionNames_SNOMED-CT.csv -> {snomed_kod: akronim}."""
    import csv

    mapping: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("Snomed_CT") or "").strip()
            acro = (row.get("Acronym Name") or "").strip()
            if code and acro:
                mapping.setdefault(code, acro)
    return mapping


def assign_superclass(dx_codes: list[str]) -> str | None:
    """Dx kod listesini tek ust sinifa indirger; hedef yoksa None doner.

    Oncelik: block > arrhythmia > normal (modul docstring'indeki veri
    analizine bakiniz).
    """
    codes = {c.strip() for c in dx_codes if c.strip()}
    if codes & BLOCK_CODES:
        return "block"
    if codes & ARRHYTHMIA_CODES:
        return "arrhythmia"
    if codes & NORMAL_CODES:
        return "normal"
    return None


def subclasses_for(dx_codes: list[str]) -> list[str]:
    """Kaydin alt tani etiketleri (asama 2 hiyerarsik kafa icin)."""
    out = []
    for c in dx_codes:
        s = SUBCLASS_BY_CODE.get(c.strip())
        if s and s not in out:
            out.append(s)
    return out
