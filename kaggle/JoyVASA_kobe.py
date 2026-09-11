# JoyVASA — Kobe talking clip (Kaggle kernel script)
#
# Runs on Kaggle's FREE GPU (30 h/week, T4 x2 / P100) with internet enabled.
# Inputs: a Kaggle dataset containing kobe.png + kobe.wav
# Output: /kaggle/working/kobe_talking.mp4  (downloaded by kaggle_run.py)
import glob
import os
import shutil
import subprocess
import sys

print("=== JoyVASA on Kaggle ===", flush=True)
subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], check=False)

# ---------------------------------------------------------------- inputs
INPUT_DIRS = glob.glob("/kaggle/input/*")
IMG = AUDIO = None
for d in INPUT_DIRS:
    for f in glob.glob(os.path.join(d, "*")):
        low = f.lower()
        if low.endswith((".png", ".jpg", ".jpeg")) and IMG is None:
            IMG = f
        elif low.endswith((".wav", ".mp3", ".m4a")) and AUDIO is None:
            AUDIO = f
print("image:", IMG, flush=True)
print("audio:", AUDIO, flush=True)
if not IMG or not AUDIO:
    sys.exit("ERROR: upload a dataset containing kobe.png + kobe.wav")

# ---------------------------------------------------------------- install
subprocess.run("apt-get -qq install -y ffmpeg git-lfs > /dev/null 2>&1", shell=True, check=False)
subprocess.run("git lfs install --skip-repo > /dev/null 2>&1", shell=True, check=False)

os.chdir("/kaggle/working")
subprocess.run("git clone -q https://github.com/jdh-algo/JoyVASA.git", shell=True, check=True)
os.chdir("/kaggle/working/JoyVASA")

print("=== installing deps (3-5 min) ===", flush=True)
subprocess.run(
    "pip install -q tyro==0.8.5 accelerate==0.28.0 bitsandbytes==0.43.1 "
    "diffusers==0.27.2 einops==0.8.0 librosa==0.10.2.post1 mediapipe==0.10.14 "
    "imageio-ffmpeg pykalman opencv-python scipy scikit-image onnxruntime-gpu soundfile",
    shell=True, check=False)

# ---------------------------------------------------------------- checkpoints
print("=== downloading checkpoints (~10GB) ===", flush=True)
os.makedirs("pretrained_weights", exist_ok=True)
for repo, dest in (
    ("https://huggingface.co/jdh-algo/JoyVASA", "pretrained_weights/JoyVASA"),
    ("https://huggingface.co/facebook/wav2vec2-base-960h", "pretrained_weights/wav2vec2-base-960h"),
    ("https://huggingface.co/KwaiVGI/LivePortrait", "pretrained_weights/liveportrait"),
):
    if not os.path.exists(dest):
        subprocess.run(f"git clone -q {repo} {dest}", shell=True, check=False)

# stage inputs into the working dir (JoyVASA expects local paths)
shutil.copy(IMG, "/kaggle/working/JoyVASA/kobe.png")
shutil.copy(AUDIO, "/kaggle/working/JoyVASA/kobe.wav")

# ---------------------------------------------------------------- inference
print("=== KOBE INFERENCE (animal mode) ===", flush=True)
cmd = [
    sys.executable, "inference.py",
    "--reference", "kobe.png",
    "--audio", "kobe.wav",
    "--animation_mode", "animal",
    "--output_dir", "outputs",
    "--flag_stitching", "False",
]
print(" ".join(cmd), flush=True)
subprocess.run(cmd, check=False)

vids = sorted(glob.glob("outputs/**/*.mp4", recursive=True), key=os.path.getmtime)
if vids:
    shutil.copy(vids[-1], "/kaggle/working/kobe_talking.mp4")
    print("SUCCESS:", vids[-1], flush=True)
else:
    print("No video produced — check the log above", flush=True)

print("=== outputs ===", flush=True)
for f in glob.glob("/kaggle/working/**/*", recursive=True):
    if f.endswith((".mp4", ".gif")):
        print(" ", f, os.path.getsize(f), flush=True)
