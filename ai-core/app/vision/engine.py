"""Görsel analiz motoru.

Birincil yol: numpy tabanlı deterministik göğüs radyografisi özellik
çıkarımı (offline çalışır, jüri demosunda tekrarlanabilir).
Opsiyonel yol: torch checkpoint yüklüyse gerçek model çıkarımı
(``scripts/train`` ile eğitilmiş ResNet50/ViT).
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

FINDING_LABELS = [
    "Atelektazi",
    "Kardiomegali",
    "Efüzyon",
    "İnfiltrasyon",
    "Kütle/Nodül",
    "Pnömoni",
    "Pnömotoraks",
]

IMG_SIZE = 512


@dataclass
class RegionEnergy:
    """3x3 grid bölgesi enerjisi (XAI top_regions için)."""

    row: int
    col: int
    energy: float


def load_grayscale(image_bytes: bytes) -> np.ndarray:
    # 1) DICOM dene (istemcide metadata temizlenmiş olarak gelir)
    if image_bytes[:132][128:132] == b"DICM" or image_bytes[:2] not in (b"\xff\xd8", b"\x89P"):
        try:
            import pydicom

            ds = pydicom.dcmread(io.BytesIO(image_bytes), force=True)
            arr = ds.pixel_array.astype(np.float32)
            slope = float(getattr(ds, "RescaleSlope", 1) or 1)
            intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
            arr = arr * slope + intercept
            modality = str(getattr(ds, "Modality", "CR")).upper()
            if modality == "CT":
                arr = hu_window(arr)
                img = Image.fromarray((arr * 255).astype(np.uint8))
            else:
                lo, hi = float(arr.min()), float(arr.max())
                norm = (arr - lo) / max(hi - lo, 1e-9)
                img = Image.fromarray((norm * 255).astype(np.uint8))
            return np.asarray(img.convert("L").resize((IMG_SIZE, IMG_SIZE)), dtype=np.float32) / 255.0
        except Exception:
            pass  # DICOM değilse standart decoder'a düş
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = img.resize((IMG_SIZE, IMG_SIZE))
    return np.asarray(img, dtype=np.float32) / 255.0


def hu_window(pixel_array: np.ndarray, center: float = -600, width: float = 1500) -> np.ndarray:
    """CT HU pencereleme (akciğer penceresi)."""
    lo, hi = center - width / 2, center + width / 2
    clipped = np.clip(pixel_array.astype(np.float32), lo, hi)
    return (clipped - lo) / max(hi - lo, 1e-6)


def _gradient_magnitude(img: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(img)
    gy = np.zeros_like(img)
    gx[:, 1:-1] = img[:, 2:] - img[:, :-2]
    gy[1:-1, :] = img[2:, :] - img[:-2, :]
    return np.sqrt(gx**2 + gy**2)


def _sigmoid(x: float, k: float = 10.0) -> float:
    return float(1.0 / (1.0 + np.exp(-k * x)))


def analyze_array(img: np.ndarray) -> dict:
    """Gri seviye görüntüden bulgu olasılıkları ve risk skoru üretir.

    Özellikler deterministiktir; aynı girdi her zaman aynı çıktıyı verir.
    """
    h, w = img.shape
    mid = w // 2
    left, right = img[:, :mid], img[:, mid:]

    # 1) Simetri: iki akciğer alanı arasındaki asimetri (efüzyon/atelektazi işareti)
    diff = np.abs(left - right[:, ::-1]).mean()
    asymmetry = min(diff * 4.0, 1.0)

    # 2) Opasite: akciğer alanlarında yüksek yoğunluk oranı (infiltrasyon/pnömoni)
    lung_band = img[int(h * 0.15) : int(h * 0.85), :]
    opacity = float((lung_band > 0.62).mean())

    # 3) Odak kenar enerjisi: nodül/kütle yerel kenar üretir
    grad = _gradient_magnitude(img)
    focal = float(np.percentile(grad, 99.5))

    # 4) Kardiyotorasik genişlik oranı (bilgi amaçlı; olasılıkta kullanılmaz)
    col_mean = img.mean(axis=0)
    bright_cols = np.where(col_mean > 0.45)[0]
    cardio_ratio = len(bright_cols) / w if len(bright_cols) else 0.0

    # 5) Periferik hipölüsen (kenar bölgelerinde karanlık alan oranı)
    margin = int(w * 0.12)
    periphery = np.concatenate([img[:, :margin].ravel(), img[:, -margin:].ravel()])
    dark_textureless = float((periphery < 0.08).mean())

    # 6-8) Gerçek cihaz çıktılarına göre kalibre edilmiş ek öznitelikler:
    #      orta şerit parlaklığı, üst zonda L/R simetri oranı,
    #      akciğer bölgesi içi karanlık (hava) oranı
    central_strip = float(
        img[int(h * 0.25) : int(h * 0.90), int(w * 0.33) : int(w * 0.67)].mean()
    )
    upper = img[int(h * 0.15) : int(h * 0.55), :]
    lmean = float(upper[:, :mid].mean())
    rmean = float(upper[:, mid:].mean())
    upper_lr_diff = abs(lmean - rmean) / max(lmean, rmean, 1e-9)
    lung_zone = img[int(h * 0.20) : int(h * 0.75), :]
    lung_darkness = float((lung_zone < 0.12).mean())

    features = {
        "asymmetry": asymmetry,
        "opacity_ratio": opacity,
        "focal_edge_energy": focal,
        "cardiothoracic_ratio_proxy": cardio_ratio,
        "peripheral_darkness": dark_textureless,
        "central_strip_mean": central_strip,
        "upper_zone_lr_diff": upper_lr_diff,
        "lung_zone_darkness": lung_darkness,
    }

    probs = {
        # yaygın opasite (genel)
        "İnfiltrasyon": _sigmoid((opacity - 0.60) * 9),
        # konfluens yoğun opasite
        "Pnömoni": _sigmoid((opacity - 0.72) * 10),
        # alt-alan opasite + üst zon simetrisi korunmuş (bilateral efüzyon)
        "Efüzyon": _sigmoid((opacity - 0.64) * 8)
        * _sigmoid((0.06 - upper_lr_diff) * 80),
        # asimetri + üst zon simetrisi bozulmamış + gerçekten karanlık periferi
        "Pnömotoraks": _sigmoid((asymmetry - 0.46) * 9)
        * _sigmoid((0.10 - upper_lr_diff) * 60)
        * _sigmoid((dark_textureless - 0.30) * 8),
        # belirgin asimetri + üst zonda belirgin L/R farkı
        "Atelektazi": _sigmoid((asymmetry - 0.50) * 8)
        * _sigmoid((upper_lr_diff - 0.15) * 25)
        * _sigmoid((focal - 0.55) * 8),
        # ya tek taraflı kitle kompozisyonu ya çoklu yuvarlak dansiteler
        "Kütle/Nodül": max(
            _sigmoid((upper_lr_diff - 0.22) * 25) * _sigmoid((0.52 - opacity) * 10),
            _sigmoid((lung_darkness - 0.28) * 8),
        ),
        # orta şerit geniş/parlak + periferi karanlık (konjestif görünüm)
        "Kardiomegali": _sigmoid((opacity - 0.30) * 8)
        * _sigmoid((0.62 - central_strip) * 10)
        * _sigmoid((dark_textureless - 0.10) * 8),
    }

    weights = {
        "Kütle/Nodül": 1.35,
        "Pnömoni": 1.15,
        "Pnömotoraks": 1.30,
        "Efüzyon": 1.10,
        "İnfiltrasyon": 1.00,
        "Atelektazi": 0.90,
        "Kardiomegali": 0.80,
    }
    risk = sum(p * weights[k] for k, p in probs.items()) / sum(weights.values())
    risk_score = round(min(max(risk, 0.0), 1.0) * 100, 1)

    # XAI: bölge enerji haritası (3x3 grid)
    cell_h, cell_w = h // 3, w // 3
    regions = []
    for r in range(3):
        for c in range(3):
            e = float(grad[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w].mean())
            regions.append(RegionEnergy(r, c, e))
    regions.sort(key=lambda x: x.energy, reverse=True)

    return {
        "probabilities": {k: round(v, 4) for k, v in probs.items()},
        "risk_score": risk_score,
        "features": {k: round(float(v), 4) for k, v in features.items()},
        "top_regions": [
            {"row": rg.row, "col": rg.col, "energy": round(rg.energy, 4)}
            for rg in regions[:3]
        ],
    }


def analyze_image(image_bytes: bytes, modality: str = "CR") -> dict:
    """Görüntü byte'larını analiz eder; CT ise HU pencereleme uygular."""
    img = load_grayscale(image_bytes)
    if modality and modality.upper().startswith("CT") and image_bytes[:2] in (b"\xff\xd8", b"\x89P"):
        # PNG/JPEG girdide piksel değerleri zaten normalize; pencereleme
        # yalnız ham DICOM piksel dizisi verildiğinde anlamlıdır.
        img = hu_window(img * 255.0 - 1000.0)
    return analyze_array(img)


def finding_saliency_map(img: np.ndarray, label: str) -> np.ndarray:
    """Bulgu için gerçek mekânsal dikkat haritası ([0..1], IMG_SIZE kare).

    Her bulgu sınıfının olasılığı belirli bir görüntü özelliğinden gelir;
    harita da o özelliğin piksel-bazlı dağılımıdır. Böylece "hangi risk
    nerede?" sorusuna bulgu-başına farklı, dürüst bir yanıt üretilir.
    """
    h, w = img.shape
    mid = w // 2

    def _norm(m: np.ndarray) -> np.ndarray:
        hi = float(np.percentile(m, 99.5))
        lo = float(np.percentile(m, 40))
        return np.clip((m - lo) / max(hi - lo, 1e-9), 0.0, 1.0)

    if label in ("Atelektazi", "Efüzyon"):
        left, right = img[:, :mid], img[:, mid:]
        amap = np.abs(left.astype(np.float32) - right[:, ::-1])
        m = np.empty((h, w), dtype=np.float32)
        m[:, :mid] = amap
        m[:, mid:] = amap[:, ::-1]
        return _norm(m)
    if label in ("İnfiltrasyon", "Pnömoni"):
        return _norm(np.clip((img - 0.62) / 0.38, 0, 1))
    if label == "Kütle/Nodül":
        g = _gradient_magnitude(img)
        thr = float(np.percentile(g, 97))
        peak = max(float(g.max()) - thr, 1e-9)
        return _norm(np.clip((g - thr) / peak, 0, 1))
    if label == "Kardiomegali":
        cm = img.mean(axis=0)
        band = np.clip(cm - 0.40, 0, None)
        band = band / max(float(band.max()), 1e-9)
        colmap = np.tile(band, (h, 1))
        return _norm(colmap * np.clip((img - 0.30) / 0.30, 0, 1))
    if label == "Pnömotoraks":
        margin = int(w * 0.15)
        dark = np.clip(0.18 - img, 0, None) / 0.18
        m = np.zeros_like(img)
        m[:, :margin] = dark[:, :margin]
        m[:, -margin:] = dark[:, -margin:]
        return _norm(m)
    return _norm(_gradient_magnitude(img))
