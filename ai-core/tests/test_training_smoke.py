"""Eğitim hattının minik sentetik veriyle uçtan uca duman testi.

Gerçek veri indirmeden boru hattının çalıştığını doğrular:
cache -> baseline (sklearn) -> deep (torch eğitim/val/calibration/CV) ->
robustness. Ayrıca test kümesinin doğrulama kümesine sızmadığını (önceki hata)
regresyon olarak kontrol eder.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from app.ecg import train as T

L = T.TARGET_FS * 10  # 2500 örnek (10 sn @ 250 Hz)
PER_CLASS = 12


def _make_cache(root: Path) -> Path:
    """Minik ama geçerli bir eğitim cache'i (X.npy/y.npy/ids.json/subclasses.json) üretir."""
    data_dir = root / "ecg"
    cache = data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    n_classes = len(T.SUPERCLASSES)
    n = PER_CLASS * n_classes
    rng = np.random.default_rng(0)
    # preprocess_record çıktısına benzer: lead bazlı z-skor (std ~ 1)
    X = rng.normal(0.0, 1.0, (n, 12, L)).astype(np.float16)
    y = np.array([c for c in range(n_classes) for _ in range(PER_CLASS)], dtype=np.int64)
    ids = [f"TX{i:05d}" for i in range(n)]
    sub = [[] for _ in range(n)]
    np.save(cache / "X.npy", X)
    np.save(cache / "y.npy", y)
    (cache / "ids.json").write_text(json.dumps(ids))
    (cache / "subclasses.json").write_text(json.dumps(sub))
    return data_dir


@pytest.fixture()
def synth(tmp_path, monkeypatch):
    data_dir = _make_cache(tmp_path)
    # _plot, repo'daki commit'li figürleri ezmesin.
    monkeypatch.setattr(T, "_plot", lambda *a, **k: None)
    return data_dir, tmp_path


def test_load_cache_roundtrip(synth):
    data_dir, _ = synth
    X, y, ids, sub = T.load_cache(data_dir)
    n_classes = len(T.SUPERCLASSES)
    assert X.shape == (PER_CLASS * n_classes, 12, L)
    assert len(y) == len(ids) == len(sub) == X.shape[0]
    assert set(np.unique(y).tolist()) == set(range(n_classes))


def test_baseline_smoke(synth):
    data_dir, tmp = synth
    out = tmp / "metrics"
    T.run_baseline(data_dir, out)
    res = json.loads((out / "baseline_metrics.json").read_text())
    assert 0.0 <= res["macro_f1"] <= 1.0
    assert len(res["confusion_matrix"]) == len(T.SUPERCLASSES)


def test_deep_and_robustness_smoke(synth):
    data_dir, tmp = synth
    out = tmp / "metrics"
    models = tmp / "models"

    # epochs=1, batch_size=8, folds=2 -> hızlı ama tüm yolları (CV + final) çalıştırır.
    T.run_deep(data_dir, out, models, epochs=1, batch_size=8, loss="focal", folds=2)

    assert (models / "ecg_resnet.pt").exists()
    cfg = json.loads((models / "ecg_config.json").read_text())
    assert cfg["architecture"] == "ECGResNet-1D"

    deep = json.loads((out / "deep_metrics.json").read_text())
    for key in ("test_macro_f1", "best_val_macro_f1", "history", "fold_eval"):
        assert key in deep
    # CV tablosu folds=2 için fold_1/fold_2 + ortalama/std içermeli.
    assert {"fold_1", "fold_2", "mean", "std"} <= set(deep["fold_eval"])

    T.run_robustness(data_dir, models, out)
    rob = json.loads((out / "robustness_metrics.json").read_text())
    assert {"temiz", "gauss_0.20", "baseline_wander"} <= set(rob)
    assert all(0.0 <= v <= 1.0 for v in rob.values())


def test_validation_split_has_no_test_leakage(synth):
    """Regresyon: doğrulama kümesi YALNIZ eğitim verisinden üretilir.

    Önceki hata, erken durdurma/model seçiminde test kümesini kullanıyordu
    (veri sızıntısı). Bu testin bölmeleri test indekslerinden tamamen ayrık olmalı.
    """
    data_dir, _ = synth
    _X, y, _ids, _sub = T.load_cache(data_dir)
    tr, va, te = T.stratified_split(y)
    train_all = np.concatenate([tr, va])
    hold_tr, hold_va = T.stratified_holdout(train_all, y)

    te_set = set(te.tolist())
    assert te_set.isdisjoint(set(hold_tr.tolist()))
    assert te_set.isdisjoint(set(hold_va.tolist()))
    # Eğitim indeksleri tam olarak train+val'e bölünür (kayıp/çakışma yok).
    assert set(hold_tr.tolist()) | set(hold_va.tolist()) == set(train_all.tolist())
    assert len(hold_va) > 0  # en az bir doğrulama örneği
    assert set(y[hold_va].tolist()) == set(y[train_all].tolist())  # her sınıf temsil edilir


# ---------------------------------------------------------------------------
# Aşama 2 (fine-grained hiyerarşik kafa) duman testi
# ---------------------------------------------------------------------------


def _write_cache(data_dir: Path, X: np.ndarray, y: np.ndarray, sub: list) -> Path:
    """Verilen dizilerle cache yazar (sınıf başına farklı örnek sayısı için)."""
    cache = data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    np.save(cache / "X.npy", X)
    np.save(cache / "y.npy", y)
    (cache / "ids.json").write_text(json.dumps([f"TX{i:05d}" for i in range(len(y))]))
    (cache / "subclasses.json").write_text(json.dumps(sub))
    return data_dir


def test_stage2_smoke(tmp_path, monkeypatch):
    """stage2 kafası: dondurulmuş backbone havuzlama + hiyerarşik kafa eğitimi.

    Aritmi sınıfına >=200 eğitim örneği ve iki alt grup (AFIB/SVT) verilir;
    böylece hem "yetersiz veri -> atla" yolu (blok) hem de gerçek kafa eğitimi
    (aritmi) aynı koşuda egzersiz edilir.
    """
    from app.ecg.model import ECGResNet

    # Sınıf indeksleri: 0=normal, 1=arrhythmia, 2=block (labels.SUPERCLASSES).
    counts = {1: 300, 2: 20, 0: 20}
    y_list, sub = [], []
    for cls, n in counts.items():
        for i in range(n):
            y_list.append(cls)
            if cls == 1:
                sub.append(["AFIB"] if i % 2 == 0 else ["SVT"])
            elif cls == 2:
                sub.append(["LBBB"] if i % 2 == 0 else ["RBBB"])
            else:
                sub.append([])
    y = np.array(y_list, dtype=np.int64)
    L2 = 500  # stage2 havuzlaması her uzunlukta çalışır; belleği küçük tutar.
    X = np.random.default_rng(1).normal(0.0, 1.0, (len(y), 12, L2)).astype(np.float16)
    data_dir = _write_cache(tmp_path / "ecg", X, y, sub)

    # Sentetik dondurulmuş backbone checkpoint'i (stage2 yalnız state_dict okur).
    models = tmp_path / "models"
    models.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"state_dict": ECGResNet(n_classes=len(T.SUPERCLASSES)).state_dict()},
        models / "ecg_resnet.pt",
    )

    # min_subclass_count düşürülür ki sentetik alt gruplar "bilinen" sayılsın.
    monkeypatch.setitem(T.CFG["stage2"], "min_subclass_count", 10)
    out = tmp_path / "metrics"
    T.run_stage2(data_dir, out, models, epochs=2, batch_size=32)

    res = json.loads((out / "stage2_metrics.json").read_text())
    heads = res["subclass_heads"]
    assert {"AFIB", "SVT", "other"} == set(heads["arrhythmia"])
    # Aritmi kafası yeterli veriyle eğitildi ve metrik üretti.
    assert 0.0 <= res["arrhythmia_macro_f1"] <= 1.0
    assert "arrhythmia_val_macro_f1" in res
    assert res["subclass_counts"]["arrhythmia"]["AFIB"] > 0

