#!/usr/bin/env python3
"""
TRACK LINKS — instrument outbound email with open pixels + click redirects.

    # one tracked link
    python3 track_link.py --link someone@x.com "https://obrienhq.com/social-stack.html" --label "Social Stack" --campaign q4-recruiting

    # one open pixel
    python3 track_link.py --pixel someone@x.com --campaign q4-recruiting

    # instrument a queued outbound row (adds pixel + rewrites links to tracked ones)
    python3 track_link.py --instrument --limit 20

    # what's happening
    python3 track_link.py --stats

Tracking base: https://tracking.bro768644.workers.dev
"""
import argparse
import json
import re
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://tracking.bro768644.workers.dev"
ENV_FILES = [Path.home() / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")]
TRACK_DOMAINS = ("obrienhq.com", "tryviewsai.com", "getviewsai.com", "viewsai.co", "booking.tryviewsai.com")


def env(k):
    import os
    if os.environ.get(k):
        return os.environ[k]
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


SB = (env("SUPABASE_URL") or "").rstrip("/")
KEY = env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_ANON_KEY")


def rest(path, method="GET", data=None):
    req = urllib.request.Request(
        f"{SB}/rest/v1/{path}", data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json",
                 "Prefer": "return=representation"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else []
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {path} :: {e.read().decode()[:250]}")


def slug(n=10):
    return secrets.token_urlsafe(n).replace("-", "").replace("_", "")[:n]


def make_link(email, destination, label=None, campaign=None):
    s = slug()
    rest("tracked_links", "POST", [{
        "slug": s, "email": email.lower(), "destination": destination,
        "label": label or destination, "campaign": campaign,
    }])
    return f"{BASE}/c/{s}"


def make_pixel(email, campaign=None, outbound_id=None):
    t = slug(12)
    rest("open_pixels", "POST", [{
        "token": t, "email": email.lower(), "campaign": campaign, "outbound_id": outbound_id,
    }])
    return f"{BASE}/o/{t}.gif"


def instrument(limit=20, campaign=None):
    """Add an open pixel + rewrite links in queued outbound bodies."""
    rows = rest(f"email_send_queue?select=id,email,subject,body,status&status=eq.pending_review"
                f"&limit={limit}")
    done = 0
    for r in rows:
        email = r.get("email")
        body = r.get("body") or ""
        if not email or not body:
            continue
        if BASE in body:
            continue
        pix = make_pixel(email, campaign=campaign or "queued", outbound_id=r["id"])
        new = body
        # rewrite bare links in the body to tracked redirects
        for m in set(re.findall(r'https?://[^"\'\s\)<>]+', body)):
            if any(d in m for d in TRACK_DOMAINS) and "unsubscribe" not in m.lower():
                new = new.replace(m, make_link(email, m, label=m[:60], campaign=campaign or "queued"))
        tag = f'<img src="{pix}" width="1" height="1" alt="" style="display:none">'
        # inject before the closing tag, or append
        if "</p>" in new[-200:]:
            i = new.rfind("</p>")
            new = new[:i] + tag + new[i:]
        else:
            new = new + tag
        rest(f"email_send_queue?id=eq.{r['id']}", "PATCH", {"body": new})
        done += 1
        print(f"  ✓ instrumented {email[:34]:36s} pixel + links")
    print(f"{done} row(s) instrumented")


def stats():
    print("=== top clicks ===")
    for l in rest("tracked_links?select=email,label,clicks,last_click_at&order=clicks.desc&limit=8"):
        if l.get("clicks"):
            print(f"  {l['clicks']:3d}  {l.get('email','')[:32]:34s} {str(l.get('label'))[:40]}")
    print("=== opens (weak signal) ===")
    for p in rest("open_pixels?select=email,opens,likely_apple_mpp&order=opens.desc&limit=5"):
        if p.get("opens"):
            print(f"  {p['opens']:3d}  {p.get('email','')[:40]}")
    print("=== intent scores ===")
    try:
        for c in rest("contact_intent?select=email,company,score,opens,clicks,replies&order=score.desc&limit=8"):
            print(f"  {c.get('score') or 0:4}  {(c.get('email') or '')[:30]:32s} "
                  f"o={c.get('opens') or 0} c={c.get('clicks') or 0} r={c.get('replies') or 0}")
    except Exception as e:
        print("  (refresh scores first)", str(e)[:80])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", nargs=2, metavar=("EMAIL", "URL"))
    ap.add_argument("--label"); ap.add_argument("--campaign")
    ap.add_argument("--pixel", metavar="EMAIL")
    ap.add_argument("--instrument", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    if args.link:
        print(make_link(args.link[0], args.link[1], args.label, args.campaign))
    elif args.pixel:
        print(make_pixel(args.pixel, args.campaign))
    elif args.instrument:
        instrument(args.limit, args.campaign)
    elif args.stats:
        stats()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
