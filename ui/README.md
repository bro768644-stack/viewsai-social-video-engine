# ViewsAI Social Video Engine — Studio

One upload. 12 platform-perfect videos. Runs 100% on your computer.

## Requirements
- macOS (or Linux/Windows with Python) with **ffmpeg** installed
- Python 3.9+ and Flask: `pip install flask` (one time)

## Run
```bash
python3 app.py
# → open http://127.0.0.1:8898
```
On macOS you can double-click **start.command** instead.

## What it does
1. Upload ONE master clip (drag & drop)
2. Write hook / caption / CTA + pick accent colors
3. Choose platforms (or "All")
4. **Create Videos** → watch per-platform progress → download finished files

Outputs land in `~/Social Media MASTER/studio/jobs/<id>/<platform>/`.

## Why it's not a scam
- No account, no login, no cloud upload — your video is processed on **your** machine by ffmpeg
- $0 tool cost — this is the whole pitch
- Every render honors that platform's spec: aspect, resolution, duration cap and **safe zones** (text never hides under TikTok/Reels/Shorts UI)

## Platform matrix
| Platform | Aspect | Size | Cap |
|---|---|---|---|
| TikTok / YT Shorts / IG Reel / IG Story / Threads / FB Reel | 9:16 | 1080×1920 | 60–300 s |
| IG Feed / LinkedIn | 4:5 | 1080×1350 | 60 s / 30 min |
| FB Account | 1:1 | 1080×1080 | 240 min |
| X | 16:9 | 1280×720 | 2:20 |
| FB Page / Telegram | 16:9 | 1920×1080 | 240 min |
