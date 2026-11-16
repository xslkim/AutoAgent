"""Export five spoiler-free Paper Lantern City promotional edits."""
import json
import os
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from build_opening import FFMPEG, ff, probe, run
from build_transitions import ROOT as TRANSITIONS

GAME = TRANSITIONS.parents[1]
ROOT = GAME / "cinematics/promos"
FRAMES = GAME / "reports/art/T16/cast/frames"
OPENING = GAME / "cinematics/opening_original/paper_lantern_city_opening_clean.mp4"
ENDING = GAME / "cinematics/ending_original/paper_lantern_city_ending_clean.mp4"

# Image IDs refer to actual game captures. tNN refers to a separately produced transition CG.
# Each edit starts with a hook and finishes with its own title card over moving art.
EDITS = [
    ("01_overview", "三关总览", [
        ("opening:1", 7, "爷爷把一座城，刻进了纸里。"),
        ("opening:28", 7, "一滴墨，顺着纸纤维渗了进去。"),
        ("station_1_alley", 6, "夜市 · 点亮巷灯"),
        ("t06", 5, ""), ("station_9_projection_booth", 6, "旧影院 · 恢复放映的光"),
        ("t11", 5, ""), ("station_12_platform", 6, "火车站 · 穿过站台与绿皮车厢"),
        ("opening:74", 7, "用光净墨，护住纸居民。"),
        ("ending:35", 7, "纸灯城　｜　三关光枪街机冒险"),
    ]),
    ("02_night_market", "夜市", [
        ("opening:54", 8, "夜市刚开张，墨已经爬上了巷灯。"),
        ("station_1_alley", 6, "先点灯，再净墨。"),
        ("t01", 4, ""), ("t02", 4, ""), ("station_2_stall", 7, "居民是要救的人。瞄准他们身上的墨。"),
        ("t03", 4, ""), ("t04", 4, ""), ("subject_bridge_warning", 6, "沿录像厅和天桥，继续往前。"),
        ("subject_dragon", 7, "在广场遇见墨舞龙。"),
        ("t05", 5, "纸灯城　｜　第一关 · 夜市"),
    ]),
    ("03_cinema", "旧影院", [
        ("ending:16", 7, "旧影院的放映机，曾照亮整条街。"),
        ("t06", 5, ""), ("t07", 4, ""), ("t08", 4, ""),
        ("station_8_auditorium", 6, "从售票窗走到空无一人的观众席。"),
        ("t09", 4, ""), ("station_9_projection_booth", 6, "三路光源，三盘墨渍。"),
        ("t10", 4, ""), ("subject_screen_shadow", 7, "清开三盘墨，银幕的影核才会显现。"),
        ("ending:17", 6, "纸灯城　｜　第二关 · 旧影院"),
    ]),
    ("04_train_station", "火车站", [
        ("ending:25", 8, "站台的灯还亮着。末班车就要离开。"),
        ("t11", 5, ""), ("station_11_waiting_room", 6, "候车室里，时钟还在走。"),
        ("t12", 4, ""), ("station_12_platform", 7, "在站台护住还没离开的人。"),
        ("t13", 4, ""), ("station_13_green_car", 7, "穿过绿皮车厢，找出墨的来处。"),
        ("t14", 5, ""), ("station_14_lantern_base", 6, "纸灯城　｜　第三关 · 火车站"),
    ]),
    ("05_paper_art", "纸雕美术", [
        ("opening:2", 7, "近处是裁开的纸，远处是透过纸的光。"),
        ("opening:36", 6, "墨沿纸的纹理往里渗。"),
        ("ending:7", 7, "夜市用暖杏，像摊前一直留着的灯。"),
        ("ending:16", 7, "影院用紫红和一束窄窄的暖光。"),
        ("ending:24", 8, "站台用青绿，车窗里藏着一格格琥珀色。"),
        ("opening:66", 6, "墨鸦的胸口，只留一点朱砂。"),
        ("ending:34", 9, "纸灯城　｜　一盏灯里的九十年代"),
    ]),
]

FRAME_FILTER = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1"


def ass_time(seconds):
    ticks = round(seconds * 100)
    return f"{ticks // 360000}:{ticks // 6000 % 60:02}:{ticks // 100 % 60:02}.{ticks % 100:02}"


def score(path, duration, index):
    rate = 48000
    time = np.arange(round(duration * rate)) / rate
    stereo = np.zeros((len(time), 2), dtype=np.float32)
    motifs = [(50, 57, 60, 64), (50, 57, 62, 65), (48, 55, 60, 63),
              (43, 55, 58, 62), (50, 57, 60, 69)]
    notes = motifs[index]
    beat = [1.12, 1.02, 1.25, 1.07, 1.46][index]
    for i, start in enumerate(np.arange(.12, duration, beat)):
        offset = round(start * rate)
        clock = time[:min(round(4 * rate), len(time) - offset)]
        phase = 2 * np.pi * 440 * 2 ** ((notes[i % 4] - 69 + (12 if i % 8 in (3, 6) else 0)) / 12) * clock
        tone = (np.sin(phase) + .16 * np.sin(phase * 2.01)) * (1 - np.exp(-clock * 45)) * np.exp(-clock / .96)
        stereo[offset:offset+len(clock)] += tone[:, None] * ([.077, .057] if i % 2 else [.057, .077])
    for midi in (notes[0] - 12, notes[1] - 12):
        phase = 2 * np.pi * 440 * 2 ** ((midi - 69) / 12) * time
        stereo += (.026 * np.sin(phase) * (.45 + .55 * np.sin(np.pi * time / (beat * 8)) ** 2))[:, None]
    fades = (np.minimum(time / .4, 1) * np.minimum((duration - time) / 1.5, 1))[:, None]
    wavfile.write(path, rate, (stereo * fades * 32767).astype(np.int16))


def clip(target, source, duration, i):
    if ":" in source:
        label, timestamp = source.split(":")
        args = ["-ss", timestamp, "-i", OPENING if label == "opening" else ENDING]
        vf = FRAME_FILTER + ",fps=30,tpad=stop_mode=clone:stop_duration=1"
    elif source.startswith("t") and source[1:].isdigit():
        path, = TRANSITIONS.glob(source[1:] + "_*.mp4")
        args = ["-i", path]
        vf = FRAME_FILTER + ",fps=30,tpad=stop_mode=clone:stop_duration=2"
    else:
        caption_source = FRAMES / f"{source}.jpg"
        args = ["-i", caption_source]
        frames = duration * 30
        zoom = f"1.025+0.06*(1-cos(PI*on/{frames-1}))/2"
        anchor = .42 if i % 2 else .58
        vf = (f"scale=2400:1350:force_original_aspect_ratio=increase,crop=2400:1350,"
              f"zoompan=z='{zoom}':x='(iw-iw/zoom)*{anchor}':y='(ih-ih/zoom)*.5':"
              f"d={frames}:s=1280x720:fps=30,setsar=1")
    ff("-filter_threads", 2, *args, "-vf", vf + ",format=yuv420p", "-frames:v", duration * 30,
       "-an", "-c:v", "libx264", "-preset", "fast", "-crf", 18, "-threads", 4,
       "-video_track_timescale", 90000, target)
    assert int(probe(target)["streams"][0]["nb_frames"]) == duration * 30, source


def render(index, name, title, edit):
    work = ROOT / "build" / name
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(work)
    captions = []
    duration = 0
    names = []
    for i, (source, seconds, text) in enumerate(edit):
        file = Path(f"shot_{i:02}.mp4")
        clip(file, source, seconds, i)
        names.append(file.name)
        if text:
            style = "Title" if i == len(edit) - 1 else "Body"
            at = duration + (.7 if style == "Title" else .38)
            end = duration + seconds - .28
            captions.append(f"Dialogue: 0,{ass_time(at)},{ass_time(end)},{style},,0,0,0,,{{\\fad(180,220)}}{text}")
        duration += seconds
    inputs = [arg for file in names for arg in ("-i", file)]
    normalized = "".join(f"[{i}:v]setpts=PTS-STARTPTS[v{i}];" for i in range(len(names)))
    joined = "".join(f"[v{i}]" for i in range(len(names))) + f"concat=n={len(names)}:v=1:a=0[out]"
    ff("-filter_complex_threads", 2, *inputs, "-filter_complex", normalized + joined,
       "-map", "[out]", "-c:v", "libx264", "-preset", "fast", "-crf", 16, "-threads", 4, "picture.mp4")
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Body,Noto Serif SC,31,&H00E5D8C7,&H00E5D8C7,&H440E0C16,&H440E0C16,0,0,0,0,100,100,1,0,3,8,0,2,42,42,58,1
Style: Title,Noto Serif SC,54,&H00A7D5EF,&H00A7D5EF,&H4D140C18,&H4D140C18,-1,0,0,0,100,100,4,0,3,15,0,5,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path("titles.ass").write_text(header + "\n".join(captions) + "\n", encoding="utf-8")
    score(Path("score.wav"), duration, index)
    destination = ROOT / f"{name}.mp4"
    ff("-i", "picture.mp4", "-i", "score.wav", "-vf",
       f"setpts=N/(30*TB),fps=30,ass=titles.ass,fade=t=in:d=0.35,fade=t=out:st={duration-.55}:d=0.55",
       "-af", "loudnorm=I=-19:TP=-2:LRA=9", "-ar", 48000, "-c:a", "aac", "-b:a", "192k",
       "-c:v", "libx264", "-preset", "fast", "-crf", 18, "-threads", 6, "-movflags", "+faststart", destination)
    streams = probe(destination)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    audio = next(s for s in streams if s["codec_type"] == "audio")
    assert int(video["nb_frames"]) == duration * 30 and video["avg_frame_rate"] == "30/1"
    assert abs(float(audio["duration"]) - duration) < .1 and duration < 120
    run([FFMPEG, "-v", "error", "-xerror", "-i", destination, "-f", "null", "-"])
    print(name, duration, flush=True)
    return {"file": destination.name, "title": title, "duration_seconds": duration,
            "shots": [{"source": s, "seconds": d, "text": t} for s, d, t in edit]}


if __name__ == "__main__":
    results = [render(i, *edit) for i, edit in enumerate(EDITS)]
    (ROOT / "promos.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
