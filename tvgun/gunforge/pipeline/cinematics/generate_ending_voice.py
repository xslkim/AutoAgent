"""Synthesize the new epilogue's fictional voice locally."""
import json
import os
import random
import sys
from pathlib import Path

from ending_plan import LINES, ROOT, VOICE_STYLE


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np
    import soundfile
    import torch
    from voxcpm import VoxCPM

    model_dir = Path(os.environ.get("GUNFORGE_VOXCPM_MODEL", "/home/xsl/models/VoxCPM2"))
    model = VoxCPM(voxcpm_model_path=str(model_dir), enable_denoiser=False, optimize=False)
    sys.path.insert(0, str(model_dir))
    from tokenization_voxcpm2 import VoxCPM2Tokenizer

    model.tts_model.text_tokenizer = VoxCPM2Tokenizer.from_pretrained(str(model_dir)).encode
    out = ROOT / "audio"
    out.mkdir(parents=True, exist_ok=True)

    def record(text, name, seed, reference=None):
        target = out / name
        if target.exists():
            return target
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        audio = model.generate(
            text=f"({VOICE_STYLE}){text}",
            reference_wav_path=str(reference) if reference else None,
            inference_timesteps=12,
        )
        soundfile.write(target, audio, 48000, subtype="PCM_16")
        print(name, text, flush=True)
        return target

    design_text = "从前我回家晚，走过站台，总能看见那盏灯。等哪天你走那条路，也替我看看。"
    reference = record(design_text, "voice_design.wav", 202611140)
    for index, (_, text) in enumerate(LINES, 1):
        record(text, f"voice_{index:02}.wav", 202611140 + index, reference)
    (out / "voice_manifest.json").write_text(
        json.dumps({"model": "local VoxCPM2", "style": VOICE_STYLE, "design_text": design_text,
                    "lines": [{"start": at, "text": text} for at, text in LINES]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
