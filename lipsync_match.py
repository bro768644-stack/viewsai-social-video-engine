#!/usr/bin/env python3
"""
LIPSYNC MATCHER — align a new line to a clip's existing mouth movements.

The Kling/Seedance clips were generated lip-synced to KNOWN scripts. Swapping in
a new line only looks right if the new words roughly match the ORIGINAL rhythm
(syllable count + pacing). This tool scores that.

Usage:
    python3 lipsync_match.py --list                 # known-script clips + syllable counts
    python3 lipsync_match.py --clip 01_AGENT --line "your new line here"
    python3 lipsync_match.py --best --line "your new line"   # which clips fit best

Rule of thumb: within ±15% of the original syllable count reads as "in sync".
"""
import argparse
import re
from pathlib import Path

LIB = Path.home() / "Social Media MASTER/kobe-library/movement"

# clips that were generated WITH speech (lip-synced) -> original script known
LIPSYNCED = {
    "01_AGENT": "Agentic recruiting? You can't do that. Watch this. Comment AGENT, and I'll send you the workflow.",
    "02_SPEED": "The fastest recruiter wins. My AI responds in under sixty seconds. Comment SPEED.",
    "03_PASSIVE": "Your next hire isn't applying anywhere. My AI finds them automatically. Comment PASSIVE.",
    "04_RECRUITER": "Meet my AI recruiter. It sources, screens, and books interviews. Comment RECRUITER.",
    "05_SCREEN": "I stopped reading resumes manually months ago. Comment SCREEN.",
    "06_QUALITY": "Hiring managers don't want more resumes. They want better candidates. Comment QUALITY.",
    "07_PIPELINE": "The best recruiters build pipelines before jobs exist. Comment PIPELINE.",
    "08_FOLLOWUP": "Candidates ghost recruiters. My AI follows up automatically. Comment FOLLOWUP.",
    "09_CLONE": "I cloned my recruiting process with AI. Comment CLONE.",
    "10_STACK": "This recruiting stack replaced six different tools. Comment STACK.",
    "11_OUTREACH": "Still sending outreach one message at a time? That's over. Comment OUTREACH.",
    "12_BOOLEAN": "Forget Boolean strings. My AI builds them for me. Comment BOOLEAN.",
    "13_SLEEP": "While you're sleeping, my AI recruiter is finding candidates. Comment SLEEP.",
    "14_SEARCH": "Finding candidates isn't hard anymore. Finding the right ones is. Comment SEARCH.",
    "15_FLOW": "This AI workflow sourced two hundred candidates before breakfast. Comment FLOW.",
    "16_FAST": "If you're waiting days to contact applicants, you've already lost. Comment FAST.",
    "17_EDGE": "The recruiters using AI aren't replacing recruiters. They're replacing slow recruiters. Comment EDGE.",
    "18_AGENCY": "Agency recruiters, this workflow could double your output. Comment AGENCY.",
    "19_EXEC": "Executive search with AI? Watch this. Comment EXEC.",
    "20_SOURCE": "I don't spend hours sourcing anymore. My AI never stops. Comment SOURCE.",
    # Seedance talking takes
    "01_kobe_intro_mic": "Yo, I'm Kobe, Chief Capture Officer at ViewsAI. Every screenshot captured and organized automatically. That's love, and views.",
    "02_kobe_podcast_cameraroll": "Real talk: your best ideas die in the camera roll. ViewsAI captures every screenshot and organizes it automatically. You're welcome.",
    # Veo take with baked dialogue
    "kobe-headshot-mic": "Drop AI in the comments and I will send you the whole system.",
}

# clips with NO speech (ambient only) -> any new line works
AMBIENT = [
    "kobe-fullbody-desk-take3", "kobe-viewsai-take2", "kobe-fullbody-office",
]


def syllables(text: str) -> int:
    """Rough English syllable count (good enough for rhythm matching)."""
    text = re.sub(r"[^a-z\s]", " ", text.lower())
    n = 0
    for w in text.split():
        groups = re.findall(r"[aeiouy]+", w)
        c = len(groups)
        if w.endswith("e") and c > 1:
            c -= 1
        n += max(1, c)
    return n


def score(orig_syl, new_syl):
    if orig_syl == 0:
        return 0.0
    return 1.0 - abs(new_syl - orig_syl) / orig_syl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--clip", default=None)
    ap.add_argument("--line", default=None)
    ap.add_argument("--best", action="store_true")
    ap.add_argument("--tolerance", type=float, default=0.15)
    args = ap.parse_args()

    if args.list or (not args.clip and not args.best):
        print("LIP-SYNCED CLIPS (audio swap only if the rhythm matches):\n")
        for k, v in LIPSYNCED.items():
            s = syllables(v)
            ok = "in library" if (LIB / f"{k}.mp4").exists() else "not imported"
            print(f"  {k:26s} {s:3d} syl  [{ok}]  {v[:62]}...")
        print("\nAMBIENT CLIPS (no speech — swap any line freely):")
        for k in AMBIENT:
            ok = "in library" if (LIB / f"{k}.mp4").exists() else "not imported"
            print(f"  {k:26s}      [{ok}]")
        return

    if not args.line:
        raise SystemExit("--line required with --clip/--best")
    new_syl = syllables(args.line)
    print(f"new line: {new_syl} syllables\n")

    if args.clip:
        orig = LIPSYNCED.get(args.clip)
        if not orig:
            print(f"{args.clip} has no known script (treat as ambient — any line works)")
            return
        o = syllables(orig)
        sc = score(o, new_syl)
        verdict = "✅ MATCHES" if sc >= 1 - args.tolerance else "⚠️  MISMATCH — lips will drift"
        print(f"  clip {args.clip}: original {o} syl vs new {new_syl} syl → {sc*100:.0f}%  {verdict}")
        print(f"  original: {orig}")
        return

    # --best
    ranked = sorted(LIPSYNCED.items(), key=lambda kv: -score(syllables(kv[1]), new_syl))
    print("best-fitting clips for this line:")
    for k, v in ranked[:6]:
        sc = score(syllables(v), new_syl)
        verdict = "✅" if sc >= 1 - args.tolerance else "⚠️"
        print(f"  {verdict} {k:26s} {syllables(v):3d} syl  ({sc*100:.0f}%)")


if __name__ == "__main__":
    main()
