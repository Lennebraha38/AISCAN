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
