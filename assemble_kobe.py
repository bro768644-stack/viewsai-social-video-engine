#!/usr/bin/env python3
"""
KOBE CONTENT ASSEMBLER — movement clip + any line + text overlay = finished post.

One keeper movement clip (locked look) becomes DOZENS of posts by swapping:
  audio  (Kokoro TTS, any line)   +   text overlay (hook/CTA)   +   platform render

Usage:
    python3 assemble_kobe.py --movement kobe-fullbody-desk-take3 \
        --line "I'm Kobe. ViewsAI builds the pipeline." \
        --title "AI recruiting. 24/7." --cta "Comment AI" \
        --out ~/Social\ Media\ MASTER/kobe-content/demo1.mp4

    --list            show movement library
    --no-text         skip text overlay (clean clip only)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = Path.home() / "Social Media MASTER/kobe-library/movement"
OUTDIR = Path.home() / "Social Media MASTER/kobe-content"
RENDER = ROOT / "platform_render.py"
KOKORO = "http://localhost:8880/v1/audio/speech"

MOVEMENTS = {
    "kobe-fullbody-desk-take3": {"file": "kobe-fullbody-desk-take3.mp4", "look": "desk full body", "quality": "FLAGSHIP"},
    "kobe-viewsai-take2": {"file": "kobe-viewsai-take2.mp4", "look": "viewsai tee", "quality": "great"},
    "kobe-headshot-mic": {"file": "kobe-headshot-mic.mp4", "look": "headshot", "quality": "good"},
    "kobe-fullbody-office": {"file": "kobe-fullbody-office.mp4", "look": "office full body", "quality": "good"},
}


def tts(line, voice, out):
    body = '{"model":"kokoro","input":%s,"voice":"%s","speed":1.05}' % (json.dumps(line), voice)
    subprocess.run(["curl", "-s", "-m", "30", "-X", "POST", KOKORO,
                    "-H", "Content-Type: application/json", "-d", body, "-o", out], check=True)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--movement", required=True, choices=list(MOVEMENTS))
    ap.add_argument("--line", required=True)
    ap.add_argument("--voice", default="am_eric")
    ap.add_argument("--title", default="")
    ap.add_argument("--caption", default="")
    ap.add_argument("--cta", default="")
    ap.add_argument("--out", default=str(OUTDIR / "out.mp4"))
    ap.add_argument("--no-text", action="store_true")
    args = ap.parse_args()

    if args.movement == "list":
        for k, v in MOVEMENTS.items():
            print(f"  {k:28s} {v['look']:20s} {v['quality']}")
        return

    src = LIB / MOVEMENTS[args.movement]["file"]
    assert src.exists(), f"missing movement clip: {src}"

    # 1) Kokoro voice line
    vo = "/tmp/kobe_vo_tmp.mp3"
    tts(args.line, args.voice, vo)
    vo_dur = dur(vo)

    # 2) mux voice over the movement clip (voice dominant, keep room tone low)
    base = OUTDIR / f"{Path(args.out).stem}-voiced.mp4"
    OUTDIR.mkdir(parents=True, exist_ok=True)
    v_dur = dur(str(src))
    # voice starts at 0.4s; clip may be longer — voice sits over the talking section
    cmd = ["ffmpeg", "-y", "-i", str(src), "-i", vo,
           "-filter_complex",
           f"[0:a]volume=0.25,apad[amb];[1:a]adelay=400|400,volume=2.2[vo];"
           f"[amb][vo]amix=inputs=2:duration=first:normalize=0,"
           f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
           "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac",
           "-b:a", "160k", "-t", str(min(v_dur, vo_dur + 1.0)), str(base)]
    subprocess.run(cmd, check=True, capture_output=True)

    # 3) optional text overlay via the platform renderer (tiktok = true 9:16)
    final = args.out if not args.no_text else base
    if not args.no_text:
        d = OUTDIR / "staging"
        subprocess.run([sys.executable, str(RENDER), "--master", str(base),
                        "--only", "tiktok", "--title", args.title,
                        "--caption", args.caption or args.title,
                        "--cta", args.cta, "--out", str(d)],
                       check=True, capture_output=True)
        mp4 = next((d / "tiktok").glob("*.mp4"))
        mp4.replace(final)
    print(f"✅ {final}")


if __name__ == "__main__":
    main()
