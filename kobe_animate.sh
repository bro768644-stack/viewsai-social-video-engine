#!/bin/bash
# Kobe LivePortrait animal animation — local, free, MPS/CPU-ready.
#
# Usage:
#   ./kobe_animate.sh                          # defaults: kobe final.png + hf_20260731_082524 driver
#   ./kobe_animate.sh <source.png> <driver.mp4> [out_dir]
#
# What it does: transfers the talking/expression MOTION from an existing
# Kobe video onto a Kobe still (source), keeping the driver's audio.
# NOTE: motion transfer only — new dialogue won't produce new lip shapes.
set -e
LP="$HOME/ViewsOSComplete/Content & Media/ai-video-tools/LivePortrait"
SRC="${1:-$HOME/Desktop/Desktop - Brendan’s MacBook Pro/kobe final.png}"
DRV="${2:-$HOME/Downloads/hf_20260731_082524_429b5908-95c1-47e9-977d-a506b3ab9005.mp4}"
OUT="${3:-/tmp/kobe_anim}"
mkdir -p "$OUT"
cd "$LP"
./venv/bin/python inference_animals.py \
  --source "$SRC" --driving "$DRV" \
  --output_dir "$OUT" --no-flag-stitching
echo "done -> $(ls -t "$OUT"/*.mp4 | head -1)"
