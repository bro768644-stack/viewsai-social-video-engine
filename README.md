# Reply Capture + RAG Agent — RUNBOOK

Inbound replies → classified → RAG-drafted with Claude → Supabase + Chatwoot → routed.
Built 2026-09-12. Everything lives in `~/ViewsOSComplete/scripts/replies/`.

## The pipeline

```
inbound reply
   ↓  (Graph reader  |  ingest API  |  manual)
classify            claude-haiku-4-5      intent / sentiment / urgency
   ↓
RAG retrieve        pgvector over reply_knowledge (13 seeded docs, embedded)
   ↓
Scout enrich        scout_people + scout_companies (by email/domain)
   ↓
Claude draft        claude-sonnet-4-6, grounded ONLY in retrieved knowledge
   ↓
Supabase            email_replies (draft, intent, links, scout context)
Chatwoot            contact + conversation + PRIVATE NOTE with the draft + labels
Listmonk            subscribe + tag (replied, intent, urgency)
PostHog             reply_received event
   ↓
routing             reply_routing_rules → forward to brendan@ (for now)
```
**Nothing auto-sends.** Every draft is a private note for human approval.

## Components

| File | Role |
|---|---|
| `reply_agent.py` | the core: classify → retrieve → draft → store → Chatwoot → route → PostHog → Listmonk |
| `ingest_server.py` | HTTP capture point (launchd `com.viewsai.reply-ingest`, port 8899) |
| `graph_reader.py` | **Microsoft 365 reader** (app-only) + creates the forward-to-Brendan rules |
| `scout_sync.py` | Scout exports (CSV/JSONL) → `scout_people` / `scout_companies` |
| `listmonk_sync.py` | subscriber + tag sync (needs an API token) |
| `../supabase/supabase_replies_schema.sql` | `reply_knowledge`, `email_replies`, `reply_routing_rules` |
| `../supabase/supabase_scout_schema.sql` | `scout_people`, `scout_companies`, `reply_context` view |

## Commands

```bash
cd ~/ViewsOSComplete/scripts/replies

python3 reply_agent.py --seed-knowledge        # load the KB (13 docs)
python3 reply_agent.py --embed                 # embeddings for vector RAG
python3 reply_agent.py --from a@b.com --subject "Re: …" --body "…" --dry-run
python3 reply_agent.py --recent                # last 10 handled

python3 ingest_server.py                       # already running via launchd
curl -X POST localhost:8899/ingest/reply -H "X-Ingest-Token: $(cat ~/.viewsai-reply-ingest-token)" \
     -H 'Content-Type: application/json' -d '{"from":"x@y.com","subject":"Re:","body":"..."}'

python3 scout_sync.py            # Scout → Supabase
python3 scout_sync.py --stats

python3 graph_reader.py --check          # verify Graph creds/mailboxes
python3 graph_reader.py --read           # one pass
python3 graph_reader.py --watch          # poll forever
python3 graph_reader.py --forward-rules  # create "forward all → brendan@" rules

python3 listmonk_sync.py --setup-check
python3 listmonk_sync.py --tag email@x.com replied interested
```

## What still needs a human click

1. **Microsoft Graph app** (the capture path — currently nothing reads the mailboxes)
   ```bash
   bash ~/ViewsOSComplete/scripts/register-graph-mail-app.sh     # prints the exact steps
   ```
   Permissions (Application): `Mail.Read`, `Mail.ReadWrite`, `MailboxSettings.ReadWrite` + admin consent.
   Then in `~/.n8n/.env`:
   ```
   MS_TENANT_ID=...
   MS_CLIENT_ID=...
   MS_CLIENT_SECRET=...
   MS_MAILBOXES=b.obrien@tryviewsai.com,carrine@tryviewsai.com,brendan.obrien@getviewsai.com,…
   MS_READ_MAILBOXES=brendan@tryviewsai.com
   MS_FORWARD_TO=brendan@tryviewsai.com
   ```
   Then `python3 graph_reader.py --forward-rules` (sets forwarding on all 10 mailboxes)
   and `python3 graph_reader.py --watch` (or launchd it).

2. **Listmonk API token** — Listmonk UI (localhost:9000, admin / ViewsAI2026!) → Users → New
   → type **API** → Save → copy the token →
   `echo 'LISTMONK_API_TOKEN=<token>' >> ~/.n8n/.env`
   (Listmonk v6 does not accept the admin password over the API; it needs an API users token.)

3. **PostHog project key** — create a free project at posthog.com, then:
   - server-side: `echo 'POSTHOG_API_KEY=phc_…' >> ~/.n8n/.env` (already wired in reply_agent)
   - site-side: replace `PASTE_POSTHOG_PROJECT_KEY` in each site's `analytics.js` and redeploy

## Chatwoot notes

- API base is `http://localhost:3002` (Oracle tunnel), but Chatwoot forces HTTPS redirects, so the
  client sends `Host: chat.tryviewsai.com` + `X-Forwarded-Proto: https` to bypass it.
- Token: `5YKwA39D3RJRTDY4kDDFD7VN` (Account 1). Inbox **2 = ViewsAI API / Integrations**.
- Labels REPLACE the set → always send the full label array in one call.
- **The public URL `chat.tryviewsai.com` is currently down (Cloudflare 1033)** — the Cloudflare
  tunnel for Chatwoot needs re-pointing. Local API works.
