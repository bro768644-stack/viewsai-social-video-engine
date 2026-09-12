#!/usr/bin/env python3
"""
GRAPH MAIL READER — Microsoft 365 → reply agent.

Two jobs:
  1. READ  brendan@tryviewsai.com (and/or any mailbox) via Microsoft Graph app-only auth,
     find inbound replies, and feed each one to reply_agent.handle()
  2. RULES optionally create "forward everything to brendan@tryviewsai.com" rules on the
     sending mailboxes, so every reply lands in one place.

Auth (app-only / client credentials). Put these in ~/.n8n/.env:
    MS_TENANT_ID=...
    MS_CLIENT_ID=...
    MS_CLIENT_SECRET=...
    MS_MAILBOXES=b.obrien@tryviewsai.com,carrine@tryviewsai.com,...   (comma separated)
    MS_READ_MAILBOXES=brendan@tryviewsai.com                          (default: MS_MAILBOXES)
    MS_FORWARD_TO=brendan@tryviewsai.com

Register the app:  scripts/register-graph-mail-app.sh (prints the exact az/portal steps)
Grant (Application): Mail.Read, Mail.ReadWrite, MailboxSettings.ReadWrite  → admin consent

Usage:
    python3 graph_reader.py --check                 # token + mailbox reachability
    python3 graph_reader.py --read                  # one pass over the read mailboxes
    python3 graph_reader.py --watch --interval 300  # poll forever (launchd-friendly)
    python3 graph_reader.py --forward-rules         # create forward rules on MS_MAILBOXES
"""
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_FILES = [Path.home() / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")]
STATE = Path.home() / ".viewsai-graph-reader-state.json"


def env(k, d=None):
    if os.environ.get(k):
        return os.environ[k]
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return d


TENANT = env("MS_TENANT_ID") or env("TRYVIEWSAI_TENANT_ID")
CLIENT = env("MS_CLIENT_ID") or env("TRYVIEWSAI_CLIENT_ID")
SECRET = env("MS_CLIENT_SECRET") or env("TRYVIEWSAI_CLIENT_SECRET")
FORWARD_TO = env("MS_FORWARD_TO", "brendan@tryviewsai.com")
ALL_BOXES = [m.strip() for m in (env("MS_MAILBOXES", "") or "").split(",") if m.strip()]
READ_BOXES = [m.strip() for m in (env("MS_READ_MAILBOXES", FORWARD_TO) or "").split(",") if m.strip()]
OUR_DOMAINS = ("tryviewsai.com", "getviewsai.com")


def token():
    if not all([TENANT, CLIENT, SECRET]):
        raise RuntimeError("MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET not set")
    body = urllib.parse.urlencode({
        "client_id": CLIENT, "client_secret": SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())["access_token"]


def graph(path, tok, method="GET", data=None):
    req = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}",
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {path} :: {e.read().decode()[:250]}")


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"seen": []}


def save_state(st):
    st["seen"] = st.get("seen", [])[-2000:]
    STATE.write_text(json.dumps(st))


def is_reply(msg):
    """Inbound, not from us, looks like a human reply."""
    frm = ((msg.get("from") or {}).get("emailAddress") or {}).get("address", "") or ""
    if not frm:
        return False
    dom = frm.split("@")[-1].lower()
    if dom in OUR_DOMAINS:
        return False
    # skip obvious machine mail
    if re.search(r"(no-?reply|do-?not-?reply|postmaster|mailer-daemon|bounce)", frm, re.I):
        return False
    subj = (msg.get("subject") or "").lower()
    if re.search(r"(out of office|automatic reply|undeliverable|delivery status)", subj):
        return False
    return True


def body_text(msg):
    b = (msg.get("body") or {})
    t = b.get("content") or ""
    if (b.get("contentType") or "").lower() == "html":
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
        t = re.sub(r"<br\s*/?>|</p>", "\n", t, flags=re.I)
        t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;?", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()[:6000]


def read_once(limit=25, dry_run=False):
    import reply_agent as agent
    tok = token()
    st = load_state()
    seen = set(st.get("seen", []))
    total = 0
    for box in READ_BOXES:
        try:
            d = graph(f"/users/{box}/mailFolders/inbox/messages"
                      f"?$top={limit}&$orderby=receivedDateTime desc"
                      f"&$select=id,subject,from,receivedDateTime,bodyPreview,body,conversationId", tok)
        except Exception as e:
            print(f"  {box}: {str(e)[:140]}")
            continue
        for m in d.get("value", []):
            mid = m.get("id")
            if not mid or mid in seen:
                continue
            if not is_reply(m):
                seen.add(mid)
                continue
            frm = m["from"]["emailAddress"]["address"]
            subj = m.get("subject") or ""
            body = body_text(m)
            print(f"  [{box}] {frm} — {subj[:60]}")
            if not dry_run:
                try:
                    agent.handle(frm, subj, body, to_mailbox=box, source="graph")
                    total += 1
                except Exception as e:
                    print("    agent:", str(e)[:120])
            seen.add(mid)
    st["seen"] = list(seen)
    save_state(st)
    print(f"processed {total} reply(ies); {len(seen)} messages tracked")
    return total


def forward_rules():
    """Create a rule on each sending mailbox: forward everything to FORWARD_TO."""
    tok = token()
    if not ALL_BOXES:
        raise SystemExit("MS_MAILBOXES not set")
    for box in ALL_BOXES:
        rule = {
            "displayName": "ViewsAI: forward all to Brendan",
            "sequence": 1,
            "isEnabled": True,
            "conditions": {"senderContains": []},
            "actions": {
                "forwardTo": [{"emailAddress": {"address": FORWARD_TO}}],
                "stopProcessingRules": False,
                "moveToFolder": "inbox",
            },
        }
        try:
            graph(f"/users/{box}/mailFolders/inbox/messageRules", tok, "POST", rule)
            print(f"  ✓ rule created on {box} → {FORWARD_TO}")
        except Exception as e:
            print(f"  ✗ {box}: {str(e)[:160]}")


def check():
    print(f"  tenant={TENANT or 'MISSING'} client={CLIENT or 'MISSING'} secret={'set' if SECRET else 'MISSING'}")
    print(f"  read mailboxes: {READ_BOXES}")
    print(f"  forward target: {FORWARD_TO}")
    try:
        tok = token()
        print("  ✓ token acquired")
        for box in (READ_BOXES or ALL_BOXES)[:5]:
            try:
                d = graph(f"/users/{box}/mailFolders/inbox?$select=displayName,totalItemCount,unreadItemCount", tok)
                print(f"  ✓ {box}: {d.get('totalItemCount')} items, {d.get('unreadItemCount')} unread")
            except Exception as e:
                print(f"  ✗ {box}: {str(e)[:130]}")
    except Exception as e:
        print("  ✗", str(e)[:200])
        print("\n  → Register the app: bash scripts/register-graph-mail-app.sh")
        print("    Permissions (Application): Mail.Read, Mail.ReadWrite, MailboxSettings.ReadWrite")
        print("    Then add MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET to ~/.n8n/.env")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--forward-rules", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not any([args.check, args.read, args.watch, args.forward_rules]):
        args.check = True
    if args.check:
        return check()
    if args.forward_rules:
        return forward_rules()
    if args.read:
        return read_once(dry_run=args.dry_run)
    if args.watch:
        print(f"[graph-reader] polling every {args.interval}s")
        while True:
            try:
                read_once()
            except Exception as e:
                print("pass failed:", str(e)[:160])
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
