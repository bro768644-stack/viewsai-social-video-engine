# Kaggle route — automated free GPU (30 h/week)

**Why Kaggle instead of Colab:** official headless API (`kaggle kernels push/status/output`),
no browser automation, no modals, and **30 GPU hours/week free** (T4 x2 / P100) vs Colab's
few hours/day. This is cron-able — real automation.

## One-time setup (2 min)
1. Create a free account at **kaggle.com**
2. Go to **kaggle.com/settings → API → Create New Token** → downloads `kaggle.json`
3. Move it into place:
   ```bash
   mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json
   pip install kaggle
   ```
4. Put your Kaggle username in `kernel-metadata.json` (`"id": "<username>/joyvasa-kobe-talking"`)
   and in `kaggle_run.py` (`--user`)

## Run it
```bash
python3 ~/ViewsOSComplete/scripts/free-stack-videos/kaggle_run.py --check      # verify auth
python3 ~/ViewsOSComplete/scripts/free-stack-videos/kaggle_run.py --setup      # upload kobe.png+kobe.wav as a dataset (once)
python3 ~/ViewsOSComplete/scripts/free-stack-videos/kaggle_run.py --run        # push + poll + download the clip
```

Output lands in `~/Social Media MASTER/kobe-library/movement/kobe_talking.mp4`,
ready for `assemble_kobe.py` (Kokoro voice + text) → `platform_render.py` (12 platforms).

## Daily automation
`kaggle_run.py --run` is fully headless — cron it:
```cron
0 7 * * * cd ~ && /usr/bin/python3 ~/ViewsOSComplete/scripts/free-stack-videos/kaggle_run.py --run >> /tmp/kaggle_daily.log 2>&1
```
