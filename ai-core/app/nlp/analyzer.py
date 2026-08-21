"""Türkçe epikriz analiz motoru.

Kural + tıbbi sözlük tabanlı aciliyet sınıflandırması ve token düzeyinde
attribution (metin XAI). Mimari, BERTurk fine-tune modeliyle değiştirilebilir
şekilde tasarlandı: ``BERTurkBackend`` arayüzü aynı şemayı üretir
(bkz. scripts/train/train_nlp.py).

Negasyon yönetimi: terimden önceki pencerede "yok / izlenmedi / saptanmadı /
kalmadı / -sız" gibi ipuçları varsa katkı ters işaretlenir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# (terim regex'i, ağırlık 0-1, açıklama)
LEXICON: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\b(?:büyük|geniş)\s+(?:alan\s+)?kapiller\s+sızıntı", re.I), 0.55, "vasküler"),
    (re.compile(r"\b\d{1,2}(?:[.,]\d)?\s*(?:mm|cm)\s*(?:boyutlu\s*)?(?:nodül|lezyon|kitle)", re.I), 0.85, "nodül/kitle"),
    (re.compile(r"\b(?:nodül|nodule)\b", re.I), 0.60, "nodül"),
    (re.compile(r"\b(?:kitle|mass|tümör|kitle)\b", re.I), 0.80, "kitle"),
    (re.compile(r"\bpnömotoraks\b", re.I), 0.90, "pnömotoraks"),
    (re.compile(r"\bplevral?\s+efüzyon\b|\befüzyon\b", re.I), 0.70, "efüzyon"),
    (re.compile(r"\bkonsolid(?:as)?yon\b", re.I), 0.65, "konsolidasyon"),
    (re.compile(r"\bpnömon[iı]\b|\bgöğüs\s+hastalıkları.*enfeksiyon\b", re.I), 0.75, "pnömoni"),
    (re.compile(r"\batelektaz[iı]\b", re.I), 0.50, "atelektazi"),
    (re.compile(r"\bkardiomegal[iı]\b", re.I), 0.55, "kardiomegali"),
    (re.compile(r"\btoraks\s*(?:bt|mr)\b", re.I), 0.30, "ileri görüntüleme"),
    (re.compile(r"\bmetastaz\b|\bmetastatik\b", re.I), 0.95, "metastaz"),
    (re.compile(r"\bmalign(?:ite|n)?\b|\bkanser\b", re.I), 0.90, "malignite şüphesi"),
    (re.compile(r"\bakut\s*koroner\b|\bmiyokard\s*enfarktüsü\b", re.I), 0.95, "kardiyak acil"),
    (re.compile(r"\bsolunum\s*sıkıntısı\b|\bdispne\b", re.I), 0.60, "solunum sıkıntısı"),
    (re.compile(r"\bhemoptizi\b", re.I), 0.70, "hemoptizi"),
    (re.compile(r"\bsiddetli\s*ağrı|\bşiddetli\b", re.I), 0.45, "şiddetli semptom"),
    (re.compile(r"\btakip\s*(?:önerilir|önerildi)\b", re.I), 0.25, "takip önerisi"),
    (re.compile(r"\bdoğaldır\b|\bnegatif\b|\bnormal\s*sınırlar(?:da)?\b", re.I), -0.30, "normal bulgu"),
]

NEGATION_CUES = re.compile(
    r"\b(yok|yoktur|izlenmedi|izlenmemiştir|saptanmadı|saptanmamıştır|"
    r"görülmedi|tespit edilmedi|kalmamış|yoktur-?dur|eksisite yok|-sız|-siz)\b",
    re.IGNORECASE,
)

URGENCY_BANDS = {"düşük": (0, 34), "orta": (35, 64), "yüksek": (65, 100)}


@dataclass
class TokenAttribution:
    text: str
    start: int
    end: int
    score: float
    negated: bool

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "score": round(self.score, 3),
            "negated": self.negated,
        }


def _is_negated(text: str, start: int, end: int, back_window: int = 48,
                fwd_window: int = 32) -> bool:
    """Türkçe SÖZ dizilişi nedeniyle hem geriye ('nodül yok') hem ileriye
    ('nodül izlenmedi') bakılır."""
    backward = text[max(0, start - back_window):start]
    forward = text[end:end + fwd_window]
    return bool(NEGATION_CUES.search(backward) or NEGATION_CUES.search(forward))


def analyze_epikriz(text: str) -> dict:
    """Maskelenmiş epikriz metnini analiz eder.

    Dönüş: {urgency, urgency_score, confidence, highlighted_tokens, rationale}
    """
    raw_score = 0.0
    tokens: list[TokenAttribution] = []
    contributions: list[tuple[str, float]] = []

    for pattern, weight, desc in LEXICON:
        for m in pattern.finditer(text):
            negated = _is_negated(text, m.start(), m.end())
            signed = -weight if negated else weight
            raw_score += signed
            score01 = min(max((signed + 1.0) / 2.0, 0.0), 1.0)
            tokens.append(TokenAttribution(m.group(0), m.start(), m.end(), score01, negated))
            if not negated:
                contributions.append((desc, weight))

    urgency_score = int(round(min(max(raw_score * 28.0, 0.0), 100)))
    urgency = next(
        band for band, (lo, hi) in URGENCY_BANDS.items() if lo <= urgency_score <= hi
    )
    confidence = round(min(0.55 + abs(raw_score) * 0.12, 0.97), 2)

    top = sorted(contributions, key=lambda x: x[1], reverse=True)[:3]
    rationale = (
        "Risk oluşturan başlıca ifadeler: "
        + ", ".join(f"{name} ({w:.2f})" for name, w in top)
        if top
        else "Belirgin risk oluşturan ifade saptanmadı."
    )

    return {
        "urgency": urgency,
        "urgency_score": urgency_score,
        "confidence": confidence,
        "highlighted_tokens": [t.to_dict() for t in sorted(tokens, key=lambda t: t.start)],
        "rationale": rationale,
    }
