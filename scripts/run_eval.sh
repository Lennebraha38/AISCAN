#!/usr/bin/env bash
# Teknofest EKG hattini uctan uca yeniden uretir (veri -> cache -> model -> raporlar).
# Kullanim:  scripts/run_eval.sh   (VENC ortam degiskeni ile venv yolunu ezebilirsin)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENC="${VENC:-$ROOT/.venv}"
PY="${VENC}/bin/python"
DATA="${ROOT}/data/ecg"

if [ ! -x "$PY" ]; then
  echo "venv yok: ${VENC}"
  echo "kurulum:  python3 -m venv ${VENC}"
  exit 1
fi

pip_require() {
  "$PY" -c "import $1" 2>/dev/null || "$VENC/bin/pip" install "$2"
}
pip_require numpy numpy
pip_require scipy scipy
pip_require sklearn scikit-learn
pip_require httpx httpx
pip_require matplotlib matplotlib
"$PY" -c "import torch" 2>/dev/null || \
  "$VENC/bin/pip" install --index-url https://download.pytorch.org/whl/cpu torch

cd "$ROOT/ai-core"
echo "== 1/6 fetch (kaynak: PhysioNet ecg-arrhythmia 1.0.0) =="
"$PY" -m app.ecg.data fetch --data-dir "$DATA" --concurrency 32
echo "== 2/6 build-cache =="
"$PY" -m app.ecg.train build-cache --data-dir "$DATA"
echo "== 3/6 baseline =="
"$PY" -m app.ecg.train baseline --data-dir "$DATA"
echo "== 4/6 deep (folds 5, focal) =="
"$PY" -m app.ecg.train deep --data-dir "$DATA" --epochs 30 --loss focal --folds 5
echo "== 5/6 robustness =="
"$PY" -m app.ecg.train robustness --data-dir "$DATA"
echo "== 6/6 stage2 (2. asama fine-grained) =="
"$PY" -m app.ecg.train stage2 --data-dir "$DATA" --epochs-stage2 15
echo "== TAMAM → docs/metrics/, docs/figures/, ai-core/models/ =="