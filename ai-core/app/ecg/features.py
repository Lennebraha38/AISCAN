"""El yapimi EKG ozellikleri + sklearn baseline (referans noktasi).

Ozellik ailesi (kayit basina ~40 boyut):
    - Ritim: kalp hizi, RR araligi istatistikleri (std, RMSSD, pNN50 benzeri),
      RR duzensizlik indeksi (AFIB ayirt edici)
    - Morfoloji: derivasyon basina enerji, tepe-genişlik, QRS benzeri
      egim olcumleri, frekans bant gucleri (5-15 Hz QRS bandina karsi 0.5-5 Hz)
    - Kanal iliskisi: derivasyon ciftleri korelasyon ozeti

Amaç: derin modele gecmeden once makul bir macro F1 referansi elde etmek;
jüriye "basit model bile X seviyesinde, derin model Y" hikayesi anlatmak.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import welch

from app.ecg.preprocess import detect_rpeaks


def rr_features(sig: np.ndarray, fs: int = 250) -> np.ndarray:
    """R-dorugu bazli ritim ozellikleri (en iyi derivasyondan)."""
    best, best_n = sig[0], -1
    for lead in sig:
        n = len(detect_rpeaks(lead, fs))
        if 3 < n > best_n:
            best, best_n = lead, n
    peaks = detect_rpeaks(best, fs)
    if len(peaks) < 3:
        return np.zeros(8, dtype=np.float32)
    rr = np.diff(peaks) / fs  # saniye
    rr = rr[(rr > 0.3) & (rr < 3.0)]
    if len(rr) < 2:
        return np.zeros(8, dtype=np.float32)
    diff_rr = np.diff(rr)
    mean_rr = float(rr.mean())
    hr = 60.0 / mean_rr if mean_rr > 0 else 0.0
    return np.asarray(
        [
            hr,
            rr.std(),
            np.mean(np.abs(diff_rr)),           # RMSSD benzeri
            (np.abs(diff_rr) > 0.05).mean(),    # pNN50 benzeri
            rr.max() / max(rr.min(), 1e-6),     # duzensizlik orani
            np.percentile(rr, 90) / max(np.percentile(rr, 10), 1e-6),
            len(rr),                            # 10 sn icindeki vurus sayisi
            mean_rr,
        ],
        dtype=np.float32,
    )


def morph_features(sig: np.ndarray, fs: int = 250) -> np.ndarray:
    """Derivasyon basina morfoloji/frekans ozetleri."""
    feats = []
    for lead in sig:
        energy = float((lead**2).mean())
        qrs_band = _bandpower(lead, fs, 5.0, 15.0)
        low_band = _bandpower(lead, fs, 0.5, 5.0)
        total = qrs_band + low_band + 1e-8
        feats.extend(
            [
                energy,
                float(lead.max() - lead.min()),
                float(np.abs(np.gradient(lead)).mean()),
                qrs_band / total,
                float(np.median(np.abs(lead))),
            ]
        )
    return np.asarray(feats, dtype=np.float32)


def channel_features(sig: np.ndarray) -> np.ndarray:
    """Derivasyonlar arasi iliski ozeti."""
    flat = sig.reshape(sig.shape[0], -1)
    corr = np.corrcoef(flat)
    iu = np.triu_indices_from(corr, k=1)
    vals = corr[iu]
    return np.asarray(
        [float(np.nanmean(vals)), float(np.nanstd(vals)), float(np.nanmin(vals))],
        dtype=np.float32,
    )


def _bandpower(x: np.ndarray, fs: int, lo: float, hi: float) -> float:
    f, pxx = welch(x, fs=fs, nperseg=min(256, len(x)))
    m = (f >= lo) & (f <= hi)
    return float(pxx[m].sum())


def extract_features(sig: np.ndarray, fs: int = 250) -> np.ndarray:
    """(12, L) on islenmis kayit -> tek boyutlu ozellik vektoru."""
    parts = [rr_features(sig, fs), morph_features(sig, fs), channel_features(sig)]
    out = np.concatenate(parts)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
