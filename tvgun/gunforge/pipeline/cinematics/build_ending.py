"""Render the 60-second epilogue and its standalone captions."""
import argparse
import hashlib
import json
import os
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

from build_opening import FFMPEG, ff, probe, run, srt_time
from ending_plan import FPS, LINES, OVERLAP, ROOT, SHOTS, SIZE

RATE = 48000
DURATION = SHOTS[-1][2]
FRAME_FILTER = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1"


def mix_sound():
    audio = ROOT / "audio"
    scratch = ROOT / "build"
    rng = np.random.default_rng(20261114)
    samples = int(DURATION * RATE)
    score = np.zeros((samples, 2), dtype=np.float32)
    effects = np.zeros_like(score)
    voice = np.zeros_like(score)

    def add(track, at, wave, pan=0):
        start = round(at * RATE)
        end = min(start + len(wave), len(track))
        track[start:end] += wave[:end - start, None] * np.sqrt([(1 - pan) / 2, (1 + pan) / 2])

    def note(midi, length, gain):
        time = np.arange(round(length * RATE)) / RATE
        phase = 2 * np.pi * 440 * 2 ** ((midi - 69) / 12) * time
        envelope = (1 - np.exp(-time * 42)) * np.exp(-time / 1.3)
        return gain * envelope * (np.sin(phase) + 0.16 * np.sin(2.01 * phase) * np.exp(-time * 2))

    melody = [(1.8, 62), (4.8, 69), (7, 72), (11.7, 74), (14.2, 69), (16.3, 65), (21.7, 69),
              (24.6, 67), (29.8, 70), (32, 74), (35, 62), (37, 69), (42.4, 72), (44.4, 74),
              (50.9, 69), (53.4, 65), (55, 64), (56.2, 62)]
    for index, (at, midi) in enumerate(melody):
        add(score, at, note(midi, 4, 0.044), 0.24 * np.sin(index))
    for at, pitches in [(5, (38, 45)), (14, (41, 48)), (24, (43, 50)), (34, (38, 45)), (49, (38, 45))]:
        time = np.arange(10 * RATE) / RATE
        for midi in pitches:
            phase = 2 * np.pi * 440 * 2 ** ((midi - 69) / 12) * time
            add(score, at, 0.013 * np.sin(phase + 0.03 * np.sin(time * 3)) * np.sin(np.pi * time / 10) ** 2)

    def texture(at, duration, low, high, gain, pan, pulse=0):
        time = np.arange(round(duration * RATE)) / RATE
        noise = sosfilt(butter(2, [low, high], btype="bandpass", fs=RATE, output="sos"),
                        rng.standard_normal(len(time)))
        envelope = np.sin(np.pi * time / duration) ** 2
        if pulse:
            envelope *= 0.55 + 0.45 * np.sin(2 * np.pi * pulse * time)
        add(effects, at, noise * envelope * gain, pan)

    texture(0, 5, 230, 2400, .021, -.12)
    texture(6, 10, 500, 5000, .013, -.27, 1.4)
    texture(15, 9, 350, 2000, .020, .26, 19)
    texture(23, 12, 65, 310, .085, .28, 6)
    texture(45, 10, 1700, 6500, .012, -.15)
    add(effects, 9, note(92, .8, .024), -.4)
    add(effects, 28, note(48, 2.8, .023), .22)
    click_time = np.arange(4800) / RATE
    add(effects, 52.3, rng.standard_normal(len(click_time)) * np.exp(-100 * click_time) * .085, -.18)

    captions = []
    duck = np.ones(samples, dtype=np.float32)
    for index, (at, text) in enumerate(LINES, 1):
        normalized = scratch / f"voice_{index:02}.wav"
        ff("-i", audio / normalized.name, "-af",
           "atempo=0.94,highpass=f=125,lowpass=f=6200,loudnorm=I=-19:TP=-3:LRA=7",
           "-ar", RATE, "-ac", 1, normalized)
        rate, data = wavfile.read(normalized)
        assert rate == RATE
        end = at + len(data) / RATE + .16
        assert end < (LINES[index][0] if index < len(LINES) else 53.7)
        add(voice, at, np.tanh(data.astype(np.float32) / 32768 * 1.15))
        captions.append((at, end, text))
        duck[round((at - .2) * RATE):round((end + .2) * RATE)] = .48

    score *= sosfilt(butter(1, 3, fs=RATE, output="sos"), duck, zi=np.array([[1., 0.]]))[0][:, None]
    time = np.arange(samples) / RATE
    fade = (np.minimum(time / .55, 1) * np.minimum((DURATION - time) / 1.8, 1))[:, None]
    for name, data in [("score", score), ("foley", effects), ("narration", voice)]:
        wavfile.write(audio / f"{name}.wav", RATE, np.round(np.clip(data * fade, -.98, .98) * 32767).astype(np.int16))
    premix = scratch / "premix.wav"
    wavfile.write(premix, RATE, np.round(np.clip((score + effects + voice) * fade, -.98, .98) * 32767).astype(np.int16))
    ff("-i", premix, "-af", "loudnorm=I=-18:TP=-1.5:LRA=11", "-ar", RATE, audio / "ending_mix.wav")
    (ROOT / "ending_zh.srt").write_text(
        "\n\n".join(f"{i}\n{srt_time(at)} --> {srt_time(end)}\n{text}"
                    for i, (at, end, text) in enumerate(captions, 1)) + "\n", encoding="utf-8")


def render_picture(motion_names):
    scratch = ROOT / "build"
    # Leave a little headroom in the brightest ink reflections and practical lights.
    grade = "curves=all='0/0 .45/.45 .70/.67 1/.74'"
    shots = []
    for index, (name, start, end, _) in enumerate(SHOTS):
        frames = round((end - start) * FPS)
        target = scratch / f"{name}.mp4"
        if name in motion_names:
            source = ROOT / "motion" / f"{name}.mp4"
            stream = next(s for s in probe(source)["streams"] if s["codec_type"] == "video")
            speed = (end - start) / float(stream["duration"])
            filters = f"setpts=(PTS-STARTPTS)*{speed:.9f},fps=30,tpad=stop_mode=clone:stop_duration=1,{FRAME_FILTER}"
            args = ["-i", source]
        else:
            source = ROOT / "keyframes" / f"{name}.png"
            step = f"(1-cos(PI*on/{frames - 1}))/2"
            zoom = f"1.095-0.073*{step}" if name in {"city", "desk"} else f"1.025+0.055*{step}"
            x = f"(iw-iw/zoom)*({'.41+.15' if index % 2 else '.57-.12'}*{step})"
            filters = (f"scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
                       f"zoompan=z='{zoom}':x='{x}':y='(ih-ih/zoom)*.51':d={frames}:s=1920x1080:fps=30,setsar=1")
            args = ["-i", source]
        if index == 0:
            filters += ",fade=t=in:d=0.55"
        if index == len(SHOTS) - 1:
            filters += f",fade=t=out:st={end-start-1.6}:d=1.6"
        ff("-filter_threads", 3, *args, "-vf", filters + f",{grade},format=yuv420p",
           "-frames:v", frames, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", 16, "-threads", 5, target)
        shots.append(target)
        print("Rendered", name, flush=True)

    inputs = [arg for path in shots for arg in ("-i", path)]
    graph = []
    last = "[0:v]"
    for index, (_, start, _, _) in enumerate(SHOTS[1:], 1):
        output = f"[v{index}]"
        graph.append(f"{last}[{index}:v]xfade=transition=fade:duration={OVERLAP}:offset={start}{output}")
        last = output
    graph.append(f"{last}format=yuv420p[picture]")
    ff("-filter_complex_threads", 2, *inputs, "-filter_complex", ";".join(graph),
       "-map", "[picture]", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", 16, "-threads", 5,
       scratch / "picture.mp4")


def export():
    os.chdir(ROOT)
    picture = ROOT / "build/picture.mp4"
    clean = ROOT / "paper_lantern_city_ending_clean.mp4"
    final = ROOT / "paper_lantern_city_ending.mp4"
    ff("-i", picture, "-i", ROOT / "audio/ending_mix.wav", "-map", "0:v", "-map", "1:a",
       "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", clean)
    style = "FontName=Noto Serif SC,FontSize=17,PrimaryColour=&H00D6C4B8,OutlineColour=&H661A1414,BorderStyle=3,Outline=4,Shadow=0,MarginV=27"
    ff("-i", clean, "-vf", f"subtitles=ending_zh.srt:force_style='{style}'", "-c:a", "copy",
       "-c:v", "libx264", "-preset", "fast", "-crf", 18, "-threads", 6, "-movflags", "+faststart", final)
    for path in (clean, final):
        media = probe(path)
        video = next(s for s in media["streams"] if s["codec_type"] == "video")
        audio = next(s for s in media["streams"] if s["codec_type"] == "audio")
        assert (video["width"], video["height"]) == SIZE
        assert video["avg_frame_rate"] == "30/1" and int(video["nb_frames"]) == DURATION * FPS
        assert abs(float(audio["duration"]) - DURATION) < .05
        run([FFMPEG, "-v", "error", "-xerror", "-i", path, "-f", "null", "-"])
    report = {"duration_seconds": DURATION, "frames": int(DURATION * FPS), "size": SIZE, "fps": FPS,
              "sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (clean, final)}}
    sample = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(clean), "-vf",
                                      "fps=1,scale=320:180", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    rgb = np.frombuffer(sample, dtype=np.uint8).reshape(-1, 180, 320, 3)
    luminance = (rgb @ np.array([.299, .587, .114])) / 255
    report["luminance_scan"] = {"samples": len(rgb), "max_y_prime": float(luminance.max()),
                                "fraction_above_75_percent": float((luminance > .75).mean())}
    loudness = subprocess.run([FFMPEG, "-hide_banner", "-i", str(final), "-af",
                               "loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                              capture_output=True, text=True, check=True).stderr
    levels = json.loads(loudness[loudness.rfind("{"):loudness.rfind("}") + 1])
    report["audio"] = {"integrated_lufs": float(levels["input_i"]), "true_peak_dbtp": float(levels["input_tp"])}
    assert report["audio"]["true_peak_dbtp"] < -1
    (ROOT / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion", nargs="*", default=["ink", "cinema", "train", "tape"],
                        choices=["ink", "cinema", "train", "tape"])
    args = parser.parse_args()
    (ROOT / "build").mkdir(exist_ok=True)
    mix_sound()
    render_picture(set(args.motion))
    export()


if __name__ == "__main__":
    main()
