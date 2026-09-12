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

import shutil as _sh

print("=== JoyVASA on Kaggle ===", flush=True)

# GPU check (guarded — nvidia-smi may be absent; never let this kill the run)
if _sh.which("nvidia-smi"):
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                           capture_output=True, text=True, check=False)
        print("GPU:", (r.stdout or r.stderr or "").strip(), flush=True)
    except Exception as e:
        print("GPU check skipped:", str(e)[:60], flush=True)
else:
    print("WARNING: nvidia-smi not found — GPU may be disabled for this kernel", flush=True)

# torch CUDA sanity (tells us definitively whether the GPU is attached)
try:
    import torch
    print("torch:", torch.__version__, "| cuda available:", torch.cuda.is_available(), flush=True)
except Exception as e:
    print("torch check skipped:", str(e)[:60], flush=True)

# ---------------------------------------------------------------- inputs
print("=== /kaggle/input listing ===", flush=True)
for root, dirs, files in os.walk("/kaggle/input"):
    for f in files:
        print("  ", os.path.join(root, f), flush=True)
print("=== env hints ===", flush=True)
for k in ("KAGGLE_KERNEL_RUN_TYPE", "KAGGLE_URL_BASE", "CUDA_VISIBLE_DEVICES"):
    if k in os.environ:
        print(f"  {k}={os.environ[k]}", flush=True)

# Kaggle mounts datasets under /kaggle/input/datasets/<user>/<slug>/ — search recursively
IMG = AUDIO = None
for f in sorted(glob.glob("/kaggle/input/**/*", recursive=True)):
    if not os.path.isfile(f):
        continue
    low = f.lower()
    if low.endswith((".png", ".jpg", ".jpeg")) and IMG is None:
        IMG = f
    elif low.endswith((".wav", ".mp3", ".m4a")) and AUDIO is None:
        AUDIO = f
print("image:", IMG, flush=True)
print("audio:", AUDIO, flush=True)
if not IMG or not AUDIO:
    sys.exit("ERROR: upload a dataset containing kobe.png + kobe.wav")

# hard stop if there's no GPU or no internet — saves a wasted 15-minute run
try:
    import torch as _t
    if not _t.cuda.is_available():
        print("!! NO CUDA — Kaggle GPU not enabled for this kernel.", flush=True)
        print("!! Fix: kaggle.com/settings -> Phone Verification (required for GPU + internet).", flush=True)
        raise SystemExit(3)
except SystemExit:
    raise
except Exception:
    pass

# ---------------------------------------------------------------- install
subprocess.run("apt-get -qq install -y ffmpeg git-lfs > /dev/null 2>&1", shell=True, check=False)
subprocess.run("git lfs install > /dev/null 2>&1", shell=True, check=False)  # NOT --skip-repo: we need real weights

# work OUTSIDE /kaggle/working so the repo/checkpoints aren't captured as output
WORK = "/kaggle/temp/joyvasa"
os.makedirs("/kaggle/temp", exist_ok=True)
if not os.path.exists(WORK):
    subprocess.run(f"git clone -q https://github.com/jdh-algo/JoyVASA.git {WORK}", shell=True, check=True)
os.chdir(WORK)

print("=== installing deps (3-5 min) ===", flush=True)
subprocess.run(
    "pip install -q tyro==0.8.5 accelerate==0.28.0 bitsandbytes==0.43.1 "
    "diffusers==0.27.2 einops==0.8.0 librosa==0.10.2.post1 mediapipe==0.10.14 "
    "imageio-ffmpeg pykalman opencv-python scipy scikit-image onnxruntime-gpu soundfile",
    shell=True, check=False)

# ---------------------------------------------------------------- checkpoints
print("=== downloading checkpoints (~10GB) ===", flush=True)
os.makedirs("pretrained_weights", exist_ok=True)

# JoyVASA motion generator + audio encoder
for repo, dest in (
    ("https://huggingface.co/jdh-algo/JoyVASA", "pretrained_weights/JoyVASA"),
    ("https://huggingface.co/facebook/wav2vec2-base-960h", "pretrained_weights/wav2vec2-base-960h"),
):
    if not os.path.exists(dest):
        subprocess.run(f"git clone -q {repo} {dest}", shell=True, check=False)

# chinese-hubert-base audio encoder — JoyVASA expects this EXACT dir name (literal colon!)
hubert = "pretrained_weights/TencentGameMate:chinese-hubert-base"
if not os.path.exists(hubert):
    subprocess.run(f'git clone -q https://huggingface.co/TencentGameMate/chinese-hubert-base "{hubert}"',
                   shell=True, check=False)
    print("cloned chinese-hubert-base ->", hubert, flush=True)

# LivePortrait renderer: HF repo keeps liveportrait/ liveportrait_animals/ insightface/
# at the ROOT, but JoyVASA expects them inside pretrained_weights/ -> clone then move.
lp_tmp = "/kaggle/temp/liveportrait_hf"
if not os.path.exists(lp_tmp):
    subprocess.run(f"git clone -q https://huggingface.co/KwaiVGI/LivePortrait {lp_tmp}",
                   shell=True, check=False)
for d in ("liveportrait", "liveportrait_animals", "insightface"):
    src = os.path.join(lp_tmp, d)
    dst = os.path.join("pretrained_weights", d)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.move(src, dst)
        print("moved", d, "-> pretrained_weights/", flush=True)

# verify the animal weights are REAL files (not git-lfs pointers ~130 bytes)
need = "pretrained_weights/liveportrait_animals/base_models_v1.1/appearance_feature_extractor.pth"
print("=== checkpoint verification ===", flush=True)
for root, _, files in os.walk("pretrained_weights"):
    for f in files:
        if f.endswith((".pth", ".onnx", ".safetensors", ".bin")):
            fp = os.path.join(root, f)
            sz = os.path.getsize(fp)
            flag = "  <-- LFS POINTER!" if sz < 10000 else ""
            print(f"  {sz:>12,}  {fp}{flag}", flush=True)

# stage inputs into the working dir (JoyVASA expects local paths)
shutil.copy(IMG, os.path.join(WORK, "kobe.png"))
shutil.copy(AUDIO, os.path.join(WORK, "kobe.wav"))


# ---------------------------------------------------------------- XPose patch
# XPose's UniPose uses a CUDA-only extension (MultiScaleDeformableAttention) that
# isn't compiled here. Same fix we validated locally on LivePortrait: make the
# import optional and swap in the repo's pure-PyTorch deformable attention core.
import re as _re
_ops = "src/utils/dependencies/XPose/models/UniPose/ops"
_f1 = os.path.join(_ops, "functions/ms_deform_attn_func.py")
_f2 = os.path.join(_ops, "modules/ms_deform_attn.py")
if os.path.exists(_f1):
    src = open(_f1, encoding="utf-8").read()
    if "import MultiScaleDeformableAttention as MSDA" in src and "except ImportError" not in src:
        src = src.replace("import MultiScaleDeformableAttention as MSDA",
                          "try:\n    import MultiScaleDeformableAttention as MSDA\nexcept ImportError:\n    MSDA = None")
        open(_f1, "w", encoding="utf-8").write(src)
        print("patched: optional MSDA import", flush=True)
if os.path.exists(_f2):
    src = open(_f2, encoding="utf-8").read()
    if "ms_deform_attn_core_pytorch" not in src:
        src = src.replace(
            "from src.utils.dependencies.XPose.models.UniPose.ops.functions.ms_deform_attn_func import MSDeformAttnFunction",
            "from src.utils.dependencies.XPose.models.UniPose.ops.functions.ms_deform_attn_func import MSDeformAttnFunction, ms_deform_attn_core_pytorch")
        src = _re.sub(
            r"output = MSDeformAttnFunction\.apply\(\s*([^,]+),\s*input_spatial_shapes,\s*input_level_start_index,\s*([^,]+),\s*attention_weights,\s*self\.im2col_step\)",
            r"output = ms_deform_attn_core_pytorch(\1, input_spatial_shapes, \2, attention_weights)",
            src)
        open(_f2, "w", encoding="utf-8").write(src)
        print("patched: pure-torch deformable attention", flush=True)


# --- transformers>=4.4x: output_attentions is rejected with sdpa attention ---
# JoyVASA's custom Hubert/Wav2Vec2 wrappers set config.output_attentions = True,
# which newer transformers refuses unless attn_implementation == "eager".
for _f in glob.glob("src/modules/*.py"):
    try:
        _src = open(_f, encoding="utf-8").read()
        if "output_attentions = True" in _src and "_attn_implementation" not in _src:
            _src = _src.replace(
                "        self.config.output_attentions = True",
                "        try:\n"
                "            self.config._attn_implementation = 'eager'\n"
                "        except Exception:\n"
                "            pass\n"
                "        self.config.output_attentions = True")
            _src = _src.replace(
                "    def __init__(self, config):\n        super().__init__(config)",
                "    def __init__(self, config):\n"
                "        try:\n"
                "            config._attn_implementation = 'eager'\n"
                "        except Exception:\n"
                "            pass\n"
                "        super().__init__(config)")
            open(_f, "w", encoding="utf-8").write(_src)
            print("patched eager attention:", _f, flush=True)
    except Exception:
        pass

# ---------------------------------------------------------------- inference
print("=== KOBE INFERENCE (animal mode) ===", flush=True)
cmd = [
    sys.executable, "inference.py",
    "--reference", "kobe.png",
    "--audio", "kobe.wav",
    "--animation_mode", "animal",
    "--output_dir", "outputs",
    "--no-flag-stitching",
]
print(" ".join(cmd), flush=True)

# torch>=2.6 defaults torch.load(weights_only=True) -> JoyVASA ckpts contain
# argparse.Namespace and fail. TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD is PyTorch's
# official opt-out (a monkeypatch would NOT apply to this subprocess).
env = dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1")

subprocess.run(cmd, check=False, env=env)

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
