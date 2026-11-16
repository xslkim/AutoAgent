"""Generate and mix the epilogue's two lines with the opening's fictional voice."""
import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

from opening_plan import ROOT as OPENING, VOICE_STYLE


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = OPENING / "audio/grandpa_original_design.wav"
OUTPUT = ROOT / "gunforge/games/g01/assets/cutscenes/epilogue/ending_wide_tape.wav"
LAMP = ROOT / "gunforge/level_design/generated/audio/combat_lamp.wav"
RATE = 48000
DURATION = 58.0
LINES = (
    ("city", 202611121, "夜市的灯，又亮了起来。", 9.0, 20.8),
    ("quote", 202611122, "灯亮着，就还在。", 49.0, 58.0),
)


def synthesize(model_dir, scratch):
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    import torch
    from voxcpm import VoxCPM

    sys.path.insert(0, str(model_dir))
    from tokenization_voxcpm2 import VoxCPM2Tokenizer

    torch.set_num_threads(4)
    original_dtype = torch.get_default_dtype()
    torch.set_default_dtype(torch.bfloat16)
    try:
        model = VoxCPM(voxcpm_model_path=str(model_dir), enable_denoiser=False, optimize=False, device="cuda:0")
    finally:
        torch.set_default_dtype(original_dtype)
    model.tts_model.text_tokenizer = VoxCPM2Tokenizer.from_pretrained(str(model_dir)).encode
    if model.tts_model.sample_rate != RATE:
        raise ValueError("Expected the opening voice model at 48 kHz")
    for name, seed, text, _, _ in LINES:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        voice = model.generate(text=f"({VOICE_STYLE}){text}", reference_wav_path=str(REFERENCE),
                               cfg_value=2.0, inference_timesteps=12, max_len=320,
                               normalize=False, denoise=False, retry_badcase=True)
        write_pcm(scratch / f"{name}_raw.wav", voice)


def write_pcm(path, audio):
    if not np.isfinite(audio).all() or np.max(np.abs(audio)) > 1:
        raise ValueError(f"Invalid or clipped audio: {path}")
    wavfile.write(path, RATE, np.rint(audio * 32767).astype(np.int16))


def bandpass(audio, lo, hi):
    return signal.sosfilt(signal.butter(2, (lo, hi), "bandpass", fs=RATE, output="sos"), audio, axis=0)


def mix(scratch):
    rng = np.random.default_rng(20261112)
    time = np.arange(round(DURATION * RATE)) / RATE
    tracks = np.zeros((len(time), 2))
    tape = bandpass(rng.standard_normal(len(time)), 1400, 6500) * .004
    rain = bandpass(rng.standard_normal(tracks.shape), 280, 4100) * .012
    tracks += rain + tape[:, None]

    def add(samples, start):
        offset = round(start * RATE)
        end = offset + len(samples)
        if end > len(tracks):
            raise ValueError("Cue exceeds the epilogue")
        tracks[offset:end] += samples[:, None]

    rate, lamp = wavfile.read(LAMP)
    if rate != 22050 or lamp.ndim != 1 or lamp.dtype != np.int16:
        raise ValueError("Unexpected format for the existing lamp cue")
    add(signal.resample_poly(lamp / 32768, 320, 147) * 10 ** (-10 / 20), 0)
    click_time = time[:round(.1 * RATE)]
    for when in (.4, 56.4):
        click = (rng.standard_normal(len(click_time)) * .019 + .032 * np.sin(2 * np.pi * 165 * click_time))
        add(click * np.exp(-75 * click_time) * np.minimum(click_time / .003, 1), when)

    # A quiet music-box reprise of the opening motif between the two spoken lines.
    note_time = time[:round(3.5 * RATE)]
    envelope = (1 - np.exp(-90 * note_time)) * np.exp(-note_time / 1.25)
    for when, pitch in ((13.7, 62), (16.0, 69), (18.5, 72), (22.0, 74), (26.0, 69),
                        (30.1, 65), (34.3, 69), (39.0, 72), (43.0, 74), (53.2, 62)):
        angle = 2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * note_time
        add(.034 * envelope * (np.sin(angle) + .24 * np.sin(2.003 * angle) * np.exp(-note_time / .4)), when)

    records = []
    for name, seed, text, start, limit in LINES:
        path = scratch / f"{name}_raw.wav"
        rate, raw = wavfile.read(path)
        if rate != RATE or raw.ndim != 1 or raw.dtype != np.int16 or not np.any(raw):
            raise ValueError(f"Expected mono 48 kHz voice PCM: {path}")
        end = start + len(raw) / RATE
        if end > limit:
            raise ValueError(f"Voice exceeds its subtitle interval: {name}")
        voice = bandpass(raw / 32768, 95, 7600)
        index = np.arange(len(voice))
        voice = np.interp(index + 6 * np.sin(2 * np.pi * .47 * index / RATE), index, voice)
        voice *= .113 / np.sqrt(np.mean(voice ** 2))
        voice = .62 * np.tanh(voice / .62)
        voice *= np.minimum(index / (RATE * .015), 1) * np.minimum((len(voice) - 1 - index) / (RATE * .08), 1)
        add(voice, start)
        records.append({"id": name, "seed": seed, "text": text, "start": start, "end": round(end, 3),
                        "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    tracks *= (np.minimum(time / .004, 1) * np.minimum((DURATION - time) / .8, 1))[:, None]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    write_pcm(OUTPUT, tracks)
    (scratch / "mix.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path, help="Directory for intermediate voice WAVs")
    parser.add_argument("--model-dir", type=Path, help="Local VoxCPM2 weights; omit to mix already generated voice WAVs")
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    if args.model_dir is not None:
        synthesize(args.model_dir, args.scratch)
    mix(args.scratch)


if __name__ == "__main__":
    main()
