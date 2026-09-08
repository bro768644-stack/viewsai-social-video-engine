#!/usr/bin/env python3
"""
FREE STACK STICK-FIGURE EXPLAINER v2 — fully local test video maker.

Draws stick-figure scenes with PIL, voices them with Kokoro TTS (localhost:8880),
and renders a vertical reel with FFmpeg. Zero cost, zero cloud.

Topics:
    outbound  — "$11 cold email system" pitch (5 scenes, female voice)
    stack     — free social stack explainer (3 scenes)
    kobe      — Kobe the stick dog explains himself (3 scenes, blue eye)

Usage:
    python3 make_stick_explainer.py --topic outbound --out /tmp/outbound.mp4
    python3 make_stick_explainer.py --lines "L1|L2|L3" --voice am_onyx --topic stack
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280                      # vertical reel
FPS = 30
BG = "#0b0e14"                        # ViewsAI dark
FG = "#e6e9f0"                        # figure / text
ACCENT = "#ffd60a"                    # ViewsAI yellow
RED = "#ff6b6b"
GREEN = "#3ddc84"
MUTED = "#8b93a7"
FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_PATH, size)


# ---------------------------------------------------------------- figures
def stick_figure(d, cx, cy, scale=1.0, pose="wave", color=FG):
    s = scale
    r = 26 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(3, int(5 * s)))
    body_b = cy + r
    hip = body_b + 60 * s
    d.line([cx, body_b, cx, hip], fill=color, width=max(3, int(5 * s)))
    d.line([cx, hip, cx - 28 * s, hip + 55 * s], fill=color, width=max(3, int(5 * s)))
    d.line([cx, hip, cx + 28 * s, hip + 55 * s], fill=color, width=max(3, int(5 * s)))
    sh = body_b + 12 * s
    poses = {
        "wave":    [(cx - 40 * s, sh + 30 * s), (cx + 45 * s, sh - 30 * s)],
        "point":   [(cx - 40 * s, sh + 30 * s), (cx + 52 * s, sh + 8 * s)],
        "hands_up": [(cx - 42 * s, sh - 40 * s), (cx + 42 * s, sh - 40 * s)],
        "shrug":   [(cx - 46 * s, sh + 18 * s), (cx + 46 * s, sh + 18 * s)],
        "rocket":  [(cx - 30 * s, sh - 52 * s), (cx + 30 * s, sh - 52 * s)],
    }
    (x1, y1), (x2, y2) = poses.get(pose, poses["wave"])
    d.line([cx, sh, x1, y1], fill=color, width=max(3, int(5 * s)))
    d.line([cx, sh, x2, y2], fill=color, width=max(3, int(5 * s)))


def dog_figure(d, cx, cy, scale=1.0, pose="talk", color=FG):
    """Stick dog: Kobe-lite. Round head, floppy ears, body, tail, BLUE eye."""
    s = scale
    r = 30 * s
    head_c = (cx, cy)
    # floppy ears (two triangles hanging off the head sides)
    d.polygon([(cx - r - 6 * s, cy - 10 * s), (cx - r + 8 * s, cy + 6 * s),
               (cx - r - 16 * s, cy + 26 * s)], outline=color, width=3)
    d.polygon([(cx + r + 6 * s, cy - 10 * s), (cx + r - 8 * s, cy + 6 * s),
               (cx + r + 16 * s, cy + 26 * s)], outline=color, width=3)
    # head
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(3, int(5 * s)))
    # signature BLUE eye (left)
    er = 9 * s
    d.ellipse([cx - r + 10 * s - er, cy - 6 * s - er, cx - r + 10 * s + er, cy - 6 * s + er],
              fill="#4aa8ff", outline=color, width=2)
    # right eye (normal)
    d.ellipse([cx + r - 18 * s - 4 * s, cy - 6 * s - 4 * s, cx + r - 18 * s + 4 * s, cy - 6 * s + 4 * s],
              outline=color, width=3)
    # snout
    d.line([cx, cy + 6 * s, cx, cy + 22 * s], fill=color, width=3)
    d.ellipse([cx - 7 * s, cy + 22 * s, cx + 7 * s, cy + 30 * s], outline=color, width=3)
    # body
    body_b = cy + r
    hip = body_b + 48 * s
    d.line([cx, body_b, cx, hip], fill=color, width=max(3, int(5 * s)))
    # legs
    d.line([cx, hip, cx - 24 * s, hip + 46 * s], fill=color, width=max(3, int(5 * s)))
    d.line([cx, hip, cx + 24 * s, hip + 46 * s], fill=color, width=max(3, int(5 * s)))
    # tail (wagging up-right)
    d.line([cx, hip - 4 * s, cx + 34 * s, hip - 40 * s], fill=color, width=4)
    # arm (talking paw)
    sh = body_b + 10 * s
    if pose == "talk":
        d.line([cx, sh, cx + 40 * s, sh - 26 * s], fill=color, width=max(3, int(5 * s)))
    else:
        d.line([cx, sh, cx - 34 * s, sh + 24 * s], fill=color, width=max(3, int(5 * s)))


# ---------------------------------------------------------------- icons
def icon_calculator(d, cx=W // 2, cy=330, s=1.0):
    box = [cx - 90 * s, cy - 110 * s, cx + 90 * s, cy + 110 * s]
    d.rounded_rectangle(box, radius=18, outline=MUTED, width=6)
    d.line([cx - 90 * s, cy - 55 * s, cx + 90 * s, cy - 55 * s], fill=MUTED, width=6)
    for i, row in enumerate(["11", "=  $11"]):
        pass
    d.text((cx, cy - 78 * s), "11", font=font(int(56 * s), True), fill=ACCENT, anchor="mm")
    for dx, dy in [(-50, 0), (0, 0), (50, 0), (-50, 55), (0, 55), (50, 55)]:
        d.ellipse([cx + dx - 14, cy + dy - 14, cx + dx + 14, cy + dy + 14], outline=MUTED, width=4)


def icon_envelope(d, cx, cy, s=1.0, color=ACCENT):
    w, h = 90 * s, 60 * s
    d.rounded_rectangle([cx - w, cy - h, cx + w, cy + h], radius=10, outline=color, width=4)
    d.line([cx - w, cy - h, cx, cy - 4], fill=color, width=3)
    d.line([cx + w, cy - h, cx, cy - 4], fill=color, width=3)


def grid_of(d, n, icon_fn, color=ACCENT, cx0=160, cy0=300, gap=130):
    for i in range(n):
        row, col = divmod(i, 3)
        icon_fn(d, cx0 + col * gap, cy0 + row * gap, s=0.62, color=color)


def icon_bars(d, cx=W // 2, cy=330):
    heights = [60, 110, 170, 230]
    for i, h in enumerate(heights):
        x = cx - 150 + i * 100
        color = ACCENT if i < len(heights) - 1 else GREEN
        d.rounded_rectangle([x, cy + 120 - h, x + 60, cy + 120], radius=8, fill=color)
    d.line([cx - 190, cy + 120, cx + 190, cy + 120], fill=MUTED, width=6)


def icon_stack(d, cx=W // 2, cy=330, s=0.9):
    labels = ["n8n", "Postiz", "Kokoro"]
    for i in range(3):
        box = [cx - 130 * s, cy + 60 * s - i * 66 * s, cx + 130 * s, cy + 96 * s - i * 66 * s]
        d.rounded_rectangle(box, radius=12, outline=[MUTED, ACCENT, GREEN][i], width=5)
    d.text((cx, cy - 120), "n8n · Postiz · Kokoro", font=font(30, True), fill=ACCENT, anchor="mm")


def icon_big_dollar(d, cx=W // 2 - 60, cy=330):
    d.text((cx, cy), "$", font=font(220, True), fill=ACCENT, anchor="mm")
    d.line([cx - 110, cy + 130, cx + 110, cy - 130], fill=RED, width=14)
    d.ellipse([cx + 130, cy - 60, cx + 210, cy + 20], outline=GREEN, width=10)
    d.line([cx + 148, cy - 20, cx + 168, cy + 2], fill=GREEN, width=10)
    d.line([cx + 168, cy + 2, cx + 198, cy - 42], fill=GREEN, width=10)


# ---------------------------------------------------------------- scenes
def scene(headline, subline, draw_fn, figure=None, fpose="wave"):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([36, 48, 300, 104], radius=28, fill="#141926", outline=MUTED, width=2)
    d.text((58, 62), "VIEWSAI", font=font(26, True), fill=ACCENT)
    d.text((198, 64), "FREE STACK", font=font(20), fill=MUTED)

    if draw_fn:
        draw_fn(d)
    elif figure == "dog":
        dog_figure(d, W // 2, 320, scale=1.7, pose=fpose)
    else:
        stick_figure(d, W // 2, 300, scale=1.6, pose=fpose)

    d.text((W // 2, 700), headline, font=font(62, True), fill=FG, anchor="mm")
    y = 792
    for ln in subline.split("\n"):
        d.text((W // 2, y), ln, font=font(34), fill=MUTED, anchor="mm")
        y += 48
    return img


def top_scenes():
    return [
        ("3 POSTS A DAY", "n8n fires at 8 / 12 / 5 PT", None, "hands_up"),
        ("9 ACCOUNTS", "X · Instagram · Facebook · YouTube", lambda d: grid_of(d, 9, icon_envelope, cx0=150, cy0=330, gap=140)),
        ("$0 A MONTH", "the whole machine, free", icon_big_dollar),
    ]


def outbound_scenes():
    return [
        ("$2,000/MO?!", "cold email 'platforms'", icon_big_dollar, "shrug"),
        ("WE PAY $11", "same machine, real infra", icon_calculator, "point"),
        ("10 MAILBOXES", "verified · warm-up · verifier", lambda d: grid_of(d, 10, icon_envelope, cx0=150, cy0=300, gap=140), "wave"),
        ("40+ EMAILS / DAY", "free tools, real volume", icon_bars, "point"),
        ("FREE STACK", "n8n · Supabase · Ghost · Kokoro", icon_stack, "hands_up"),
    ]


def kobe_scenes():
    return [
        ("I'M KOBE", "the office dog. the blue eye gives it away", None, "talk"),
        ("I DO THE TALKING", "new clips. same face. every time.", None, "talk"),
        ("BUILT ON VIEWSAI", "free tools. real character.", icon_stack, "talk"),
    ]


TOPICS = {
    "stack": (top_scenes(), "Three posts a day.|Nine social accounts.|Zero dollars a month.", "am_onyx"),
    "outbound": (outbound_scenes(),
                 "Cold email software? Two thousand dollars a month.|We run the same machine for eleven.|Ten verified mailboxes, warm-up router, verifier gate.|Forty plus emails a day. Zero software fees.|Free tools. Real system. That's the stack.",
                 "af_heart"),
    "kobe": (kobe_scenes(),
             "I'm Kobe. The office dog. The blue eye gives it away.|I do the talking around here. New clips, same face, every time.|Built on ViewsAI. Free tools, real character.",
             "am_eric"),
}


# ---------------------------------------------------------------- audio
def tts(text, out, voice):
    subprocess.run(
        ["curl", "-s", "-m", "30", "-X", "POST", "http://localhost:8880/v1/audio/speech",
         "-H", "Content-Type: application/json",
         "-d", f'{{"model":"kokoro","input":{json.dumps(text)},"voice":"{voice}","speed":1.05}}',
         "-o", out], check=True)
    assert os.path.getsize(out) > 1000, "TTS output too small"


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="outbound", choices=list(TOPICS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--voice", default=None)
    ap.add_argument("--lines", default=None, help="pipe-separated VO lines (overrides topic defaults)")
    args = ap.parse_args()

    scenes, default_lines, default_voice = TOPICS[args.topic]
    voice = args.voice or default_voice
    lines = (args.lines or default_lines).split("|")
    if len(lines) < len(scenes):
        lines += [lines[-1]] * (len(scenes) - len(lines))
    out = args.out or f"/tmp/{args.topic}_explainer.mp4"

    # 1) TTS per scene
    voices = []
    for i, line in enumerate(lines[:len(scenes)]):
        mp3 = f"/tmp/{args.topic}_scene_{i}.mp3"
        tts(line.strip(), mp3, voice=voice)
        voices.append((mp3, duration(mp3)))

    # 2) render frames (pad ~0.5s before/after each VO)
    pad = 0.5
    frame_dir = tempfile.mkdtemp()
    frame_idx = 0
    for i, (head, sub, draw_fn, fpose) in enumerate(scenes):
        n_frames = int((voices[i][1] + 2 * pad) * FPS)
        for f in range(n_frames):
            progress = min(1.0, f / (0.35 * FPS))
            img = scene(head, sub, draw_fn, figure="dog" if args.topic == "kobe" else None, fpose=fpose)
            if progress < 1.0:
                bg = Image.new("RGB", (W, H), BG)
                img = Image.blend(bg, img, progress)
            img.save(f"{frame_dir}/{frame_idx:05d}.png")
            frame_idx += 1

    v_dur = sum(int((voices[i][1] + 2 * pad) * FPS) for i in range(len(scenes))) / FPS

    cmd = ["ffmpeg", "-y", "-framerate", str(FPS), "-i", f"{frame_dir}/%05d.png"]
    for mp3, _ in voices:
        cmd += ["-i", mp3]
    filters = ["[0:v]format=yuv420p[v]"]
    for i in range(len(voices)):
        offset = sum(voices[j][1] + 2 * pad for j in range(i)) + pad
        filters.append(f"[{i+1}:a]adelay={int(offset*1000)}|{int(offset*1000)},apad[a{i}]")
    amix_in = "".join(f"[a{i}]" for i in range(len(voices)))
    filters.append(f"{amix_in}amix=inputs={len(voices)}:normalize=0[aout]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[aout]",
            "-t", f"{v_dur + 0.1}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k", "-shortest", out]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"\n✅ {args.topic} explainer: {out} ({v_dur:.1f}s, {len(scenes)} scenes, voice={voice})")


if __name__ == "__main__":
    main()
