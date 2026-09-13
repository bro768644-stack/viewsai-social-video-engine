/**
 * Model Chain Fallback
 *
 * Keeps a session alive when a free model hits its daily cap. Reads the queue that
 * `~/.pi/agent/scripts/model_preflight.py` writes each morning, and on a rate-limit /
 * quota / auth / provider error it advances to the next model in YOUR priority order —
 * telling you why, instead of just stopping.
 *
 *   /chain            show the queue, where you are, and which models are resting
 *   /chain next       advance manually
 *   /chain refresh    re-read the queue after a pre-flight run
 *
 * Commands:
 *   python3 ~/.pi/agent/scripts/model_preflight.py --notify     # morning probe
 */
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const STATUS_FILE = join(homedir(), ".pi/agent/model-chain-status.json");
const COOLDOWN_MS = 15 * 60 * 1000; // a rate-limited model rests before we try it again

export default function modelFallback(pi) {
  /** @type {{provider:string,id:string,label:string}[]} */
  let queue = [];
  let cooling = new Map(); // "provider/id" -> epoch ms until we avoid it
  let lastSwitch = null;

  function loadQueue() {
    try {
      if (!existsSync(STATUS_FILE)) return queue;
      const doc = JSON.parse(readFileSync(STATUS_FILE, "utf8"));
      queue = (doc.queue || []).filter((q) => q && q.provider && q.id);
    } catch {
      /* leave the previous queue in place */
    }
    return queue;
  }

  const key = (provider, id) => `${provider}/${id}`;
  const currentKey = (ctx) => (ctx?.model ? key(ctx.model.provider, ctx.model.id) : null);

  function positionOf(ctx) {
    const cur = currentKey(ctx);
    return queue.findIndex((q) => key(q.provider, q.id) === cur);
  }

  function labelFor(provider, id) {
    const hit = queue.find((q) => key(q.provider, q.id) === key(provider, id));
    return hit?.label || key(provider, id);
  }

  /** Move to the next usable model in the queue. Returns true if we switched. */
  async function advance(ctx, reason, opts = {}) {
    if (!queue.length) loadQueue();
    if (!queue.length) {
      ctx.ui.notify(
        `⚠ ${reason} — no model chain loaded. Run: python3 ~/.pi/agent/scripts/model_preflight.py`,
        "error",
      );
      return false;
    }

    const cur = currentKey(ctx);
    if (cur && !opts.noCooldown) cooling.set(cur, Date.now() + COOLDOWN_MS);
    const start = Math.max(positionOf(ctx), -1) + 1;

    for (let step = 0; step < queue.length; step++) {
      const i = (start + step) % queue.length;
      const q = queue[i];
      const k = key(q.provider, q.id);
      if (k === cur) continue;
      if ((cooling.get(k) || 0) > Date.now()) continue;

      const model = ctx.modelRegistry.find(q.provider, q.id);
      if (!model) continue;

      const ok = await pi.setModel(model);
      if (!ok) continue;

      lastSwitch = { from: cur, to: k, reason, at: Date.now() };
      ctx.ui.notify(
        `↻ ${reason} → switched to ${q.label}  (chain ${i + 1}/${queue.length})`,
        "warning",
      );
      if (ctx.ui.setStatus) ctx.ui.setStatus("chain", `chain ${i + 1}/${queue.length}`);
      return true;
    }

    ctx.ui.notify(
      `⛔ All ${queue.length} chain models are unavailable (${reason}). ` +
        `Change the model manually with /model, or run the pre-flight.`,
      "error",
    );
    return false;
  }

  function reasonForStatus(status) {
    if (status === 429) return "rate limit / daily tokens exhausted";
    if (status === 402) return "quota or billing limit";
    if (status === 401 || status === 403) return "auth failed";
    if (status === 404) return "model not available";
    if (status === 408 || status === 504) return "provider timeout";
    if (status >= 500) return `provider error (HTTP ${status})`;
    return null;
  }

  // ── detect a failed request as early as possible ────────────────────────────
  pi.on("after_provider_response", async (event, ctx) => {
    const reason = reasonForStatus(event?.status);
    if (reason) await advance(ctx, reason);
  });

  // ── belt and braces: error text on the finalized assistant message ───────────
  pi.on("message_end", async (event, ctx) => {
    const msg = event?.message;
    if (!msg || msg.role !== "assistant") return;
    const err = msg.errorMessage || msg.error || "";
    if (!err || typeof err !== "string") return;
    if (/rate.?limit|too many requests|quota|insufficient|exceeded|429|capacity|overloaded/i.test(err)) {
      await advance(ctx, `error: ${err.slice(0, 70)}`);
    }
  });

  pi.on("session_start", async (_event, ctx) => {
    loadQueue();
    const pos = positionOf(ctx);
    if (pos >= 0 && ctx.ui.setStatus) {
      ctx.ui.setStatus("chain", `chain ${pos + 1}/${queue.length}`);
    }
  });

  pi.registerCommand("chain", {
    description: "Show the free-model fallback queue, or advance it (/chain next)",
    handler: async (args, ctx) => {
      const sub = (args || "").trim().toLowerCase();

      if (sub === "next") {
        const moved = await advance(ctx, "manual advance", { noCooldown: false });
        if (!moved) ctx.ui.notify("No other chain model available.", "error");
        return;
      }

      if (sub === "refresh") {
        const before = queue.length;
        loadQueue();
        ctx.ui.notify(`Chain reloaded: ${before} → ${queue.length} models`, "info");
        return;
      }

      const cur = currentKey(ctx);
      const lines = [];
      lines.push(`Model chain — ${queue.length} in queue${cur ? `, current: ${labelFor(...cur.split("/"))}` : ""}`);
      queue.forEach((q, i) => {
        const k = key(q.provider, q.id);
        const rest = (cooling.get(k) || 0) > Date.now();
        const here = k === cur;
        lines.push(`${here ? "▶" : rest ? "⏸" : " "} ${i + 1}. ${q.label}${rest ? "  (rate-limited, resting)" : ""}`);
      });
      if (lastSwitch) {
        lines.push(
          `last switch: ${lastSwitch.from} → ${lastSwitch.to} (${lastSwitch.reason}) at ` +
            new Date(lastSwitch.at).toISOString().slice(11, 19),
        );
      }
      lines.push("", "/chain next to advance · /chain refresh to reload after a pre-flight");
      ctx.ui.notify(lines.join("\n"), "info");
    },
  });
}
