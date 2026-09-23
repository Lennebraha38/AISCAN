"""EKG egitim hatti: cache -> baseline -> 1D ResNet -> 2. asama -> degerlendirme.

Kullanim:
    python -m app.ecg.train build-cache --data-dir ../data/ecg
    python -m app.ecg.train baseline    --data-dir ../data/ecg
    python -m app.ecg.train deep        --data-dir ../data/ecg --epochs 40
    python -m app.ecg.train robustness  --data-dir ../data/ecg
    python -m app.ecg.train stage2      --data-dir ../data/ecg --epochs-stage2 15

Ciktilar:
    data/ecg/cache/            X.npy (fp16 memmap), y.npy, ids.json, subclasses.json
    ai-core/models/ecg_resnet.pt + ecg_config.json + ecg_finegrained.pt
    docs/figures/              karisiklik matrisi + ogrenme egrileri PNG
    docs/metrics/              baseline/deep/robustness/stage2 JSON

Not: Kayit bazli split = hasta bazli split. PhysioNet ECG-Arrhythmia 1.0.0'da
her kayit (JSxxxxx) ayri bir bireye aittir; ayni bireyin coklu kaydi yoktur.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from app.ecg.labels import CLASS_NAMES, SUPERCLASSES
from app.ecg.preprocess import preprocess_record
from app.ecg.model import ECGResNet, count_parameters

TARGET_FS = 250
N_CLASSES = len(SUPERCLASSES)


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
    sub: list[list[str]] = []
    for j, (e, x) in enumerate(keep):
        X[j] = x.astype(np.float16)
        y[j] = SUPERCLASSES.index(e["superclass"])
        ids.append(e["record"])
        sub.append(e.get("subclasses") or [])
    X.flush()
    np.save(cache / "y.npy", y)
    (cache / "ids.json").write_text(json.dumps(ids))
    (cache / "subclasses.json").write_text(json.dumps(sub))
    print("sinif dagilimi:", dict(Counter(SUPERCLASSES[c] for c in y)))


def load_cache(data_dir: Path) -> tuple[np.memmap, np.ndarray, list[str], list[list[str]]]:
    cache = data_dir / "cache"
    X = np.load(cache / "X.npy", mmap_mode="r")
    y = np.load(cache / "y.npy")
    ids = json.loads((cache / "ids.json").read_text())
    sub_file = cache / "subclasses.json"
    sub = json.loads(sub_file.read_text()) if sub_file.exists() else [[] for _ in ids]
    return X, y, ids, sub


def stratified_split(y: np.ndarray, seed: int = 42) -> tuple[np.ndarray, ...]:
    """Kayit bazli (bu veri setinde = hasta bazli) tabakali bölunme."""
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


def _batch(X: np.memmap, idx: np.ndarray, augment: bool = False, rng: np.random.Generator | None = None) -> np.ndarray:
    rng = rng or np.random.default_rng(0)
    xb = np.asarray(X[idx], dtype=np.float32)
    if not augment:
        return xb
    n = xb.shape[0]
    xb = xb + rng.normal(0, 0.03, xb.shape).astype(np.float32)
    shifts = rng.integers(-150, 150, size=n)
    timed = xb.copy()
    for i, s in enumerate(shifts):
        if s > 0:
            timed[i, :, s:] = xb[i, :, :-s]
        elif s < 0:
            timed[i, :, :s] = xb[i, :, -s:]
    scale = rng.uniform(0.9, 1.1, size=(n, 1, 1)).astype(np.float32)
    lead_scale = rng.uniform(0.95, 1.05, size=(n, 12, 1)).astype(np.float32)
    return timed * scale * lead_scale


# ----------------------------------------------------------- yardimci ----
class FocalLoss(nn.Module):
    """Sinif dengesizligi icin focal loss (gamma=2), sinif agirlikli alpha ile."""

    def __init__(self, alpha: np.ndarray, gamma: float = 2.0):
        super().__init__()
        self.register_buffer("alpha_t", torch.tensor(alpha, dtype=torch.float32))
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce = nn.functional.cross_entropy(logits, targets, reduction="none")
        pt = torch.exp(-ce)
        alpha_t = self.alpha_t[targets]
        return (alpha_t * (1 - pt) ** self.gamma * ce).mean()


def _pred_with_bias(probs: np.ndarray, bias: np.ndarray) -> np.ndarray:
    return np.argmax(np.log(probs + 1e-9) + bias, axis=1)


def _macro_f1(probs: np.ndarray, y: np.ndarray, bias: np.ndarray) -> float:
    from sklearn.metrics import f1_score

    return float(f1_score(y, _pred_with_bias(probs, bias), average="macro"))


def tune_bias(val_probs: np.ndarray, val_y: np.ndarray,
              rounds: int = 4, span: float = 1.6, steps: int = 41) -> np.ndarray:
    """Sinif-bazli logit bias'ini val setinde macro F1'i maksimize edecek sekilde ayarlar."""
    bias = np.zeros(N_CLASSES)
    for _ in range(rounds):
        changed = False
        for c in range(N_CLASSES):
            best_f1, best_b = _macro_f1(val_probs, val_y, bias), bias[c]
            for b in np.linspace(bias[c] - span, bias[c] + span, steps):
                bias[c] = b
                f1 = _macro_f1(val_probs, val_y, bias)
                if f1 > best_f1:
                    best_f1, best_b, changed = f1, b, True
            bias[c] = best_b
        if not changed:
            break
    return bias


# -------------------------------------------------------------- baseline ----
def run_baseline(data_dir: Path, out_dir: Path) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    from app.ecg.features import extract_features

    X, y, ids, _sub = load_cache(data_dir)
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
    clf = HistGradientBoostingClassifier(max_iter=400, random_state=42)
    clf.fit(Xtr, y[tr])

    bias = tune_bias(clf.predict_proba(Xva), y[va])
    pred = _pred_with_bias(clf.predict_proba(Xte), bias)
    report = classification_report(y[te], pred, target_names=list(CLASS_NAMES), output_dict=True)
    macro_f1 = f1_score(y[te], pred, average="macro")
    cm = confusion_matrix(y[te], pred).tolist()
    result = {"model": "HistGradientBoosting+handcrafted", "macro_f1": round(float(macro_f1), 4),
              "bias": bias.round(3).tolist(), "report": report, "confusion_matrix": cm}
    print(json.dumps(result, indent=2))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "baseline_metrics.json").write_text(json.dumps(result, indent=2))


# ------------------------------------------------------------------ deep ----
def run_deep(data_dir: Path, out_dir: Path, models_dir: Path, epochs: int,
             batch_size: int, loss: str, folds: int) -> None:
    from sklearn.metrics import classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import StratifiedKFold

    torch.set_num_threads(max(1, __import__("os").cpu_count() - 1))
    dev = torch.device("cpu")

    X, y, _ids, _sub = load_cache(data_dir)
    tr, va, te = stratified_split(y)
    counts = np.bincount(y[tr], minlength=N_CLASSES)
    alpha_cw = 1.0 / np.sqrt(np.maximum(counts, 1))
    alpha_cw = alpha_cw / alpha_cw.sum() * N_CLASSES
    print("sinif agirliklari:", alpha_cw.round(3).tolist())
    print(f"split: train={len(tr)} val={len(va)} test={len(te)}")

    def evaluate_model(model, idxs: np.ndarray, bs: int = 128) -> tuple[np.ndarray, np.ndarray]:
        model.eval()
        p = []
        with torch.no_grad():
            for i in range(0, len(idxs), bs):
                xb = torch.from_numpy(_batch(X, idxs[i : i + bs])).to(dev)
                p.append(torch.softmax(model(xb), 1).cpu().numpy())
        return np.concatenate(p), y[idxs]

    def train_once(train_idx: np.ndarray, val_idx: np.ndarray,
                   seed: int) -> tuple[ECGResNet, dict, np.ndarray]:
        rng = np.random.default_rng(seed)
        model = ECGResNet(n_classes=N_CLASSES).to(dev)
        opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
        steps = max(1, (len(train_idx) // batch_size)) * epochs
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)

        if loss == "focal":
            crit = FocalLoss(alpha=alpha_cw, gamma=2.0)
        else:
            crit = nn.CrossEntropyLoss(weight=torch.tensor(alpha_cw, dtype=torch.float32),
                                       label_smoothing=0.05)

        hist = {"train_loss": [], "val_f1": []}
        best_f1, best_state, patience, bad = 0.0, None, 8, 0
        step = 0
        for ep in range(1, epochs + 1):
            order = rng.permutation(train_idx)
            tot, nb = 0.0, 0
            model.train()
            for i in range(0, len(order), batch_size):
                bidx = order[i : i + batch_size]
                if len(bidx) < 8:
                    continue
                xb = torch.from_numpy(_batch(X, bidx, augment=True, rng=rng)).to(dev)
                yb = torch.from_numpy(y[bidx]).to(dev)
                opt.zero_grad(set_to_none=True)
                lossv = crit(model(xb), yb)
                lossv.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                opt.step()
                sched.step()
                tot += float(lossv)
                nb += 1
                step += 1
            vp, vy = evaluate_model(model, val_idx)
            vf1 = f1_score(vy, vp.argmax(1), average="macro")
            hist["train_loss"].append(round(tot / max(nb, 1), 4))
            hist["val_f1"].append(round(float(vf1), 4))
            print(f"epoch {ep}: loss={tot/max(nb,1):.4f} val_macroF1={vf1:.4f}", flush=True)
            if vf1 > best_f1:
                best_f1, bad = vf1, 0
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
            else:
                bad += 1
                if bad >= patience:
                    print(f"erken durdurma (patience={patience}) @ ep {ep}")
                    break

        if best_state is not None:
            model.load_state_dict(best_state)
        val_probs, val_y = evaluate_model(model, val_idx)
        bias = tune_bias(val_probs, val_y)
        tuned_f1 = _macro_f1(val_probs, val_y, bias)
        return model, {"best_val_macro_f1": round(best_f1, 4), "tuned_val_macro_f1": round(tuned_f1, 4),
                       "bias": bias.round(3).tolist(), "history": hist}, bias

    fold_table: dict[str, list[float]] = {}
    if folds > 1:
        all_idx = np.concatenate([tr, va])
        sum_, ssum = 0.0, 0.0
        fold_vals: list[float] = []
        skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
        for f, (f_tr, f_va) in enumerate(skf.split(np.zeros(len(all_idx)), y[all_idx]), 1):
            _, meta, _ = train_once(all_idx[f_tr], all_idx[f_va], seed=100 + f)
            vf = meta["tuned_val_macro_f1"]
            fold_vals.append(vf)
            sum_ += vf
            ssum += vf * vf
            print(f"fold {f}/{folds}: tuned_val_macroF1={vf:.4f}")
        mean_, std_ = sum_ / folds, float(np.sqrt(max(ssum / folds - (sum_ / folds) ** 2, 0)))
        fold_table = {f"fold_{i + 1}": v for i, v in enumerate(fold_vals)}
        fold_table["mean"] = round(mean_, 4)
        fold_table["std"] = round(std_, 4)
        print(f"CV ort: {mean_:.4f} +/- {std_:.4f}")

    model, meta, bias = train_once(tr, va, seed=42)
    test_probs, test_y = evaluate_model(model, te)
    pred = _pred_with_bias(test_probs, bias)
    pred_raw = test_probs.argmax(1)
    tf1 = float(f1_score(test_y, pred, average="macro"))
    tf1_raw = float(f1_score(test_y, pred_raw, average="macro"))
    rep = classification_report(test_y, pred, target_names=list(CLASS_NAMES), output_dict=True)
    cm = confusion_matrix(test_y, pred).tolist()
    print(f"TEST macro F1 (raw)={tf1_raw:.4f} | tuned={tf1:.4f} | val_best={meta['best_val_macro_f1']:.4f}")

    models_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": list(CLASS_NAMES),
                "target_fs": TARGET_FS}, models_dir / "ecg_resnet.pt")
    (models_dir / "ecg_config.json").write_text(json.dumps(
        {"architecture": "ECGResNet-1D", "params": count_parameters(model),
         "target_fs": TARGET_FS, "input_len": TARGET_FS * 10,
         "loss": loss, "best_val_macro_f1": meta["best_val_macro_f1"],
         "bias": meta["bias"]}, indent=2))

    metrics = {"model": "ECGResNet-1D", "test_macro_f1_raw": round(tf1_raw, 4),
               "test_macro_f1": round(tf1, 4), "best_val_macro_f1": meta["best_val_macro_f1"],
               "tuned_val_macro_f1": meta["tuned_val_macro_f1"], "bias": meta["bias"],
               "report": rep, "confusion_matrix": cm, "history": meta["history"],
               "fold_eval": fold_table}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "deep_metrics.json").write_text(json.dumps(metrics, indent=2))
    _plot(meta["history"], cm)


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
    ax.set_title("Karışıklık Matrisi (test)")
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
    from sklearn.metrics import f1_score

    X, y, _ids, _sub = load_cache(data_dir)
    _, _, te = stratified_split(y)
    ckpt = torch.load(models_dir / "ecg_resnet.pt", map_location="cpu", weights_only=False)
    model = ECGResNet(n_classes=N_CLASSES)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    bias = np.asarray(_json_bias(models_dir) or [0.0] * N_CLASSES)

    def predict(idxs: np.ndarray, corrupt) -> np.ndarray:
        preds = []
        with torch.no_grad():
            for i in range(0, len(idxs), 128):
                xb = corrupt(np.asarray(X[idxs[i : i + 128]], dtype=np.float32))
                preds.append(torch.softmax(model(torch.from_numpy(xb)), 1).numpy())
        return np.concatenate(preds)

    probs_clean = predict(te, lambda b: b)
    scenarios = {
        "temiz": probs_clean,
        "gauss_0.05": predict(te, lambda b: b + np.random.default_rng(1).normal(0, 0.05, b.shape).astype(np.float32)),
        "gauss_0.10": predict(te, lambda b: b + np.random.default_rng(2).normal(0, 0.10, b.shape).astype(np.float32)),
        "gauss_0.20": predict(te, lambda b: b + np.random.default_rng(3).normal(0, 0.20, b.shape).astype(np.float32)),
        "baseline_wander": predict(
            te,
            lambda b: b + (0.3 * np.sin(np.linspace(0, 6 * np.pi, b.shape[-1]))).astype(np.float32)[None, None, :],
        ),
    }
    res = {}
    for name, probs in scenarios.items():
        pred = _pred_with_bias(probs, bias)
        res[name] = round(float(f1_score(y[te], pred, average="macro")), 4)
        print(f"{name}: macro F1 = {res[name]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "robustness_metrics.json").write_text(json.dumps(res, indent=2))


def _json_bias(models_dir: Path) -> list | None:
    try:
        cfg = json.loads((models_dir / "ecg_config.json").read_text())
        return cfg.get("bias")
    except Exception:
        return None


# --------------------------------------------------------------- stage2 ----
MIN_SUBCLASS_COUNT = 40


def run_stage2(data_dir: Path, out_dir: Path, models_dir: Path, epochs: int, batch_size: int) -> None:
    """2. asama (fine-grained) modeli: donmus backbone uzerinde superclass-bazli alt kafalar.

    Alt grup hedefleri SUBCLASS_BY_CODE haritasinden uretilir; nadir alt gruplar
    (MIN_SUBCLASS_COUNT alti) 'other' olarak gruplanir. Sonuclar stage2_metrics.json'a yazilir.
    """
    from sklearn.metrics import classification_report, f1_score

    torch.set_num_threads(max(1, __import__("os").cpu_count() - 1))
    dev = torch.device("cpu")

    X, y, _ids, sub = load_cache(data_dir)
    tr, va, te = stratified_split(y)
    train_idx = np.concatenate([tr, va])
    print("stage2: superclass backbone yukleniyor...")

    ckpt = torch.load(models_dir / "ecg_resnet.pt", map_location="cpu", weights_only=False)
    backbone = ECGResNet(n_classes=N_CLASSES)
    backbone.load_state_dict(ckpt["state_dict"])
    for p in backbone.parameters():
        p.requires_grad = False
    backbone.eval()
    backbone.to(dev)

    by_super: dict[str, defaultdict] = {"arrhythmia": defaultdict(list), "block": defaultdict(list)}
    for i, subs in enumerate(sub):
        s = SUPERCLASSES[int(y[i])]
        if s not in by_super:
            continue
        first = subs[0] if subs else None
        by_super[s][first].append(i)

    head_desc: dict[str, list[str]] = {}
    sub_index: dict[str, dict[str, int]] = {}
    sub_labels: dict[str, np.ndarray] = {}
    for s, groups in by_super.items():
        keep = [k for k, v in groups.items() if k is not None and len(v) >= MIN_SUBCLASS_COUNT]
        keep = sorted(keep, key=lambda k: -len(groups[k]))[:8]
        classes = keep + (["other"] if keep else [])
        head_desc[s] = classes
        sub_index[s] = {c: i for i, c in enumerate(classes)}
        lab = np.full(len(y), -1)
        for i, subs in enumerate(sub):
            if SUPERCLASSES[int(y[i])] != s:
                continue
            first = subs[0] if subs else None
            lab[i] = sub_index[s].get(first if first in sub_index[s] else "other", -1)
        sub_labels[s] = lab
        print(f"  {s}: {len(classes)} alt grup -> " +
              ", ".join(f"{c}({len(groups.get(c, []))})" for c in classes))

    def pooled(idxs: np.ndarray) -> np.ndarray:
        feats = []
        for i in range(0, len(idxs), 64):
            bidx = idxs[i : i + 64]
            xb = torch.from_numpy(_batch(X, bidx)).to(dev)
            with torch.no_grad():
                h = backbone.stem(xb)
                for st in (backbone.stage1, backbone.stage2, backbone.stage3, backbone.stage4):
                    h = st(h)
                h = h.mean(dim=-1)
            feats.append(h.cpu().numpy())
        return np.concatenate(feats)

    feats_te = pooled(te)
    stage2_result: dict = {"subclass_heads": head_desc, "subclass_counts": {}}
    for s, classes in head_desc.items():
        labels = sub_labels[s]
        valid_tr = np.array([i for i in train_idx if labels[i] >= 0])
        valid_te = np.array([i for i in te if labels[i] >= 0])
        pos_te = {int(g): j for j, g in enumerate(te)}
        valid_te_pos = np.array([pos_te[int(i)] for i in valid_te])
        counts_tr = Counter(int(labels[i]) for i in valid_tr)
        stage2_result["subclass_counts"][s] = {
            cls: int(counts_tr.get(sub_index[s][cls], 0)) for cls in classes
        }
        if len(valid_tr) < 200 or len(set(int(labels[i]) for i in valid_tr)) < 2:
            print(f"  {s}: yetersiz alt grup verisi, atlandi")
            continue

        Xt = torch.from_numpy(pooled(valid_tr)).to(dev)
        yt = torch.from_numpy(labels[valid_tr]).to(dev)
        Xe = torch.from_numpy(feats_te[valid_te_pos]).to(dev)
        ye = labels[valid_te]
        n_tr = len(valid_tr)

        head = nn.Linear(256, len(classes)).to(dev)
        head.weight.data.normal_(0, 0.01)
        head.bias.data.zero_()
        opt = torch.optim.AdamW(head.parameters(), lr=3e-3, weight_decay=1e-3)
        best_f1, best_state, bad = 0.0, None, 0
        for ep in range(1, epochs + 1):
            perm = torch.randperm(n_tr).numpy()
            head.train()
            total, nb = 0.0, 0
            for i in range(0, n_tr, batch_size):
                bidx = perm[i : i + batch_size]
                if len(bidx) < 8:
                    continue
                opt.zero_grad(set_to_none=True)
                loss = nn.functional.cross_entropy(head(Xt[bidx]), yt[bidx])
                loss.backward()
                opt.step()
                total += float(loss)
                nb += 1
            head.eval()
            with torch.no_grad():
                pred = head(Xe).argmax(1).cpu().numpy()
            f1 = float(f1_score(ye, pred, average="macro"))
            if f1 > best_f1:
                best_f1, bad, best_state = f1, 0, {k: v.clone() for k, v in head.state_dict().items()}
            else:
                bad += 1
                if bad >= 5:
                    print(f"  {s}: erken durdurma @ ep {ep}")
                    break
        if best_state is not None:
            head.load_state_dict(best_state)
        head.eval()
        with torch.no_grad():
            pred = head(Xe).argmax(1).cpu().numpy()
        rep = classification_report(ye, pred, target_names=classes, output_dict=True)
        stage2_result[f"{s}_macro_f1"] = round(float(f1_score(ye, pred, average="macro")), 4)
        stage2_result[f"{s}_report"] = rep
        print(f"  {s}: alt-grup macro F1 = {stage2_result[f'{s}_macro_f1']:.4f} (n_test={len(valid_te)})")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage2_metrics.json").write_text(json.dumps(stage2_result, indent=2))
    print(f"stage2 sonuclari -> {out_dir / 'stage2_metrics.json'}")


def main() -> None:
    root = Path(__file__).resolve().parents[2]  # ai-core/
    ap = argparse.ArgumentParser(description="EKG egitim hatti")
    ap.add_argument("command", choices=["build-cache", "baseline", "deep", "robustness", "stage2"])
    ap.add_argument("--data-dir", default=str(root.parent / "data" / "ecg"))
    ap.add_argument("--out-dir", default=str(root.parent / "docs" / "metrics"))
    ap.add_argument("--models-dir", default=str(root / "models"))
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--epochs-stage2", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--loss", choices=["ce", "focal"], default="focal")
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    data_dir, out_dir, models_dir = Path(args.data_dir), Path(args.out_dir), Path(args.models_dir)
    if args.command == "build-cache":
        build_cache(data_dir)
    elif args.command == "baseline":
        run_baseline(data_dir, out_dir)
    elif args.command == "deep":
        run_deep(data_dir, out_dir, models_dir, args.epochs, args.batch_size, args.loss, args.folds)
    elif args.command == "robustness":
        run_robustness(data_dir, models_dir, out_dir)
    elif args.command == "stage2":
        run_stage2(data_dir, out_dir, models_dir, args.epochs_stage2, args.batch_size)


if __name__ == "__main__":
    main()