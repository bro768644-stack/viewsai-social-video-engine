#!/usr/bin/env python3
"""Kobe look presets for the Veo pipeline.

Flagship everyday looks (canonical refs in Brands/Kobe/refs/):
  desk     — sitting at his desk (framework video framing)
  podcast  — podcast mic setup
  viewsai  — navy VIEWS tee portrait
  lebron   — basketball look
  fullbody — full body, true eye color authority

Each look maps to a still-edit instruction for the office/warm-light QC pass.
"""
LOOKS = {
    "desk": {
        "ref": "kobe-desk.png",
        "eye_ref": "kobe-fullbody-square.png",
        "prompt_extra": "He sits at his desk like the reference image.",
    },
    "podcast": {
        "ref": "kobe-podcast.png",
        "eye_ref": "kobe-fullbody-square.png",
        "prompt_extra": "Same podcast setup as the reference image.",
    },
    "viewsai": {
        "ref": "kobe-viewsai.png",
        "eye_ref": "kobe-fullbody-square.png",
        "prompt_extra": "Wearing the navy VIEWS tee exactly as in the reference image.",
    },
    "lebron": {
        "ref": "kobe-lebron.png",
        "eye_ref": "kobe-fullbody-square.png",
        "prompt_extra": "Same basketball look and background as the reference image.",
    },
    "fullbody": {
        "ref": "kobe-fullbody-square.png",
        "eye_ref": "kobe-fullbody-square.png",
        "prompt_extra": "Full body, same office background as the reference image.",
    },
}

DEFAULT_EYE_LINE = (
    "His heterochromia must match the reference EXACTLY: one eye bright luminous "
    "light-blue that shines, one eye brown. Blue eye visibly catches the key light."
)

if __name__ == "__main__":
    import json
    print(json.dumps(LOOKS, indent=1))
