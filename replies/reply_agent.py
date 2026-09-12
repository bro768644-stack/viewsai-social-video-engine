#!/usr/bin/env python3
"""
REPLY AGENT — inbound reply → classify → RAG retrieve → Claude draft → Chatwoot + Supabase.

Pipeline (per reply):
  1. classify intent / sentiment / urgency            (Claude Haiku, cheap+fast)
  2. retrieve relevant knowledge                      (pgvector if embeddings exist, else lexical)
  3. draft the reply, grounded ONLY in retrieved docs (Claude Sonnet)
  4. store in Supabase .email_replies
  5. create/update the Chatwoot conversation + private note with the draft
  6. apply routing rules (forward to brendan@ for now, labels, assignment)
  7. emit a PostHog event

Usage:
    python3 reply_agent.py --from a@b.com --subject "Re: ..." --body "..." [--dry-run]
    python3 reply_agent.py --file reply.eml
    python3 reply_agent.py --seed-knowledge          # load the built-in KB
    python3 reply_agent.py --embed                   # backfill embeddings for the KB
    python3 reply_agent.py --recent                  # show the last 10 replies handled
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- config
HOME = Path.home()
ENV_FILES = [HOME / ".n8n" / ".env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")]

CHATWOOT_URL = "https://chat.tryviewsai.com"   # public (tunnel restored 2026-09-12)
CHATWOOT_HOST_HEADER = "chat.tryviewsai.com"
CHATWOOT_ACCOUNT = 1
CHATWOOT_INBOX = 2                            # "ViewsAI API / Integrations"
FORWARD_TO = "brendan@tryviewsai.com"
POSTHOG_HOST = "https://us.i.posthog.com"


def env(key, default=None):
    v = os.environ.get(key)
    if v:
        return v
    for f in ENV_FILES:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default


SB_URL = (env("SUPABASE_URL") or "").rstrip("/")
SB_KEY = env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_ANON_KEY")
ANTHROPIC = env("ANTHROPIC_API_KEY")
OPENAI = env("OPENAI_API_KEY")
CHATWOOT_TOKEN = env("CHATWOOT_TOKEN") or "5YKwA39D3RJRTDY4kDDFD7VN"
POSTHOG_KEY = env("POSTHOG_API_KEY") or env("POSTHOG_KEY")

MODEL_FAST = "claude-haiku-4-5-20251001"   # fast + cheap classification
MODEL_DRAFT = "claude-sonnet-4-6"            # drafting quality


# ---------------------------------------------------------------- http helpers
def _req(url, method="GET", headers=None, data=None, timeout=60):
    h = dict(headers or {})
    # Cloudflare (1010) blocks default python UAs on the public tunnels
    h.setdefault("User-Agent", "ViewsAI-ReplyAgent/1.0 (+https://obrienhq.com)")
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        raise RuntimeError(f"HTTP {e.code} {url.split('?')[0]} :: {detail}")


def sb(path, method="GET", data=None):
    return _req(f"{SB_URL}/rest/v1/{path}", method,
                {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}",
                 "Prefer": "return=representation"}, data)


def chatwoot(path, method="GET", data=None):
    # Host + X-Forwarded-Proto bypass Chatwoot's force-SSL redirect on localhost
    return _req(f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT}{path}", method,
                {"api_access_token": CHATWOOT_TOKEN}, data)


def claude(prompt, system, model, max_tokens=700):
    if not ANTHROPIC:
        raise SystemExit("ANTHROPIC_API_KEY missing")
    out = _req("https://api.anthropic.com/v1/messages", "POST",
               {"x-api-key": ANTHROPIC, "anthropic-version": "2023-06-01"}, {
                   "model": model, "max_tokens": max_tokens, "system": system,
                   "messages": [{"role": "user", "content": prompt}]}, timeout=120)
    return "".join(b.get("text", "") for b in out.get("content", []))


def embed(text):
    """OpenAI embeddings (1536) — optional; falls back to lexical retrieval."""
    if not OPENAI:
        return None
    try:
        out = _req("https://api.openai.com/v1/embeddings", "POST",
                   {"Authorization": f"Bearer {OPENAI}"},
                   {"model": "text-embedding-3-small", "input": text[:8000]}, timeout=60)
        return out["data"][0]["embedding"]
    except Exception:
        return None


# ---------------------------------------------------------------- knowledge
KB = [
    ("social-stack-offer", "Social Media Stack Creator — $197 one-time",
     "offer", "The Full Social Media Stack Creator is $197 one-time, no subscription. "
     "It replaces CapCut, Higgsfield, Seedance, ElevenLabs, Opus Clip, Buffer and Canva "
     "(about $1,692/year in list-price subscriptions). You get: a local Studio app "
     "(drag a video in, pick platforms, add text, click Create), a 12-platform renderer "
     "(TikTok, Reels, Shorts, IG Feed/Stories, FB Reel/Page/Profile, LinkedIn, X, Threads, Telegram), "
     "68 free voices with audio-swap (take footage you already have and replace the audio with a new line), "
     "a character/persona pipeline, a batch content engine (a list of hooks becomes finished posts), "
     "and publishing plus comment-keyword routing. Includes a live done-with-you install and updates. "
     "Runs on the customer's own computer; the files never leave their machine.",
     ["social-stack", "pricing", "offer", "197"], 95),

    ("postiz-offer", "Postiz Setup — $97 one-time",
     "offer", "The Postiz Setup is $97 one-time. We install the open-source Postiz scheduler on the "
     "customer's own server, connect every social account (X, Instagram, Facebook Pages, LinkedIn, YouTube, "
     "TikTok, Threads, Pinterest, Bluesky, Telegram, Mastodon) via official OAuth, brand it, load their "
     "content calendar and prove it posts with a real test post. Delivered in 48 hours with 30 days support. "
     "It replaces Hootsuite ($99/mo), Sprout Social ($249/mo), Later ($25/mo) or Buffer ($18/mo). "
     "There is no subscription afterward — they own the install. Bundle with the $197 Social Media Stack "
     "Creator for $249 (saves $45).",
     ["postiz", "pricing", "offer", "97", "scheduler"], 95),

    ("pi-offers", "Pi offers — free / $7 / $97",
     "offer", "Pi is the AI worker with hands on your computer. Free tier: the Pi harness plus free models "
     "via a setup script (free-pi-setup.sh). $7: Pi Slack On-The-Go so you can run Pi from your phone. "
     "$97: Full Plug & Play Setup with pre-built agents, Chrome hands (Playwright) and desktop hands "
     "(computer use), all installed live. Pi's difference vs other assistants: no permission pop-ups.",
     ["pi", "pricing", "offer", "free", "97"], 85),

    ("outbound-stack-offer", "Free Outbound Stack",
     "offer", "The Free Outbound Stack is our free lead magnet: the social posting stack, free lead "
     "sourcing, and a real two-layer email verifier. We also document the exact paid-tool setups "
     "(Clay, Instantly, Apollo, WhatsApp) priced by how hard they actually are.",
     ["outbound", "offer", "free", "leads"], 80),

    ("services-recruiting", "ViewsAI recruiting services",
     "recruiting", "ViewsAI is a recruiting intelligence company. We (1) fill the role, (2) preserve the "
     "departing person's knowledge, and (3) equip the new hire with AI. We run AI recruiting agents that "
     "source, screen and book interviews, with passive-candidate sourcing rather than job-board applicants. "
     "We also offer done-for-you recruiting where we deliver a shortlist of qualified passive candidates "
     "for a specific role in a specific market.",
     ["recruiting", "services", "sourcing", "candidates"], 90),

    ("services-gtm", "ViewsAI GTM / outbound services",
     "gtm", "We build and run outbound systems: verified lists, warm-up rotation across real Microsoft "
     "mailboxes, personalized humanized copy, daily sending, reply handling and routing. We also deploy "
     "the full social automation stack (scheduling, comment-to-DM funnels, unified inbox).",
     ["gtm", "outbound", "services", "email"], 85),

    ("objection-too-expensive", "Objection: too expensive / can't afford it",
     "objection", "Reframe against what they already pay: the $197 stack replaces roughly $1,692/year of "
     "creator subscriptions (Higgsfield, CapCut, Seedance, ElevenLabs, Opus Clip, Buffer, Canva), so it "
     "pays for itself in about seven weeks. The $97 Postiz setup is cheaper than five months of Buffer. "
     "There is no subscription afterward. If cash flow is the blocker, offer to start with the free "
     "outbound stack and revisit.",
     ["objection", "price", "expensive", "afford"], 90),

    ("objection-no-time", "Objection: I don't have time to learn this",
     "objection", "We do the install with them on a live call, and the Studio is a drag-drop, pick "
     "platforms, type text, click Create app. Setup is done-with-you, not a course. Most people are "
     "posting the same day.",
     ["objection", "time", "learn", "busy"], 85),

    ("objection-do-i-need-ai", "Objection: do I need to be technical / does it need AI skills?",
     "objection", "No coding needed. The heavy lifting runs on free tools we configure. They use buttons "
     "and text fields.",
     ["objection", "technical", "code", "skills"], 80),

    ("proof-results", "Proof: what we run ourselves",
     "proof", "We run this stack on ourselves: 10 Microsoft mailboxes sending daily with warm-up rotation "
     "and verification, 127+ outbound emails sent through the queue, a 12-platform renderer, a 36-clip "
     "character library, and 45+ content hooks batched into finished vertical posts. The offers are the "
     "productized version of our own operations, not a course.",
     ["proof", "results", "case", "ourselves"], 85),

    ("process-next-steps", "Process: what happens after they say yes",
     "process", "1) We send the checkout link for the chosen offer ($97 Postiz, $197 Social Stack, or "
     "$249 bundle). 2) On payment we schedule the kickoff within 48 hours. 3) We collect access "
     "(accounts, server or machine) and do the install live. 4) Handover walkthrough, recorded. "
     "5) 30 days of support on setups. Refunds: 14-day money-back on the digital-delivery products.",
     ["process", "next steps", "onboarding", "how it works"], 80),

    ("pricing-refunds", "Refunds and guarantees",
     "pricing", "14-day money-back on the digital-delivery products ($7 Slack, $97 Postiz, $197 Social "
     "Stack) — a real refund, no interrogation. After 48 hours of delivered setup work on managed "
     "services, no refund. All billing questions go to brendan@tryviewsai.com.",
     ["refund", "guarantee", "billing", "policy"], 75),

    ("who-is-brendan", "Who is behind this",
     "personal", "Brendan O'Brien runs ViewsAI / O'Brien HQ. He builds recruiting and GTM systems with AI "
     "and documents the whole stack publicly. Happy to jump on a short call.",
     ["about", "who", "brendan", "viewsai"], 70),
]


def seed_knowledge():
    rows = []
    for slug, title, cat, content, tags, prio in KB:
        rows.append({"slug": slug, "title": title, "category": cat, "content": content,
                     "tags": tags, "priority": prio, "source": "reply_agent.py#KB"})
    # upsert by slug
    for r in rows:
        try:
            sb(f"reply_knowledge?slug=eq.{r['slug']}", "DELETE")
        except Exception:
            pass
    return sb("reply_knowledge", "POST", rows)


def backfill_embeddings():
    rows = sb("reply_knowledge?select=id,title,content&limit=500")
    n = 0
    for r in rows:
        e = embed(f"{r['title']}. {r['content']}")
        if not e:
            print("embeddings unavailable (no OPENAI_API_KEY or call failed)")
            return n
        sb(f"reply_knowledge?id=eq.{r['id']}", "PATCH", {"embedding": e})
        n += 1
    return n


# ---------------------------------------------------------------- retrieval
def retrieve(query, k=5):
    """Vector search when embeddings exist, else lexical/tag scoring."""
    q_emb = embed(query)
    if q_emb:
        try:
            # pgvector cosine distance via RPC-free ordering (Supabase supports <=> in select)
            rows = _req(f"{SB_URL}/rest/v1/rpc/match_reply_knowledge", "POST",
                        {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"},
                        {"query_embedding": q_emb, "match_count": k})
            if rows:
                return rows
        except Exception:
            pass
    # lexical fallback
    words = set(re.findall(r"[a-z]{3,}", query.lower()))
    rows = sb("reply_knowledge?select=id,slug,title,category,content,tags,priority&limit=500")
    scored = []
    for r in rows:
        blob = (r["title"] + " " + r["content"] + " " + " ".join(r.get("tags") or [])).lower()
        hits = sum(1 for w in words if w in blob)
        score = hits + (r.get("priority") or 0) / 100.0
        if hits:
            scored.append((score, r))
    scored.sort(key=lambda t: -t[0])
    return [r for _, r in scored[:k]]


# ---------------------------------------------------------------- scout context
def scout_lookup(email_addr):
    """Find the sender in Scout data (person by email/domain, else company by domain)."""
    dom = None
    m = re.search(r"@([a-z0-9.-]+\.[a-z]{2,})", (email_addr or "").lower())
    if m:
        dom = m.group(1)
    person = company = None
    try:
        if dom:
            rows = sb(f"scout_people?select=*&or=(email.ilike.*{dom},company_domain.eq.{dom})&limit=1")
            person = rows[0] if rows else None
        if not person:
            rows = sb(f"scout_people?select=*&email=ilike.{email_addr}&limit=1")
            person = rows[0] if rows else None
        if dom:
            rows = sb(f"scout_companies?select=*&domain=eq.{dom}&limit=1")
            company = rows[0] if rows else None
        if not company and person and person.get("company"):
            rows = sb(f"scout_companies?select=*&company=ilike.{person['company']}&limit=1")
            company = rows[0] if rows else None
    except Exception as e:
        print("  scout lookup:", str(e)[:80])
    return person, company


def scout_context_text(person, company):
    bits = []
    if person:
        who = ", ".join(x for x in [person.get("full_name"), person.get("title"),
                                    person.get("company")] if x)
        if who:
            bits.append(f"Scout profile: {who}.")
        if person.get("bio"):
            bits.append(f"Bio: {person['bio'][:200]}")
        if person.get("location"):
            bits.append(f"Location: {person['location']}.")
        if person.get("followers"):
            bits.append(f"Followers: {person['followers']}.")
    if company:
        bits.append(f"Company: {company.get('company')}"
                    + (f" ({company.get('job_count')} open roles)" if company.get("job_count") else "")
                    + ("." if not company.get("sample_roles") else f". Roles: {company['sample_roles'][:200]}"))
        if company.get("hiring_signal"):
            bits.append("They are actively hiring (job-board signal).")
    return " ".join(bits) or ""


# ---------------------------------------------------------------- classify + draft
CLASSIFY_SYS = (
    "You classify inbound email replies to cold outbound. Return ONLY compact JSON with keys: "
    "intent (interested|question|objection|not_interested|unsubscribe|ooo|referral|wrong_person), "
    "sentiment (positive|neutral|negative), urgency (hot|warm|nurture|parked), "
    "summary (one sentence), needs_human (true|false). No prose, JSON only."
)

DRAFT_SYS = (
    "You write replies for Brendan O'Brien (ViewsAI / O'Brien HQ). Rules: "
    "be warm, direct and specific; short paragraphs; never use em dashes or en dashes; "
    "use contractions; no corporate filler; never invent facts, prices or promises. "
    "Ground every claim ONLY in the KNOWLEDGE provided. If the answer is not in the knowledge, "
    "say you'll get the exact detail and ask one clarifying question instead of guessing. "
    "End with a single clear next step (a question or a proposed time). Sign as Brendan. "
    "Do not include a subject line."
)


def classify(subject, body):
    txt = claude(f"SUBJECT: {subject}\n\nBODY:\n{body[:3000]}", CLASSIFY_SYS, MODEL_FAST, 300)
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


def draft(subject, body, docs, scout_ctx=""):
    kb = "\n\n".join(f"### {d['title']}\n{d['content']}" for d in docs) or "(no knowledge matched)"
    prompt = (f"INBOUND REPLY\nSUBJECT: {subject}\nBODY:\n{body[:3000]}\n\n"
              + (f"SCOUT CONTEXT (who they are; use to personalize, do not quote verbatim)\n{scout_ctx}\n\n"
                 if scout_ctx else "")
              + f"KNOWLEDGE (use only this)\n{kb}\n\nWrite the reply now.")
    return claude(prompt, DRAFT_SYS, MODEL_DRAFT, 800)


# ---------------------------------------------------------------- chatwoot + posthog
def chatwoot_upsert(email_addr, name, subject, body, draft_text, intent, labels):
    """Find/create contact → conversation → private note with the draft."""
    out = {"contact_id": None, "conversation_id": None}
    try:
        found = chatwoot(f"/contacts/search?q={email_addr}")
        contacts = found.get("payload") or []
        if contacts:
            out["contact_id"] = contacts[0]["id"]
        else:
            c = chatwoot("/contacts", "POST", {"name": name or email_addr,
                                               "email": email_addr, "inbox_id": CHATWOOT_INBOX})
            out["contact_id"] = (c.get("payload") or {}).get("contact", {}).get("id") or c.get("id")
    except Exception as e:
        print("  chatwoot contact:", str(e)[:100])
        return out
    try:
        conv = chatwoot("/conversations", "POST", {
            "source_id": None, "inbox_id": CHATWOOT_INBOX,
            "contact_id": out["contact_id"],
            "additional_attributes": {},
            "status": "open",
            "message": {"content": f"INBOUND ({intent or 'unclassified'}) — {subject}\n\n{body[:1500]}"},
        })
        out["conversation_id"] = conv.get("id")
        if out["conversation_id"]:
            if draft_text:
                chatwoot(f"/conversations/{out['conversation_id']}/messages", "POST",
                         {"content": f"DRAFTED REPLY (review before sending)\n\n{draft_text}",
                          "message_type": "outgoing", "private": True})
            # labels REPLACE the set in Chatwoot -> send them all in one call
            if labels:
                try:
                    chatwoot(f"/conversations/{out['conversation_id']}/labels", "POST",
                             {"labels": labels})
                except Exception:
                    pass
    except Exception as e:
        print("  chatwoot conversation:", str(e)[:110])
    return out


def posthog(event, props):
    if not POSTHOG_KEY:
        return False
    try:
        _req(f"{POSTHOG_HOST}/capture/", "POST", None,
             {"api_key": POSTHOG_KEY, "event": event,
              "properties": {"distinct_id": "viewsai-system", **props}}, timeout=20)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- routing
def route(intent, urgency, labels):
    """Apply reply_routing_rules in priority order. Returns (action, value)."""
    try:
        rules = sb("reply_routing_rules?select=*&enabled=eq.true&order=priority.asc&limit=50")
    except Exception:
        rules = []
    for r in rules:
        if r.get("match_intent") and r["match_intent"] != intent:
            continue
        if r.get("match_tags") and not set(r["match_tags"]) & set(labels):
            continue
        if r.get("match_from") and r["match_from"] not in "":
            continue
        return r["action"], r.get("action_value")
    return "forward", FORWARD_TO


# ---------------------------------------------------------------- main
def handle(from_email, subject, body, to_mailbox=None, dry_run=False, source="manual"):
    print(f"→ reply from {from_email}: {subject[:60]}")
    c = classify(subject, body)
    intent = c.get("intent", "question")
    print(f"  intent={intent} sentiment={c.get('sentiment')} urgency={c.get('urgency')}")

    person, company = scout_lookup(from_email)
    scout_ctx = scout_context_text(person, company)
    if scout_ctx:
        print(f"  scout: {scout_ctx[:90]}…")

    docs = retrieve(f"{subject}\n{body}", k=5)
    print(f"  knowledge retrieved: {[d['title'][:34] for d in docs]}")

    draft_text = draft(subject, body, docs, scout_ctx)
    labels = [intent] + ([c.get("urgency")] if c.get("urgency") else [])
    action, value = route(intent, c.get("urgency"), labels)
    print(f"  route: {action} → {value}")

    row = {
        "from_email": from_email, "subject": subject, "body": body,
        "to_mailbox": to_mailbox, "intent": intent, "sentiment": c.get("sentiment"),
        "urgency": c.get("urgency"), "status": "drafted",
        "routed_to": value if action == "forward" else action,
        "draft_reply": draft_text, "draft_model": MODEL_DRAFT,
        "retrieved_ids": [d["id"] for d in docs if d.get("id")],
        "source": source, "tags": labels,
        "scout_person_id": (person or {}).get("id"),
        "scout_company_id": (company or {}).get("id"),
        "scout_context": scout_ctx or None,
        "raw": {"classify": c, "action": action, "action_value": value},
    }
    cw = chatwoot_upsert(from_email, None, subject, body, draft_text, intent, labels)
    row["chatwoot_conversation_id"] = cw.get("conversation_id")
    row["chatwoot_contact_id"] = cw.get("contact_id")

    if dry_run:
        print("\n--- DRAFT ---\n" + draft_text[:900] + "\n-------------")
        return row

    try:
        saved = sb("email_replies", "POST", [row])
        print(f"  saved to supabase: {saved[0]['id'] if saved else '?'}")
    except Exception as e:
        print("  supabase save failed:", str(e)[:140])

    posthog("reply_received", {"from": from_email, "intent": intent,
                               "urgency": c.get("urgency"), "action": action})

    # behavioral graph: a reply is the strongest intent signal (weight 10)
    try:
        sb("contact_events", "POST", [{
            "email": from_email, "event": "REPLY", "source": "email",
            "campaign": None, "asset": "reply",
            "signal_weight": 10,
            "metadata": {"intent": intent, "urgency": c.get("urgency"),
                         "subject": (subject or "")[:200]},
        }])
        print("  behavior: REPLY event recorded (weight 10)")
    except Exception as e:
        print("  behavior:", str(e)[:80])

    # newsletter tag: a replier is a real human -> tag them in Listmonk
    try:
        import listmonk_sync
        if listmonk_sync.TOKEN:
            listmonk_sync.upsert(from_email, tags=["replied", intent]
                                 + ([c.get("urgency")] if c.get("urgency") else []),
                                 attribs={"last_intent": intent, "last_subject": (subject or "")[:120]})
            print("  listmonk: tagged replier")
    except Exception as e:
        print("  listmonk:", str(e)[:80])
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_email")
    ap.add_argument("--subject", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--file")
    ap.add_argument("--to-mailbox")
    ap.add_argument("--seed-knowledge", action="store_true")
    ap.add_argument("--embed", action="store_true")
    ap.add_argument("--recent", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.seed_knowledge:
        rows = seed_knowledge()
        print(f"✅ seeded {len(rows)} knowledge entries")
        return
    if args.embed:
        n = backfill_embeddings()
        print(f"✅ embedded {n} entries")
        return
    if args.recent:
        rows = sb("email_replies?select=from_email,subject,intent,urgency,status,routed_to,received_at&order=received_at.desc&limit=10")
        for r in rows:
            print(f"  {r['received_at'][:16]} | {r['from_email'][:26]:28s} | {r['intent'] or '?':12s} "
                  f"| {r['urgency'] or '?':8s} | {r['status']:8s} | {(r['subject'] or '')[:36]}")
        return

    if args.file:
        raw = Path(args.file).read_text(errors="ignore")
        frm = re.search(r"^From:\s*(.+)$", raw, re.M)
        sub = re.search(r"^Subject:\s*(.+)$", raw, re.M)
        parts = re.split(r"\n\s*\n", raw, maxsplit=1)
        handle((frm.group(1) if frm else "unknown").strip(),
               (sub.group(1) if sub else "").strip(),
               (parts[1] if len(parts) > 1 else raw)[:6000],
               source="file")
        return

    if not args.from_email:
        ap.error("--from (or --file) required")
    handle(args.from_email, args.subject, args.body, args.to_mailbox, args.dry_run)


if __name__ == "__main__":
    main()
