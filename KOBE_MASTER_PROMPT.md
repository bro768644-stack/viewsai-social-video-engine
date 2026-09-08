# KOBE MASTER PROMPT — LOCKED (replicates kobe-FLAGSHIP-LOCKED-take3.mp4)

**Source image:** `refs/kobe-viewsai.png` pre-cropped to **exactly 1080×1920 (9:16)**
(veo_kobe.py does this automatically — the pre-crop kills the start-morph).

**Model:** `veo-3.1-fast-generate-preview` · aspect 9:16 · duration 8s · free tier.

## The EXACT prompt (do not reword — this is the lock)

```
Talking head video. He starts from this exact image and stays IDENTICAL the whole clip - same dog, same face, same heterochromia eyes (soft natural light blue + brown), same navy tee, same background. He speaks directly to camera, confident and friendly, subtle head movement only, no shape change, no morphing. Warm office lighting. Cinematic, photorealistic.
```

## Adding a spoken line (the ONLY allowed addition)

Append at the end:

```
 He says exactly: "<the line>"
```

Example:
```
Talking head video. He starts from this exact image and stays IDENTICAL the whole clip - same dog, same face, same heterochromia eyes (soft natural light blue + brown), same navy tee, same background. He speaks directly to camera, confident and friendly, subtle head movement only, no shape change, no morphing. Warm office lighting. Cinematic, photorealistic. He says exactly: "I'm a Pomeranian. And I automated your recruiting."
```

## Do NOT add
- No "bright/luminous eye" language (over-blues)
- No scene/wardrobe changes (they drift identity)
- No extra camera/direction terms after the base prompt

Batch tool uses this automatically: `batch_kobe_takes.py`.
