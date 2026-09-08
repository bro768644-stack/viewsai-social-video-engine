#!/usr/bin/env python3
"""
Edit the Kobe reference still with free Gemini image model (gemini-3-pro-image),
then it's ready for Veo. Guides: eye color, lighting, background branding.

Usage:
    python3 edit_kobe_still.py --image <in.png> --out <edited.png> --brand VIEWSAI
"""
import argparse
import base64
import json
import urllib.request
from pathlib import Path

MODEL = "gemini-3-pro-image"
API = "https://generativelanguage.googleapis.com/v1beta"

INSTRUCTIONS = {
    "VIEWSAI": (
        "Keep this golden retriever dog IDENTICAL - same face, fur, markings, proportions, pose, framing. "
        "Set his eye color to match the SECOND image EXACTLY - that image shows his real eye color: bright, "
        "luminous light-blue that catches the light and visibly shines. Not dark, not dull. "
        "Recolor the whole scene to warm AMBER/ORANGE lighting instead of yellow. "
        "Background: a modern AI-builder's office at night - dark charcoal walls, Mac mini computers and "
        "monitors on a desk behind him, subtle desk clutter, and a tasteful glowing VIEWSAI wall sign "
        "naturally integrated. Not an advertisement - part of the office. "
        "Cinematic, photorealistic, sharp focus, premium creator quality."
    ),
    "OBRIENHQ": (
        "Keep this golden retriever dog IDENTICAL - same face, fur, markings, proportions, pose, framing. "
        "Set his eye color to match the SECOND image EXACTLY - bright luminous light-blue that shines. "
        "Recolor the scene to warm AMBER/ORANGE lighting instead of yellow. "
        "Background: a modern AI-builder's office at night - dark walls, monitors and Mac minis on a desk, "
        "and a tasteful glowing OBRIENHQ wall sign. Cinematic, photorealistic, sharp focus."
    ),
    "NEUTRAL": (
        "PHOTOREALISTIC EDIT. Change ONLY the scene: warm amber/orange lighting instead of yellow, and "
        "background = a modern AI-builder's office at night with a subtle glowing VIEWSAI sign. "
        "CRITICAL: Do NOT touch Kobe's face, fur, pose, or his EYES AT ALL. His heterochromia eyes must stay "
        "EXACTLY as in the first image - the blue eye at its natural, real, subtle tone. No brightening, no "
        "saturation, no glow, no color change. Keep everything about him identical and realistic."
    ),
    "BRENDAN": (
        "PHOTOREALISTIC EDIT. This is a REAL PERSON. Keep him IDENTICAL - exact face, features, hair, "
        "expression, age. Do NOT alter, beautify, age, or reshape him. Change ONLY the scene: place him at a "
        "desk in a modern AI-builder's office at night - dark walls, Mac mini computers and monitors on the "
        "desk behind him, subtle desk clutter, a tasteful glowing VIEWSAI sign in the background, warm "
        "amber/orange lighting. He looks at the camera naturally. Photorealistic, sharp focus, premium."
    ),
}


def load_key():
    for f in (Path.home() / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")):
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no GEMINI_API_KEY")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--eye-ref", default=None, help="second image: source of Kobe's true eye color")
    ap.add_argument("--out", default="/tmp/kobe_edited.png")
    ap.add_argument("--brand", default="VIEWSAI", choices=list(INSTRUCTIONS))
    ap.add_argument("--aspect", default="9:16", choices=["9:16", "4:5", "1:1"])
    args = ap.parse_args()

    key = load_key()

    def img_part(path):
        mime = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
        return {"inline_data": {"mime_type": mime, "data": base64.b64encode(Path(path).read_bytes()).decode()}}

    parts = [{"text": INSTRUCTIONS[args.brand]}, img_part(args.image)]
    if args.eye_ref:
        parts.append(img_part(args.eye_ref))

    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": args.aspect},
        },
    }
    req = urllib.request.Request(
        f"{API}/models/{MODEL}:generateContent?key={key}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode()[:500]}")

    parts = resp["candidates"][0]["content"]["parts"]
    img = next((p["inlineData"]["data"] for p in parts if "inlineData" in p), None)
    if not img:
        raise SystemExit(f"no image returned: {json.dumps(resp)[:400]}")
    Path(args.out).write_bytes(base64.b64decode(img))
    print(f"✅ edited still saved: {args.out}")


if __name__ == "__main__":
    main()
