#!/usr/bin/env python3
"""
MODEL CHAIN PRE-FLIGHT — refresh the free-model queue before the day starts.

Probes every model in ~/.pi/agent/model-chain.json and writes back a healthy,
latency-ordered queue that the pi fallback extension reads. Free tiers reset on a
daily clock, so run this each morning (launchd: com.viewsai.model-preflight).

Usage:
    python3 model_preflight.py            # probe + write status
    python3 model_preflight.py --show     # print current queue
    python3 model_preflight.py --notify   # probe + Slack summary
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHAIN_FILE = Path.home() / ".pi/agent/model-chain.json"
STATUS_FILE = Path.home() / ".pi/agent/model-chain-status.json"
ENV_FILES = [Path.home() / ".n8n/.env", Path("/Users/viewsai/ViewsOSComplete/.env.keys")]
SLACK_CHANNEL = "D0BKSG1QU2Y"

# probes are tiny; reasoning models burn the budget on thoughts, so we only need
# "did the provider answer without an error?" — 40 tokens is enough to see that.
PROBE = {"messages": [{"role": "user", "content": "Reply with the single word: ok"}],
         "max_tokens": 40, "temperature": 0}
TIMEOUT = 60


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


def default_chain():
    """The user's requested order. Steps needing a missing key are kept but marked."""
    return {
        "version": 1,
        "updated": None,
        "order": [
            # ── 1-2: free DeepSeek via Ollama Cloud (needs OLLAMA_API_KEY) ──
            {"provider": "ollama", "id": "deepseek-v4-pro:0813",   "label": "DeepSeek v4 Pro (Ollama Cloud, free)",  "requires": "OLLAMA_API_KEY"},
            {"provider": "ollama", "id": "deepseek-v4-flash:0731", "label": "DeepSeek v4 Flash (Ollama Cloud, free)", "requires": "OLLAMA_API_KEY"},
            # ── 3: Claude (cheapest available route) ──
            {"provider": "freellm", "id": "or-nex-pro", "label": "Claude-class via OpenRouter free", "requires": None},
            # ── 4: gpt-oss 120B (Groq, free) ──
            {"provider": "freellm", "id": "groq-gpt-oss-120b", "label": "GPT-OSS 120B (Groq, free)", "requires": None},
            # ── 5: NVIDIA (needs NVIDIA_API_KEY) ──
            {"provider": "freellm", "id": "nemotron-ultra", "label": "NVIDIA Nemotron Ultra (free)", "requires": None},
            # ── 6: Gemma ──
            {"provider": "freellm", "id": "gemma-31b", "label": "Gemma 31B (free)", "requires": None},
            # ── spares: also free, used if earlier ones are down ──
            {"provider": "freellm", "id": "gemini-3-flash",  "label": "Gemini 3 Flash (free)",  "requires": None},
            {"provider": "freellm", "id": "minimax-m3",      "label": "MiniMax M3 (free)",      "requires": None},
            {"provider": "freellm", "id": "glm-5",           "label": "GLM-5 (free)",           "requires": None},
            {"provider": "freellm", "id": "groq-qwen-36-27b", "label": "Qwen 3.6 27B (Groq, free)", "requires": None},
            {"provider": "freellm", "id": "groq-gpt-oss-20b", "label": "GPT-OSS 20B (Groq, free)", "requires": None},
        ],
    }


def load_chain():
    if not CHAIN_FILE.exists():
        CHAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHAIN_FILE.write_text(json.dumps(default_chain(), indent=2))
        print(f"  created {CHAIN_FILE}")
    return json.loads(CHAIN_FILE.read_text())


def endpoints():
    """base url + auth header per provider (from pi's own config)."""
    eps = {
        "freellm": ("http://localhost:4000/v1", "sk-litellm-master-key-change-me", "bearer"),
    }
    # ollama cloud (OpenAI-compatible /v1)
    oll = env("OLLAMA_API_KEY")
    if oll:
        eps["ollama-cloud"] = ("https://ollama.com/v1", oll, "bearer")
    return eps


def probe(base, key, style, model_id):
    body = json.dumps({**PROBE, "model": model_id}).encode()
    headers = {"Content-Type": "application/json"}
    if style == "bearer":
        headers["Authorization"] = f"Bearer {key}"
    elif style == "none":
        headers["Authorization"] = key
    req = urllib.request.Request(f"{base}/chat/completions", data=body, headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read())
        ms = int((time.time() - t0) * 1000)
        if isinstance(d, dict) and d.get("error"):
            return False, ms, f"api_error: {str(d['error'])[:70]}"
        if not d.get("choices"):
            return False, ms, "no choices in response"
        return True, ms, "ok"
    except urllib.error.HTTPError as e:
        ms = int((time.time() - t0) * 1000)
        detail = e.read().decode()[:160]
        kind = "rate_limited" if e.code == 429 else ("auth" if e.code in (401, 403) else f"http_{e.code}")
        return False, ms, f"{kind}: {detail[:110]}"
    except Exception as e:
        return False, int((time.time() - t0) * 1000), f"{type(e).__name__}: {str(e)[:80]}"


def run():
    chain = load_chain()
    eps = endpoints()
    results = []
    print(f"pre-flight — {datetime.now(timezone.utc).isoformat()[:19]}Z")
    for m in chain["order"]:
        need = m.get("requires")
        if need and not env(need):
            results.append({**m, "ok": False, "ms": None, "note": f"needs {need}",
                            "checked": datetime.now(timezone.utc).isoformat()})
            print(f"  ⊘ {m['label'][:42]:44s} needs {need}")
            continue
        ep = eps.get(m["provider"])
        if not ep:
            results.append({**m, "ok": False, "ms": None, "note": "no endpoint",
                            "checked": datetime.now(timezone.utc).isoformat()})
            print(f"  ⊘ {m['label'][:42]:44s} no endpoint")
            continue
        ok, ms, note = probe(ep[0], ep[1], ep[2], m["id"])
        results.append({**m, "ok": ok, "ms": ms, "note": note,
                        "checked": datetime.now(timezone.utc).isoformat()})
        print(f"  {'✓' if ok else '✗'} {m['label'][:42]:44s} {str(ms)+'ms' if ms else '':>8s} {note[:52] if not ok else ''}")

    # keep the user's PRIORITY order — only drop the ones that failed
    healthy = [r for r in results if r["ok"]]
    dead = [r for r in results if not r["ok"]]
    status = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "unavailable": dead,
        "queue": [{"provider": r["provider"], "id": r["id"], "label": r["label"]} for r in healthy],
    }
    STATUS_FILE.write_text(json.dumps(status, indent=2))
    print(f"\n  queue ({len(healthy)} live): " + " → ".join(r["label"].split(" (")[0] for r in healthy))
    if dead:
        print(f"  unavailable: " + ", ".join(f"{r['label'].split(' (')[0]} ({r['note'][:34]})" for r in dead))
    return status


def notify(status):
    tok = env("SLACK_BOT_TOKEN")
    if not tok:
        print("  (no SLACK_BOT_TOKEN; skipping notification)")
        return
    lines = [f"*Model chain pre-flight — {datetime.now(timezone.utc).date()}*", ""]
    if status["healthy"]:
        lines.append(f"*{len(status['healthy'])} live models (your priority order):")
        for i, r in enumerate(status["healthy"][:8], 1):
            lines.append(f"  {i}. {r['label']}  `{r['ms']}ms`")
    else:
        lines.append("⚠ *No models responded* — check the free proxy / keys.")
    un = status.get("unavailable") or []
    if un:
        lines.append("")
        lines.append("*Unavailable:*")
        for r in un[:6]:
            lines.append(f"  • {r['label'].split(' (')[0]} — {r['note'][:60]}")
    body = {"channel": SLACK_CHANNEL, "text": "\n".join(lines), "unfurl_links": False}
    try:
        req = urllib.request.Request("https://slack.com/api/chat.postMessage",
                                     data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=25).read())
        print(f"  slack: {'sent' if d.get('ok') else d.get('error')}")
    except Exception as e:
        print("  slack failed:", str(e)[:80])


def show():
    if not STATUS_FILE.exists():
        print("  no status yet — run the pre-flight first")
        return
    s = json.loads(STATUS_FILE.read_text())
    print(f"  checked: {s['checked_at'][:19]}Z")
    for i, r in enumerate(s.get("healthy", []), 1):
        print(f"  {i}. {r['label']:46s} {r['ms']}ms")
    for r in s.get("unavailable", []):
        print(f"  ⊘ {r['label']:46s} {r['note'][:50]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--notify", action="store_true")
    args = ap.parse_args()
    if args.show:
        return show()
    st = run()
    if args.notify:
        notify(st)


if __name__ == "__main__":
    main()
