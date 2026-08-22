"""EKG tahmin servisi: on isleme -> model -> XAI ciktilari.

Iki calisma modu:
    - checkpoint varsa : egitilmis ECGResNet + Grad-CAM + input saliency
    - checkpoint yoksa : kural tabanli heuristik motor (RR duzensizligi,
      kalp hizi) - platformun egitimden once de calismasini saglar;
      health endpoint'i aktif motoru raporlar.

MDR notu: cikti yalnizca karar destek amaclidir; nihai klinik karar hekim
onayina tabidir (human-in-the-loop).
"""

from __future__ import annotations

import base64
import io
import threading
from pathlib import Path

import numpy as np

from app.ecg.labels import CLASS_NAMES
from app.ecg.preprocess import detect_rpeaks, preprocess_record

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
TARGET_FS = 250
CAM_DOWNSAMPLE = 250  # tasinabilir saliency cozunurlugu


class EcgAnalyzer:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()

    @property
    def backend(self) -> str:
        return "ecg-resnet-1d" if self.model is not None else "rr-heuristic"

    @property
    def model(self):
        if self._model is None:
            with self._lock:
                if self._model is None and (MODELS_DIR / "ecg_resnet.pt").exists():
                    self._load()
        return self._model

    def _load(self) -> None:
        import torch

        ckpt = torch.load(MODELS_DIR / "ecg_resnet.pt", map_location="cpu", weights_only=False)
        from app.ecg.model import ECGResNet

        model = ECGResNet(n_classes=len(ckpt.get("classes", list(CLASS_NAMES))))
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        self._model = model

    # ------------------------------------------------------------- yardimci
    @staticmethod
    def decode_mat(mat_b64: str) -> tuple[np.ndarray, int]:
        """Base64 .mat icerigi -> (12, N) float64 sinyal."""
        from scipy.io import loadmat

        raw = base64.b64decode(mat_b64)
        m = loadmat(io.BytesIO(raw))
        val = m.get("val")
        if val is None:
            raise ValueError("'val' degiskeni bulunamadi")
        arr = np.asarray(val, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[0] != 12:
            raise ValueError(f"12 derivasyon bekleniyordu, gelen: {arr.shape}")
        return arr, 500

    # ------------------------------------------------------------ ana yol
    def analyze_signal(self, signal: np.ndarray, fs: int) -> dict:
        x = preprocess_record(signal, fs_in=fs, target_fs=TARGET_FS)
        if self.model is not None:
            return self._predict_nn(x)
        return self._predict_heuristic(x)

    def _predict_nn(self, x: np.ndarray) -> dict:
        import torch

        model = self.model
        assert model is not None
        xb = torch.from_numpy(x[None].astype(np.float32))
        with torch.no_grad():
            logits = model(xb)
        probs = torch.softmax(logits, dim=1)[0].detach().numpy()
        cls = int(probs.argmax())

        cam = model.grad_cam(xb, class_idx=cls)[0]          # (L,)
        sal = model.input_saliency(xb, class_idx=None)[0]   # (12, L)

        return {
            "backend": "ecg-resnet-1d",
            "superclass_index": cls,
            "superclass": CLASS_NAMES[cls],
            "confidence": round(float(probs[cls]), 4),
            "probabilities": {CLASS_NAMES[i]: round(float(p), 4) for i, p in enumerate(probs)},
            "grad_cam": [round(float(v), 3) for v in _downsample(cam, CAM_DOWNSAMPLE)],
            "lead_saliency": [
                [round(float(v), 3) for v in row]
                for row in _downsample(sal, CAM_DOWNSAMPLE, axis=-1)
            ],
            "heart_rate_bpm": _hr_estimate(x),
            "xai_method": "grad-cam-1d+input-saliency",
        }

    def _predict_heuristic(self, x: np.ndarray) -> dict:
        """Egitim oncesi calisan kural tabanli motor.

        Sinyal isaretleri: kalp hizi (bradi/tasikardi) + RR duzensizligi
        (AFIB ipucu). QRS genisligi kabaca iletim bozuklugu ipucu verir.
        """
        hr = _hr_estimate(x)
        peaks = detect_rpeaks(x[1].astype(np.float64), TARGET_FS)  # lead II
        irregularity = 0.0
        if len(peaks) >= 4:
            rr = np.diff(peaks) / TARGET_FS
            irregularity = float(rr.std() / max(rr.mean(), 1e-6))

        scores = {c: 0.05 for c in CLASS_NAMES}
        reasons: list[str] = []
        if hr and hr > 100:
            scores["arrhythmia"] += 0.5
            reasons.append(f"kalp hizi yuksek ({hr:.0f} bpm)")
        elif hr and hr < 50:
            scores["arrhythmia"] += 0.45
            reasons.append(f"kalp hizi dusuk ({hr:.0f} bpm)")
        if irregularity > 0.15:
            scores["arrhythmia"] += min(0.4, irregularity * 2)
            reasons.append(f"RR araliklari duzensiz (CV={irregularity:.2f})")
        if hr and 55 <= hr <= 95 and irregularity <= 0.15:
            scores["normal"] += 0.75
            reasons.append("ritim duzenli, kalp hizi fizyolojik aralikta")

        total = sum(scores.values())
        probs = {k: v / total for k, v in scores.items()}
        cls = max(probs, key=probs.get)  # type: ignore[arg-type]
        cls_idx = CLASS_NAMES.index(cls)

        # heuristic XAI: R-dorugu cevreleri enerji tabanli vurgu
        cam = _beat_localized_cam(x)
        sal = np.tile(cam * 0.6 + 0.2, (12, 1))

        return {
            "backend": "rr-heuristic",
            "superclass_index": cls_idx,
            "superclass": cls,
            "confidence": round(probs[cls], 4),
            "probabilities": {k: round(v, 4) for k, v in probs.items()},
            "grad_cam": [round(float(v), 3) for v in cam],
            "lead_saliency": [[round(float(v), 3) for v in row] for row in sal],
            "heart_rate_bpm": hr,
            "rationale": "; ".join(reasons) or "belirgin isaret yok",
            "xai_method": "energy-saliency",
        }


def _hr_estimate(x: np.ndarray) -> float | None:
    for lead in (x[1], x[0]):  # II, sonra I
        peaks = detect_rpeaks(lead.astype(np.float64), TARGET_FS)
        if len(peaks) >= 3:
            rr = np.diff(peaks) / TARGET_FS
            rr = rr[(rr > 0.3) & (rr < 3.0)]
            if len(rr):
                return round(60.0 / float(np.median(rr)), 1)
    return None


def _downsample(arr: np.ndarray, n: int, axis: int = -1) -> np.ndarray:
    L = arr.shape[axis]
    idx = np.linspace(0, L - 1, n).astype(int)
    return np.take(arr, idx, axis=axis)


def _beat_localized_cam(x: np.ndarray) -> np.ndarray:
    """R-dorukleri etrafinde gauss yumusatilmis onem haritasi (250 nokta)."""
    peaks = detect_rpeaks(x[1].astype(np.float64), TARGET_FS)
    dense = np.zeros(TARGET_FS * 10)
    L = x.shape[-1]
    for p in peaks:
        if 0 <= p < L:
            dense[p] = 1.0
    k = np.exp(-0.5 * (np.arange(-60, 61) / 25.0) ** 2)
    dense = np.convolve(dense, k / k.sum(), mode="same")[:L]
    ds = _downsample(dense, CAM_DOWNSAMPLE)
    peak = ds.max() + 1e-8
    return (ds / peak).astype(float)


_analyzer = EcgAnalyzer()


def get_analyzer() -> EcgAnalyzer:
    return _analyzer
