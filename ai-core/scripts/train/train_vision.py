"""Vision modeli eğitim iskeleti (ResNet50 / ViT-B16).

ChestX-ray14 veya CheXpert etiketleriyle fine-tune için iskelettir.
Demo dağıtımında checkpoint yoksa AI Core deterministik numpy motoruyla
çalışır; bu script ile üretilen checkpoint `app/vision/cam.py` içindeki
torch yolunu otomatik etkinleştirir.

Kullanım:
    PYTHONPATH=ai-core python ai-core/scripts/train/train_vision.py \
        --data-dir /path/to/chestxray --epochs 20 --arch resnet50
"""
from __future__ import annotations

import argparse


def build_model(arch: str, num_classes: int):
    import torch.nn as nn
    from torchvision import models

    if arch == "resnet50":
        model = models.resnet50(weights="IMAGENET1K_V2")
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        target_layers = [model.layer4[-1]]
    elif arch == "vit-b16":
        from timm import create_model

        model = create_model("vit_base_patch16_224", pretrained=True, num_classes=num_classes)
        target_layers = [model.blocks[-1].norm1]
    else:
        raise ValueError(f"Bilinmeyen mimari: {arch}")
    return model, target_layers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--arch", choices=["resnet50", "vit-b16"], default="resnet50")
    args = parser.parse_args()

    # NOT: Tam veri yükleme döngüsü veri seti formatına bağlıdır.
    # ChestXrayDataset: görüntü + 14 ikili etiket (multi-label BCEWithLogitsLoss).
    print(f"[train_vision] arch={args.arch} data={args.data_dir} epochs={args.epochs}")
    print("Bu iskelet, veri seti bağlandığında doldurulmak üzere hazırdır:")
    print("  - Dataset/DataLoader tanımı (ChestXray14 CSV formatı)")
    print("  - BCEWithLogitsLoss + AdamW + cosine LR")
    print("  - Epoch sonu AUROC raporu ve checkpoint kaydı")


if __name__ == "__main__":
    main()
