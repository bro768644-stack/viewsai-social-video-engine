# Platform Video Formats — RESEARCH (verified 2026-09-01)

One master video → platform-perfect renders. Safe-zone-aware text overlays.
Used by `platform_render.py`. These are the current industry-standard specs.

## Aspect / resolution / duration

| Platform | Aspect | Size (px) | Max length | Max file | Codec | Notes |
|---|---|---|---|---|---|---|
| **TikTok** | 9:16 | 1080×1920 | 10 min (app); sweet spot 21–34s | 2 GB | MP4 H.264/AAC | 30 or 60 fps |
| **YouTube Shorts** | 9:16 | 1080×1920 | **60 s** (hard cap for Shorts feed) | 2 GB | MP4 H.264 + AAC | also accepts 1:1 / 16:9 but 9:16 wins |
| **Instagram Reels** | 9:16 | 1080×1920 | 90 s | 4 GB | MP4/MOV | cover must be 1080×1920 |
| **Instagram Feed** | 4:5 (preferred) | 1080×1350 | 60 min | 4 GB | MP4/MOV | also 1:1 1080×1080, 16:9 1080×566 |
| **Instagram Stories** | 9:16 | 1080×1920 | 60 s | — | MP4 | 90 s supported for some accounts |
| **Facebook Feed** | 1:1 or 16:9 | 1080×1080 / 1280×720 | 240 min | 10 GB | MP4 | Reels: 9:16 ≤90 s |
| **Facebook Page video** | 16:9 (pref) / 1:1 | 1920×1080 / 1080×1080 | 240 min | 10 GB | MP4 | Pages can post up to 240 min; thumbnail 1.91:1 |
| **Facebook Account (profile)** | 1:1 / 16:9 | 1080×1080 / 1280×720 | 240 min | 10 GB | MP4 | profile feed video = same as Pages; Stories 9:16 ≤60 s |
| **Telegram (channel + bot)** | aspect-agnostic | 16:9 1920×1080 or 9:16 1080×1920 | ≤2 GB (4 GB Premium) | **50 MB via Bot API** | MP4 H.264 | no UI safe zones — full-frame is fine; bots send via `sendVideo`
| **LinkedIn** | 1:1–1.91:1 | 1080×1350 / 1920×1080 | 30 min | 5 GB | MP4 | vertical 9:16 renders in feed; captions strongly recommended (80% muted) |
| **X (Twitter)** | 16:9 (feed) | 1280×720 | **2:20** (standard acct); 4 h+ w/ Premium | 512 MB (Premium 1 GB+) | MP4 H.264 | 9:16 vertical also fills feed now |
| **Threads** | 9:16 or 16:9 | 1080×1920 / 1920×1080 | 5 min | 100 MB (approx) | MP4 | carousels up to 20 items |

## Safe zones (critical — UI covers parts of the frame)

Percentages measured from the EDGE of the 9:16 frame:

| Platform | Top | Bottom | Left | Right | What covers it |
|---|---|---|---|---|---|
| TikTok | ~6% | ~20% | ~4% | ~16% | caption, username, action rail |
| YouTube Shorts | ~6% | ~18% | ~4% | ~16% | title, action rail |
| Instagram Reels | ~6% | ~22% | ~4% | ~15% | username, caption, action rail |
| Instagram Feed | ~4% | ~10% | ~4% | ~4% | caption below, minimal |
| LinkedIn | ~4% | ~10% | ~4% | ~4% | actions row |
| Facebook Reels | ~5% | ~22% | ~4% | ~4% | caption, action rail |
| Facebook Page/Account feed | ~4% | ~10% | ~4% | ~4% | actions row (desktop) / minimal |
| Telegram | 0 | 0 | 0 | 0 | no UI overlay — full frame usable |
| X / Threads | ~4% | ~12% | ~4% | ~4% | actions row |

**Rule of thumb:** keep text between 8% and 78% height; keep faces above 70% height; never place critical content in the bottom 20% or right 16% of 9:16.

## Text overlay strategy (automated, free — replaces Canva)

| Element | Placement | Timing |
|---|---|---|
| Hook (headline) | top third, centered, ≤3 lines | 0–3.5 s, fade in/out |
| Captions (spoken words) | lower third, above bottom safe zone | 0.8 s → end |
| CTA (e.g., "Follow @viewsai") | bottom chip, inside safe zone | last 3 s, fade in/out |

## Engineering rules (FFmpeg)

- **Same-orientation** master → `crop` (scale to cover + center crop, Lanczos + mild unsharp).
- **Orientation change** (e.g., square → 9:16, or 9:16 → 16:9) → `blurpad` by default: scale to fit width, blurred + darkened duplicate as background (keeps the whole subject, looks pro).
- Encode H.264 `yuv420p`, CRF 20, `+faststart`, AAC 160k, 30 fps, audio loudnorm -16 LUFS.
- Always render a 9:16 **cover** (frame 1) for TikTok/Reels/Shorts.

## This system sells as an offer

"**AI Social Video Engine** — send one Kobe-style clip, get back 8 platform-ready
files with safe-zone text, burned in. $0 tool cost (ffmpeg + Python + Kokoro +
LivePortrait)." 10-min turnaround per video, fully automated.
