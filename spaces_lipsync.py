#!/usr/bin/env python3
"""
FREE HF SPACE LIP-SYNC — drives the free ZeroGPU Spaces (no GPU on your Mac).

  LatentSync  : video + audio  -> lipsynced video   (BEST quality, human faces)
  EchoMimic   : image + audio  -> talking video     (human faces)

Both Spaces are free but use @spaces.GPU(duration>=180s), so they need a FREE
Hugging Face account token to raise the ZeroGPU allowance (anonymous requests get
"requested GPU duration larger than maximum allowed").

Get one: https://huggingface.co/settings/tokens  (free, no card)
Then either:
    export HF_TOKEN=hf_xxx
    or put HF_TOKEN=hf_xxx in ~/.n8n/.env

Usage:
    # human talking (Brendan) — video + audio
    python3 spaces_lipsync.py --space latentsync \
        --video clip.mp4 --audio line.wav --out out.mp4

    # image + audio (EchoMimic)
    python3 spaces_lipsync.py --space echomimic \
        --image portrait.png --audio line.wav --out out.mp4

    python3 spaces_lipsync.py --check      # test which spaces are reachable
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

SPACES = {
    "latentsync": {"id": "fffiloni/LatentSync", "api": "/generate_lip_sync_video",
                   "inputs": ("video", "audio"), "gpu_s": 180},
    "echomimic": {"id": "fffiloni/EchoMimic", "api": None,
                  "inputs": ("image", "audio"), "gpu_s": 200},
    "echomimic-v2": {"id": "fffiloni/echomimic-v2", "api": None,
                     "inputs": ("image", "audio"), "gpu_s": 200},
}


def token():
    t = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if t:
        return t
    for f in (Path.home() / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")):
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith("HF_TOKEN=") or line.startswith("HUGGINGFACE_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default="latentsync", choices=list(SPACES))
    ap.add_argument("--video")
    ap.add_argument("--image")
    ap.add_argument("--audio", required=False)
    ap.add_argument("--out", default="/tmp/lipsync_out.mp4")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    try:
        from gradio_client import Client, handle_file
    except ImportError:
        sys.exit("pip install -U gradio_client  (needs Python 3.10+; use /opt/homebrew/bin/python3.12)")

    tok = token()
    print(f"HF token: {'yes' if tok else 'NONE — ZeroGPU will reject long jobs'}")

    cfg = SPACES[args.space]
    if args.check:
        for name, c in SPACES.items():
            try:
                Client(c["id"], token=tok)
                print(f"  ✓ {name:14s} {c['id']}")
            except Exception as e:
                print(f"  ✗ {name:14s} {str(e)[:60]}")
        return

    if not args.audio:
        sys.exit("--audio is required")
    need = "video" if cfg["inputs"][0] == "video" else "image"
    src = args.video if need == "video" else args.image
    if not src:
        sys.exit(f"--{need} is required for {args.space}")

    c = Client(cfg["id"], token=tok)
    print(f"→ {cfg['id']}  ({need} + audio)")
    t = time.time()
    kwargs = {}
    if cfg["api"]:
        kwargs["api_name"] = cfg["api"]
    out = c.predict(handle_file(src), handle_file(args.audio), **kwargs)
    print(f"  done in {time.time()-t:.0f}s -> {out}")

    if isinstance(out, str) and os.path.exists(out):
        shutil.copy(out, args.out)
        print(f"✅ saved {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB)")
    else:
        print("result:", out)


if __name__ == "__main__":
    main()
