#!/usr/bin/env python3
"""
KAGGLE RUNNER — automated free-GPU Kobe clips (headless, cron-able).

  --check   verify kaggle auth + show GPU quota
  --setup   upload kobe.png + kobe.wav as a private dataset (once)
  --run     push the kernel, wait for it, download the resulting clip
  --status  show the last kernel status

Requires: ~/.kaggle/kaggle.json  (kaggle.com -> Settings -> API -> Create New Token)
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KAGGLE_DIR = HERE / "kaggle"
UPLOADS = Path.home() / "Social Media MASTER/kobe-library/colab-uploads"
DEST = Path.home() / "Social Media MASTER/kobe-library/movement"
DATASET_SLUG = "kobe-inputs"


def sh(cmd, check=True, capture=True):
    return subprocess.run(cmd, shell=True, check=check, text=True,
                          capture_output=capture)


def kaggle_ok():
    if not (Path.home() / ".kaggle" / "kaggle.json").exists():
        print("✗ missing ~/.kaggle/kaggle.json")
        print("  1. kaggle.com/settings → API → Create New Token (free)")
        print("  2. mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json")
        return False
    try:
        r = sh("kaggle --version")
        print("✓ kaggle CLI:", (r.stdout or '').strip())
    except Exception:
        print("✗ kaggle CLI not installed → pip install kaggle")
        return False
    return True


def user():
    try:
        return json.loads((Path.home() / ".kaggle" / "kaggle.json").read_text())["username"]
    except Exception:
        return "bro768644"


def setup_dataset():
    tmp = Path("/tmp/kobe-dataset")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for f in ("kobe.png", "kobe.wav"):
        src = UPLOADS / f
        if not src.exists():
            sys.exit(f"missing {src} — stage your upload files there first")
        shutil.copy(src, tmp / f)
    (tmp / "dataset-metadata.json").write_text(json.dumps({
        "title": "Kobe Inputs",
        "id": f"{user()}/{DATASET_SLUG}",
        "licenses": [{"name": "CC0-1.0"}],
    }, indent=1))
    print("→ creating dataset…")
    r = sh(f'kaggle datasets create -p "{tmp}"', check=False)
    out = (r.stdout or '') + (r.stderr or '')
    print(out[-400:])
    if "already exists" in out.lower() or "409" in out:
        print("dataset exists → creating a new version…")
        r = sh(f'kaggle datasets version -p "{tmp}" -m "update"', check=False)
        print(((r.stdout or '') + (r.stderr or ''))[-300:])


def push_and_run(timeout=3600):
    meta = KAGGLE_DIR / "kernel-metadata.json"
    m = json.loads(meta.read_text())
    m["id"] = f"{user()}/joyvasa-kobe-talking"
    m["dataset_sources"] = [f"{user()}/{DATASET_SLUG}"]
    meta.write_text(json.dumps(m, indent=1))
    print(f"→ pushing kernel {m['id']} (GPU={m['enable_gpu']}, internet={m['enable_internet']})")
    r = sh(f'kaggle kernels push -p "{KAGGLE_DIR}"', check=False)
    print(((r.stdout or '') + (r.stderr or ''))[-400:])

    print("→ waiting for completion (free GPU queue + ~10 min run)…")
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(45)
        r = sh(f'kaggle kernels status {m["id"]}', check=False, capture=True)
        txt = ((r.stdout or '') + (r.stderr or '')).strip()
        el = int(time.time() - start)
        print(f"  t={el}s {txt[-120:]}")
        if "complete" in txt.lower() or "succeeded" in txt.lower():
            break
        if "error" in txt.lower() or "failed" in txt.lower():
            print("✗ kernel failed → inspect:", f"https://www.kaggle.com/code/{m['id']}")
            return False

    DEST.mkdir(parents=True, exist_ok=True)
    print("→ downloading outputs…")
    r = sh(f'kaggle kernels output {m["id"]} -p "{DEST}"', check=False)
    print(((r.stdout or '') + (r.stderr or ''))[-400:])
    vids = sorted(DEST.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if vids:
        print("✅ got:", vids[0])
        return True
    print("✗ no mp4 downloaded — check the kernel log page")
    return False


def status():
    m = json.loads((KAGGLE_DIR / "kernel-metadata.json").read_text())
    r = sh(f'kaggle kernels status {m["id"]}', check=False)
    print(((r.stdout or '') + (r.stderr or '')).strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if not any([args.check, args.setup, args.run, args.status]):
        args.check = True

    if not kaggle_ok():
        sys.exit(1)
    if args.check:
        print("✓ ready. next: --setup (once), then --run")
        return
    if args.setup:
        setup_dataset()
        return
    if args.status:
        status()
        return
    if args.run:
        ok = push_and_run()
        sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
