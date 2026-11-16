"""Run this from WSL against the local H3 ComfyUI instance."""
import hashlib
import json
import time
from pathlib import Path

from ending_plan import ROOT
from generate_opening_h3 import request, workflow

MOTIONS = {
    "ink": "Locked camera. The small suspended black brush-stroke fragment softens into a few curling wisps, falls gently into the inkstone, and is completely gone by the last second. One tiny ripple settles. Keep every paper prop, exposure and dark teal night background unchanged. No new characters, light sources, letters or flashes. Quiet.",
    "train": "Locked camera under the station canopy, exactly this dark nocturnal cut-paper scene. Green train moves slowly down its existing track toward the right and away from camera, its windows stay muted amber. Station attendant on the platform raises a hand in a small farewell. Preserve the architecture and fixed indigo night exposure. No sun, flashes, text or smoke covering the picture.",
    "cinema": "Locked composition, stable low exposure. The two reels on the right rotate steadily in place, a few dust particles drift across the thin amber projector beam. On the screen the existing dark paper rooftops stay in place with only subtle projector flicker. Keep the projectionist facing away, preserve his silhouette and the empty seats. Quiet paper-cut miniature. No new people, text, cut, flash or change of scene.",
    "tape": "Quiet locked close-up of this exact paper cassette recorder. Only the two exposed tape spools rotate slowly clockwise and a subtle amount of warm lantern light breathes in the distant background. Spools and every other object remain their original shapes. No new lights, no added objects, no text, no hands, no exposure change. No movement except these details.",
}


def main():
    input_dir = Path("/home/xsl/aivideo/ComfyUI/input/g01_ending_20261114")
    output_dir = input_dir.parents[1] / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    shots = ROOT / "motion"
    shots.mkdir(parents=True, exist_ok=True)
    for index, (name, motion) in enumerate(MOTIONS.items(), 1):
        source = ROOT / "keyframes" / f"{name}.png"
        target = shots / f"{name}.mp4"
        record = shots / f"{name}_job.json"
        if target.exists():
            continue
        if record.exists():
            job = json.loads(record.read_text(encoding="utf-8"))
            if not job.get("prompt_id"):
                raise RuntimeError(f"Unknown submission state for {name}")
        else:
            (input_dir / source.name).write_bytes(source.read_bytes())
            prompt = workflow({"id": f"s{index:02}", "frame": None, "motion": motion})
            prompt["6"]["inputs"].update(width=960, height=544, length=124, first_frame=["16", 0])
            prompt["7"]["inputs"]["noise_seed"] = 2026111400 + index
            prompt["15"]["inputs"]["filename_prefix"] = f"g01_ending_20261114/{name}"
            prompt["16"] = {"class_type": "LoadImage", "inputs": {"image": f"{input_dir.name}/{source.name}"}}
            job = {"prompt_id": None, "workflow": prompt, "image_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            record.write_text(json.dumps(job, indent=2), encoding="utf-8")
            job["prompt_id"] = request("/prompt", {"prompt": prompt})["prompt_id"]
            record.write_text(json.dumps(job, indent=2), encoding="utf-8")
        print(name, job["prompt_id"], flush=True)
        while True:
            item = request(f"/history/{job['prompt_id']}").get(job["prompt_id"])
            if item:
                if item["status"]["status_str"] != "success":
                    raise RuntimeError(item["status"])
                result = item["outputs"]["15"]["images"][0]
                source_video = output_dir / result["subfolder"] / result["filename"]
                target.write_bytes(source_video.read_bytes())
                print("Collected", target.name, flush=True)
                break
            time.sleep(10)


if __name__ == "__main__":
    main()
