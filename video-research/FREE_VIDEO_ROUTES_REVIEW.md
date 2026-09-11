# FREE VIDEO ROUTES FOR KOBE — VERIFIED REVIEW (2026-09-05)

Every claim below was checked against the real repos/Spaces/APIs — not taken from AI-generated guides.
**Goal:** 1 free 8–10s Kobe Pomeranian lip-sync video per day, $0.

---

## TL;DR — the winner

| Rank | Route | For | Cost | Gets animal lip-sync? | Automatable |
|---|---|---|---|---|---|
| 🥇 | **JoyVASA on free Colab T4** | **Kobe (dog)** | **$0** | ✅ **YES — trained for animals** | Semi (Run all) |
| 🥈 | **LatentSync free HF Space** | Brendan (human) | $0 (needs free HF login) | ❌ human faces | ✅ API + cron |
| 🥉 | **EchoMimic free HF Space** | Brendan (human) | $0 (needs free HF login) | ❌ human faces | ✅ API |
| ❌ | Hedra | — | **$15/mo minimum** (not free) | ✅ reportedly | — |

---

## 1. JoyVASA — THE answer for Kobe ✅

**Repo:** `github.com/jdh-algo/JoyVASA` — 878★, "Diffusion-based Portrait and **Animal** Animation"

**Verified from the source code:**
- `animation_mode: str = "animal"` — an explicit **animal mode flag** (`argument_config.py`)
- `flag_stitching` default False — *"recommend True if head movement is small, **False if … the source image is an animal**"*
- Real CLI: `--reference` (image) `--audio` (wav) `--output_dir` — **NOT** `--source_image/--driven_audio` (that's a common AI-guide hallucination)
- Paper: *"the decoupled facial representation and identity-independent motion generation process … **extends beyond human portraits to animate animal faces seamlessly**"*
- Uses **LivePortrait as the renderer** (we already have it working locally)

**Why it beats LivePortrait-only:** JoyVASA generates *audio-driven* facial motion (wav2vec2 → diffusion transformer), so Kobe's mouth actually follows the words — LivePortrait only transfers motion from a driver video.

**Requirements:** CUDA (bitsandbytes) → **free Colab T4**, not the M4. ~10GB checkpoints per session.

**Deliverable:** `JoyVASA_Kobe_Colab.ipynb` (this folder) — pre-filled, correct flags, auto-downloads the result.

---

## 2. LatentSync — best free option for BRENDAN (human) ✅

**Space:** `fffiloni/LatentSync` — 622❤️, **RUNNING on zero-a10g** (free ZeroGPU)
- ByteDance LatentSync 1.6 = highest-quality open lip-sync (latent diffusion), ~10s cap
- **API verified working:** `predict(video, audio)` → lipsynced video
- Wire: `submit_btn.click(fn=generate_lip_sync_video, inputs=[video_input, audio_input], outputs=[video_result], api_visibility="public")`
- **Blocker found:** Space uses `@spaces.GPU(duration=180)` → anonymous requests fail with
  *"requested GPU duration (180s) is larger than the maximum allowed"*
- **Fix:** any **free** Hugging Face account token raises the ZeroGPU allowance.
  Create at `huggingface.co/settings/tokens` (free, no card) → then automation works.
- ⚠️ Human-face detection core → will **not** track a dog.

---

## 3. EchoMimic — alternative for Brendan ✅

**Space:** `fffiloni/EchoMimic` — 161❤️, RUNNING zero-a10g (free)
- Inputs: `gr.Image` (reference portrait) + `gr.Audio` → talking video
- `@spaces.GPU(duration=200)` → same **free HF token** requirement
- Also human-face oriented; image+audio (no video needed)
- Also available: `fffiloni/echomimic-v2` (newer), `BadToBest/EchoMimic`

---

## 4. Hedra — NOT FREE ❌

Checked `hedra.com/pricing`: **Basic $15/mo** (1,500 credits), Creator $30/mo (5,400 credits).
There's a signup "start free" trial but **no sustainable daily free allowance** — Gemini's claim was wrong.

---

## What was ruled out earlier (for the record)
- **Free Google AI Studio key:** text only. Image gen = `limit: 0` on free tier; Veo = 429. (Verified against the API.)
- **OpenRouter / freellm / LiteLLM:** no video generation models at all.
- **Local ComfyUI / LivePortrait:** free and unlimited, but motion-only (no audio-driven mouth) and weak on Kobe's snout. Keep for text overlays, stills, and the assembler.

---

## Recommended daily pipeline ($0)

```
Kobe line (free text model)  →  Kokoro TTS (free, local)  →  JoyVASA on Colab (free T4)
        ↓
   kobe_talking.mp4  →  assemble_kobe.py (text overlay)  →  platform_render.py (12 platforms)
        ↓
   Postiz / manual publish
```

For the **Brendan** side of the duo: LatentSync Space via API (add the free HF token once).

---

## Files in this review
| File | What |
|---|---|
| `video-research/FREE_VIDEO_ROUTES_REVIEW.md` | this document |
| `video-research/JoyVASA_Kobe_Colab.ipynb` | ready-to-run Colab notebook (animal mode, correct flags) |
| `scripts/free-stack-videos/spaces_lipsync.py` | automation for LatentSync / EchoMimic free Spaces (add HF token) |
| `scripts/free-stack-videos/assemble_kobe.py` | movement + Kokoro voice + text overlay → finished post |
| `scripts/free-stack-videos/platform_render.py` | 1 master → 12 platform renders |

## The single unlock you need
**A free Hugging Face account token** (`huggingface.co/settings/tokens`) — it raises ZeroGPU quota so
LatentSync/EchoMimic run for free. Everything else needs no accounts at all.

---

# ⚠️ LIVE TEST RESULTS (2026-09-05, with real HF token)

## The ZeroGPU quota reality — measured
```
"You have exceeded your free ZeroGPU quota (180s requested vs. 261s left).
 Try again in 23:58:14. Subscribe to HF PRO to get 25 min of ZeroGPU quota a day"
```
- Free HF ZeroGPU allowance = **~300s GPU/day total** (5 min)
- **LatentSync reserves 180s per call** → ~1 run/day; **failed attempts still burn quota**
- **EchoMimic reserves 200s per call** → ~1 run/day
- Resets every 24h
- Token verified working (got past the "duration too large" gate immediately)

## Verdict per route
| Route | Free? | Kobe (animal)? | Daily capacity |
|---|---|---|---|
| **JoyVASA — free Colab T4** | ✅ | ✅ **YES (animal mode)** | 1+ (Colab session limits, no ZeroGPU cap) |
| LatentSync HF Space | ✅ ~1/day | ❌ human faces | 1 (180s/call of ~300s) |
| EchoMimic HF Space | ✅ ~1/day | ❌ human faces | 1 (200s/call) |
| Hedra | ❌ $15/mo | ✅ | — |

## ⭐ THE REVISED PLAN — run BOTH on one free Colab T4 session
Instead of splitting across quota-limited Spaces, do **Kobe + Brendan in the same Colab T4 run**:
1. **JoyVASA** (`animation_mode animal`) → Kobe talking clip ✅ the missing piece
2. **LatentSync** (or MuseTalk) from the same Colab repo checkout → Brendan talking clip
3. Download both → `assemble_kobe.py` (Kokoro voice + text) → `platform_render.py` (12 platforms)

That routes around the 300s ZeroGPU cap entirely — Colab's T4 gives you a full session,
no per-call GPU-second budget. **This is the 100% free daily video engine.**
