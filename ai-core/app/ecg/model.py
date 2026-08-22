"""1D ResNet EKG siniflandirici + Grad-CAM 1D aciklanabilirlik.

Girdi : (B, 12, L)  - on islenmis 12 derivasyon (250 Hz @ 10 sn -> L=2500)
Cikti : (B, 3) logits - [normal, arrhythmia, block]

Tasarim hedefleri:
    - CPU (aarch64/NEON) egitimine uygun ~2M parametre
    - Genis baslangic resepsiyon alani (k=11) QRS/P/T morfolojisi icin
    - Grad-CAM: son konvolasyon katmani aktivasyon+gradyan hook'lari
    - Input saliency: derivasyon x zaman onem haritasi (gradient*input)
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from app.ecg.labels import CLASS_NAMES


class ConvBlock(nn.Module):
    """[Conv-BN-GELU-Conv-BN] + skip; boyut degisirsek 1x1 conv skip."""

    def __init__(self, cin: int, cout: int, stride: int = 1, k: int = 7):
        super().__init__()
        pad = k // 2
        self.conv1 = nn.Conv1d(cin, cout, k, stride=stride, padding=pad, bias=False)
        self.bn1 = nn.BatchNorm1d(cout)
        self.conv2 = nn.Conv1d(cout, cout, k, padding=pad, bias=False)
        self.bn2 = nn.BatchNorm1d(cout)
        if stride != 1 or cin != cout:
            self.skip = nn.Sequential(
                nn.Conv1d(cin, cout, 1, stride=stride, bias=False),
                nn.BatchNorm1d(cout),
            )
        else:
            self.skip = nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.gelu(self.bn1(self.conv1(x)))
        y = self.bn2(self.conv2(y))
        return F.gelu(y + self.skip(x))


class ECGResNet(nn.Module):
    def __init__(self, n_classes: int = 3, in_ch: int = 12, dropout: float = 0.3):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(in_ch, 32, 11, stride=2, padding=5, bias=False),
            nn.BatchNorm1d(32),
            nn.GELU(),
        )
        self.stage1 = nn.Sequential(ConvBlock(32, 32), ConvBlock(32, 32))
        self.stage2 = nn.Sequential(ConvBlock(32, 64, stride=2), ConvBlock(64, 64))
        self.stage3 = nn.Sequential(ConvBlock(64, 128, stride=2), ConvBlock(128, 128))
        self.stage4 = nn.Sequential(ConvBlock(128, 256, stride=2), ConvBlock(256, 256))
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(256, n_classes),
        )
        self._cam_acts: torch.Tensor | None = None
        self._cam_grads: torch.Tensor | None = None
        self.stage4.register_forward_hook(self._hook_fwd)
        self.stage4.register_full_backward_hook(self._hook_bwd)

    def _hook_fwd(self, _m: nn.Module, _inp, out: torch.Tensor) -> None:
        self._cam_acts = out.detach()

    def _hook_bwd(self, _m: nn.Module, _gi, go) -> None:
        self._cam_grads = go[0].detach()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.stem(x)
        y = self.stage1(y)
        y = self.stage2(y)
        y = self.stage3(y)
        y = self.stage4(y)
        return self.head(y)

    # --- Aciklanabilirlik -------------------------------------------------
    def grad_cam(self, x: torch.Tensor, class_idx: int | None = None) -> np.ndarray:
        """Zaman ekseninde 1D Grad-CAM; donen: (B, L_in), 0-1 normalize.

        Sinif agirligi w_c = gradyanlarin zaman ortalamasi,
        CAM = ReLU(sum_c w_c * A_c), giris uzunluguna upsample edilir.
        """
        was_training = self.training
        self.eval()
        xin = x.clone().requires_grad_(True)
        logits = self.forward(xin)
        if class_idx is None:
            class_idx = int(logits.argmax(dim=1).max())
        self.zero_grad(set_to_none=True)
        logits[:, class_idx].sum().backward()
        acts = self._cam_acts  # (B, C, T')
        grads = self._cam_grads  # (B, C, T')
        weights = grads.mean(dim=-1, keepdim=True)
        cam = F.relu((weights * acts).sum(dim=1, keepdim=True))
        cam = F.interpolate(cam, size=x.shape[-1], mode="linear", align_corners=False)[:, 0]
        cam = cam / (cam.amax(dim=-1, keepdim=True) + 1e-8)
        if was_training:
            self.train()
        return cam.detach().cpu().numpy()

    def input_saliency(self, x: torch.Tensor, class_idx: int | None = None) -> np.ndarray:
        """Derivasyon x zaman onem haritasi (B, 12, L), 0-1 normalize."""
        was_training = self.training
        self.eval()
        xin = x.clone().requires_grad_(True)
        logits = self.forward(xin)
        if class_idx is None:
            class_idx = logits.argmax(dim=1)
        self.zero_grad(set_to_none=True)
        logits.gather(1, class_idx.view(-1, 1)).sum().backward()
        sal = (xin.grad * xin).abs()
        sal = F.avg_pool1d(sal, kernel_size=25, stride=1, padding=12)
        peak = sal.amax(dim=-1, keepdim=True).amax(dim=1, keepdim=True) + 1e-8
        sal = sal / peak
        if was_training:
            self.train()
        return sal.detach().cpu().numpy()


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
