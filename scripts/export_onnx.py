#!/usr/bin/env python
"""
ONNX Export Script for ECGResNet-1D

Usage:
    python scripts/export_onnx.py --model-path ai-core/models/ecg_resnet.pt --output-path ai-core/models/ecg_resnet.onnx
    python scripts/export_onnx.py --config ai-core/config.yaml --output-path ai-core/models/ecg_resnet.onnx
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-core"))

from app.ecg.model import ECGResNet


def load_model_from_checkpoint(ckpt_path: Path, config_path: Path | None = None) -> ECGResNet:
    """Load ECGResNet model from checkpoint."""
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    
    classes = ckpt.get("classes", ["normal", "arrhythmia", "block"])
    n_classes = len(classes)
    
    # Load config if available
    dropout = 0.3
    if config_path and config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            dropout = cfg.get("model", {}).get("dropout", 0.3)
        except Exception:
            pass
    
    model = ECGResNet(n_classes=n_classes, dropout=dropout)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    
    print(f"Loaded model: {n_classes} classes, {sum(p.numel() for p in model.parameters()):,} params")
    return model


def export_onnx(
    model: ECGResNet,
    output_path: Path,
    input_shape: tuple = (1, 12, 2500),
    opset_version: int = 17,
    dynamic_axes: bool = True
) -> None:
    """Export model to ONNX format."""
    
    # Create dummy input
    dummy_input = torch.randn(*input_shape)
    
    # Define dynamic axes for batch size
    dynamic_axes_dict = None
    if dynamic_axes:
        dynamic_axes_dict = {
            "input": {0: "batch_size"},
            "output": {0: "batch_size"}
        }
    
    # Export
    print(f"Exporting to ONNX: {output_path}")
    print(f"Input shape: {input_shape}")
    print(f"Opset version: {opset_version}")
    
    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        export_params=True,
        opset_version=opset_version,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes=dynamic_axes_dict,
        verbose=False
    )
    
    print("ONNX export completed!")


def verify_onnx(model: ECGResNet, onnx_path: Path, input_shape: tuple = (1, 12, 2500)) -> None:
    """Verify ONNX model outputs match PyTorch model."""
    try:
        import onnxruntime as ort
    except ImportError:
        print("Warning: onnxruntime not installed, skipping verification")
        return
    
    # PyTorch inference
    dummy_input = torch.randn(*input_shape)
    with torch.no_grad():
        pytorch_out = model(dummy_input).numpy()
    
    # ONNX inference
    session = ort.InferenceSession(str(onnx_path))
    onnx_out = session.run(None, {"input": dummy_input.numpy()})[0]
    
    # Compare
    max_diff = np.abs(pytorch_out - onnx_out).max()
    mean_diff = np.abs(pytorch_out - onnx_out).mean()
    
    print(f"\nVerification:")
    print(f"  PyTorch output shape: {pytorch_out.shape}")
    print(f"  ONNX output shape: {onnx_out.shape}")
    print(f"  Max absolute difference: {max_diff:.6f}")
    print(f"  Mean absolute difference: {mean_diff:.6f}")
    
    if max_diff < 1e-4:
        print("  ✅ ONNX model matches PyTorch model!")
    else:
        print(f"  ⚠️  Difference > 1e-4, check model")


def export_torchscript(model: ECGResNet, output_path: Path, input_shape: tuple = (1, 12, 2500)) -> None:
    """Export model to TorchScript format."""
    dummy_input = torch.randn(*input_shape)
    
    print(f"Exporting to TorchScript: {output_path}")
    
    # Trace the model
    traced_model = torch.jit.trace(model, dummy_input)
    traced_model.save(str(output_path))
    
    # Verify
    with torch.no_grad():
        original_out = model(dummy_input)
        traced_out = traced_model(dummy_input)
    
    max_diff = (original_out - traced_out).abs().max().item()
    print(f"  Max difference: {max_diff:.6f}")
    if max_diff < 1e-5:
        print("  ✅ TorchScript model matches original!")
    else:
        print(f"  ⚠️  Difference > 1e-5")


def main():
    parser = argparse.ArgumentParser(description="Export ECGResNet to ONNX/TorchScript")
    parser.add_argument("--model-path", type=str, default="ai-core/models/ecg_resnet.pt",
                        help="Path to PyTorch checkpoint")
    parser.add_argument("--config", type=str, default="ai-core/config.yaml",
                        help="Path to config YAML")
    parser.add_argument("--output-path", type=str, default="ai-core/models/ecg_resnet.onnx",
                        help="Output ONNX path")
    parser.add_argument("--torchscript-path", type=str, default=None,
                        help="Optional TorchScript output path")
    parser.add_argument("--opset", type=int, default=17, help="ONNX opset version")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size for export")
    parser.add_argument("--verify", action="store_true", help="Verify ONNX output matches PyTorch")
    parser.add_argument("--no-dynamic", action="store_true", help="Disable dynamic batch axis")
    
    args = parser.parse_args()
    
    model_path = Path(args.model_path)
    config_path = Path(args.config) if args.config else None
    output_path = Path(args.output_path)
    
    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        return 1
    
    # Load model
    model = load_model_from_checkpoint(model_path, config_path)
    
    # Determine input shape
    input_shape = (args.batch_size, 12, 2500)
    
    # Export ONNX
    export_onnx(
        model,
        output_path,
        input_shape=input_shape,
        opset_version=args.opset,
        dynamic_axes=not args.no_dynamic
    )
    
    # Export TorchScript if requested
    if args.torchscript_path:
        export_torchscript(model, Path(args.torchscript_path), input_shape)
    
    # Verify if requested
    if args.verify:
        verify_onnx(model, output_path, input_shape=(1, 12, 2500))
    
    print("\n✅ Export completed successfully!")
    return 0


if __name__ == "__main__":
    exit(main())