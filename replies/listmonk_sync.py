#!/usr/bin/env python3
"""
LISTMONK SYNC — subscriber tags from reply behaviour.

When someone replies, they're a real human worth tagging in the newsletter list:
    replied, interested/objection/question, <pillar>, offer-<x>

Usage:
    python3 listmonk_sync.py --setup-check
    python3 listmonk_sync.py --tag email@example.com replied interested recruiting
    python3 listmonk_sync.py --backfill        # tag everyone in email_replies

Config (env or ~/.n8n/.env):
    LISTMONK_URL        default http://localhost:9000
    LISTMONK_API_USER   default admin
    LISTMONK_API_TOKEN  (create: Listmonk → Users → New → type "API" → copy token)
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILES = [Path.home() / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")]


def env(k, d=None):
    if os.environ.get(k):
        return os.environ[k]
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return d


BASE = (env("LISTMONK_URL", "http://localhost:9000")).rstrip("/")
USER = env("LISTMONK_API_USER", "viewsai-api")
TOKEN = env("LISTMONK_API_TOKEN")
LIST_ID = int(env("LISTMONK_LIST_ID", "1"))   # 3 = ViewsAI Newsletter (v6: no subscriber tags)


def _call(path, method="GET", data=None, form=False):
    if not TOKEN:
        raise RuntimeError("LISTMONK_API_TOKEN not set (create one in Listmonk → Users → New → API)")
    body = None
    headers = {"Authorization": f"token {USER}:{TOKEN}"}
    if data is not None:
        if form:
            body = "".join(f"{k}={v}&" for k, v in data.items()).rstrip("&").encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}/api{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {path} :: {e.read().decode()[:250]}")


def subscriber_by_email(email):
    """Listmonk v6: the SQL-ish `query` param 400s on /subscribers; `search` works."""
    import urllib.parse
    try:
        d = _call("/subscribers?page=1&per_page=20&search=" + urllib.parse.quote(email))
        results = (d.get("data") or {}).get("results") or []
        for r in results:
            if (r.get("email") or "").lower() == email.lower():
                return r
        return results[0] if results else None
    except Exception as e:
        print("  lookup:", str(e)[:120])
        return None


def upsert(email, name=None, tags=None, attribs=None):
    """Listmonk v6 has NO subscriber tags — everything goes in `attribs`.

    `tags` are stored as attribs['tags'] (array) so segment queries still work:
        subscriber.attribs->'tags' ? 'replied'
    """
    tags = list(dict.fromkeys(t for t in (tags or []) if t))
    sub = subscriber_by_email(email)
    existing = (sub or {}).get("attribs") or {}
    merged_tags = list(dict.fromkeys((existing.get("tags") or []) + tags))
    new_attribs = {**existing, **(attribs or {}), "tags": merged_tags}
    if sub:
        _call(f"/subscribers/{sub['id']}", "PUT", {
            "email": email, "name": sub.get("name") or name or email,
            "status": sub.get("status", "enabled"),
            "lists": [LIST_ID], "attribs": new_attribs,
        })
        return "updated", sub["id"], merged_tags
    d = _call("/subscribers", "POST", {
        "email": email, "name": name or email, "status": "enabled",
        "lists": [LIST_ID], "attribs": new_attribs, "preconfirm_subscriptions": True,
    })
    return "created", (d.get("data") or {}).get("id"), merged_tags


def setup_check():
    print(f"  LISTMONK_URL   = {BASE}")
    print(f"  LISTMONK_API_USER = {USER}")
    print(f"  LISTMONK_API_TOKEN = {'set (' + TOKEN[:8] + '…)' if TOKEN else 'MISSING'}")
    try:
        d = _call("/lists")
        lists = (d.get("data") or {}).get("results") or []
        print(f"  ✓ API reachable — {len(lists)} list(s): "
              + ", ".join(f"{l['id']}:{l['name']}" for l in lists[:5]))
    except Exception as e:
        print("  ✗ API:", str(e)[:200])
        print("  → create a token: Listmonk UI → Users → New → type 'API' → Save → copy token")
        print("    then: echo 'LISTMONK_API_TOKEN=<token>' >> ~/.n8n/.env")


def backfill():
    import reply_agent as agent
    rows = agent.sb("email_replies?select=from_email,intent,urgency,tags&limit=500")
    n = 0
    for r in rows:
        try:
            upsert(r["from_email"], tags=["replied", r.get("intent") or "unknown"] +
                   ([r["urgency"]] if r.get("urgency") else []))
            n += 1
        except Exception as e:
            print("  ", r["from_email"], str(e)[:60])
    print(f"tagged {n} repliers")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup-check", action="store_true")
    ap.add_argument("--tag", nargs="+", help="email tag1 tag2 …")
    ap.add_argument("--backfill", action="store_true")
    args = ap.parse_args()

    if not any([args.setup_check, args.tag, args.backfill]):
        args.setup_check = True

    if args.setup_check:
        setup_check()
        return
    if args.backfill:
        backfill()
        return
    email, *tags = args.tag
    action, sid, final = upsert(email, tags=tags)
    print(f"✅ {action} subscriber {sid} tags={final}")


if __name__ == "__main__":
    main()
