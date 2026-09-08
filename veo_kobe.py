#!/usr/bin/env python3
"""
VEO KOBE — free-tier Veo 3.1 video generation via Google Gemini API.

One shot: reference image (optional) + script → 9:16 / 16:9 talking clip.

Usage:
    python3 veo_kobe.py --prompt "Drop AI in the comments and I'll send the system" \
        --image /path/kobe.png --out /tmp/kobe_veo.mp4 --aspect 9:16 --seconds 8

    # no reference image (pure text-to-video):
    python3 veo_kobe.py --prompt "..." --out /tmp/x.mp4

Reads GEMINI_API_KEY from ~/.n8n/.env or .env.keys (AI Studio free key).
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "veo-3.1-fast-generate-preview"   # fast; fallbacks: veo-3.1-generate-preview, veo-3.1-lite
API = "https://generativelanguage.googleapis.com/v1beta"


def load_key():
    for f in (Path.home() / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")):
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GEMINI_API_KEY not found in ~/.n8n/.env or .env.keys")


def post(url, key, body):
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + "key=" + key,
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:600]
        raise SystemExit(f"HTTP {e.code}: {msg}")


def get_json(url, key):
    req = urllib.request.Request(url + "?key=" + key)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:600]
        raise SystemExit(f"HTTP {e.code}: {msg}")


def b64(path):
    mime = "image/png" if str(path).lower().endswith((".png",)) else "image/jpeg"
    return mime, base64.b64encode(Path(path).read_bytes()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--image", default=None, help="reference image (character lock)")
    ap.add_argument("--out", default="/tmp/veo_out.mp4")
    ap.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
    ap.add_argument("--seconds", type=int, default=8, choices=range(4, 9))
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    key = load_key()
    instance = {"prompt": args.prompt}
    if args.image:
        # pre-crop the source to the EXACT output aspect -> kills Veo's start-morph
        import subprocess as sp
        crop = Path(args.image).with_name(Path(args.image).stem + f"_{args.aspect.replace(':','x')}.png")
        ar_w, ar_h = (int(x) for x in args.aspect.split(":"))
        try:
            sp.run(["ffmpeg", "-y", "-v", "error", "-i", args.image,
                    "-vf", f"scale={ar_w}:{ar_h}:force_original_aspect_ratio=increase,crop={ar_w}:{ar_h}",
                    str(crop)], check=True, capture_output=True)
            args.image = str(crop)
        except Exception:
            pass  # fall back to original if crop fails
        mime, data = b64(args.image)
        instance["image"] = {"bytesBase64Encoded": data, "mimeType": mime}

    url = f"{API}/models/{args.model}:predictLongRunning"
    op = post(url, key, {"instances": [instance],
                         "parameters": {"aspectRatio": args.aspect,
                                        "durationSeconds": args.seconds,
                                        "sampleCount": 1}})
    op_name = op.get("name")
    if not op_name:
        raise SystemExit(f"no operation: {op}")
    print(f"job accepted: {op_name}")

    for i in range(60):  # poll up to ~15 min
        time.sleep(12)
        res = get_json(f"{API}/{op_name}", key)
        if res.get("done"):
            break
        print(f"  ...{(i + 1) * 12}s")
    else:
        raise SystemExit("timed out")

    if "error" in res:
        raise SystemExit(f"job error: {res['error']}")

    videos = (res.get("response", {}).get("generateVideoResponse", {})
                 .get("generatedSamples", []))
    if not videos:
        raise SystemExit(f"no video in result: {json.dumps(res)[:400]}")
    uri = videos[0]["video"]["uri"]

    req = urllib.request.Request(uri + "&key=" + key)
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    Path(args.out).write_bytes(data)
    print(f"\n✅ saved {len(data)/1e6:.1f} MB -> {args.out}")
    subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                    "stream=codec_name,width,height", "-of", "compact",
                    args.out], capture_output=True)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", args.out], capture_output=True, text=True)
    print("streams:", r.stdout.strip().replace("\n", ", "))


if __name__ == "__main__":
    main()
