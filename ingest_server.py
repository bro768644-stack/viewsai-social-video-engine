#!/usr/bin/env python3
"""
INGEST API — the capture point for inbound replies.

Any source (a Microsoft 365 forwarding rule, Zapmail, a mail service webhook,
or you, manually) POSTs a reply here. The agent classifies it, RAG-drafts a
response, stores it in Supabase and drops a private note in Chatwoot.

Endpoints:
    POST /ingest/reply   {from, subject, body, to_mailbox?}       JSON
    POST /ingest/raw     raw RFC822 email as text/plain body
    GET  /health
    GET  /recent                                                  last handled replies

Run:
    python3 ingest_server.py            # port 8899
Auth: X-Ingest-Token header must equal INGEST_TOKEN (from ~/.n8n/.env, else auto-generated)
"""
import json
import os
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import reply_agent as agent

PORT = int(os.environ.get("REPLY_INGEST_PORT", "8899"))
TOKEN_FILE = Path.home() / ".viewsai-reply-ingest-token"


def ingest_token():
    t = os.environ.get("INGEST_TOKEN") or agent.env("INGEST_TOKEN")
    if t:
        return t
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    t = uuid.uuid4().hex
    TOKEN_FILE.write_text(t)
    TOKEN_FILE.chmod(0o600)
    return t


TOKEN = ingest_token()


def parse_raw(raw: str):
    frm = re.search(r"^From:\s*(.+)$", raw, re.M)
    sub = re.search(r"^Subject:\s*(.+)$", raw, re.M)
    to = re.search(r"^To:\s*(.+)$", raw, re.M)
    body = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    email = frm.group(1).strip() if frm else "unknown@unknown"
    m = re.search(r"<([^>]+)>", email)
    if m:
        email = m.group(1)
    return {"from": email,
            "subject": (sub.group(1).strip() if sub else ""),
            "body": (body[1] if len(body) > 1 else raw)[:8000],
            "to_mailbox": (to.group(1).strip() if to else None)}


class H(BaseHTTPRequestHandler):
    server_version = "viewsai-reply-ingest/1.0"

    def log_message(self, *a):
        return

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        return self.headers.get("X-Ingest-Token") == TOKEN

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n).decode("utf-8", "ignore")

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True, "service": "reply-ingest",
                                    "chatwoot": bool(agent.CHATWOOT_TOKEN),
                                    "anthropic": bool(agent.ANTHROPIC),
                                    "supabase": bool(agent.SB_URL)})
        if self.path == "/recent":
            if not self._auth():
                return self._json(401, {"error": "bad token"})
            try:
                rows = agent.sb("email_replies?select=from_email,subject,intent,urgency,status,"
                                "routed_to,received_at&order=received_at.desc&limit=20")
                return self._json(200, {"replies": rows})
            except Exception as e:
                return self._json(500, {"error": str(e)[:200]})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return self._json(401, {"error": "bad token"})
        raw = self._body()
        try:
            if self.path == "/ingest/reply":
                d = json.loads(raw or "{}")
                from_email = d.get("from") or d.get("from_email") or "unknown@unknown"
                to_mailbox = d.get("to_mailbox")
                subject = d.get("subject") or ""
                body = d.get("body") or d.get("text") or ""
            elif self.path == "/ingest/raw":
                d = parse_raw(raw)
                from_email, subject, body, to_mailbox = d["from"], d["subject"], d["body"], d["to_mailbox"]
            else:
                return self._json(404, {"error": "not found"})
        except Exception as e:
            return self._json(400, {"error": f"bad payload: {str(e)[:120]}"})

        # process inline (fast enough) and return the outcome
        try:
            row = agent.handle(from_email, subject, body, to_mailbox, source="ingest")
            return self._json(200, {"ok": True, "intent": row.get("intent"),
                                    "urgency": row.get("urgency"),
                                    "routed_to": row.get("routed_to"),
                                    "chatwoot_conversation_id": row.get("chatwoot_conversation_id")})
        except Exception as e:
            return self._json(500, {"ok": False, "error": str(e)[:300]})


if __name__ == "__main__":
    print(f"[reply-ingest] listening on http://127.0.0.1:{PORT}")
    print(f"[reply-ingest] token: {TOKEN}")
    print(f"[reply-ingest] token file: {TOKEN_FILE}")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    srv.serve_forever()
