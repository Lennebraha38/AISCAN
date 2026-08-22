"""EKG etiket haritalama ve on isleme testleri."""
import numpy as np
import pytest

from app.ecg.labels import (
    CLASS_NAMES,
    assign_superclass,
    subclasses_for,
)
from app.ecg.preprocess import (
    detect_rpeaks,
    normalize_leadwise,
    preprocess_record,
)


# ---------------------------------------------------------------- labels ----
def test_afib_only_is_arrhythmia():
    assert assign_superclass(["164889003"]) == "arrhythmia"


def test_sr_only_is_normal():
    assert assign_superclass(["426783006"]) == "normal"


def test_lbbb_only_is_block():
    assert assign_superclass(["164909002"]) == "block"


def test_priority_block_over_arrhythmia():
    # gercek kayit: AFIB + RBBB (JS00001) -> blok onceligi ile "block"
    assert assign_superclass(["164889003", "59118001", "164934002"]) == "block"


def test_arrhythmia_when_no_block():
    # SB + APB: blok kodu yok -> arrhythmia
    assert assign_superclass(["426177001", "284470004"]) == "arrhythmia"


def test_non_target_codes_excluded():
    # MI + LVH: hedef disi -> None
    assert assign_superclass(["164865005", "164873001"]) is None


def test_sr_with_non_target_is_normal():
    assert assign_superclass(["426783006", "164873001"]) == "normal"


def test_subclass_extraction():
    subs = subclasses_for(["164889003", "59118001", "270492004"])
    assert subs == ["AFIB", "RBBB", "1AVB"]


def test_class_names_order():
    assert CLASS_NAMES == ("normal", "arrhythmia", "block")


# ------------------------------------------------------------ preprocess ----
def _synthetic_ecg(fs: int = 500, seconds: int = 10, bpm: float = 60.0) -> np.ndarray:
    """Sabit ritimli sentetik EKG: QRS benzeri dar spike'lar + baseline."""
    n = fs * seconds
    t = np.arange(n) / fs
    period = 60.0 / bpm
    sig = np.zeros(n)
    beat_t = np.arange(0.2, seconds, period)
    for bt in beat_t:
        idx = int(bt * fs)
        w = min(40, n - idx)
        sig[idx : idx + w] += np.exp(-0.5 * ((np.arange(w) - 6) / 3.0) ** 2) * 1.2
        sig[:n] += 0  # no-op
    sig += 0.05 * np.sin(2 * np.pi * 0.3 * t)  # baseline wander
    sig += 0.02 * np.sin(2 * np.pi * 50 * t)   # sebekesizlik gurultusu
    return sig


def test_preprocess_output_shape_and_dtype():
    raw = np.stack([_synthetic_ecg() for _ in range(12)])
    out = preprocess_record(raw, fs_in=500, target_fs=250)
    assert out.shape == (12, 2500)
    assert out.dtype == np.float32


def test_preprocess_resamples_from_257hz():
    raw = np.stack([_synthetic_ecg(fs=257)[:2570] for _ in range(12)])
    out = preprocess_record(raw, fs_in=257, target_fs=250)
    assert out.shape == (12, 2500)


def test_normalize_zero_mean_unit_std():
    x = np.random.default_rng(0).normal(5, 3, (2, 1000))
    z = normalize_leadwise(x)
    assert abs(z.mean()) < 1e-8
    assert abs(z.std() - 1.0) < 1e-6


def test_rpeaks_detects_expected_beats():
    sig = _synthetic_ecg(bpm=60).astype(np.float32)
    proc = preprocess_record(np.stack([sig] * 12), fs_in=500, target_fs=250)[0]
    peaks = detect_rpeaks(proc.astype(np.float64), fs=250)
    assert 8 <= len(peaks) <= 12  # 10 sn @ 60 bpm ~ 10 vurus


def test_notch_suppresses_mains_hum():
    t = np.arange(2500) / 250
    clean = np.sin(2 * np.pi * 8 * t)
    noisy = clean + 0.5 * np.sin(2 * np.pi * 50 * t)
    from app.ecg.preprocess import notch_mains

    filtered = notch_mains(noisy, fs=250)
    residual_50 = abs(np.dot(filtered - clean, np.sin(2 * np.pi * 50 * t)))
    raw_50 = abs(np.dot(noisy - clean, np.sin(2 * np.pi * 50 * t)))
    assert residual_50 < raw_50 / 3
