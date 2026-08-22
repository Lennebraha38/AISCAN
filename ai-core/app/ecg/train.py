"""EKG egitim hatti: cache -> baseline -> 1D ResNet -> degerlendirme.

Kullanim:
    python -m app.ecg.train build-cache --data-dir ../data/ecg
    python -m app.ecg.train baseline    --data-dir ../data/ecg
    python -m app.ecg.train deep        --data-dir ../data/ecg --epochs 20
    python -m app.ecg.train robustness  --data-dir ../data/ecg

Ciktilar:
    data/ecg/cache/            X.npy (fp16 memmap), y.npy, ids.json
    ai-core/models/ecg_resnet.pt + ecg_config.json + metrics.json
    docs/figures/              karisiklik matrisi + ogrenme egrileri PNG
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np

from app.ecg.labels import CLASS_NAMES, SUPERCLASSES
from app.ecg.preprocess import preprocess_record
from app.ecg.model import ECGResNet, count_parameters

TARGET_FS = 250


# ---------------------------------------------------------------- cache ----
def build_cache(data_dir: Path) -> None:
    from scipy.io import loadmat

    sel_path = data_dir / "selected.jsonl"
    entries = [json.loads(l) for l in open(sel_path) if l.strip()]
    cache = data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    L = TARGET_FS * 10
    keep: list[tuple[dict, np.ndarray]] = []
    skipped = 0
    for i, e in enumerate(entries):
        mat = data_dir / "raw" / e["dir"] / f"{e['record']}.mat"
        try:
            m = loadmat(str(mat))
            raw = m["val"]
            if raw.shape[0] != 12:
                raise ValueError(f"derivasyon sayisi {raw.shape[0]}")
            x = preprocess_record(raw, fs_in=e.get("fs", 500), target_fs=TARGET_FS)
        except Exception:
            skipped += 1
            continue
        keep.append((e, x))
        if (i + 1) % 500 == 0:
            print(f"[{i+1}/{len(entries)}] on islendi ({skipped} atlandi)", flush=True)

    n = len(keep)
    print(f"toplam {n} kayit hazir, {skipped} atlandi")
    X = np.lib.format.open_memmap(cache / "X.npy", mode="w+", dtype=np.float16, shape=(n, 12, L))
    y = np.zeros(n, dtype=np.int64)
    ids: list[str] = []
    for j, (e, x) in enumerate(keep):
        X[j] = x.astype(np.float16)
        y[j] = SUPERCLASSES.index(e["superclass"])
        ids.append(e["record"])
    X.flush()
    np.save(cache / "y.npy", y)
    (cache / "ids.json").write_text(json.dumps(ids))
    print("sinif dagilimi:", dict(Counter(SUPERCLASSES[c] for c in y)))


def load_cache(data_dir: Path) -> tuple[np.memmap, np.ndarray, list[str]]:
    cache = data_dir / "cache"
    X = np.load(cache / "X.npy", mmap_mode="r")
    y = np.load(cache / "y.npy")
    ids = json.loads((cache / "ids.json").read_text())
    return X, y, ids


def stratified_split(y: np.ndarray, seed: int = 42) -> tuple[np.ndarray, ...]:
    rng = random.Random(seed)
    idx_by_cls: dict[int, list[int]] = {}
    for i, c in enumerate(y):
        idx_by_cls.setdefault(int(c), []).append(i)
    tr, va, te = [], [], []
    for _, idxs in sorted(idx_by_cls.items()):
        rng.shuffle(idxs)
        n = len(idxs)
        n_tr = int(n * 0.8)
        n_va = int(n * 0.1)
        tr += idxs[:n_tr]
        va += idxs[n_tr : n_tr + n_va]
        te += idxs[n_tr + n_va :]
    for lst in (tr, va, te):
        rng.shuffle(lst)
    return np.array(tr), np.array(va), np.array(te)


def _batch(X: np.memmap, idx: np.ndarray, augment: bool = False) -> np.ndarray:
    xb = np.asarray(X[idx], dtype=np.float32)
    if augment:
        noise = np.random.default_rng(idx[0]).normal(0, 0.03, xb.shape).astype(np.float32)
        xb = xb + noise
    return xb


# -------------------------------------------------------------- baseline ----
def run_baseline(data_dir: Path, out_dir: Path) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    from app.ecg.features import extract_features

    X, y, ids = load_cache(data_dir)
    tr, va, te = stratified_split(y)
    print(f"split: train={len(tr)} val={len(va)} test={len(te)}")

    def feats(idxs: np.ndarray) -> np.ndarray:
        out = []
        for j, i in enumerate(idxs):
            sig = np.asarray(X[i], dtype=np.float32)
            out.append(extract_features(sig, TARGET_FS))
            if (j + 1) % 1000 == 0:
                print(f"  ozellik {j+1}/{len(idxs)}", flush=True)
        return np.stack(out)

    Xtr, Xva, Xte = feats(tr), feats(va), feats(te)
    clf = HistGradientBoostingClassifier(max_iter=300, random_state=42)
    clf.fit(Xtr, y[tr])
    pred = clf.predict(Xte)
    report = classification_report(y[te], pred, target_names=list(CLASS_NAMES), output_dict=True)
    macro_f1 = f1_score(y[te], pred, average="macro")
    cm = confusion_matrix(y[te], pred).tolist()
    result = {"model": "HistGradientBoosting+handcrafted", "macro_f1": round(float(macro_f1), 4),
              "report": report, "confusion_matrix": cm}
    print(json.dumps(result, indent=2))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "baseline_metrics.json").write_text(json.dumps(result, indent=2))


# ------------------------------------------------------------------ deep ----
def run_deep(data_dir: Path, out_dir: Path, models_dir: Path, epochs: int, batch_size: int) -> None:
    import torch
    import torch.nn as nn
    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    torch.set_num_threads(max(1, __import__("os").cpu_count() - 1))
    dev = torch.device("cpu")

    X, y, _ids = load_cache(data_dir)
    tr, va, te = stratified_split(y)

    counts = np.bincount(y[tr], minlength=len(SUPERCLASSES))
    weights = torch.tensor(
        (1.0 / np.sqrt(np.maximum(counts, 1))), dtype=torch.float32
    )
    weights = weights / weights.sum() * len(SUPERCLASSES)
    print("sinif agirliklari:", weights.tolist())

    model = ECGResNet(n_classes=len(SUPERCLASSES)).to(dev)
    print(f"parametre sayisi: {count_parameters(model):,}")
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    steps = max(1, (len(tr) // batch_size)) * epochs
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    lossf = nn.CrossEntropyLoss(weight=weights, label_smoothing=0.05)

    def evaluate(idxs: np.ndarray) -> tuple[float, np.ndarray]:
        model.eval()
        preds = []
        with torch.no_grad():
            for i in range(0, len(idxs), 128):
                xb = torch.from_numpy(_batch(X, idxs[i : i + 128])).to(dev)
                preds.append(model(xb).argmax(1).cpu())
        p = torch.cat(preds).numpy()
        return f1_score(y[idxs], p, average="macro"), p

    history = {"train_loss": [], "val_f1": []}
    best_f1, best_state, patience, bad = 0.0, None, 5, 0
    rng = np.random.default_rng(42)
    step = 0
    for ep in range(1, epochs + 1):
        order = rng.permutation(tr)
        tot, nb = 0.0, 0
        model.train()
        for i in range(0, len(order), batch_size):
            bidx = order[i : i + batch_size]
            if len(bidx) < 8:
                continue
            xb = torch.from_numpy(_batch(X, bidx, augment=True)).to(dev)
            yb = torch.from_numpy(y[bidx]).to(dev)
            opt.zero_grad(set_to_none=True)
            loss = lossf(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            sched.step()
            tot += float(loss)
            nb += 1
            step += 1
        vf1, _ = evaluate(va)
        history["train_loss"].append(round(tot / max(nb, 1), 4))
        history["val_f1"].append(round(float(vf1), 4))
        print(f"epoch {ep}: loss={tot/max(nb,1):.4f} val_macroF1={vf1:.4f}", flush=True)
        if vf1 > best_f1:
            best_f1, bad = vf1, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                print(f"erken durdurma (patience={patience})")
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    tf1, pred = evaluate(te)
    rep = classification_report(y[te], pred, target_names=list(CLASS_NAMES), output_dict=True)
    cm = confusion_matrix(y[te], pred).tolist()
    print(f"TEST macro F1 = {tf1:.4f}")

    models_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": list(CLASS_NAMES), "target_fs": TARGET_FS},
               models_dir / "ecg_resnet.pt")
    (models_dir / "ecg_config.json").write_text(json.dumps(
        {"architecture": "ECGResNet-1D", "params": count_parameters(model),
         "target_fs": TARGET_FS, "input_len": TARGET_FS * 10,
         "best_val_macro_f1": round(best_f1, 4)}, indent=2))

    metrics = {"model": "ECGResNet-1D", "test_macro_f1": round(float(tf1), 4),
               "best_val_macro_f1": round(best_f1, 4), "report": rep,
               "confusion_matrix": cm, "history": history}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "deep_metrics.json").write_text(json.dumps(metrics, indent=2))
    _plot(history, cm)


def _plot(history: dict, cm: list[list[int]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    figdir = Path(__file__).resolve().parents[2] / "docs" / "figures"
    figdir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].plot(history["train_loss"], label="egitim kaybi")
    ax[0].set_title("Kayip Egrisi")
    ax[0].set_xlabel("epoch")
    ax[1].plot(history["val_f1"], label="val macro F1", color="tab:green")
    ax[1].set_title("Dogrulama Macro F1")
    ax[1].set_xlabel("epoch")
    for a in ax:
        a.legend()
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(figdir / "learning_curves.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 4.4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(CLASS_NAMES)), CLASS_NAMES, rotation=20)
    ax.set_yticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    for i in range(len(cm)):
        for j in range(len(cm)):
            ax.text(j, i, str(cm[i][j]), ha="center", va="center",
                    color="white" if cm[i][j] > max(map(max, cm)) / 2 else "black")
    ax.set_title("Karısıklık Matrisi (test)")
    ax.set_xlabel("tahmin")
    ax.set_ylabel("gercek")
    fig.colorbar(im, shrink=0.85)
    fig.tight_layout()
    fig.savefig(figdir / "confusion_matrix.png", dpi=130)
    plt.close(fig)
    print(f"grafikler -> {figdir}")


# ------------------------------------------------------------ robustness ----
def run_robustness(data_dir: Path, models_dir: Path, out_dir: Path) -> None:
    """External validation simülasyonu: gurultu + baseline wander bozulmalari."""
    import torch
    from sklearn.metrics import f1_score

    X, y, _ids = load_cache(data_dir)
    _, _, te = stratified_split(y)
    ckpt = torch.load(models_dir / "ecg_resnet.pt", map_location="cpu", weights_only=False)
    model = ECGResNet(n_classes=len(SUPERCLASSES))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    def predict(idxs: np.ndarray, corrupt) -> np.ndarray:
        preds = []
        with torch.no_grad():
            for i in range(0, len(idxs), 128):
                xb = corrupt(np.asarray(X[idxs[i : i + 128]], dtype=np.float32))
                preds.append(model(torch.from_numpy(xb)).argmax(1))
        return torch.cat(preds).numpy()

    clean = predict(te, lambda b: b)
    scenarios = {
        "temiz": clean,
        "gauss_0.05": predict(te, lambda b: b + np.random.default_rng(1).normal(0, 0.05, b.shape).astype(np.float32)),
        "gauss_0.10": predict(te, lambda b: b + np.random.default_rng(2).normal(0, 0.10, b.shape).astype(np.float32)),
        "baseline_wander": predict(
            te,
            lambda b: b + (0.3 * np.sin(np.linspace(0, 6 * np.pi, b.shape[-1]))).astype(np.float32)[None, None, :],
        ),
    }
    res = {}
    for name, pred in scenarios.items():
        res[name] = round(float(f1_score(y[te], pred, average="macro")), 4)
        print(f"{name}: macro F1 = {res[name]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "robustness_metrics.json").write_text(json.dumps(res, indent=2))


def main() -> None:
    root = Path(__file__).resolve().parents[2]  # ai-core/
    ap = argparse.ArgumentParser(description="EKG egitim hatti")
    ap.add_argument("command", choices=["build-cache", "baseline", "deep", "robustness"])
    ap.add_argument("--data-dir", default=str(root.parent / "data" / "ecg"))
    ap.add_argument("--out-dir", default=str(root.parent / "docs" / "metrics"))
    ap.add_argument("--models-dir", default=str(root / "models"))
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    data_dir, out_dir, models_dir = Path(args.data_dir), Path(args.out_dir), Path(args.models_dir)
    if args.command == "build-cache":
        build_cache(data_dir)
    elif args.command == "baseline":
        run_baseline(data_dir, out_dir)
    elif args.command == "deep":
        run_deep(data_dir, out_dir, models_dir, args.epochs, args.batch_size)
    elif args.command == "robustness":
        run_robustness(data_dir, models_dir, out_dir)


if __name__ == "__main__":
    main()
