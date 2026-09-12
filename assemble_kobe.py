#!/usr/bin/env python3
"""
KOBE CONTENT ASSEMBLER — movement clip + voice + text overlay = finished post.

Two modes:
  * motion-only clips (LivePortrait/Veo takes): mix a fresh Kokoro line over it
  * lip-synced clips (JoyVASA/MuseTalk):       keep their audio, just add text  (--keep-audio)

Usage:
    # lip-synced Kaggle clip + text overlay
    python3 assemble_kobe.py --movement kobe_talking --keep-audio \
        --title "DROP AI IN THE COMMENTS" --caption "I'll send you the system" --cta "Comment AI" \
        --out ~/Social\ Media\ MASTER/kobe-content/post1.mp4

    # motion-only clip with a fresh Kokoro voice
    python3 assemble_kobe.py --movement kobe-fullbody-desk-take3 \
        --line "I'm Kobe. ViewsAI builds the pipeline." \
        --title "AI recruiting" --cta "Comment AI"

    python3 assemble_kobe.py --movement list --line x     # show the library
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

LABELS = {
    "kobe-fullbody-desk-take3": ("desk full body", "FLAGSHIP"),
    "kobe-viewsai-take2": ("viewsai tee", "great"),
    "kobe-headshot-mic": ("headshot", "good"),
    "kobe-fullbody-office": ("office full body", "good"),
    "kobe_talking": ("JoyVASA animal lip-sync", "FREE (Kaggle)"),
}


def discover():
    """Every .mp4 in the library is a usable movement clip."""
    found = {}
    if LIB.exists():
        for f in sorted(LIB.glob("*.mp4")):
            look, quality = LABELS.get(f.stem, ("unlabeled", "new"))
            found[f.stem] = {"file": f.name, "look": look, "quality": quality}
    return found


def tts(line, voice, out):
    body = json.dumps({"model": "kokoro", "input": line, "voice": voice, "speed": 1.05})
    subprocess.run(["curl", "-s", "-m", "30", "-X", "POST", KOKORO,
                    "-H", "Content-Type: application/json", "-d", body, "-o", out], check=True)


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--movement", required=True, help="clip name in the movement library (use 'list')")
    ap.add_argument("--line", default="", help="spoken line (motion-only mode)")
    ap.add_argument("--voice", default="am_eric")
    ap.add_argument("--title", default="")
    ap.add_argument("--caption", default="")
    ap.add_argument("--cta", default="")
    ap.add_argument("--out", default=str(OUTDIR / "out.mp4"))
    ap.add_argument("--no-text", action="store_true")
    ap.add_argument("--keep-audio", action="store_true",
                    help="clip already has lip-synced speech (JoyVASA) — don't mix a new VO")
    ap.add_argument("--replace-audio", action="store_true",
                    help="REPLACE the clip's audio with the new Kokoro line (clean; keeps a whisper of room tone)")
    ap.add_argument("--keep-length", action="store_true",
                    help="keep the clip's full duration (default: trim to the voice length)")
    ap.add_argument("--room-tone", type=float, default=0.0,
                    help="original audio level when replacing (0=fully silent, 0.08=subtle ambience)")
    args = ap.parse_args()

    movements = discover()

    if args.movement in ("list", "--list"):
        for k, v in movements.items():
            print(f"  {k:28s} {v['look']:24s} {v['quality']}")
        return
    if args.movement not in movements:
        print("unknown movement. available:")
        for k, v in movements.items():
            print(f"  {k:28s} {v['look']:24s} {v['quality']}")
        sys.exit(2)

    src = LIB / movements[args.movement]["file"]
    assert src.exists(), f"missing clip: {src}"
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.keep_audio:
        print(f"lip-synced clip → keeping its audio: {src.name}")
        base = src
    else:
        if not args.line:
            sys.exit("--line is required unless --keep-audio")
        vo = Path("/tmp/kobe_vo_tmp.mp3")
        tts(args.line, args.voice, str(vo))
        vo_dur = dur(vo)
        v_dur = dur(src)
        base = OUTDIR / f"{out.stem}-voiced.mp4"

        if args.replace_audio:
            # REPLACE the track: silence (or a whisper of room tone) + the new line only.
            # Voice starts at 0.35s; video is trimmed to the voice length.
            have_orig = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                 "stream=codec_type", "-of", "csv=p=0", str(src)],
                capture_output=True, text=True).stdout.strip() != ""
            rt = max(0.0, float(args.room_tone))
            if have_orig and rt > 0:
                fc = (f"[0:a]volume={rt},apad[amb];"
                      f"[1:a]adelay=350|350,volume=1.9[vo];"
                      f"[amb][vo]amix=inputs=2:duration=first:normalize=0,"
                      f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
            else:
                fc = (f"[1:a]adelay=350|350,volume=1.9,apad,"
                      f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
            # default: trim to the voice; --keep-length: use the whole clip
            duration = v_dur if args.keep_length else (vo_dur + 0.7)
            cmd = ["ffmpeg", "-y", "-i", str(src), "-i", str(vo),
                   "-filter_complex", fc,
                   "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac",
                   "-b:a", "160k", "-t", str(duration), str(base)]
            print(f"audio REPLACED (room-tone={rt}) → {base.name}")
        else:
            cmd = ["ffmpeg", "-y", "-i", str(src), "-i", str(vo),
                   "-filter_complex",
                   "[0:a]volume=0.25,apad[amb];[1:a]adelay=400|400,volume=2.2[vo];"
                   "[amb][vo]amix=inputs=2:duration=first:normalize=0,"
                   "loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
                   "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac",
                   "-b:a", "160k", "-t", str(min(v_dur, vo_dur + 1.0)), str(base)]
            print(f"voiced (mixed) → {base.name}")
        subprocess.run(cmd, check=True, capture_output=True)

    if args.no_text:
        if base != out:
            import shutil
            shutil.copy(base, out)
        print(f"✅ {out}")
        return

    staging = OUTDIR / "staging"
    subprocess.run([sys.executable, str(RENDER), "--master", str(base),
                    "--only", "tiktok",
                    "--title", args.title,
                    "--caption", args.caption or args.title,
                    "--cta", args.cta,
                    "--out", str(staging)], check=True, capture_output=True)
    mp4s = sorted((staging / "tiktok").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert mp4s, "renderer produced no output"
    import shutil
    shutil.copy(mp4s[0], out)
    print(f"✅ {out}")


if __name__ == "__main__":
    main()
