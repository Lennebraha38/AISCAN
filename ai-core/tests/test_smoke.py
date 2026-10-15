"""Smoke tests for ai-core ECG module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch

from app.ecg.model import ECGResNet, count_parameters
from app.ecg.labels import assign_superclass, subclasses_for, SUPERCLASSES, CLASS_NAMES
from app.ecg.preprocess import preprocess_record, detect_rpeaks, resample_to, normalize_leadwise
from app.ecg.train import DEFAULT_CFG, load_config, merge_config


def test_config_defaults_and_merge():
    """Config yükleme ve derin birleştirme (CLI > config > varsayılan)."""
    # Varsayılanlar beklenen anahtarları içerir
    for section in ("data", "model", "training", "augmentation", "calibration", "cv", "stage2"):
        assert section in DEFAULT_CFG, f"eksik bölüm: {section}"
    assert DEFAULT_CFG["model"]["in_channels"] == 12
    assert DEFAULT_CFG["training"]["loss"] == "focal"

    # Kısmi override, iç içe alanları korur
    merged = merge_config(DEFAULT_CFG, {"training": {"epochs": 7}})
    assert merged["training"]["epochs"] == 7
    assert merged["training"]["batch_size"] == DEFAULT_CFG["training"]["batch_size"]
    assert merged["model"] == DEFAULT_CFG["model"]

    # Repo config.yaml yüklenebilir olmalı (PyYAML varsa)
    cfg_path = Path(__file__).resolve().parents[1] / "config.yaml"
    loaded = load_config(cfg_path)
    assert loaded.get("model", {}).get("in_channels") == 12
    assert loaded.get("cv", {}).get("folds") == 5
    # Var olmayan dosya -> boş sözlük
    assert load_config(Path("yok-boyle-bir-dosya.yaml")) == {}

    print("[OK] test_config_defaults_and_merge")


def test_labels_mapping():
    """Test SNOMED-CT to superclass mapping."""
    # Block codes should map to block
    assert assign_superclass(["164909002"]) == "block"  # LBBB
    assert assign_superclass(["59118001"]) == "block"   # RBBB
    
    # Arrhythmia codes should map to arrhythmia
    assert assign_superclass(["164889003"]) == "arrhythmia"  # AFIB
    assert assign_superclass(["426761007"]) == "arrhythmia"  # SVT
    assert assign_superclass(["17338001"]) == "arrhythmia"   # VPB
    
    # Normal codes
    assert assign_superclass(["426783006"]) == "normal"  # SR
    
    # Priority: block > arrhythmia > normal
    assert assign_superclass(["164889003", "164909002"]) == "block"
    assert assign_superclass(["426783006", "17338001"]) == "arrhythmia"
    
    # Unknown codes
    assert assign_superclass(["999999999"]) is None
    assert assign_superclass([]) is None
    
    print("[OK] test_labels_mapping passed")


def test_subclasses_for():
    """Test subclass extraction."""
    subs = subclasses_for(["164889003", "164909002"])
    assert "AFIB" in subs
    assert "LBBB" in subs
    
    subs = subclasses_for(["426783006"])
    assert subs == []
    
    print("[OK] test_subclasses_for passed")


def test_preprocess_record():
    """Test ECG preprocessing pipeline."""
    # Create synthetic raw signal (12 leads, 5000 samples @ 500 Hz)
    raw = np.random.randn(12, 5000).astype(np.float64)
    
    processed = preprocess_record(raw, fs_in=500, target_fs=250)
    
    # Check output shape: 12 leads, 10 seconds @ 250 Hz = 2500 samples
    assert processed.shape == (12, 2500), f"Expected (12, 2500), got {processed.shape}"
    assert processed.dtype == np.float32
    
    # Check normalization: zero mean, unit variance per lead
    means = processed.mean(axis=1)
    stds = processed.std(axis=1)
    assert np.allclose(means, 0, atol=1e-5), f"Means not zero: {means}"
    assert np.allclose(stds, 1, atol=1e-5), f"Stds not one: {stds}"
    
    print("[OK] test_preprocess_record passed")


def test_resample():
    """Test resampling."""
    x = np.random.randn(12, 5000).astype(np.float64)
    y = resample_to(x, fs_in=500, fs_out=250)
    assert y.shape == (12, 2500)
    
    # Same fs should return copy
    z = resample_to(x, fs_in=500, fs_out=500)
    assert z.shape == (12, 5000)
    assert np.allclose(x, z)
    
    print("[OK] test_resample passed")


def test_normalize_leadwise():
    """Test lead-wise z-score normalization."""
    x = np.random.randn(12, 1000).astype(np.float64) * 10 + 5
    y = normalize_leadwise(x)
    assert np.allclose(y.mean(axis=1), 0, atol=1e-10)
    assert np.allclose(y.std(axis=1), 1, atol=1e-10)
    
    print("[OK] test_normalize_leadwise passed")


def test_detect_rpeaks():
    """Test R-peak detection."""
    fs = 250
    # Create signal with clear peaks every ~0.8s (75 bpm)
    t = np.arange(0, 10, 1/fs)
    signal = np.zeros_like(t)
    for i in range(8):
        center = int((i + 1) * 0.8 * fs)
        if center < len(signal):
            signal[center] = 1.0
            if center + 1 < len(signal): signal[center + 1] = 0.5
            if center - 1 >= 0: signal[center - 1] = 0.5
    
    peaks = detect_rpeaks(signal, fs)
    assert len(peaks) >= 6, f"Expected at least 6 peaks, got {len(peaks)}"
    # Check RR intervals are reasonable
    if len(peaks) >= 2:
        rr = np.diff(peaks) / fs
        assert np.all(rr > 0.4) and np.all(rr < 1.5), f"RR intervals unreasonable: {rr}"
    
    print("[OK] test_detect_rpeaks passed")


def test_model_creation():
    """Test ECGResNet model instantiation and forward pass."""
    model = ECGResNet(n_classes=3, in_ch=12, dropout=0.3)
    
    # Check parameter count
    n_params = count_parameters(model)
    assert 2_000_000 < n_params < 3_000_000, f"Expected ~2.2M params, got {n_params}"
    
    # Forward pass
    x = torch.randn(2, 12, 2500)
    with torch.no_grad():
        logits = model(x)
    
    assert logits.shape == (2, 3), f"Expected (2, 3), got {logits.shape}"
    
    # Test grad_cam
    cam = model.grad_cam(x, class_idx=1)
    assert cam.shape == (2, 2500), f"Grad-CAM shape mismatch: {cam.shape}"
    assert np.all(cam >= 0) and np.all(cam <= 1), "Grad-CAM not normalized to [0,1]"
    
    # Test input_saliency
    sal = model.input_saliency(x, class_idx=None)
    assert sal.shape == (2, 12, 2500), f"Saliency shape mismatch: {sal.shape}"
    assert np.all(sal >= 0) and np.all(sal <= 1), "Saliency not normalized to [0,1]"
    
    print("[OK] test_model_creation passed")


def test_model_eval_mode():
    """Test model behaves correctly in eval mode."""
    model = ECGResNet(n_classes=3)
    model.eval()
    
    x = torch.randn(1, 12, 2500)
    with torch.no_grad():
        logits1 = model(x)
        logits2 = model(x)
    
    # Deterministic in eval mode
    assert torch.allclose(logits1, logits2)
    
    print("[OK] test_model_eval_mode passed")


if __name__ == "__main__":
    test_config_defaults_and_merge()
    test_labels_mapping()
    test_subclasses_for()
    test_preprocess_record()
    test_resample()
    test_normalize_leadwise()
    test_detect_rpeaks()
    test_model_creation()
    test_model_eval_mode()
    print("\n[OK] All ai-core smoke tests passed!")