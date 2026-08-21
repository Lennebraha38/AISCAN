"""Türkçe Medical-BERT (BERTurk) eğitim iskeleti.

dbmdz/bert-base-turkish-cased modelini klinik aciliyet sınıflandırması için
fine-tune eder. Üretilen checkpoint `app/nlp` içindeki BERTurkBackend
arayüzüne bağlanır; checkpoint yoksa kural tabanlı deterministik motor
kullanılır (aynı yanıt şeması: urgency + token attribution).

Kullanım:
    PYTHONPATH=ai-core python ai-core/scripts/train/train_nlp.py \
        --data epikriz-etiketli.csv --epochs 5
"""
from __future__ import annotations

import argparse

MODEL_NAME = "dbmdz/bert-base-turkish-cased"
LABELS = ["düşük", "orta", "yüksek"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="CSV: text,urgency_label")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    args = parser.parse_args()

    print(f"[train_nlp] model={MODEL_NAME} data={args.data} epochs={args.epochs}")
    print("Bu iskelet, etiketli veri bağlandığında doldurulmak üzere hazırdır:")
    print("  - AutoTokenizer/AutoModelForSequenceClassification (3 sınıf)")
    print("  - Girdi: İSTEMCİDE MASKELENMİŞ epikriz (PII içermemeli)")
    print("  - Token attribution: Integrated Gradients (captum) ile span skorları")
    print("  - Çıktı checkpoint'i AI Core'a MODEL_PATH env ile bağlanır")


if __name__ == "__main__":
    main()
