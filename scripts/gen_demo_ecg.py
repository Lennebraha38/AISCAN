"""Demo icin SENTETIK 12-derivasyonlu EKG kayitlari uretir.

UYARI: Bu kayitlar GERCEK hasta verisi DEGILDIR. Matematiksel olarak uretilmis
(sentetik) dalga formlaridir; yalnizca arayuz/entegrasyon demolarinda ve
birim testlerinde kullanilmak uzere tasarlanmistir. Kayit kimlikleri SYNxxxx
olup PhysioNet ECG-Arrhythmia kayitlariyla KARISTIRILMAMALIDIR.

Kullanim:
    python scripts/gen_demo_ecg.py [cikti_dizini]
    (varsayilan cikti: data/ecg/demo)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

FS = 500
DUR = 10
N = FS * DUR  # 5000 ornek

# 12 standart derivasyon icin (isaret, olcek) - kabaca morfoloji taklidi
# (I, II, III, aVR, aVL, aVF, V1..V6)
LEAD_SCALE = np.array([
    0.6, 1.0, 0.5, -0.7, 0.3, 0.7,   # I, II, III, aVR, aVL, aVF
    -0.4, 0.2, 0.9, 1.2, 1.1, 0.8,   # V1..V6
])

LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]

# Demo senaryolari: (kayit no, etiket, Dx SNOMED, ritim, QRS genisligi sn, RR duzensiz)
# Kayit numaralari WFDB kuralina ([A-Za-z]{2}\d{5}) uyar; boylece .hea
# anonimlestirme hattindaki kayit-no pseudonymize adimi da demoda gorulur.
SCENARIOS = [
    ("SX00001", "normal", "426783006", "normal", 0.09, False),
    ("SX00002", "afib", "164889003", "afib", 0.09, True),
    ("SX00003", "lbbb", "164909002", "lbbb", 0.15, False),
]


def _gaussian(t: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    return np.exp(-0.5 * ((t - mu) / sigma) ** 2)


def _beat(t_rel: np.ndarray, qrs: float, p_wave: bool, notched: bool) -> np.ndarray:
    """RR araligina gore normalize edilmis tek atim morfolojisi."""
    w = np.zeros_like(t_rel)
    if p_wave:
        w += 0.12 * _gaussian(t_rel, 0.0, 0.025)          # P
    # QRS: Q, R, S
    w -= 0.10 * _gaussian(t_rel, 0.10, qrs * 0.25)
    w += 1.00 * _gaussian(t_rel, 0.13, qrs * 0.35)         # R
    if notched:
        w += 0.35 * _gaussian(t_rel, 0.16, qrs * 0.18)     # LBBB çentik
    w -= 0.22 * _gaussian(t_rel, 0.20, qrs * 0.30)         # S
    w += 0.25 * _gaussian(t_rel, 0.34, 0.06)               # T
    return w


def synth_ecg(kind: str, qrs: float, irregular: bool, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(N) / FS
    base = np.zeros(N)

    # RR araliklari
    mean_rr = 0.83  # ~72 bpm
    rr = []
    t_beat = 0.4
    while t_beat < DUR - 0.3:
        rr.append(t_beat)
        if irregular:
            t_beat += float(rng.uniform(0.45, 1.25))  # AFib: duzensiz
        else:
            t_beat += mean_rr + float(rng.normal(0, 0.02))

    p_wave = kind == "normal"
    notched = kind == "lbbb"
    for start in rr:
        idx = np.where((t >= start - 0.05) & (t < start + 0.5))[0]
        if idx.size == 0:
            continue
        trel = t[idx] - start
        base[idx] += _beat(trel, qrs, p_wave, notched)

    # Bazal gurultu + hafif baseline wander
    base += rng.normal(0, 0.015, N)
    base += 0.05 * np.sin(2 * np.pi * 0.25 * t)

    sig = np.outer(LEAD_SCALE, base)  # (12, N)
    sig += rng.normal(0, 0.01, sig.shape)
    return sig.astype(np.float64)


def write_hea(path: Path, rec: str, dx: str, age_band: str, sex: str, label: str) -> None:
    lines = [f"{rec} 12 {FS} {N}"]
    for lead in LEADS:
        lines.append(f"{rec}.mat 16+24 1000/mV 16 0 0 0 0 {lead}")
    lines.append(f"#Scenario: {label}")
    lines.append(f"#Age: {age_band}")
    lines.append(f"#Sex: {sex}")
    lines.append(f"#Dx: {dx}")
    lines.append("#Synthetic: true")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from scipy.io import savemat

    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/ecg/demo")
    outdir.mkdir(parents=True, exist_ok=True)

    for i, (rec, label, dx, kind, qrs, irregular) in enumerate(SCENARIOS):
        sig = synth_ecg(kind, qrs, irregular, seed=1000 + i)
        savemat(outdir / f"{rec}.mat", {"val": sig})
        write_hea(outdir / f"{rec}.hea", rec, dx, age_band="60-69", sex="U", label=label)
        print(f"uretildi (sentetik): {rec}.mat / {rec}.hea  [{label}]")


if __name__ == "__main__":
    main()
