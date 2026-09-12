#!/usr/bin/env python3
"""
BATCH POSTS — turn the content doc's scripts into finished vertical posts.

Each post = existing Kobe footage (audio REPLACED with a fresh Kokoro line)
+ burned-in hook/CTA. No GPU, no quota, ~20-30s per post.

Usage:
    python3 batch_kobe_posts.py --list
    python3 batch_kobe_posts.py --group kobe        # 15 pattern interrupts
    python3 batch_kobe_posts.py --limit 5
    python3 batch_kobe_posts.py                     # all 45
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASM = HERE / "assemble_kobe.py"
OUT = Path.home() / "Social Media MASTER/kobe-content"

# hero movements rotated across posts (all vertical, best quality)
MOVES = [
    # newest / best first (auto-skipped if a clip is missing)
    "video_1_1d5fac49b6f44dd4b145dca9578c79c3",
    "Kobe_lebron_connical",
    "kobe_body_views_only",
    "ViewsAI_Orchestrator_9.16",
    "kobe-fullbody-desk-take3",
    "kobe-viewsai-take2",
    "kobe-headshot-mic",
    "kobe-fullbody-office",
    "01_kobe_intro_mic",
    "02_kobe_podcast_cameraroll",
    "03_kobe_walk_tagline",
    "hf_20260730_184745_641c68fc-4c4e-4b33-87",
    "hf_20260730_231328_a57bd5b6-9ce9-41b4-a4",
    "bro_Learn_high_how_to_c",
]

# (slug, spoken line, on-screen hook, CTA keyword, group)
POSTS = [
    # ---------------- KOBE PATTERN INTERRUPTS (highest scroll-stop) ----------------
    ("kobe-pom-recruiting", "I'm a Pomeranian. And I automated your recruiting.", "AI recruiting. 24/7.", "AI", "kobe"),
    ("kobe-sdr", "You hired another SDR? I wouldn't have done that.", "There's a better way.", "AI", "kobe"),
    ("kobe-400-candidates", "I found four hundred candidates before breakfast.", "AI sourcing never stops.", "AI", "kobe"),
    ("kobe-outbound-sucks", "Your outbound is leaving money on the table.", "We fix the system.", "OUTBOUND", "kobe"),
    ("kobe-spreadsheet", "I'm not a recruiter. I just replaced their spreadsheet.", "Recruiting automation.", "AGENT", "kobe"),
    ("kobe-four-legs", "I have four legs and better outbound than you.", "ViewsAI builds the pipeline.", "OUTBOUND", "kobe"),
    ("kobe-fix-gtm", "I'm Kobe. Let's fix your GTM.", "Automated outbound plus recruiting.", "OUTBOUND", "kobe"),
    ("kobe-woof", "You're manually sourcing candidates? Woof.", "AI does it while you sleep.", "SOURCE", "kobe"),
    ("kobe-wasting-money", "My human was wasting money on SDRs. I put a stop to it.", "Same output. A fraction of the cost.", "OUTBOUND", "kobe"),
    ("kobe-complicated", "My human said AI was complicated. I fixed it.", "It is not complicated.", "AI", "kobe"),
    ("kobe-supervise", "My human built an AI recruiting team. I supervise.", "They work. I keep them honest.", "AGENT", "kobe"),
    ("kobe-bark", "I bark. ViewsAI builds your pipeline.", "That is the whole deal.", "OUTBOUND", "kobe"),
    ("kobe-competitors", "Your competitors have AI agents. You have me.", "Which is honestly fine by me.", "AI", "kobe"),
    ("kobe-asked-viewsai", "I asked ViewsAI to fix your outbound.", "They said yes.", "OUTBOUND", "kobe"),
    ("kobe-still-manual", "You're still manually finding prospects?", "That is a lot of clicking.", "OUTBOUND", "kobe"),

    # ---------------- OUTBOUND / LEAD GEN ----------------
    ("out-better-outbound", "Your sales team doesn't need more leads. It needs better outbound.", "Better outbound, not more leads.", "OUTBOUND", "outbound"),
    ("out-paying-humans", "Still paying humans to find your prospects? That's adorable.", "Let the system do it.", "OUTBOUND", "outbound"),
    ("out-competitors-auto", "Your competitors are automating outbound. Are you?", "The gap widens daily.", "OUTBOUND", "outbound"),
    ("out-247", "What if your outbound worked around the clock?", "It can.", "OUTBOUND", "outbound"),
    ("out-ten-sdrs", "You don't need ten SDRs. You need a better system.", "Systems beat headcount.", "OUTBOUND", "outbound"),
    ("out-crm-full", "Your CRM is full. Your pipeline isn't.", "Let's fix the pipeline.", "OUTBOUND", "outbound"),
    ("out-cold-email", "Cold email isn't dead. Bad cold email is.", "We write the good kind.", "OUTBOUND", "outbound"),
    ("out-stop-buying", "Stop buying leads. Build your own pipeline.", "Own the asset, not the rental.", "OUTBOUND", "outbound"),
    ("out-database", "Your next customer might already be in your database.", "We mine it properly.", "OUTBOUND", "outbound"),
    ("out-spreadsheets", "If your outbound depends on spreadsheets, it depends on luck.", "Automate the boring part.", "OUTBOUND", "outbound"),

    # ---------------- RECRUITING ----------------
    ("rec-automation", "You don't need another recruiter. You need recruiting automation.", "Hire leverage, not headcount.", "AGENT", "recruiting"),
    ("rec-one-profile", "Still sourcing candidates one profile at a time?", "That is a full-time job you don't need.", "SOURCE", "recruiting"),
    ("rec-process", "Your recruiter isn't slow. Your process is.", "Fix the process.", "PIPELINE", "recruiting"),
    ("rec-never-stop", "What if your recruiting team never stopped sourcing?", "It can work all night.", "SLEEP", "recruiting"),
    ("rec-paying-search", "You're paying recruiters to search. AI can do that.", "Let people do the human part.", "SCREEN", "recruiting"),
    ("rec-best-candidate", "Your best candidate probably isn't applying.", "We go find them.", "PASSIVE", "recruiting"),
    ("rec-job-boards", "Job boards show you applicants. We find the people you actually want.", "Applicants versus candidates.", "SOURCE", "recruiting"),
    ("rec-right-people", "Your open role isn't the problem. Finding the right people is.", "Sourcing is the bottleneck.", "FAST", "recruiting"),
    ("rec-every-hour", "Imagine a recruiter working every hour you're not.", "That is what automation is for.", "SLEEP", "recruiting"),
    ("rec-stop-waiting", "Stop waiting for candidates to apply.", "Go get them instead.", "PASSIVE", "recruiting"),

    # ---------------- VIEWSAI / AI AGENTS ----------------
    ("ai-workforce", "What if your company could hire its own AI workforce?", "Agents that actually work.", "AI", "agents"),
    ("ai-coworkers", "You're not replacing your team. You're giving them AI coworkers.", "Better team, same payroll.", "AI", "agents"),
    ("ai-employee", "This is what an AI employee actually looks like.", "Not a chatbot. A worker.", "AI", "agents"),
    ("ai-repetitive", "Your business has repetitive work. AI should have it.", "Give the robots the busywork.", "AI", "agents"),
    ("ai-why-hire", "Why hire another employee for work AI can handle?", "Spend on growth instead.", "AI", "agents"),
    ("ai-while-sleep", "Imagine your business running while you sleep.", "It can, tonight.", "AI", "agents"),
    ("ai-agents-work", "We build AI agents that actually do the work.", "Shipped, not slides.", "AI", "agents"),
    ("ai-no-salary", "Your next hire might not need a salary.", "It just needs instructions.", "AI", "agents"),
    ("ai-workload", "AI isn't coming for your job. It's coming for your workload.", "That is a good trade.", "AI", "agents"),
    ("ai-kobe-knows", "This little dog knows more about AI than your sales team.", "He has good teachers.", "AI", "agents"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--group", default="", help="kobe | outbound | recruiting | agents")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", type=int, default=0, help="skip the first N (resume a batch)")
    args = ap.parse_args()

    posts = POSTS
    if args.group:
        posts = [p for p in posts if p[4] == args.group]
    if args.start:
        posts = posts[args.start:]
    if args.limit:
        posts = posts[: args.limit]

    if args.list:
        for i, (slug, line, hook, cta, grp) in enumerate(posts):
            print(f"  [{i:02d}] {grp:10s} {slug:22s} {hook[:34]:36s} → Comment {cta}")
        print(f"\n{len(posts)} posts")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    lib = {f.stem for f in (Path.home() / "Social Media MASTER/kobe-library/movement").glob("*.mp4")}
    usable = [m for m in MOVES if m in lib] or list(lib)
    for i, (slug, line, hook, cta, grp) in enumerate(posts):
        move = usable[i % len(usable)]
        out = OUT / f"{slug}.mp4"
        if out.exists():
            print(f"  ✓ skip (exists) {slug}")
            continue
        r = subprocess.run(
            [sys.executable, str(ASM), "--movement", move, "--line", line,
             "--replace-audio", "--title", hook, "--caption", hook,
             "--cta", f"Comment {cta}", "--out", str(out)],
            capture_output=True, text=True)
        if r.returncode == 0:
            ok += 1
            print(f"  ✓ [{i+1}/{len(posts)}] {slug}  ({move[:26]})  →  Comment {cta}")
        else:
            fail += 1
            print(f"  ✗ {slug}: {r.stderr[-140:]}")
    print(f"\n{ok} produced, {fail} failed → {OUT}")


if __name__ == "__main__":
    main()
