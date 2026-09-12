#!/usr/bin/env python3
"""ViewsAI Launcher — a single local dashboard for every app.

Serves a one-page dashboard (launcher/index.html) listing all your local tools
with live up/down status, and a health endpoint that TCP-checks each app's port
(plus `docker ps` for container status and `pgrep` for native apps like
Obsidian).

No third-party dependencies — Python 3.9+ standard library only.

Run:
    python3 launcher/launcher.py --open
Then open http://127.0.0.1:8787
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.resolve()
INDEX = ROOT / "index.html"

# Single source of truth for the dashboard. Add/edit apps here.
# kind: "web" (TCP-checked) or "native" (process-checked).
# container: docker container name, used to show live container status.
APPS = [
    # Core Systems — first, because this is the main agent workspace
    {"name": "PI-Desktop", "desc": "Desktop workspace for AI coding agents (terminal sessions)", "cat": "Core Systems",
     "url": "file:///Applications/PI-Desktop.app", "launch": "pi_desktop", "open_after_launch": False,
     "kind": "native", "proc": "PI-Desktop"},
    # Memory & Content
    {"name": "Obsidian Vault", "desc": "Your memory system", "cat": "Memory & Content",
     "url": "obsidian://open?vault=Obsidian Vault", "kind": "native"},
    {"name": "Ghost CMS", "desc": "Blog / newsletter / publishing", "cat": "Memory & Content",
     "url": "http://localhost:2368", "desc_note": "cloud: Oracle (SSH tunnel)"},

    # Core Systems (cloud via tunnel unless noted)
    {"name": "ChatbotX", "desc": "ManyChat replacement (flows, DMs, webhook)", "cat": "Core Systems",
     "url": "http://localhost:3123", "desc_note": "cloud: Contabo (tunnel)"},
    {"name": "n8n", "desc": "Automation (ViewsOS)", "cat": "Core Systems",
     "url": "https://flow.tryviewsai.com", "desc_note": "cloud: Oracle (public via tunnel)"},
    {"name": "Chatwoot", "desc": "Support inbox", "cat": "Core Systems",
     "url": "https://chat.tryviewsai.com", "desc_note": "cloud: Oracle (public via tunnel)"},
    {"name": "AgeniusDesk", "desc": "Fleet dashboard", "cat": "Core Systems",
     "url": "https://desk.tryviewsai.com", "desc_note": "cloud: Oracle (public via tunnel, auth required)"},
    {"name": "Postiz", "desc": "Social scheduler", "cat": "Core Systems",
     "url": "https://social.tryviewsai.com", "desc_note": "cloud: Oracle (public via tunnel)"},
    {"name": "Nango", "desc": "OAuth / integrations", "cat": "Core Systems",
     "url": "https://auth.tryviewsai.com", "desc_note": "cloud: Oracle (public via tunnel)"},
    {"name": "Qdrant", "desc": "Vector database", "cat": "Core Systems",
     "url": "http://localhost:6333", "desc_note": "cloud: Oracle"},
    {"name": "AppFlowy", "desc": "Notes / Offers DB + MCP (12 containers)", "cat": "Core Systems",
     # 127.0.0.1 not localhost: cookies are per-host, so this avoids the shared
     # localhost cookie jar that overflows nginx headers (400 Bad Request)
     "url": "http://127.0.0.1"},

    # Cloudflare Workers (serverless - check via workers.dev URLs)
    {"name": "Email Gate Worker", "desc": "Offer page email capture → Ghost + Lead Capture", "cat": "Cloudflare Workers",
     "url": "https://email-gate.bro768644.workers.dev/"},
    {"name": "Lead Capture Worker", "desc": "Social DM → Supabase + Twenty + Scoring", "cat": "Cloudflare Workers",
     "url": "https://lead-capture.bro768644.workers.dev/"},
    {"name": "Stripe Checkout Worker", "desc": "$7/$97 checkout sessions (allowlisted)", "cat": "Cloudflare Workers",
     "url": "https://stripe-checkout.bro768644.workers.dev/create-checkout-session"},

    # Content Studio
    {"name": "Reel Factory", "desc": "7s sign reels (ComfyUI + overlay)", "cat": "Content Studio",
     "url": "file:///Users/viewsai/ViewsOSComplete/launcher/Make%20Reel.command",
     "launch": "reelfactory", "open_after_launch": False},
    {"name": "Reel How-To", "desc": "Local AI Video Stack doc", "cat": "Content Studio",
     "url": "obsidian://open?vault=Obsidian Vault&file=Local%20AI%20Video%20Stack"},
    {"name": "Social Video Studio", "desc": "1 upload → 12 platform videos (text overlays, colors) — SELLABLE", "cat": "Content Studio",
     "url": "http://127.0.0.1:8898", "launch": "studio", "launch_desc": "localhost:8898"},

    # AI & Models (local Mac)
    {"name": "JARVIS", "desc": "Voice assistant (Gemini Live + Pi) — click to launch", "cat": "AI & Models",
     "url": "", "launch": "jarvis", "launch_desc": "JARVIS.app (packaged)", "open_after_launch": False},
    {"name": "ComfyUI", "desc": "Image gen + AnimateDiff (video stack)", "cat": "AI & Models",
     "url": "http://127.0.0.1:8188", "launch": "comfyui", "launch_desc": "localhost:8188"},
    {"name": "Kokoro TTS", "desc": "68-voice free text-to-speech (video stack)", "cat": "AI & Models",
     "url": "http://127.0.0.1:8880", "launch": "kokoro", "launch_desc": "localhost:8880"},
    {"name": "Local MuAPI", "desc": "Free api.muapi.ai replacement (video stack)", "cat": "AI & Models",
     "url": "http://127.0.0.1:3005", "launch": "muapi", "launch_desc": "localhost:3005"},
    {"name": "Ollama", "desc": "Local LLM (API)", "cat": "AI & Models",
     "url": "http://localhost:11434"},
    {"name": "Open Generative AI", "desc": "Image/video generation (video stack)", "cat": "AI & Models",
     "url": "http://localhost:3500", "launch": "opengenai", "launch_desc": "docker container"},
    {"name": "FreeLLM APIs (LiteLLM)", "desc": "10 free models + auto-fallback", "cat": "AI & Models",
     "url": "http://localhost:8080"},
    {"name": "Smart LLM Router", "desc": "LiteLLM proxy (port 4000) — CURRENTLY DOWN", "cat": "AI & Models",
     "url": "http://localhost:4000"},

    # CRM & Scheduling (local Mac, public via tunnels)
    {"name": "Twenty CRM", "desc": "CRM (public: twenty.tryviewsai.com)", "cat": "CRM & Scheduling",
     "url": "http://localhost:3020"},
    {"name": "Rallly (Booking)", "desc": "Scheduling (public: booking.tryviewsai.com)", "cat": "CRM & Scheduling",
     "url": "http://localhost:3009"},

    # Lead Gen & Data (cloud via tunnel)
    {"name": "Job Pipeline", "desc": "Recruiting automation", "cat": "Lead Gen & Data",
     "url": "http://localhost:8094", "desc_note": "cloud: Oracle"},
    {"name": "Email Verifier", "desc": "SMTP verification (8090)", "cat": "Lead Gen & Data",
     "url": "http://localhost:8090", "desc_note": "cloud: Oracle"},
    {"name": "Fire-Enrich", "desc": "Company enrichment", "cat": "Lead Gen & Data",
     "url": "http://localhost:3050", "desc_note": "cloud: Oracle"},
    {"name": "Decision Maker Finder", "desc": "Finds decision makers", "cat": "Lead Gen & Data",
     "url": "http://localhost:3070", "desc_note": "cloud: Oracle"},
    {"name": "JobSpy (retired)", "desc": "Replaced by Scrapling Jobs API below", "cat": "Lead Gen & Data",
     "url": "http://127.0.0.1:3080", "desc_note": "dead - use Scrapling"},
    {"name": "Reacher", "desc": "Email verification", "cat": "Lead Gen & Data",
     "url": "http://localhost:8085", "desc_note": "cloud: Oracle"},

    # GTM & Scraping (local)
    {"name": "GTM Cockpit", "desc": "Review/edit email copy + lead funnel + call log", "cat": "GTM & Scraping",
     "url": "http://127.0.0.1:3120", "launch": "cockpit", "desc_note": "local: gtm-cockpit"},
    {"name": "Free Claude Code", "desc": "Claude Code on free models (LiteLLM proxy)", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/launcher/Free-Claude.command",
     "launch": "freeclaude", "open_after_launch": False},
    {"name": "Listmonk", "desc": "Newsletter / campaign email lists", "cat": "GTM & Scraping",
     "url": "http://127.0.0.1:9001", "desc_note": "cloud: Oracle (tunnel)"},
    {"name": "Scrapling Jobs API", "desc": "Job scraping (JobSpy-compatible :3080)", "cat": "GTM & Scraping",
     "url": "http://127.0.0.1:3080", "launch": "scraplingjobs", "desc_note": "local: Scrapling engine"},
    {"name": "Instagram Downloader", "desc": "gallery-dl (IG/Reddit/X/TikTok)", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/launcher/Instagram-Downloader.command",
     "launch": "igdownloader", "open_after_launch": False},
    {"name": "yt-dlp Downloader", "desc": "YouTube/IG/TikTok/HLS video + audio", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/launcher/YT-DLP-Downloader.command",
     "launch": "ytdlpdownloader", "open_after_launch": False},
    {"name": "IG Burner Setup", "desc": "Export burner IG session -> cookies file", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/launcher/IG-Burner-Setup.command",
     "launch": "igburnersetup", "open_after_launch": False},
    {"name": "Downloaded Media", "desc": "Open instagram-raw folder", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/tools/instagram-raw",
     "launch": "igdownloads", "open_after_launch": False},
    {"name": "IG Raw Clips", "desc": "instagram-raw-clips (edited output)", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/tools/instagram-raw-clips",
     "launch": "igclips", "open_after_launch": False},
    {"name": "Latest Download", "desc": "Reveal newest file in Finder", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/launcher/Latest-IG-Download.command",
     "launch": "iglatest", "open_after_launch": False},
    {"name": "Scout Discovery", "desc": "Scrapling: GitHub + Reddit lead discovery", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/launcher/Scout-Discovery.command",
     "launch": "scoutdiscovery", "open_after_launch": False},
    {"name": "Call List (emailed leads)", "desc": "107 leads to call + LinkedIn", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/gtm-cockpit/exports/call-list-2026-09-09.md",
     "launch": "calldoc", "open_after_launch": False},
    {"name": "Scrapling README", "desc": "Scrape engine docs + commands", "cat": "GTM & Scraping",
     "url": "file:///Users/viewsai/ViewsOSComplete/Scrapling/README.md",
     "launch": "readme", "open_after_launch": False},

    # Supabase Local
    {"name": "Supabase API (Kong)", "desc": "Supabase REST/GraphQL", "cat": "Supabase Local",
     "url": "http://localhost:54321"},
    {"name": "Supabase Studio", "desc": "Supabase dashboard", "cat": "Supabase Local",
     "url": "http://localhost:54323"},

    # Public URLs (via Cloudflare Tunnels)
    {"name": "Ghost (Public)", "desc": "ghost.tryviewsai.com", "cat": "Public URLs",
     "url": "https://ghost.tryviewsai.com"},
    {"name": "Twenty CRM (Public)", "desc": "twenty.tryviewsai.com", "cat": "Public URLs",
     "url": "https://twenty.tryviewsai.com"},
    {"name": "Booking (Public)", "desc": "cal.tryviewsai.com (Cal.com DIY)", "cat": "Public URLs",
     "url": "https://cal.tryviewsai.com/brendan/15min"},
    {"name": "Offer Pages (Public)", "desc": "obrienhq.com/pi-free, /pi-slack, /pi-full", "cat": "Public URLs",
     "url": "https://obrienhq.com/pi-free"},
]


# Launchable apps: name -> command to start (if not already up) + how to probe.
LAUNCHERS = {
    "jarvis": {
        "cmd": [
            "/bin/zsh", "-c",
            "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; "
            "open -a '/Users/viewsai/ViewsOSComplete/Brands/Kobe/assistant/release/mac-arm64/JARVIS.app'",
        ],
        "probe": "proc:JARVIS",
        # `open -a` on an already-running app brings its window to front, so
        # always re-open even when running (activation, not just cold start).
        "always_open": True,
    },
    "comfyui": {
        "cmd": [
            "/bin/zsh", "-c",
            "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; "
            "cd /Users/viewsai/ComfyUI && "
            "nohup ./venv/bin/python3.12 main.py --port 8188 --listen 127.0.0.1 --force-fp16 > /tmp/comfyui.log 2>&1 &",
        ],
        "probe": "http://127.0.0.1:8188",
        "wait_seconds": 60,  # model loading takes a while on first start
    },
    "kokoro": {
        "cmd": [
            "/bin/zsh", "-c",
            "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; "
            "cd '/Users/viewsai/ViewsOSComplete/Content & Media/ai-video-tools/Kokoro-FastAPI' && "
            "nohup ./.venv/bin/python -m uvicorn api.src.main:app --host 127.0.0.1 --port 8880 > /tmp/kokoro.log 2>&1 &",
        ],
        "probe": "http://127.0.0.1:8880",
        "wait_seconds": 30,
    },
    "muapi": {
        "cmd": [
            "/bin/zsh", "-c",
            "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; "
            "cd '/Users/viewsai/ViewsOSComplete/Content & Media/local-muapi' && "
            "nohup ./venv/bin/python3 server.py > /tmp/muapi.log 2>&1 &",
        ],
        "probe": "http://127.0.0.1:3005",
        "wait_seconds": 30,
    },
    "opengenai": {
        "cmd": [
            "/bin/zsh", "-c",
            "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; "
            "docker start open-generative-ai",
        ],
        "probe": "http://127.0.0.1:3500",
        "wait_seconds": 20,
    },
    "studio": {
        "cmd": [
            "/bin/zsh", "-c",
            "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; "
            "cd '/Users/viewsai/ViewsOSComplete/scripts/free-stack-videos/ui' && "
            "nohup python3 app.py > /tmp/studio.log 2>&1 &",
        ],
        "probe": "http://127.0.0.1:8898",
        "wait_seconds": 15,
    },
    # --- fire-and-forget: opens a Terminal window / a document, no service probe ---
    "igdownloader": {
        "cmd": ["/usr/bin/osascript",
                "-e", 'tell application "Terminal" to do script "/Users/viewsai/ViewsOSComplete/launcher/Instagram-Downloader.command"',
                "-e", 'tell application "Terminal" to activate'],
        "probe": "fire",
    },
    "ytdlpdownloader": {
        "cmd": ["/usr/bin/osascript",
                "-e", 'tell application "Terminal" to do script "/Users/viewsai/ViewsOSComplete/launcher/YT-DLP-Downloader.command"',
                "-e", 'tell application "Terminal" to activate'],
        "probe": "fire",
    },
    "igdownloads": {
        "cmd": ["/usr/bin/open", "/Users/viewsai/ViewsOSComplete/tools/instagram-raw"],
        "probe": "fire",
    },
    "igclips": {
        "cmd": ["/usr/bin/open", "/Users/viewsai/ViewsOSComplete/tools/instagram-raw-clips"],
        "probe": "fire",
    },
    "iglatest": {
        "cmd": ["/bin/bash", "/Users/viewsai/ViewsOSComplete/launcher/Latest-IG-Download.command"],
        "probe": "fire",
    },
    "freeclaude": {
        "cmd": ["/usr/bin/osascript",
                "-e", 'tell application "Terminal" to do script "/Users/viewsai/ViewsOSComplete/launcher/Free-Claude.command"',
                "-e", 'tell application "Terminal" to activate'],
        "probe": "fire",
    },
    "scoutdiscovery": {
        "cmd": ["/usr/bin/osascript",
                "-e", 'tell application "Terminal" to do script "/Users/viewsai/ViewsOSComplete/launcher/Scout-Discovery.command"',
                "-e", 'tell application "Terminal" to activate'],
        "probe": "fire",
    },
    "igburnersetup": {
        "cmd": ["/usr/bin/osascript",
                "-e", 'tell application "Terminal" to do script "/Users/viewsai/ViewsOSComplete/launcher/IG-Burner-Setup.command"',
                "-e", 'tell application "Terminal" to activate'],
        "probe": "fire",
    },
    "reelfactory": {
        "cmd": ["/usr/bin/osascript",
                "-e", 'tell application "Terminal" to do script "/Users/viewsai/ViewsOSComplete/launcher/Make Reel.command"',
                "-e", 'tell application "Terminal" to activate'],
        "probe": "fire",
    },
    "calldoc": {
        "cmd": ["/usr/bin/open",
                "/Users/viewsai/ViewsOSComplete/gtm-cockpit/exports/call-list-2026-09-09.md"],
        "probe": "fire",
    },
    "readme": {
        "cmd": ["/usr/bin/open", "/Users/viewsai/ViewsOSComplete/Scrapling/README.md"],
        "probe": "fire",
    },
    "cockpit": {
        "cmd": ["/bin/bash", "/Users/viewsai/ViewsOSComplete/gtm-cockpit/start.sh"],
        "probe": "http://127.0.0.1:3120",
        "wait_seconds": 10,
        "always_open": True,
    },
    "scraplingjobs": {
        "cmd": ["/bin/zsh", "-c",
                "cd /Users/viewsai/ViewsOSComplete/Scrapling && "
                "nohup ./venv/bin/python -m scrapling_gtm serve --port 3080 > /tmp/scrapling-serve.log 2>&1 &"],
        "probe": "http://127.0.0.1:3080",
        "wait_seconds": 10,
    },
    # PI-Desktop — desktop workspace for AI coding agents (main SDK workspace)
    "pi_desktop": {
        "cmd": ["/usr/bin/open", "-a", "/Applications/PI-Desktop.app"],
        "probe": "proc:PI-Desktop",
        "wait_seconds": 20,
        "always_open": True,
    },
}


def _proc_up(name: str) -> bool:
    try:
        return subprocess.run(["pgrep", "-x", name], capture_output=True, timeout=3).returncode == 0
    except Exception:
        return False


def _launch(name: str) -> tuple[bool, bool]:
    """Start app `name`. Returns (ok, already_running)."""
    info = LAUNCHERS.get(name)
    if not info:
        return False, False
    probe = info["probe"]
    # fire-and-forget: launching a Terminal window or a document has no service
    # to probe, so don't block waiting for one (this is what made .command
    # entries appear to "fail" before).
    if probe == "fire":
        try:
            subprocess.Popen(info["cmd"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return True, False
        except Exception:
            return False, False
    already = False
    if probe.startswith("proc:"):
        already = _proc_up(probe[5:])
    else:
        already, _ = _tcp_up(probe)
    if already and not info.get("always_open"):
        return True, True
    try:
        subprocess.Popen(info["cmd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        return False, False
    budget = int(info.get("wait_seconds", 20) * 2)  # 0.5s steps
    for _ in range(budget):  # wait up to wait_seconds for the process/port
        time.sleep(0.5)
        if probe.startswith("proc:"):
            if _proc_up(probe[5:]):
                return True, already
        else:
            up, _ = _tcp_up(probe)
            if up:
                return True, already
    return False, already


def _tcp_up(url: str, timeout: float = 1.2) -> tuple[bool, float]:
    host = urlparse(url).hostname or "127.0.0.1"
    port = urlparse(url).port or 80
    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, round((time.time() - start) * 1000)
    except OSError:
        return False, 0


def _docker_status() -> dict[str, str]:
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=5,
        )
        status: dict[str, str] = {}
        for line in out.stdout.strip().splitlines():
            if "\t" in line:
                name, st = line.split("\t", 1)
                status[name] = st
        return status
    except Exception:
        return {}


def _native_up(proc_name: str) -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-x", proc_name], capture_output=True, timeout=3,
        ).returncode == 0
    except Exception:
        return False


def health() -> dict:
    docker = _docker_status()
    apps = []
    for a in APPS:
        info = dict(a)
        if a.get("kind") == "native":
            # native entries name their process explicitly (default: Obsidian)
            info["running"] = _native_up(a.get("proc") or "Obsidian")
        elif str(a.get("url", "")).startswith("file:"):
            info["up"] = None  # local document link - nothing to probe
        else:
            up, ms = _tcp_up(a["url"])
            info["up"] = up
            info["latency_ms"] = ms
            if a.get("container") and a["container"] in docker:
                info["container_status"] = docker[a["container"]]
        apps.append(info)
    return {"apps": apps, "time": int(time.time() * 1000)}


class Handler(BaseHTTPRequestHandler):
    server_version = "viewsai-launcher/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = INDEX.read_text(encoding="utf-8").replace("__APPS_JSON__", json.dumps(APPS))
            self._send(200, html, "text/html; charset=utf-8")
            return
        if self.path == "/api/health":
            self._json(200, health())
            return
        if self.path.startswith("/api/launch/"):
            name = self.path.rsplit("/", 1)[-1]
            ok, already = _launch(name)
            self._json(200, {"ok": ok, "already": already})
            return
        self._json(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser(description="ViewsAI launcher")
    ap.add_argument("--host", default=os.environ.get("LAUNCHER_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("LAUNCHER_PORT", "8787")))
    ap.add_argument("--open", action="store_true", help="Open the launcher in your browser")
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    url = f"http://{args.host}:{args.port}"
    print(f"[launcher] → {url}", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[launcher] shutting down", flush=True)


if __name__ == "__main__":
    main()
