"""PhysioNet ECG Arrhythmia 1.0.0 veri indirici ve manifest araci.

Kullanim:
    python -m app.ecg.data scan     --data-dir data/ecg --concurrency 24
    python -m app.ecg.data select   --data-dir data/ecg --normal 6000 --arrhythmia 6000 --block 4000
    python -m app.ecg.data fetch    --data-dir data/ecg --concurrency 16

Asamalar:
    scan   : tum .hea dosyalarini indirir, Dx/Age/Sex ayristirir, manifest.jsonl yazar
    select : manifest uzerinden ust sinif dengeli alt kume secer -> selected.jsonl
    fetch  : secili kayitlarin .mat dosyalarini indirir (resume destekli)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx
import numpy as np

BASE_URL = "https://physionet.org/files/ecg-arrhythmia/1.0.0"

from app.ecg.labels import assign_superclass, subclasses_for  # noqa: E402

_LINK_RE = re.compile(r'href="([^"]+\.hea)"')
_DX_RE = re.compile(r"#Dx:\s*(.+)")
_AGE_RE = re.compile(r"#Age:\s*(\S+)")
_SEX_RE = re.compile(r"#Sex:\s*(\S+)")


def _record_dirs(records_file: Path) -> list[str]:
    out = []
    for line in records_file.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(line)
    return out


async def _scan_dir(client: httpx.AsyncClient, sem: asyncio.Semaphore, d: str) -> list[str]:
    url = f"{BASE_URL}/{d}/"
    async with sem:
        for attempt in range(3):
            try:
                r = await client.get(url)
                r.raise_for_status()
                return [href for href in _LINK_RE.findall(r.text)]
            except Exception:
                if attempt == 2:
                    print(f"  ! liste basarisiz: {d}", file=sys.stderr)
                    return []
                await asyncio.sleep(1.5 * (attempt + 1))
    return []


def _parse_hea(text: str) -> dict | None:
    lines = text.splitlines()
    if not lines:
        return None
    head = lines[0].split()
    if len(head) < 4:
        return None
    record, _nlead, fs, nsamp = head[0], int(head[1]), int(head[2]), int(head[3])
    dx_m = _DX_RE.search(text)
    age_m = _AGE_RE.search(text)
    sex_m = _SEX_RE.search(text)
    dx = [c.strip() for c in dx_m.group(1).split(",")] if dx_m else []
    sup = assign_superclass(dx)
    return {
        "record": record,
        "fs": fs,
        "samples": nsamp,
        "dx": dx,
        "age": int(age_m.group(1)) if age_m and age_m.group(1).isdigit() else None,
        "sex": sex_m.group(1) if sex_m else None,
        "superclass": sup,
        "subclasses": subclasses_for(dx),
    }


async def cmd_scan(data_dir: Path, concurrency: int) -> None:
    raw_hea = data_dir / "hea"
    raw_hea.mkdir(parents=True, exist_ok=True)
    manifest_path = data_dir / "manifest.jsonl"
    done: set[str] = set()
    if manifest_path.exists():
        with open(manifest_path) as fh:
            done = {json.loads(l)["record"] for l in fh if l.strip()}
        print(f"manifest mevcut: {len(done)} kayit taranmis, kalani taraniyor")

    dirs = _record_dirs(data_dir / "RECORDS")
    print(f"{len(dirs)} klasor listeleniyor...")
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        listings = await asyncio.gather(*[_scan_dir(client, sem, d) for d in dirs])

    hea_urls: dict[str, str] = {}
    dir_of: dict[str, str] = {}
    for d, hrefs in zip(dirs, listings):
        for href in hrefs:
            rec = href.rsplit("/", 1)[-1]
            hea_urls[rec] = f"{BASE_URL}/{d}/{rec}"
            dir_of[rec] = d

    todo = [(r, u) for r, u in sorted(hea_urls.items()) if r not in done]
    print(f"{len(todo)} .hea taranacak (toplam {len(hea_urls)})")
    sem2 = asyncio.Semaphore(concurrency)

    async def fetch_one(client: httpx.AsyncClient, rec: str, url: str, fh) -> None:
        async with sem2:
            for attempt in range(3):
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    meta = _parse_hea(r.text)
                    if meta:
                        meta["dir"] = dir_of[rec]
                        fh.write(json.dumps(meta) + "\n")
                        fh.flush()
                    return
                except Exception:
                    if attempt == 2:
                        print(f"  ! hea basarisiz: {rec}", file=sys.stderr)
                    else:
                        await asyncio.sleep(1.0 * (attempt + 1))

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        with open(manifest_path, "a") as fh:
            batch = 500
            for i in range(0, len(todo), batch):
                await asyncio.gather(*(fetch_one(client, r, u, fh) for r, u in todo[i : i + batch]))
                scanned = sum(1 for _ in open(manifest_path))
                print(f"\r[{scanned}/{len(hea_urls)}] tarandi", end="", flush=True)
    print("\ntarama bitti")


def cmd_select(
    data_dir: Path,
    limits: dict[str, int],
    seed: int = 42,
) -> None:
    manifest_path = data_dir / "manifest.jsonl"
    entries: list[dict] = []
    with open(manifest_path) as fh:
        for line in fh:
            if line.strip():
                e = json.loads(line)
                if e.get("superclass"):
                    entries.append(e)

    rng = random.Random(seed)
    by_super: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_super[e["superclass"]].append(e)

    selected: list[dict] = []
    report = {}
    for sup, want in limits.items():
        pool = by_super.get(sup, [])
        # alt tani cesitliligi: birincil alt taniya gore round-robin secim
        by_sub: dict[str, list[dict]] = defaultdict(list)
        for e in pool:
            key = e["subclasses"][0] if e["subclasses"] else "_diger"
            by_sub[key].append(e)
        for lst in by_sub.values():
            rng.shuffle(lst)
        queues = sorted(by_sub.items())
        picked: list[dict] = []
        while len(picked) < min(want, len(pool)):
            progressed = False
            for _, lst in queues:
                if lst and len(picked) < min(want, len(pool)):
                    picked.append(lst.pop())
                    progressed = True
            if not progressed:
                break
        selected.extend(picked)
        sub_counts = Counter(e["subclasses"][0] if e["subclasses"] else "_diger" for e in picked)
        report[sup] = {"istenen": want, "bulunan": len(pool), "secilen": len(picked), "alt_tani": dict(sub_counts)}

    rng.shuffle(selected)
    out = data_dir / "selected.jsonl"
    with open(out, "w") as fh:
        for e in selected:
            fh.write(json.dumps(e) + "\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"toplam secilen: {len(selected)} -> {out}")


async def cmd_fetch(data_dir: Path, concurrency: int) -> None:
    mat_root = data_dir / "raw"
    mat_root.mkdir(parents=True, exist_ok=True)
    sel_path = data_dir / "selected.jsonl"
    entries = [json.loads(l) for l in open(sel_path) if l.strip()]

    jobs = []
    for e in entries:
        d = e["dir"]
        rec = e["record"]
        target = mat_root / d / f"{rec}.mat"
        if not target.exists():
            jobs.append((e, f"{BASE_URL}/{d}/{rec}.mat", target))
    print(f"{len(jobs)}/{len(entries)} .mat indirilecek (kalanlar atlandi)")
    sem = asyncio.Semaphore(concurrency)

    async def fetch_one(client: httpx.AsyncClient, e: dict, url: str, target: Path) -> None:
        async with sem:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".part")
            for attempt in range(4):
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    tmp.write_bytes(r.content)
                    tmp.replace(target)
                    return
                except Exception:
                    if attempt == 3:
                        print(f"  ! mat basarisiz: {e['record']}", file=sys.stderr)
                    else:
                        await asyncio.sleep(1.5 * (attempt + 1))

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        done_n = 0
        batch = 200
        for i in range(0, len(jobs), batch):
            await asyncio.gather(*(fetch_one(client, e, u, t) for e, u, t in jobs[i : i + batch]))
            done_n += len(jobs[i : i + batch])
            print(f"\r[{min(done_n, len(jobs))}/{len(jobs)}] indi", end="", flush=True)
    print("\nindirme bitti")


def load_record(mat_path: Path, fs_expected: int | None = None) -> tuple[np.ndarray, int]:
    """Kayit .mat -> (12, N) float64 sinyal."""
    from scipy.io import loadmat

    m = loadmat(str(mat_path))
    val = m.get("val")
    if val is None:
        raise KeyError(f"'val' yok: {mat_path}")
    return np.asarray(val, dtype=np.float64), int(fs_expected or 500)


def main() -> None:
    ap = argparse.ArgumentParser(description="ECG Arrhythmia 1.0.0 veri araci")
    ap.add_argument("command", choices=["scan", "select", "fetch"])
    ap.add_argument("--data-dir", default="data/ecg")
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--normal", type=int, default=6000)
    ap.add_argument("--arrhythmia", type=int, default=6000)
    ap.add_argument("--block", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if args.command == "scan":
        asyncio.run(cmd_scan(data_dir, args.concurrency))
    elif args.command == "select":
        cmd_select(data_dir, {"normal": args.normal, "arrhythmia": args.arrhythmia, "block": args.block}, args.seed)
    elif args.command == "fetch":
        asyncio.run(cmd_fetch(data_dir, args.concurrency))


if __name__ == "__main__":
    main()
