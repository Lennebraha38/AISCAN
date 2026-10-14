#!/usr/bin/env python
"""docs/metrics/*.json içindeki gerçek metriklerden figür üretir.

Eğitim hattı (app/ecg/train.py) figürleri eğitim sırasında üretir; bu script
ise commit edilmiş metrik dosyalarından (CI artefaktları) yeniden üretim
sağlar. Hiçbir sayı uydurulmaz: yalnızca JSON içeriği görselleştirilir.

Kullanım:
    python scripts/plot_metrics.py
    python scripts/plot_metrics.py --metrics-dir docs/metrics --figures-dir docs/figures
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict | None:
    if not path.is_file():
        print(f"  atlandı (yok): {path}")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def plot_confusion_matrix(cm: list[list[int]], labels: list[str], title: str, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    arr = np.asarray(cm, dtype=float)
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    im = ax.imshow(arr, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=20, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("Tahmin")
    ax.set_ylabel("Gerçek")
    ax.set_title(title)
    total = arr.sum() or 1
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = int(arr[i, j])
            frac = arr[i, j] / total
            ax.text(j, i, f"{val}\n{frac*100:.1f}%", ha="center", va="center",
                    color="white" if arr[i, j] > arr.max() * 0.6 else "black", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  yazıldı: {out}")


def plot_learning_curves(history: dict, out: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    train_loss = history.get("train_loss") or []
    val_f1 = history.get("val_f1") or []
    if not train_loss and not val_f1:
        print(f"  atlandı (history boş): {out}")
        return

    epochs = list(range(1, max(len(train_loss), len(val_f1)) + 1))
    fig, ax1 = plt.subplots(figsize=(6.2, 4.2))
    if train_loss:
        ax1.plot(range(1, len(train_loss) + 1), train_loss, "o-", color="#2c4b8f", label="Eğitim kaybı")
        ax1.set_xlabel("Epoch")
        ax1.set_ylabel("Eğitim kaybı", color="#2c4b8f")
        ax1.tick_params(axis="y", labelcolor="#2c4b8f")
    ax2 = ax1.twinx()
    if val_f1:
        ax2.plot(range(1, len(val_f1) + 1), val_f1, "s-", color="#1f8b4c", label="Doğrulama macro F1")
        ax2.set_ylabel("Doğrulama macro F1", color="#1f8b4c")
        ax2.tick_params(axis="y", labelcolor="#1f8b4c")
    ax1.set_xticks(epochs)
    ax1.set_title(title)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  yazıldı: {out}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="docs/metrics JSON -> docs/figures PNG")
    ap.add_argument("--metrics-dir", default=str(root / "docs" / "metrics"))
    ap.add_argument("--figures-dir", default=str(root / "docs" / "figures"))
    args = ap.parse_args()

    metrics_dir = Path(args.metrics_dir)
    figures_dir = Path(args.figures_dir)
    labels = ["Normal", "Aritmi", "Blok"]

    print("Figürler üretiliyor (gerçek metriklerden)...")
    deep = _load(metrics_dir / "deep_metrics.json")
    if deep:
        if deep.get("confusion_matrix"):
            plot_confusion_matrix(deep["confusion_matrix"], labels,
                                  "ECGResNet-1D — Karışıklık Matrisi (test)",
                                  figures_dir / "confusion_matrix.png")
        if deep.get("history"):
            plot_learning_curves(deep["history"],
                                 figures_dir / "learning_curves.png",
                                 "ECGResNet-1D — Öğrenme Eğrileri")

    baseline = _load(metrics_dir / "baseline_metrics.json")
    if baseline and baseline.get("confusion_matrix"):
        plot_confusion_matrix(baseline["confusion_matrix"], labels,
                              "Baseline (HistGradientBoosting) — Karışıklık Matrisi",
                              figures_dir / "baseline_confusion_matrix.png")
    print("Bitti.")


if __name__ == "__main__":
    main()
