#!/usr/bin/env python3
"""Batch: add safe-zone text overlays to the 20 recruiting keyword clips (9:16)."""
import subprocess
import sys
from pathlib import Path

SRC = Path.home() / "Downloads/Kobe_Recruiting"
OUT = Path.home() / "Social Media MASTER/platform-renders/recruiting-keyword-9x16"
RENDER = Path.home() / "ViewsOSComplete/scripts/free-stack-videos/platform_render.py"

# keyword: (hook, cta)
CLIPS = {
    "01_AGENT": ("Agentic recruiting? You can't do that.", "Comment AGENT"),
    "02_SPEED": ("The fastest recruiter wins.", "Comment SPEED"),
    "03_PASSIVE": ("Your next hire isn't applying anywhere.", "Comment PASSIVE"),
    "04_RECRUITER": ("Meet my AI recruiter.", "Comment RECRUITER"),
    "05_SCREEN": ("I stopped reading resumes manually.", "Comment SCREEN"),
    "06_QUALITY": ("Hiring managers want better candidates.", "Comment QUALITY"),
    "07_PIPELINE": ("Build pipelines before jobs exist.", "Comment PIPELINE"),
    "08_FOLLOWUP": ("My AI follows up automatically.", "Comment FOLLOWUP"),
    "09_CLONE": ("I cloned my recruiting process.", "Comment CLONE"),
    "10_STACK": ("One stack. Six tools replaced.", "Comment STACK"),
    "11_OUTREACH": ("One message at a time? Over.", "Comment OUTREACH"),
    "12_BOOLEAN": ("My AI builds the booleans.", "Comment BOOLEAN"),
    "13_SLEEP": ("My AI recruits while you sleep.", "Comment SLEEP"),
    "14_SEARCH": ("Finding the RIGHT ones is hard.", "Comment SEARCH"),
    "15_FLOW": ("200 candidates before breakfast.", "Comment FLOW"),
    "16_FAST": ("Days to reply? You already lost.", "Comment FAST"),
    "17_EDGE": ("Replacing slow recruiters.", "Comment EDGE"),
    "18_AGENCY": ("Agency recruiters, double output.", "Comment AGENCY"),
    "19_EXEC": ("Executive search with AI.", "Comment EXEC"),
    "20_SOURCE": ("My AI never stops sourcing.", "Comment SOURCE"),
}

TARGETS = "tiktok,youtube-shorts,instagram-reel,threads"


def main():
    ok = fail = 0
    for stem, (title, cta) in CLIPS.items():
        src = SRC / f"{stem}.mp4"
        if not src.exists():
            print("skip (missing):", stem)
            continue
        r = subprocess.run(
            [sys.executable, str(RENDER), "--master", str(src),
             "--title", title, "--caption", title, "--cta", cta,
             "--only", TARGETS, "--mode", "blurpad",
             "--out", str(OUT / stem)],
            capture_output=True, text=True)
        if r.returncode == 0:
            ok += 1
            print(f"✓ {stem}: {title}")
        else:
            fail += 1
            print(f"✗ {stem}: {r.stderr[-300:]}")
    print(f"\n{ok} ok, {fail} failed")


if __name__ == "__main__":
    main()
