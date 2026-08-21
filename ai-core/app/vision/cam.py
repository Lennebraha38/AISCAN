"""XAI ısı haritası üretimi (Grad-CAM).

Birincil yol: torch + pytorch-grad-cam (checkpoint varsa gerçek Grad-CAM).
Fallback: numpy tabanlı enerji saliency — gradyan büyüklüğü × yoğunluk
anomalisi; demo ve testlerde deterministik, offline çalışır.

Her iki yolda çıktı: orijinal görüntü üzerine %40 opaklıkta bindirilmiş
jet-colormap ısı haritası PNG (base64).
"""
from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from .engine import IMG_SIZE, _gradient_magnitude

OVERLAY_ALPHA = 0.40

try:  # pragma: no cover - torch ortamda yoksa fallback kullanılır
    import torch
    from torchvision import transforms

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    TORCH_AVAILABLE = False


def _jet_colormap(x: np.ndarray) -> np.ndarray:
    """0-1 aralığındaki haritayı RGB'ye çevirir (jet benzeri)."""
    r = np.clip(1.5 - np.abs(4.0 * x - 3.0), 0, 1)
    g = np.clip(1.5 - np.abs(4.0 * x - 2.0), 0, 1)
    b = np.clip(1.5 - np.abs(4.0 * x - 1.0), 0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _blur(map_: np.ndarray, passes: int = 3) -> np.ndarray:
    """Basit box-blur (scipy bağımlılığı olmadan)."""
    for _ in range(passes):
        padded = np.pad(map_, 1, mode="edge")
        map_ = (
            padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:]
            + padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:]
            + padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
        ) / 9.0
    return map_


def energy_saliency(img: np.ndarray) -> np.ndarray:
    """Numpy saliency: kenar enerjisi × yerel yoğunluk anomalisi."""
    grad = _gradient_magnitude(img)
    intensity_anomaly = np.abs(img - img.mean())
    sal = grad * (0.5 + intensity_anomaly)
    sal = _blur(sal)
    lo, hi = np.percentile(sal, [70, 99.5])
    if hi - lo < 1e-9:
        return np.zeros_like(sal)
    return np.clip((sal - lo) / (hi - lo), 0, 1)


def gradcam_heatmap(model, input_tensor, target_layers):  # pragma: no cover
    """Gerçek Grad-CAM (torch checkpoint mevcutsa kullanılır)."""
    from pytorch_grad_cam import GradCAM
    from pytorch_grad_cam.utils.image import show_cam_on_image

    with GradCAM(model=model, target_layers=target_layers) as cam:
        grayscale = cam(input_tensor=input_tensor)[0]
    rgb = input_tensor[0].permute(1, 2, 0).numpy()
    rgb = (rgb - rgb.min()) / max(rgb.max() - rgb.min(), 1e-9)
    return show_cam_on_image(rgb, grayscale, use_rgb=True)


def overlay_heatmap(img_gray: np.ndarray, heatmap01: np.ndarray,
                    alpha: float = OVERLAY_ALPHA) -> bytes:
    """Isı haritasını gri görüntünün üzerine alpha ile bindirip PNG döner."""
    base = np.stack([img_gray] * 3, axis=-1)
    base = (base * 255).astype(np.uint8)
    colored = _jet_colormap(np.clip(heatmap01, 0, 1))
    out = ((1 - alpha) * base + alpha * colored).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, format="PNG")
    return buf.getvalue()


def produce_cam_overlay(image_bytes: bytes, model=None, target_layers=None) -> tuple[str, np.ndarray]:
    """(base64_png, heatmap) döner. Torch yolu yoksa enerji saliency kullanılır."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((IMG_SIZE, IMG_SIZE))
    gray = np.asarray(img, dtype=np.float32) / 255.0

    if model is not None and target_layers and TORCH_AVAILABLE:  # pragma: no cover
        tf = transforms.Compose([transforms.ToTensor()])
        tensor = tf(gray)[None]
        rgb = gradcam_heatmap(model, tensor, target_layers)
        heat = rgb.mean(axis=-1) / 255.0
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode(), heat

    heat = energy_saliency(gray)
    png = overlay_heatmap(gray, heat)
    return base64.b64encode(png).decode(), heat
