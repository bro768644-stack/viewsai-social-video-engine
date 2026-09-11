#!/usr/bin/env python3
"""
GEMINI VIDEO AUTOMATION — drive the Gemini web UI (no API exists) to generate
avatar videos of Kobe / Brendan, then download the result into the library.

Flow (matches the manual steps, automated):
    open Chrome (persistent profile) → gemini.google.com → type prompt
    → optional reference image upload → send → wait for VIDEO → download
    → save to kobe-library/movement/ → ready for assemble_kobe.py

Usage:
    # 1) first run: opens Chrome so you can log into Google once
    python3 gemini_video.py --login

    # 2) safe probe: opens Gemini, reports the UI selectors it finds (no send)
    python3 gemini_video.py --probe

    # 3) real generation
    python3 gemini_video.py \
        --prompt "Animate this photo of my dog Kobe: he looks at the camera, nods, and talks" \
        --image "/path/kobe.png" \
        --out "kobe-library/movement/kobe-gemini-01.mp4" \
        --timeout 600

Notes:
    - Uses your real Chrome (channel="chrome") + a dedicated profile so you stay logged in.
    - Headful by design: you can watch/step in. --headless for no window (may trip Google).
    - Gemini video gen can take 1-6 min; the script polls the DOM for the video.
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROFILE = Path.home() / ".viewsai-chrome-gemini"
GEMINI = "https://gemini.google.com/app"
MOVEMENT = Path.home() / "Social Media MASTER/kobe-library/movement"

# candidate selectors — Gemini's DOM shifts, so we try several
PROMPT_SEL = [
    'div.ql-editor[contenteditable="true"]',
    'rich-textarea div[contenteditable="true"]',
    'div[contenteditable="true"][role="textbox"]',
    'textarea[placeholder]',
]
SEND_SEL = [
    'button[aria-label*="Send"]',
    'button.send-button',
    'button[mattooltip*="Send"]',
]
UPLOAD_SEL = [
    'input[type="file"]',
    'button[aria-label*="Upload"]',
    'button[aria-label*="Add file"]',
]
VIDEO_SEL = 'video, img[src*="blob:"], a[download]'
DOWNLOAD_SEL = [
    'button[aria-label*="Download"]',
    'a[download]',
    'button:has-text("Download")',
]


def log(*a):
    print(*a, flush=True)


def find_first(page, selectors, timeout=8000):
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                return el, sel
        except PWTimeout:
            continue
    return None, None


def profile_ctx(pw, headless):
    PROFILE.mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        channel="chrome",
        headless=headless,
        accept_downloads=True,
        viewport={"width": 1440, "height": 960},
        args=["--disable-blink-features=AutomationControlled"],
    )


def logged_in(page):
    """Logged in if the prompt box exists AND no 'Sign in' call-to-action is present."""
    for sel in ('a:has-text("Sign in")', 'button:has-text("Sign in")',
                'a[href*="accounts.google.com/ServiceLogin"]'):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return False
        except Exception:
            pass
    el, _ = find_first(page, PROMPT_SEL, timeout=6000)
    return el is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="just open Gemini for a manual login")
    ap.add_argument("--probe", action="store_true", help="report UI selectors, do not send")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--image", default=None, help="reference image to animate")
    ap.add_argument("--out", default=str(MOVEMENT / "kobe-gemini-out.mp4"))
    ap.add_argument("--timeout", type=int, default=600, help="seconds to wait for the video")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    with sync_playwright() as pw:
        ctx = profile_ctx(pw, args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(GEMINI, wait_until="domcontentloaded")
        time.sleep(3)

        if not logged_in(page):
            log("⚠️  Not logged in. A Chrome window is open — sign into Google, then re-run.")
            if args.login:
                log("   waiting up to 15 min for login...")
                for _ in range(180):
                    time.sleep(5)
                    if logged_in(page):
                        log("✓ logged in — profile saved. Re-run without --login.")
                        break
                ctx.close()
                return 0
            ctx.close()
            return 1

        log("✓ logged in, Gemini ready")

        if args.login:
            ctx.close()
            return 0

        # probe mode: report what we can see
        box, boxsel = find_first(page, PROMPT_SEL)
        send, sendsel = find_first(page, SEND_SEL, timeout=3000)
        up, upset = find_first(page, UPLOAD_SEL, timeout=3000)
        log(f"  prompt box : {boxsel or 'NOT FOUND'}")
        log(f"  send button: {sendsel or 'not found (Enter may work)'}")
        log(f"  upload     : {upset or 'not found'}")
        if args.probe or not args.prompt:
            ctx.close()
            return 0

        # attach reference image if provided
        if args.image:
            fi, fisel = find_first(page, ['input[type="file"]'], timeout=5000)
            if fi:
                fi.set_input_files(args.image)
                log(f"  attached: {Path(args.image).name}")
                time.sleep(6)  # let the upload settle
            else:
                log("  ⚠️ no file input found — continuing text-only")

        # type + send
        box.click()
        box.fill(args.prompt) if hasattr(box, "fill") else box.type(args.prompt)
        time.sleep(1)
        if send:
            send.click()
        else:
            page.keyboard.press("Enter")
        log("  prompt sent — waiting for the video (this can take minutes)…")

        deadline = time.time() + args.timeout
        got = None
        while time.time() < deadline:
            time.sleep(10)
            vids = page.query_selector_all("video")
            if vids:
                src = vids[-1].get_attribute("src") or ""
                log(f"  video element found (src={'blob' if src.startswith('blob') else src[:40]})")
                got = vids[-1]
                break
            log("  …still generating")

        if not got:
            log("⚠️ no video within timeout — check the browser window.")
            ctx.close()
            return 1

        # download: try the download button first (captures a real file)
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        dl, dlsel = find_first(page, DOWNLOAD_SEL, timeout=5000)
        saved = False
        if dl:
            try:
                with page.expect_download(timeout=60000) as di:
                    dl.click()
                download = di.value
                download.save_as(str(out))
                saved = True
                log(f"✓ downloaded via button ({dlsel})")
            except Exception as e:
                log(f"  download button failed ({str(e)[:60]}), trying blob fetch")

        if not saved:
            # fallback: pull the blob bytes through the page context (has cookies)
            b64 = page.evaluate(
                """async () => {
                    const v = document.querySelector('video');
                    if (!v || !v.src) return null;
                    const r = await fetch(v.src);
                    const b = await r.arrayBuffer();
                    let s = '';
                    const bytes = new Uint8Array(b);
                    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
                    return btoa(s);
                }"""
            )
            if b64:
                out.write_bytes(base64.b64decode(b64))
                saved = True
                log("✓ saved via blob fetch")

        if saved:
            meta = {"file": out.name, "prompt": args.prompt, "image": args.image,
                    "source": "gemini-web", "created": int(time.time())}
            (out.parent / f"{out.stem}.json").write_text(json.dumps(meta, indent=1))
            log(f"✅ {out} ({out.stat().st_size/1e6:.1f} MB) — added to movement library")
        else:
            log("⚠️ could not download — grab it manually from the browser.")

        if not args.headless:
            log("  leaving the browser open; close it when done (Ctrl+C here to end script)")
            time.sleep(2)
        ctx.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
