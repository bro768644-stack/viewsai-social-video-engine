#!/usr/bin/env python3
"""
IMPORT CLIPS — add Kobe footage to the movement library.

Scans a folder (default: the inbox) for videos, probes them, names them cleanly
and copies them into ~/Social Media MASTER/kobe-library/movement/ so
assemble_kobe.py can use them immediately.

Usage:
    python3 import_clips.py                       # scan the inbox
    python3 import_clips.py --from ~/Downloads/new_kobe
    python3 import_clips.py --from ~/Downloads/Kobe_Recruiting/   # skip wides/tests
    python3 import_clips.py --list                # show the library
"""
import argparse
import re
import shutil
import subprocess
from pathlib import Path

LIB = Path.home() / "Social Media MASTER/kobe-library/movement"
INBOX = Path.home() / "Social Media MASTER/kobe-library/inbox"
VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
SKIP = ("TEST_", "wides", "palette")


def probe(p):
    def q(args):
        return subprocess.run(args, capture_output=True, text=True).stdout.strip()
    wh = q(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(p)])
    d = q(["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "csv=p=0", str(p)])
    a = q(["ffprobe", "-v", "error", "-select_streams", "a",
           "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(p)])
    try:
        w, h = (int(x) for x in wh.split("x"))
    except Exception:
        w = h = 0
    return w, h, float(d or 0), bool(a)


def slug(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    s = re.sub(r"_+", "_", s)
    return s[:48]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default=str(INBOX))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--move", action="store_true", help="move instead of copy")
    args = ap.parse_args()

    LIB.mkdir(parents=True, exist_ok=True)

    if args.list:
        for f in sorted(LIB.glob("*.mp4")):
            w, h, d, a = probe(f)
            kind = "9:16" if h > w else ("16:9" if w > h else "1:1")
            print(f"  {f.stem:46s} {w}x{h} {kind:5s} {d:5.1f}s {'audio' if a else 'silent'}")
        print(f"\n{len(list(LIB.glob('*.mp4')))} clips in the library")
        return

    src = Path(args.src).expanduser()
    if not src.exists():
        raise SystemExit(f"not found: {src}")

    added = skipped = 0
    candidates = []
    for f in sorted(src.rglob("*")):
        if f.suffix.lower() in VIDEO and f.is_file():
            if any(k in str(f) for k in SKIP):
                continue
            candidates.append(f)

    for f in candidates:
        name = slug(f.stem) + ".mp4"
        dest = LIB / name
        if dest.exists():
            skipped += 1
            continue
        w, h, d, a = probe(f)
        if d < 2 or w == 0:
            skipped += 1
            continue
        (shutil.move if args.move else shutil.copy)(str(f), str(dest))
        kind = "9:16" if h > w else ("16:9" if w > h else "1:1")
        print(f"  + {name:46s} {w}x{h} {kind:5s} {d:5.1f}s {'audio' if a else 'silent'}")
        added += 1

    print(f"\n{added} imported, {skipped} skipped → library now "
          f"{len(list(LIB.glob('*.mp4')))} clips")
    if added:
        print("next: python3 batch_kobe_posts.py --list")


if __name__ == "__main__":
    main()
