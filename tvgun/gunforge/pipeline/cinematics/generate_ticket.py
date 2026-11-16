"""Run in WSL. Keep GPU work serial and persist accepted H3 jobs."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from generate_opening_h3 import request, workflow
from ticket_plan import LINES, ROOT, SHOTS, VOICE_STYLE


def voice():
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    import soundfile
    import torch
    from voxcpm import VoxCPM
    models = "/home/xsl/models/VoxCPM2"
    engine = VoxCPM(voxcpm_model_path=models, enable_denoiser=False, optimize=False)
    sys.path.insert(0, models)
    from tokenization_voxcpm2 import VoxCPM2Tokenizer
    engine.tts_model.text_tokenizer = VoxCPM2Tokenizer.from_pretrained(models).encode
    out = ROOT / "audio"
    out.mkdir(exist_ok=True)
    design = "从前啊，车站外头有条小路。走得晚了，顺着那盏灯，也能找到家。"
    for i, text in enumerate([design] + [text for _, text in LINES]):
        path = out / f"voice_{i:02}.wav"
        if path.exists():
            continue
        torch.manual_seed(202611140 + i)
        wav = engine.generate(text=f"({VOICE_STYLE}){text}", inference_timesteps=12,
                              reference_wav_path=str(out / "voice_00.wav") if i else None)
        soundfile.write(path, wav, 48000, subtype="PCM_16")
        print("Voice", i, text, flush=True)


def motion():
    home = Path("/home/xsl/aivideo/ComfyUI")
    inputs = home / "input/last_ticket_20261114"
    inputs.mkdir(parents=True, exist_ok=True)
    out = ROOT / "motion"
    out.mkdir(exist_ok=True)
    remaining = list(enumerate(SHOTS))
    deadline = time.monotonic() + 3600
    while remaining:
        if time.monotonic() > deadline:
            raise TimeoutError([s[1][0] for s in remaining])
        ready = next((item for item in remaining if (ROOT / "keyframes" / f"{item[1][0]}.png").exists()), None)
        if ready is None:
            time.sleep(5)
            continue
        index, (name, _, action) = ready
        remaining.remove(ready)
        output = out / f"{name}.mp4"
        if output.exists():
            continue
        record = out / f"{name}_job.json"
        if record.exists():
            job = json.loads(record.read_text(encoding="utf-8"))
            if not job.get("prompt_id"):
                raise RuntimeError(f"Unknown submission state: {name}")
        else:
            keyframe = (ROOT / "keyframes" / f"{name}.png").read_bytes()
            (inputs / f"{name}.png").write_bytes(keyframe)
            graph = workflow({"id": f"s{index+1:02}", "frame": None, "motion": action})
            graph["6"]["inputs"].update(width=1152, height=640, length=192, first_frame=["16", 0])
            graph["7"]["inputs"]["noise_seed"] = 2026111420 + index
            graph["15"]["inputs"]["filename_prefix"] = f"{inputs.name}/{name}"
            graph["16"] = {"class_type": "LoadImage", "inputs": {"image": f"{inputs.name}/{name}.png"}}
            job = {"prompt_id": None, "keyframe_sha256": hashlib.sha256(keyframe).hexdigest(), "workflow": graph}
            record.write_text(json.dumps(job, indent=2), encoding="utf-8")
            job["prompt_id"] = request("/prompt", {"prompt": graph})["prompt_id"]
            record.write_text(json.dumps(job, indent=2), encoding="utf-8")
        print("Generating", name, job["prompt_id"], flush=True)
        while time.monotonic() < deadline:
            finished = request(f"/history/{job['prompt_id']}").get(job["prompt_id"])
            if finished:
                if finished["status"]["status_str"] != "success":
                    raise RuntimeError(finished["status"])
                video = finished["outputs"]["15"]["images"][0]
                data = (home / "output" / video["subfolder"] / video["filename"]).read_bytes()
                temporary = output.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(output)
                print("Collected", name, len(data), flush=True)
                break
            time.sleep(8)
        else:
            raise TimeoutError(name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["voice", "motion"])
    args = parser.parse_args()
    (voice if args.stage == "voice" else motion)()
