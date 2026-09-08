#!/usr/bin/env python3
"""
ViewsAI Social Video Engine — LOCAL STUDIO UI (Flask).

The sellable face of the engine: upload one master clip, pick platforms,
set text/colors, hit Create. Everything renders on YOUR machine — nothing
is uploaded to any server. No accounts. No subscriptions. $0 tool cost.

Run:
    python3 app.py            # → http://127.0.0.1:8898
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort

ROOT = Path(__file__).resolve().parent
RENDER = ROOT.parent / "platform_render.py"          # engine CLI
WORK = Path.home() / "Social Media MASTER/studio"    # workspace
UPLOADS = WORK / "uploads"
JOBS = WORK / "jobs"
UPLOADS.mkdir(parents=True, exist_ok=True)
JOBS.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB

JOBS_STATE = {}  # job_id -> dict
ALLOWED_VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}

PLATFORMS = {
    "tiktok": ("9:16", "1080×1920"), "youtube-shorts": ("9:16", "1080×1920"),
    "instagram-reel": ("9:16", "1080×1920"), "instagram-story": ("9:16", "1080×1920"),
    "threads": ("9:16", "1080×1920"), "facebook-reel": ("9:16", "1080×1920"),
    "instagram-feed": ("4:5", "1080×1350"), "linkedin": ("4:5", "1080×1350"),
    "facebook-account": ("1:1", "1080×1080"),
    "facebook-page": ("16:9", "1920×1080"), "telegram": ("16:9", "1920×1080"),
    "x": ("16:9", "1280×720"),
}
PLATFORM_ORDER = list(PLATFORMS)


def probe(path):
    def run(args):
        return subprocess.run(args, capture_output=True, text=True).stdout.strip()
    w, h = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path]).split("x")
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", path]))
    audio = "audio" in run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                            "-of", "csv=p=0", path]).splitlines()
    return {"width": int(w), "height": int(h), "duration": round(dur, 2),
            "has_audio": audio, "aspect": f"{int(w)}:{int(h)}"}


@app.get("/api/platforms")
def platforms():
    return jsonify({k: {"aspect": v[0], "size": v[1]} for k, v in PLATFORMS.items()})


@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "no file"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO:
        return jsonify({"error": f"unsupported type {ext}"}), 400
    fid = uuid.uuid4().hex[:10]
    name = f"{fid}{ext}"
    dest = UPLOADS / name
    f.save(dest)
    info = probe(str(dest))
    info.update({"id": fid, "name": Path(f.filename).name})
    return jsonify(info)


@app.post("/api/jobs")
def create_job():
    b = request.get_json(force=True)
    master_id = b.get("master_id")
    src = UPLOADS / f"{master_id}"
    cands = list(UPLOADS.glob(f"{master_id}.*"))
    if not cands:
        return jsonify({"error": "master not found"}), 400
    src = cands[0]
    platforms = [p for p in b.get("platforms", []) if p in PLATFORMS]
    if not platforms:
        return jsonify({"error": "pick at least one platform"}), 400
    jid = uuid.uuid4().hex[:10]
    jdir = JOBS / jid
    (jdir / "raw").mkdir(parents=True)

    state = {
        "id": jid, "master": src.name, "platforms": platforms,
        "done": [], "current": None, "errors": [], "finished": False,
        "created": time.time(), "cover": bool(b.get("cover", False)),
    }
    JOBS_STATE[jid] = state

    def worker():
        for p in platforms:
            state["current"] = p
            cmd = [sys.executable, str(RENDER), "--master", str(src), "--only", p,
                   "--out", str(jdir)]
            if b.get("mode") and b.get("mode") != "auto":
                cmd += ["--mode", b["mode"]]
            for key in ("title", "caption", "cta"):
                if b.get(key):
                    cmd += [f"--{key}", b[key]]
            if b.get("accent"):
                cmd += ["--accent", b["accent"]]
            if b.get("fg"):
                cmd += ["--fg", b["fg"]]
            if state["cover"]:
                cmd += ["--cover"]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                if r.returncode != 0:
                    state["errors"].append({"platform": p, "detail": r.stderr[-400:]})
                else:
                    state["done"].append(p)
            except Exception as e:  # noqa
                state["errors"].append({"platform": p, "detail": str(e)[:400]})
            state["current"] = None
        state["finished"] = True

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"id": jid})


@app.get("/api/jobs/<jid>")
def job_status(jid):
    s = JOBS_STATE.get(jid)
    if not s:
        return jsonify({"error": "unknown job"}), 404
    return jsonify({"current": s["current"], "done": s["done"],
                    "errors": s["errors"], "finished": s["finished"],
                    "total": len(s["platforms"])})


@app.get("/api/jobs/<jid>/results")
def job_results(jid):
    s = JOBS_STATE.get(jid)
    if not s:
        return jsonify({"error": "unknown job"}), 404
    jdir = JOBS / jid
    results = []
    for p in s["platforms"]:
        pdir = jdir / p
        for mp4 in sorted(pdir.glob("*.mp4")):
            results.append({"platform": p, "name": mp4.name,
                            "size_mb": round(mp4.stat().st_size / 1e6, 1),
                            "url": f"/outputs/{jid}/{p}/{mp4.name}"})
        if s["cover"]:
            for jpg in sorted(pdir.glob("*.jpg")):
                results.append({"platform": p, "name": jpg.name,
                                "size_mb": round(jpg.stat().st_size / 1e6, 1),
                                "url": f"/outputs/{jid}/{p}/{jpg.name}", "cover": True})
    return jsonify({"results": results})


@app.get("/outputs/<jid>/<platform>/<name>")
def download(jid, platform, name):
    p = JOBS / jid / platform / name
    if not p.exists():
        abort(404)
    return send_from_directory(p.parent, name, as_attachment=True)


@app.get("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    print(f"\n  ViewsAI Social Video Engine Studio")
    print(f"  → http://127.0.0.1:8898  (close this window to stop)\n")
    app.run(host="127.0.0.1", port=8898, debug=False, threaded=True)
