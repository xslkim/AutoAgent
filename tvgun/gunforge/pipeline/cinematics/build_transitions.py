"""Render one original transition CG per adjacent playable scene."""
import json
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

from build_opening import FFMPEG, ff, probe, run

GUNFORGE = Path(__file__).resolve().parents[2]
ROOT = GUNFORGE / "games/g01/cinematics/transitions_original"
FPS = 30
SCENES = [
    ("alley", "巷口", "alley"),
    ("puddle", "巷口水洼", "puddle"),
    ("stall", "糖葫芦摊", "stall"),
    ("video_shop", "录像厅门口", "video_shop"),
    ("footbridge", "天桥", "footbridge"),
    ("plaza", "广场", "plaza"),
    ("ticket_office", "售票处", "cinema.ticket_office"),
    ("poster_hall", "海报长廊", "cinema.poster_hall"),
    ("auditorium", "观众席", "cinema.auditorium"),
    ("projection_booth", "放映室", "cinema.projection_booth"),
    ("screen_stage", "银幕前", "cinema.screen_stage"),
    ("waiting_room", "候车室", "waiting_room"),
    ("platform", "站台", "platform"),
    ("green_car", "绿皮车厢", "green_car"),
    ("lantern_base", "灯座", "lantern_base.lantern_base"),
    ("workbench", "爷爷的工作台", "lantern_base.workbench"),
]
# Mood, transition, seconds, cue note, foley texture (band in Hz), cue description.
EDITS = [
    ("wipeup", 3.2, 74, (450, 3100), "顺着灯光低头，看见水洼里的倒影"),
    ("smoothright", 3.4, 76, (650, 3800), "水洼的暖色反光接到摊口"),
    ("slideleft", 3.4, 69, (800, 4100), "从糖葫芦摊转向半开的卷帘门"),
    ("smoothup", 3.6, 76, (450, 2400), "离开录像厅，沿墙上到天桥"),
    ("dissolve", 3.7, 67, (330, 1600), "桥栏让开一片广场"),
    ("smoothleft", 5.0, 65, (95, 1300), "墨舞龙战后，广场暖灯接到旧影院的售票窗"),
    ("wiperight", 3.3, 68, (550, 2300), "越过售票窗，进入海报长廊"),
    ("smoothleft", 3.4, 65, (180, 1500), "海报边缘滑开，露出一排排座椅"),
    ("wipeup", 3.5, 72, (350, 2200), "沿过道抬头，找到放映室的光"),
    ("fade", 3.7, 77, (600, 3100), "放映机的光束接上银幕"),
    ("smoothright", 5.0, 62, (85, 720), "银幕暖光收束为候车室门口的灯"),
    ("slideright", 3.5, 70, (220, 1900), "穿出候车室，沿有顶站台前行"),
    ("smoothleft", 3.8, 67, (70, 500), "顺着车窗进入绿皮车厢"),
    ("fade", 4.2, 64, (160, 1050), "车窗斜光接上纸灯内层的光缝"),
    ("smoothdown", 5.0, 62, (140, 1600), "由灯座向外拉远，落到爷爷的工作台"),
]


def route_revision():
    review = GUNFORGE / "level_design/reviews/lantern_city_cast_build.json"
    revision = json.loads(review.read_text(encoding="utf-8"))["source_revision"]
    path = GUNFORGE / f"level_design/packages/paper.lantern_city_cast/revisions/{revision}/level.json"
    level = json.loads(path.read_text(encoding="utf-8"))
    route = []
    for section, value in sorted(level["sections"].items(), key=lambda item: item[1]["index"]):
        if "station" not in value:
            continue
        name = section if section in {entry[2] for entry in SCENES} else section.split(".")[0]
        if not route or name != route[-1]:
            route.append(name)
    assert route == [scene[2] for scene in SCENES], route
    return revision


def extract_art():
    art = ROOT / "art"
    art.mkdir(exist_ok=True)
    for index, (name, _, _) in enumerate(SCENES):
        with Image.open(ROOT / "atlases" / f"atlas_{index // 4 + 1}.png") as sheet:
            width, height = sheet.size
            quadrant = index % 4
            x, y = quadrant % 2, quadrant // 2
            # Trim the atlas seam so no pixels from neighboring images enter a shot.
            box = (x * width // 2 + 9, y * height // 2 + 9,
                   (x + 1) * width // 2 - 9, (y + 1) * height // 2 - 9)
            sheet.crop(box).convert("RGB").save(art / f"{name}.png")


def sound(number, seconds, note, band, center):
    rate = 48000
    time = np.arange(round(seconds * rate)) / rate
    rng = np.random.default_rng(202611140 + number)
    grain = sosfilt(butter(2, band, btype="bandpass", fs=rate, output="sos"),
                     rng.standard_normal(len(time)))
    motion = np.exp(-((time - center) / .44) ** 2)
    onset = np.maximum(time - center - .12, 0)
    phase = 2 * np.pi * 440 * 2 ** ((note - 69) / 12) * onset
    chime = .063 * (np.sin(phase) + .16 * np.sin(phase * 2.01))
    chime *= (1 - np.exp(-onset * 48)) * np.exp(-onset * 3.1)
    fade = np.clip(time * 5, 0, 1) * np.clip((seconds - time) * 4, 0, 1)
    stereo = np.column_stack((grain * motion * .035 + chime * .72,
                              grain * motion * .025 + chime * .86)) * fade[:, None]
    path = ROOT / "build/foley.wav"
    wavfile.write(path, rate, (stereo * 32767).astype(np.int16))
    return path


def camera(frames, incoming, reverse):
    ease = f"(1-cos(PI*on/{frames - 1}))/2"
    zoom = f"1.02+0.09*{ease}" if not incoming else f"1.13-0.08*{ease}"
    x = f".66-.30*{ease}" if reverse else f".34+.30*{ease}"
    return (f"scale=2400:1350:force_original_aspect_ratio=increase,crop=2400:1350,"
            f"zoompan=z='{zoom}':x='(iw-iw/zoom)*({x})':y='(ih-ih/zoom)*.48':"
            f"d={frames}:s=1280x720:fps={FPS},setsar=1,format=yuv444p")


def render(number, pair, edit):
    source, target = pair
    effect, seconds, note, band, description = edit
    overlap = .8 if seconds < 4 else 1.2
    frames = round(seconds * FPS)
    offset_frames = (frames - round(overlap * FPS)) // 2
    offset = offset_frames / FPS
    first_frames = offset_frames + round(overlap * FPS) + 1
    second_frames = frames - offset_frames + 1
    first = camera(first_frames, False, number % 2)
    second = camera(second_frames, True, number % 2)
    graph = (f"[0:v]{first}[a];[1:v]{second}[b];"
             f"[a][b]xfade=transition={effect}:duration={overlap}:offset={offset},"
             "curves=all='0/0 .45/.45 .7/.67 1/.74',format=yuv420p[v]")
    filename = f"{number:02}_{source[0]}_to_{target[0]}.mp4"
    path = ROOT / filename
    audio = sound(number, seconds, note, band, offset + .4 * overlap)
    ff("-filter_complex_threads", 2, "-i", ROOT / "art" / f"{source[0]}.png",
       "-i", ROOT / "art" / f"{target[0]}.png", "-i", audio, "-filter_complex", graph,
       "-map", "[v]", "-map", "2:a", "-frames:v", frames, "-c:v", "libx264",
       "-preset", "fast", "-crf", 18, "-threads", 4, "-c:a", "aac", "-b:a", "160k",
       "-movflags", "+faststart", path)
    streams = probe(path)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio_stream = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert int(video["nb_frames"]) == frames and video["avg_frame_rate"] == "30/1", video
    assert abs(float(audio_stream["duration"]) - seconds) < .075
    run([FFMPEG, "-v", "error", "-xerror", "-i", path, "-f", "null", "-"])
    print(filename, seconds, flush=True)
    return {"file": filename, "from": source[2], "to": target[2], "from_title": source[1],
            "to_title": target[1], "seconds": seconds, "frames": frames, "direction": description,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    revision = route_revision()
    (ROOT / "build").mkdir(exist_ok=True)
    extract_art()
    pairs = list(zip(SCENES, SCENES[1:]))
    assert len(pairs) == len(EDITS) == 15
    items = [render(number, pair, edit) for number, (pair, edit) in enumerate(zip(pairs, EDITS), 1)]
    manifest = {"campaign_revision": revision, "size": [1280, 720], "fps": FPS, "transitions": items}
    (ROOT / "transitions.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    concat = ROOT / "build/concat.txt"
    concat.write_text("".join(f"file '../{item['file']}'\n" for item in items), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", "-movflags", "+faststart",
       ROOT / "paper_lantern_city_transitions_review.mp4")
    run([FFMPEG, "-v", "error", "-xerror", "-i", ROOT / "paper_lantern_city_transitions_review.mp4",
         "-f", "null", "-"])


if __name__ == "__main__":
    main()
