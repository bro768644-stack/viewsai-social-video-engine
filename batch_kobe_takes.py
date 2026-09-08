#!/usr/bin/env python3
"""
Batch Kobe/ViewsAI content takes on the LOCKED flagship look.

Format per item:
    Kobe says the HOOK (Veo, real dialogue) → overlay pivots to VALUE
    (platform_render title) → CTA keyword (routes to ChatbotX lead magnet).

Usage:
    python3 batch_kobe_takes.py --limit 2 --pillar kobe --overlay
    python3 batch_kobe_takes.py --list
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VEO = ROOT / "veo_kobe.py"
RENDER = ROOT / "platform_render.py"
LOOK = "/Users/viewsai/ViewsOSComplete/Brands/Kobe/refs/kobe-viewsai.png"
OUT = Path.home() / "Social Media MASTER/kobe-takes"

# speaker line -> (pivot text for overlay, CTA keyword)
TAKES = {
    # -- kobe pattern interrupts (highest scroll-stop) --
    "kobe-pom-recruiting": ("kobe", "I'm a Pomeranian. And I automated your recruiting.",
                            "AI recruiting. 24/7.", "AI"),
    "kobe-sdr": ("kobe", "You hired another SDR? I wouldn't have done that.",
                 "There's a better way.", "AI"),
    "kobe-400": ("kobe", "I found four hundred candidates before breakfast.",
                 "AI sourcing never stops.", "AI"),
    "kobe-outbound": ("kobe", "Kobe here. Your outbound is leaving money on the table.",
                      "We fix the system.", "OUTBOUND"),
    "kobe-spreadsheet": ("kobe", "I'm not a recruiter. I just replaced their spreadsheet.",
                         "Recruiting automation.", "AI"),
    "kobe-4legs": ("kobe", "I have four legs and better outbound than you.",
                   "ViewsAI builds the pipeline.", "OUTBOUND"),
    "kobe-gtm": ("kobe", "I'm Kobe. Let's fix your GTM.",
                 "Automated outbound + recruiting.", "OUTBOUND"),
    "kobe-woof": ("kobe", "You're manually sourcing candidates? Woof.",
                  "AI does it while you sleep.", "AI"),
    # -- recruiting pillar --
    "rec-never-stop": ("kobe", "What if your recruiting team never stopped sourcing?",
                       "AI recruiting agents.", "AI"),
    "rec-best-candidate": ("kobe", "Your best candidate probably isn't applying.",
                           "We find them anyway.", "AI"),
    # -- outbound pillar --
    "out-247": ("kobe", "What if your outbound worked 24-7?",
                "The system never sleeps.", "OUTBOUND"),
    "out-crm": ("kobe", "Your CRM is full. Your pipeline isn't.",
                "We build the pipeline.", "OUTBOUND"),
    "out-buying-leads": ("kobe", "Stop buying leads. Build your own pipeline.",
                         "10 mailboxes. Real outbound.", "OUTBOUND"),
}

VOICE_LOCK = (
    "Talking head video. He starts from this exact image and stays IDENTICAL the whole clip - "
    "same dog, same face, same heterochromia eyes (soft natural light blue + brown), same navy tee, "
    "same background. He speaks directly to camera, confident and friendly, subtle head movement only, "
    "no shape change, no morphing. Warm office lighting. Cinematic, photorealistic."
)


def veo_take(slug, speaker, line):
    prompt = f'{VOICE_LOCK} He says exactly: "{line}"'
    out = OUT / speaker / f"{slug}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(VEO), "--image", LOOK,
                        "--prompt", prompt, "--out", str(out),
                        "--aspect", "9:16", "--seconds", "8"],
                       capture_output=True, text=True)
    return r.returncode == 0, out


def overlay(slug, speaker, pivot, cta, src):
    title = pivot
    outdir = OUT / speaker / f"{slug}-text"
    r = subprocess.run(
        [sys.executable, str(RENDER), "--master", str(src), "--only", "tiktok",
         "--title", title, "--caption", pivot, "--cta", f"Comment {cta}",
         "--out", str(outdir), "--cover"],
        capture_output=True, text=True)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--pillar", default="kobe")
    ap.add_argument("--slug", default=None, help="specific take")
    ap.add_argument("--no-overlay", action="store_true")
    ap.add_argument("--rolls", type=int, default=1, help="generate N candidates per line (Veo varies composition per roll)")
    args = ap.parse_args()

    if args.list:
        for k, (s, line, pivot, cta) in TAKES.items():
            print(f"{k:24s} [{s}] {line}  →  \"{pivot}\" / Comment {cta}")
        return

    items = list(TAKES.items())
    if args.slug:
        items = [i for i in items if i[0] == args.slug]
    items = items[: args.limit]

    for slug, (speaker, line, pivot, cta) in items:
        ok, out = veo_take(slug, speaker, line)
        print(f"{'✓' if ok else '✗'} Veo {slug}: {line[:50]}")
        if args.rolls > 1:
            # extra candidate rolls get a roll-N suffix so keepers can be picked
            for r in range(2, args.rolls + 1):
                okr, outr = veo_take(f"{slug}-r{r}", speaker, line)
                print(f"   {'✓' if okr else '✗'} roll {r} -> {outr.name}")
        if ok and not args.no_overlay:
            ok2 = overlay(slug, speaker, pivot, cta, out)
            print(f"   {'✓' if ok2 else '✗'} overlay → {speaker}/{slug}-text/")


if __name__ == "__main__":
    main()
