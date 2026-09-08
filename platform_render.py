#!/usr/bin/env python3
"""
AI SOCIAL VIDEO ENGINE — one master video → platform-perfect renders.

Takes ONE master clip and produces every platform render with the correct
aspect ratio, resolution, duration cap, safe-zone-aware text overlays and
broadcast-level audio. Fully local, $0 tool cost.

Usage:
    python3 platform_render.py --master kobe.mp4 \
        --title "The blue eye sees everything" \
        --caption "Kobe. ViewsAI office dog." \
        --cta "Follow @viewsai" \
        --out ~/Social\ Media\ MASTER/platform-renders

    # variants:
    --only tiktok,youtube-shorts      # render subset
    --mode blurpad                    # force blur-pad everywhere (default auto)
    --no-text                         # skip overlays
    --cover                           # also export a 9:16 cover JPG per video

Output tree:
    out/<platform>/<name>-<platform>-<WxH>.mp4 (+ cover.jpg)

Specs live in FORMATS.md. Safe zones honored for every 9:16 target.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- palette
BG = "#0b0e14"
FG = "#e6e9f0"
ACCENT = "#ffd60a"
RED = "#ff6b6b"
GREEN = "#3ddc84"
MUTED = "#8b93a7"
PILL = "#141926"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT = "/System/Library/Fonts/Helvetica.ttc"

# ---------------------------------------------------------------- platform table (FORMATS.md)
PLATFORMS = {
    # key: (target size, aspect, mode auto?, max seconds, top, bottom, left, right safe %)
    "tiktok":          dict(size=(1080, 1920), mode="crop", max_dur=180,  safe=(6, 20, 4, 16)),
    "youtube-shorts":  dict(size=(1080, 1920), mode="crop", max_dur=60,   safe=(6, 18, 4, 16)),
    "instagram-reel":  dict(size=(1080, 1920), mode="crop", max_dur=90,   safe=(6, 22, 4, 15)),
    "instagram-feed":  dict(size=(1080, 1350), mode="crop", max_dur=60,   safe=(4, 10, 4, 4)),
    "instagram-story": dict(size=(1080, 1920), mode="crop", max_dur=60,   safe=(8, 26, 4, 4)),
    "facebook-reel":   dict(size=(1080, 1920), mode="crop", max_dur=90,   safe=(5, 22, 4, 4)),
    "facebook-page":   dict(size=(1920, 1080), mode="blurpad", max_dur=240, safe=(4, 10, 4, 4)),
    "facebook-account":dict(size=(1080, 1080), mode="crop", max_dur=240,  safe=(4, 10, 4, 4)),
    "linkedin":        dict(size=(1080, 1350), mode="crop", max_dur=1800, safe=(4, 10, 4, 4)),
    "x":               dict(size=(1280, 720),  mode="blurpad", max_dur=140, safe=(4, 12, 4, 4)),
    "threads":         dict(size=(1080, 1920), mode="crop", max_dur=300,  safe=(5, 20, 4, 4)),
    "telegram":        dict(size=(1920, 1080), mode="blurpad", max_dur=1800, safe=(0, 0, 0, 0)),
}

ORDER = ["tiktok", "youtube-shorts", "instagram-reel", "instagram-feed",
         "instagram-story", "facebook-reel", "facebook-page", "facebook-account",
         "linkedin", "x", "threads", "telegram"]


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- overlay PNGs
def make_overlays(out_dir, W, H, safe, title, caption, cta):
    """Return list of (png_path, t_in, t_out)."""
    top, bottom, left, right = safe
    overlays = []
    d = ImageDraw.Draw  # noqa

    # 1) title — top third, below top safe zone
    if title:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        max_w = W * (1 - (left + right) / 100 - 0.08)
        fsize = int(W * 0.062)
        fnt = font(fsize, True)
        lines = wrap(dr, title, fnt, max_w)[:3]
        block_h = len(lines) * int(fsize * 1.15)
        y0 = int(H * (top + 2) / 100)
        for i, ln in enumerate(lines):
            y = y0 + i * int(fsize * 1.15)
            dr.text((W // 2, y), ln, font=fnt, fill=FG, anchor="mm",
                    stroke_width=4, stroke_fill=BG)
        overlays.append((save_png(img, out_dir, "title"), 0.0, 3.6))

    # 2) caption — lower third, above bottom safe zone
    if caption:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        max_w = W * 0.86
        fsize = int(W * 0.045)
        fnt = font(fsize)
        lines = wrap(dr, caption, fnt, max_w)[:2]
        lh = int(fsize * 1.3)
        pill_h = len(lines) * lh + 28
        pill_w = int(min(max_w, max(dr.textlength(ln, font=fnt) for ln in lines)) + 56)
        py = int(H * (100 - bottom) / 100) - pill_h - int(H * 0.015)
        px = (W - pill_w) // 2
        dr.rounded_rectangle([px, py, px + pill_w, py + pill_h], radius=pill_h // 2,
                             fill=(20, 25, 38, 200), outline=(255, 214, 10, 220), width=3)
        for i, ln in enumerate(lines):
            dr.text((W // 2, py + 14 + i * lh + lh // 2), ln, font=fnt, fill=FG, anchor="lm")
        overlays.append((save_png(img, out_dir, "caption"), 0.8, None))

    # 3) CTA — bottom chip, inside safe zone
    if cta:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        fnt = font(int(W * 0.04), True)
        tw = dr.textlength(cta, font=fnt)
        pw = int(tw + 60)
        ph = int(W * 0.075)
        px = (W - pw) // 2
        py = int(H * (100 - bottom) / 100) - ph - int(H * 0.004)
        dr.rounded_rectangle([px, py, px + pw, py + ph], radius=ph // 2,
                             fill=(255, 214, 10, 235))
        dr.text((W // 2, py + ph // 2), cta, font=fnt, fill=BG, anchor="mm")
        overlays.append((save_png(img, out_dir, "cta"), None, None))
    return overlays


def save_png(img, out_dir, name):
    p = Path(out_dir) / f"{name}.png"
    img.save(p)
    return str(p)


# ---------------------------------------------------------------- ffmpeg helpers
def probe(path, key="format=duration"):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", key,
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return r.stdout.strip()


def has_audio(path):
    return bool(probe(path, "stream=codec_type").splitlines())


def build_filters(master, W, H, mode, overlays, dur, safe_dur=None):
    """Return (filter_complex, duration)."""
    mw, mh = (int(x) for x in probe(master, "stream=width,height").split(",")[:2])
    sar = mw / mh
    tar = W / H
    same_orient = (sar >= 1) == (tar >= 1)
    use_blur = (mode == "blurpad") or (mode == "auto" and not same_orient)

    if use_blur:
        fc = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=24:2,eq=brightness=-0.25[bg];"
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base]"
        )
    else:
        fc = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        fc += "unsharp=5:5:0.6:5:5:0.0[base]"

    # chain overlays with fades
    cur = "[base]"
    dur_f = float(dur)
    for idx, (png, t_in, t_out) in enumerate(overlays):
        lab = f"o{idx}"
        if t_out is None:
            t_out = dur_f - 0.2
        if t_in is None:
            t_in = max(0.0, t_out - 3.0)
        fc += f";[{idx+1}:v]format=rgba,fade=t=in:st={t_in}:d=0.3:alpha=1,"
        fc += f"fade=t=out:st={t_out}:d=0.3:alpha=1[{lab}];"
        fc += f"{cur}[{lab}]overlay=0:0:enable='between(t,{t_in},{t_out})'[v{idx}]"
        cur = f"[v{idx}]"
    fc += ";"
    fc += f"{cur}format=yuv420p[out]"
    return fc


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--caption", default="")
    ap.add_argument("--cta", default="")
    ap.add_argument("--out", default="~/Social Media MASTER/platform-renders")
    ap.add_argument("--only", default="", help="comma-separated platform keys")
    ap.add_argument("--mode", default="auto", choices=["auto", "crop", "blurpad"])
    ap.add_argument("--no-text", action="store_true")
    ap.add_argument("--cover", action="store_true")
    ap.add_argument("--accent", default=None, help="hex accent color, e.g. ffd60a")
    ap.add_argument("--fg", default=None, help="hex text color, e.g. e6e9f0")
    args = ap.parse_args()

    global ACCENT, FG
    if args.accent:
        ACCENT = "#" + args.accent.lstrip("#")
    if args.fg:
        FG = "#" + args.fg.lstrip("#")

    master = Path(args.master).expanduser()
    assert master.exists(), f"master not found: {master}"
    dur = float(probe(master))
    audio = has_audio(master)
    out_root = Path(args.out).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    base = master.stem

    keys = [k.strip() for k in args.only.split(",") if k.strip()] or ORDER

    for key in keys:
        cfg = PLATFORMS[key]
        W, H = cfg["size"]
        mode = args.mode if args.mode != "auto" else cfg["mode"]
        safe = cfg["safe"]
        max_dur = cfg["max_dur"]
        out_dir = out_root / key
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{base}-{key}-{W}x{H}.mp4"

        # trim if over platform cap
        t_dur = min(dur, max_dur)

        overlays = []
        if not args.no_text:
            overlays = make_overlays(out_dir, W, H, safe,
                                     args.title, args.caption, args.cta)

        fc = build_filters(master, W, H, mode, overlays, t_dur)

        cmd = ["ffmpeg", "-y", "-i", str(master)]
        for png, _, _ in overlays:
            cmd += ["-i", png]
        af = ""
        if audio:
            af = f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        cmd += ["-filter_complex", fc + (f";{af}" if af else ""),
                "-map", "[out]"]
        if audio:
            cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-r", "30", "-t", str(t_dur),
                "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)

        if args.cover:
            cover = out_dir / f"{base}-{key}-cover.jpg"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.3", "-i", str(out),
                            "-frames:v", "1", "-q:v", "2", str(cover)], check=True)

        print(f"  ✓ {key:16s} {W}x{H} {mode:8s} {t_dur:.1f}s -> {out.name}")

    print(f"\n✅ rendered {len(keys)} platforms to {out_root}")


if __name__ == "__main__":
    main()
