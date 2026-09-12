#!/usr/bin/env python3
"""
SCOUT SYNC — load Scout's sourced leads into Supabase so replies/outbound can use them.

Reads:
    ~/ViewsOSComplete/Scout/linkedin-connection-queue.csv   (people w/ emails)
    ~/ViewsOSComplete/Scout/linkedin_people_context.csv     (people, no email)
    ~/ViewsOSComplete/Scout/agency-leads-companies.csv      (companies + roles)
    ~/ViewsOSComplete/Scout/exports/*.jsonl                 (github / scrapling exports)

Writes: supabase scout_people + scout_companies (upsert, deduped by email/domain)

Usage:
    python3 scout_sync.py                 # sync everything
    python3 scout_sync.py --stats         # show what's in Supabase
"""
import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCOUT = Path.home() / "ViewsOSComplete/Scout"
ENV_FILES = [Path.home() / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")]


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


def rest(path, method="GET", data=None, prefer="resolution=merge-duplicates,return=minimal"):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"{SB}/rest/v1/{path}", data=body, method=method,
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json", "Prefer": prefer})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else []
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {path} :: {e.read().decode()[:300]}")


def domain_of(url_or_email):
    if not url_or_email:
        return None
    s = str(url_or_email).strip().lower()
    m = re.search(r"[@]([a-z0-9.-]+\.[a-z]{2,})", s)
    if m:
        return m.group(1)
    s = re.sub(r"^https?://", "", s).split("/")[0]
    s = re.sub(r"^www\.", "", s)
    return s if "." in s else None


# ---------------------------------------------------------------- loaders
def load_connection_queue():
    p = SCOUT / "linkedin-connection-queue.csv"
    if not p.exists():
        return []
    out = []
    with p.open(newline="", errors="ignore") as f:
        for r in csv.DictReader(f):
            email = (r.get("email") or "").strip()
            if not email or "example.com" in email:
                continue
            out.append({
                "email": email.lower(),
                "first_name": r.get("first_name") or None,
                "last_name": r.get("last_name") or None,
                "full_name": " ".join(x for x in [r.get("first_name"), r.get("last_name")] if x) or None,
                "title": r.get("title") or None,
                "company": r.get("company") or None,
                "company_domain": domain_of(email),
                "linkedin_url": r.get("linkedin_url") or None,
                "priority": (r.get("priority") or "").lower() or None,
                "source": r.get("source") or "scout",
                "tags": ["scout", "connection-queue"],
            })
    return out


def load_people_context():
    p = SCOUT / "linkedin_people_context.csv"
    if not p.exists():
        return []
    out = []
    with p.open(newline="", errors="ignore") as f:
        for r in csv.DictReader(f):
            if not (r.get("username") or r.get("full_name") or r.get("company")):
                continue
            out.append({
                "full_name": (r.get("full_name") or "").strip() or None,
                "title": (r.get("headline") or "").strip() or None,
                "company": (r.get("company") or "").strip() or None,
                "company_domain": domain_of(r.get("company")),
                "linkedin_url": (f"https://linkedin.com/in/{r['username']}"
                                 if r.get("username") else None),
                "source": "linkedin",
                "tags": ["scout", "people-context"],
            })
    return out


def load_companies():
    p = SCOUT / "agency-leads-companies.csv"
    if not p.exists():
        return []
    out = []
    with p.open(newline="", errors="ignore") as f:
        for r in csv.DictReader(f):
            if not r.get("company"):
                continue
            out.append({
                "company": r["company"].strip(),
                "domain": domain_of(r.get("website")) or domain_of(r.get("company")),
                "website": r.get("website") or None,
                "job_count": int(r.get("jobCount") or 0),
                "sample_roles": (r.get("sampleRoles") or "")[:500] or None,
                "source": r.get("source") or "agency-leads",
                "hiring_signal": bool(int(r.get("jobCount") or 0) > 0),
                "tags": ["scout", "hiring-signal"] if int(r.get("jobCount") or 0) > 0 else ["scout"],
            })
    return out


def load_jsonl_exports():
    people, companies = [], []
    for f in sorted((SCOUT / "exports").glob("*.jsonl")):
        for line in f.read_text(errors="ignore").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = (d.get("type") or "").lower()
            if t == "organization" or d.get("company"):
                companies.append({
                    "company": d.get("name") or d.get("company"),
                    "domain": domain_of(d.get("blog")) or domain_of(d.get("email")),
                    "website": d.get("blog"),
                    "location": d.get("location"),
                    "source": d.get("source") or "github",
                    "hiring_signal": True,
                    "geo_score": d.get("score"),
                    "notes": (d.get("bio") or "")[:400] or None,
                    "raw": d,
                    "tags": ["scout", "github"],
                })
            else:
                people.append({
                    "email": (d.get("email") or "").lower() or None,
                    "full_name": d.get("name") or d.get("full_name"),
                    "github_handle": d.get("handle"),
                    "company": d.get("company") or None,
                    "company_domain": domain_of(d.get("blog")) or domain_of(d.get("email")),
                    "location": d.get("location"),
                    "bio": (d.get("bio") or "")[:500] or None,
                    "followers": d.get("followers"),
                    "score": d.get("score"),
                    "source": d.get("source") or "github",
                    "query": d.get("query"),
                    "tags": ["scout", "github"],
                })
    return people, companies


def normalize(rows, columns):
    """PostgREST requires every object in a batch to have the SAME keys."""
    return [{c: r.get(c) for c in columns} for r in rows]


PEOPLE_COLS = ["email", "first_name", "last_name", "full_name", "title", "company",
               "company_domain", "linkedin_url", "github_handle", "location", "bio",
               "followers", "priority", "source", "query", "score", "tags"]
COMPANY_COLS = ["domain", "company", "website", "location", "job_count", "sample_roles",
                "source", "hiring_signal", "geo_score", "notes", "tags"]


def dedupe(rows, key):
    seen, out = set(), []
    for r in rows:
        v = (r.get(key) or "").lower() if isinstance(r.get(key), str) else r.get(key)
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    if args.stats:
        for t in ("scout_people", "scout_companies"):
            rows = rest(f"{t}?select=id&limit=5000")
            print(f"  {t}: {len(rows)} rows")
        for t in ("email_replies", "reply_knowledge", "reply_routing_rules"):
            rows = rest(f"{t}?select=id&limit=5000")
            print(f"  {t}: {len(rows)} rows")
        return

    people = load_connection_queue() + load_people_context()
    people += load_jsonl_exports()[0]
    companies = load_companies() + load_jsonl_exports()[1]

    # people: dedupe by email when present, else by linkedin/github
    p_by_email = dedupe([p for p in people if p.get("email")], "email")
    p_rest = dedupe([p for p in people if not p.get("email")],
                    "linkedin_url" if any(p.get("linkedin_url") for p in people) else "full_name")
    companies = dedupe(companies, "domain")  # conflict key is domain
    companies = [c for c in companies if c.get("company")]

    p_by_email = normalize(p_by_email, PEOPLE_COLS)
    p_rest = normalize(p_rest, PEOPLE_COLS)
    companies = normalize(companies, COMPANY_COLS)
    if any(r.get("raw") for r in companies):
        pass  # raw jsonb intentionally dropped for batch uniformity

    added = {"people": 0, "companies": 0}
    if p_by_email:
        rest("scout_people?on_conflict=email", "POST", p_by_email)
        added["people"] += len(p_by_email)
    for batch in [p_rest[i:i + 50] for i in range(0, len(p_rest), 50)]:
        if batch:
            rest("scout_people", "POST", batch, prefer="return=minimal")
            added["people"] += len(batch)
    if companies:
        rest("scout_companies?on_conflict=domain", "POST", companies)
        added["companies"] = len(companies)

    print(f"✅ synced {added['people']} people, {added['companies']} companies")
    print("   (re-run --stats to confirm)")


if __name__ == "__main__":
    main()
