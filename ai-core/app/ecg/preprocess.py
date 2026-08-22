"""EKG on isleme hatti.

Adimlar (her derivasyon icin):
    1. Sabit uzunluk: 10 sn @ 500 Hz = 5000 ornek (baska oranlardan yeniden ornekleme)
    2. Baseline wander kaldirma (0.5 Hz yuksek geciren, Butterworth)
    3. Bant geciren 0.5-40 Hz (filtfilt - faz kaymasiz)
    4. 50 Hz sebekesizlik notch filtresi
    5. Kayit bazli derivasyon basina z-skor normalizasyonu

Tum filtreler scipy ile; torch bagimliligi yoktur (veri hattinin
test edilebilirligi ve tekrarlanabilirligi icin).
"""

from __future__ import annotations

import numpy as np
from scipy import signal as sps

TARGET_FS = 500
TARGET_SAMPLES = 5000  # 10 saniye


def resample_to(x: np.ndarray, fs_in: int, fs_out: int = TARGET_FS) -> np.ndarray:
    if fs_in == fs_out:
        return x.astype(np.float64)
    n_out = int(round(x.shape[-1] * fs_out / fs_in))
    return sps.resample_poly(x, fs_out, fs_in, axis=-1).astype(np.float64)


def _safe_filter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Kisa/bozuk sinyallerde filtfilt padlen hatasini engeller."""
    padlen = min(3 * (max(len(a), len(b)) - 1), x.shape[-1] - 1)
    if padlen < 1:
        return x
    return sps.filtfilt(b, a, x, axis=-1, padlen=padlen)


def remove_baseline_wander(x: np.ndarray, fs: int = TARGET_FS) -> np.ndarray:
    b, a = sps.butter(2, 0.5 / (fs / 2), btype="highpass")
    return _safe_filter(b, a, x)


def bandpass(x: np.ndarray, fs: int = TARGET_FS, lo: float = 0.5, hi: float = 40.0) -> np.ndarray:
    nyq = fs / 2
    hi = min(hi, nyq * 0.99)
    b, a = sps.butter(3, [lo / nyq, hi / nyq], btype="bandpass")
    return _safe_filter(b, a, x)


def notch_mains(x: np.ndarray, fs: int = TARGET_FS, freq: float = 50.0) -> np.ndarray:
    nyq = fs / 2
    if freq >= nyq:
        return x
    b, a = sps.iirnotch(freq / nyq, Q=30.0)
    return _safe_filter(b, a, x)


def normalize_leadwise(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    std = x.std(axis=-1, keepdims=True)
    return (x - x.mean(axis=-1, keepdims=True)) / np.maximum(std, eps)


def fixed_length(x: np.ndarray, n: int = TARGET_SAMPLES) -> np.ndarray:
    """Orta kismi alarak sabit uzunluga getirir (kirpma/sifir dolgu)."""
    cur = x.shape[-1]
    if cur == n:
        return x
    if cur > n:
        start = (cur - n) // 2
        return x[..., start : start + n]
    pad = np.zeros((*x.shape[:-1], n - cur), dtype=x.dtype)
    return np.concatenate([x, pad], axis=-1)


def preprocess_record(
    raw: np.ndarray,
    fs_in: int = TARGET_FS,
    apply_notch: bool = True,
    target_fs: int = TARGET_FS,
) -> np.ndarray:
    """(12, N) ham sinyal -> (12, n_out) on islenmis float32.

    Sira: resample -> baseline -> bandpass -> notch -> sabit uzunluk -> z-skor.
    target_fs=250 icin cikti (12, 2500) olur (egitim varsayilani).
    """
    x = resample_to(np.asarray(raw, dtype=np.float64), fs_in, target_fs)
    x = remove_baseline_wander(x, target_fs)
    x = bandpass(x, target_fs)
    if apply_notch:
        x = notch_mains(x, target_fs)
    x = fixed_length(x, n=target_fs * 10)
    x = normalize_leadwise(x)
    return x.astype(np.float32)


# --- Basit R-dorugu algilama (baseline ozellikleri icin, Pan-Tompkins lite) ---
def detect_rpeaks(x: np.ndarray, fs: int = TARGET_FS) -> np.ndarray:
    """Tek derivasyon icin R-dorugu indeksleri.

    Yontem: bant geciren (5-15 Hz) -> turev -> kare -> hareketli ortanca esik.
    """
    nyq = fs / 2
    b, a = sps.butter(2, [5.0 / nyq, min(15.0, nyq * 0.99) / nyq], btype="bandpass")
    y = _safe_filter(b, a, x)
    y = np.diff(y, prepend=y[..., :1])
    y = y * y
    win = max(int(0.15 * fs), 3)
    kernel = np.ones(win) / win
    ma = np.convolve(y, kernel, mode="same")
    thr = np.median(ma) + 0.2 * ma.mean()
    peaks: list[int] = []
    refractory = int(0.25 * fs)  # 250 ms - fizyolojik refrakter periyot
    last = -refractory
    for i in range(1, len(ma) - 1):
        if ma[i] > thr and ma[i] >= ma[i - 1] and ma[i] > ma[i + 1] and i - last >= refractory:
            peaks.append(i)
            last = i
    return np.asarray(peaks, dtype=np.int64)
