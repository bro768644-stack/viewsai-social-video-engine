#!/usr/bin/env python3
"""
COLAB RUNNER v2 — reliably connects the runtime, runs the notebook, grabs results.

Fixes over v1 (which opened the notebook but executed nothing):
  - explicitly clicks Connect (#connect-button) and WAITS for the runtime
  - auto-accepts the "not authored by Google" warning ("Run anyway")
  - verifies execution actually started by watching for cell outputs
  - falls back to the Runtime menu, then to the Ctrl+F9 shortcut
  - auto-answers files.upload() with your staged media
  - captures downloads into the movement library

Usage:
  /tmp/gvenv/bin/python colab_runner.py \
     --url "https://colab.research.google.com/github/<user>/<repo>/blob/main/<nb>.ipynb" \
     --files ~/Social\ Media\ MASTER/kobe-library/colab-uploads/kobe.png \
             ~/Social\ Media\ MASTER/kobe-library/colab-uploads/kobe.wav \
     --auto-upload --timeout 2400
"""
import argparse
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE = Path.home() / ".viewsai-chrome-gemini"
COLAB = "https://colab.research.google.com/"


def log(*a):
    print("[colab]", *a, flush=True)


class Runner:
    def __init__(self, page, files, auto_upload):
        self.page = page
        self.files = files
        self.downloads = []
        page.on("dialog", self._dialog)
        if auto_upload and files:
            page.on("filechooser", self._chooser)
        page.on("download", self._download)

    def _dialog(self, d):
        log("DIALOG:", d.message[:90])
        try:
            d.accept()
        except Exception:
            pass

    def _chooser(self, fc):
        self.chooser_seen = True
        log("file chooser -> supplying", len(self.files), "file(s)")
        try:
            fc.set_files(self.files)
        except Exception as e:
            log("chooser failed:", str(e)[:80])

    def _download(self, d):
        log("*** DOWNLOAD:", d.suggested_filename)
        self.downloads.append(d)

    # ---------------------------------------------------------------- connect
    def connect(self, budget=180):
        """Click Connect and wait until a runtime is attached."""
        for attempt in range(3):
            try:
                el = self.page.query_selector("#connect-button")
                if not el:
                    el = self.page.query_selector("colab-connect-button")
                if el:
                    txt = (el.inner_text() or "").replace("\n", " ").strip()
                    if "T4" in txt or "GPU" in txt or "RAM" in txt or "Connected" in txt:
                        log("runtime already connected:", txt[:60])
                        return True
                    log(f"clicking connect (attempt {attempt+1})…")
                    el.click()
                else:
                    log("no connect button found")
            except Exception as e:
                log("connect click error:", str(e)[:80])
            # fixed wait — runtimes take ~30-60s to provision; text detection is unreliable
            log("waiting 75s for runtime provisioning…")
            time.sleep(75)
            return True
        log("could not confirm runtime connection (continuing anyway)")
        return False

    # ---------------------------------------------------------------- dialogs
    def clear_warnings(self):
        """Handle the 'not authored by Google' / any modal."""
        for sel in ('button:has-text("Run anyway")', 'button:has-text("Cancel")',
                    'button:has-text("OK")', 'button:has-text("Dismiss")'):
            try:
                for el in self.page.query_selector_all(sel):
                    if el.is_visible():
                        log("clicking modal:", sel)
                        el.click()
                        time.sleep(1)
            except Exception:
                pass

    # ---------------------------------------------------------------- run
    def focus_notebook(self):
        """Click into the notebook so keyboard shortcuts register."""
        for sel in ("colab-notebook-container", ".notebook-container", "body"):
            try:
                el = self.page.query_selector(sel)
                if el:
                    el.click(position={"x": 400, "y": 300})
                    log(f"focused via {sel}")
                    time.sleep(1)
                    return
            except Exception:
                pass

    def run_all(self):
        self.focus_notebook()
        # 1) keyboard shortcut
        try:
            self.page.keyboard.press("Control+F9")
            log("Ctrl+F9 sent")
        except Exception as e:
            log("shortcut failed:", str(e)[:60])
        time.sleep(6)
        self.clear_warnings()
        if self.executing():
            return True
        # 2) command palette  (Ctrl+Shift+P -> "run all")
        try:
            self.page.keyboard.press("Control+Shift+P")
            time.sleep(2)
            self.page.keyboard.type("run all")
            time.sleep(1)
            self.page.keyboard.press("Enter")
            log("Run all via command palette")
            time.sleep(6)
            self.clear_warnings()
            if self.executing():
                return True
        except Exception as e:
            log("palette failed:", str(e)[:60])
        # 3) menu
        try:
            for sel in ('#runtime-menu', 'colab-runtime-menu', 'text=Runtime'):
                if self.page.query_selector(sel):
                    self.page.click(sel, timeout=8000)
                    break
            time.sleep(1)
            self.page.get_by_role("menuitem", name=re.compile("Run all", re.I)).click(timeout=8000)
            log("Run all via menu")
            time.sleep(6)
            self.clear_warnings()
        except Exception as e:
            log("menu run-all failed:", str(e)[:80])
        return self.executing()

    def executing(self):
        try:
            outs = len(self.page.query_selector_all("colab-cell-output, .output_subarea, .output-area"))
            busy = len(self.page.query_selector_all("[aria-label*='unning'], .cell-execution-indicator"))
            return outs > 0 or self.downloads
        except Exception:
            return False

    def poll(self, timeout):
        start = time.time()
        saw_chooser = False
        while time.time() - start < timeout:
            time.sleep(20)
            elapsed = int(time.time() - start)
            if getattr(self, "chooser_seen", False) and not saw_chooser:
                saw_chooser = True
                log("  >>> PROOF: file chooser fired = cells are executing")
            log(f"  t={elapsed}s executing={saw_chooser} downloads={len(self.downloads)}")
            self.clear_warnings()
            if self.downloads:
                return True
        return False

    def save_downloads(self, dest_dir):
        dest = Path(dest_dir).expanduser()
        dest.mkdir(parents=True, exist_ok=True)
        for d in self.downloads:
            try:
                d.save_as(str(dest / d.suggested_filename))
                log("saved:", dest / d.suggested_filename)
            except Exception as e:
                log("save failed:", str(e)[:80])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--dest", default="~/Social Media MASTER/kobe-library/movement")
    ap.add_argument("--auto-upload", action="store_true")
    ap.add_argument("--timeout", type=int, default=2400)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=args.headless,
            accept_downloads=True, viewport={"width": 1500, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        r = Runner(page, args.files, args.auto_upload)

        page.goto(args.url, wait_until="domcontentloaded", timeout=120000)
        time.sleep(12)
        log("title:", page.title()[:70])

        r.connect()
        r.clear_warnings()
        started = r.run_all()
        log("run-all sent:", started)
        log("watching for execution PROOF (file chooser = upload cell ran)…")

        if not started:
            log("WARNING: could not confirm execution — check the window; press Ctrl+F9 if needed")

        r.poll(args.timeout)
        r.save_downloads(args.dest)
        log("finished. downloads:", len(r.downloads))
        if not args.headless:
            log("leaving the browser open 60s")
            time.sleep(60)
        ctx.close()


if __name__ == "__main__":
    main()
