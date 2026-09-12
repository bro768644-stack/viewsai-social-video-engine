#!/usr/bin/env python3
"""
Build + deploy the BEHAVIOR GRAPH workflow to n8n:
  1. hourly  → Supabase RPC refresh_contact_scores()
  2. daily   → reply digest (new replies + hottest contacts) → Slack DM

Deploy: python3 build_behavior_graph.py --deploy [--id=<existing>]
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SLACK_CHANNEL = "D0BKSG1QU2Y"   # Brendan's DM with the pihomebase bot


def load_env(*files):
    env = {}
    for f in files:
        p = Path(f).expanduser()
        if not p.exists():
            continue
        for raw in p.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http_node(name, nid, method, url, headers, body=None, position=(0, 0)):
    params = {
        "method": method,
        "url": url,
        "authentication": "none",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": k, "value": v} for k, v in headers.items()]},
        "options": {},
    }
    if body is not None:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = body
    return {"parameters": params, "id": nid, "name": name,
            "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": list(position)}


def build(env):
    sb = env["SUPABASE_URL"].rstrip("/")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env["SUPABASE_ANON_KEY"]
    slack = env["SLACK_BOT_TOKEN"]
    sbh = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    nodes = [
        # ---------------- hourly score refresh
        {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 * * * *"}]}},
         "id": "sched-hourly", "name": "Every hour",
         "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [-560, -120]},
        http_node("Refresh contact scores", "rpc-refresh", "POST",
                  f"{sb}/rest/v1/rpc/refresh_contact_scores", sbh,
                  body="={}", position=(-320, -120)),

        # ---------------- daily digest
        {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 14 * * *"}]}},
         "id": "sched-daily", "name": "Daily 7am PT (14:00 UTC)",
         "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [-560, 160]},
        http_node("New replies (24h)", "get-replies", "GET",
                  "=" + f"{sb}/rest/v1/email_replies?select=from_email,subject,intent,urgency,status,"
                  f"routed_to,draft_reply,received_at&received_at=gte."
                  f"{{{{ new Date(Date.now()-86400000).toISOString() }}}}&order=received_at.desc&limit=25",
                  sbh, position=(-320, 160)),
        http_node("Hottest contacts", "get-hot", "GET",
                  f"{sb}/rest/v1/contact_scores?select=email,company,score,tier,opens,clicks,replies,"
                  f"last_event,last_event_at&order=score.desc&limit=6",
                  sbh, position=(-100, 160)),
        {"parameters": {"jsCode": """const replies = $('New replies (24h)').all().flatMap(i => Array.isArray(i.json) ? i.json : [i.json]);
const hot = $('Hottest contacts').all().flatMap(i => Array.isArray(i.json) ? i.json : [i.json]);

const emoji = { interested: '🔥', question: '❓', objection: '⚠️', not_interested: '🚫',
                unsubscribe: '🔕', ooo: '🌴', referral: '🔁', wrong_person: '👤' };
const tierEmoji = { hot: '🔴', warm: '🟠', nurture: '🟡', cold: '⚪' };

const lines = [];
lines.push(`*Reply digest — ${new Date().toISOString().slice(0,10)}*`);
lines.push('');

if (!replies.length) {
  lines.push('_No new replies in the last 24h._');
} else {
  lines.push(`*${replies.length} new repl${replies.length === 1 ? 'y' : 'ies'}*`);
  for (const r of replies.slice(0, 12)) {
    lines.push(`${emoji[r.intent] || '•'} *${r.intent || 'unclassified'}*${r.urgency ? ' / ' + r.urgency : ''} — ${r.from_email}`);
    if (r.subject) lines.push(`     _${String(r.subject).slice(0, 70)}_`);
  }
}
lines.push('');
if (hot.length) {
  lines.push('*Hottest contacts*');
  for (const c of hot) {
    lines.push(`${tierEmoji[c.tier] || '•'} ${c.email}${c.company ? ' · ' + c.company : ''} — score ${c.score} ` +
               `(opens ${c.opens||0}, clicks ${c.clicks||0}, replies ${c.replies||0})`);
  }
}
lines.push('');
lines.push('_Drafts are in Chatwoot as private notes — nothing sends without you._');

return [{ json: { text: lines.join('\\n'), count: replies.length } }];"""},
         "id": "digest", "name": "Build digest",
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [140, 160]},
        http_node("Post to Slack", "slack-post", "POST",
                  "https://slack.com/api/chat.postMessage",
                  {"Authorization": f"Bearer {slack}", "Content-Type": "application/json"},
                  body="={{ JSON.stringify({ channel: '" + SLACK_CHANNEL + "', text: $json.text, "
                       "unfurl_links: false, mrkdwn: true }) }}",
                  position=(380, 160)),
    ]

    connections = {
        "Every hour": {"main": [[{"node": "Refresh contact scores", "type": "main", "index": 0}]]},
        "Daily 7am PT (14:00 UTC)": {"main": [[{"node": "New replies (24h)", "type": "main", "index": 0}]]},
        "New replies (24h)": {"main": [[{"node": "Hottest contacts", "type": "main", "index": 0}]]},
        "Hottest contacts": {"main": [[{"node": "Build digest", "type": "main", "index": 0}]]},
        "Build digest": {"main": [[{"node": "Post to Slack", "type": "main", "index": 0}]]},
    }
    return {"name": "Behavior Graph — Score Refresh + Reply Digest",
            "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}}


def deploy(wf, n8n_key, n8n_url, wf_id=None):
    url = f"{n8n_url}/api/v1/workflows" + (f"/{wf_id}" if wf_id else "")
    method = "PUT" if wf_id else "POST"
    req = urllib.request.Request(
        url, data=json.dumps(wf).encode(), method=method,
        headers={"X-N8N-API-KEY": n8n_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
            print(f"{'updated' if wf_id else 'deployed'}: {d['id']} {d['name']}")
            return d["id"]
    except urllib.error.HTTPError as e:
        print(f"deploy failed: {e.code} {e.read().decode()[:400]}")
        return None


def main():
    env = load_env(ROOT / ".env.keys", Path.home() / ".n8n" / ".env")
    env.update(load_env(Path.home() / ".n8n" / ".env"))
    # slack token lives in the pi settings
    if not env.get("SLACK_BOT_TOKEN"):
        try:
            s = json.loads((Path.home() / ".pi/agent/settings.json").read_text())
            env["SLACK_BOT_TOKEN"] = s.get("slackHomebase", {}).get("botToken", "")
        except Exception:
            pass
    n8n_key = env.get("N8N_API_KEY") or env.get("N8N_API_KEY_ORACLE")
    n8n_url = env.get("N8N_URL", "http://localhost:5679")
    if not env.get("SLACK_BOT_TOKEN"):
        sys.exit("SLACK_BOT_TOKEN missing")

    wf = build(env)
    if "--deploy" in sys.argv:
        wf_id = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--id=")), None)
        deploy(wf, n8n_key, n8n_url, wf_id)
    else:
        out = ROOT / "n8n-workflows" / "behavior-graph.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(wf, indent=2))
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
