"""Collect isolated production-player cutscene evidence for the current campaign."""
import argparse
from pathlib import Path
import wave

from PIL import Image, ImageDraw, ImageFont, ImageOps

from artlib import GAME, digest, write_json
from t10_preview import read_json, save_jpg

CAST = GAME / "reports/art/T16/cast"
OUTPUT = CAST / "cutscene_player"
REFERENCE = GAME / "reports/art/T15/wide_checks.json"
OPENING = Path("gunforge/games/g01/cinematics/opening_original")
PLAYER = "gunforge/framework/tools/level_player.gd"
TAPE = "lantern_base.ending.tape"


def preview_sheet(captures, font, output):
    width, height = 444, 250
    margin, gap, caption = 16, 12, 24
    row_height = height + caption + gap
    page = Image.new("RGB", (2 * margin + 2 * width + gap, 2 * margin + 2 * row_height), "#181c28")
    draw = ImageDraw.Draw(page)
    previews = (("opening_caption", "开场字幕"), ("ending_voice_0", "夜市旁白"),
                ("ending_voice_2", "工作台旁白"), ("ending_result", "自然播放后的结算"))
    sources = {}
    for index, (name, label) in enumerate(previews):
        path = captures / "natural" / f"{name}.png"
        x = margin + (index % 2) * (width + gap)
        y = margin + (index // 2) * row_height
        with Image.open(path) as source:
            image = ImageOps.contain(source.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
        draw.text((x, y), label, font=font, fill="#e7e2d6")
        page.paste(image, (x + (width - image.width) // 2, y + caption + (height - image.height) // 2))
        sources[name] = digest(path)
    save_jpg(page, output)
    return sources


def verified_media(stage, build, manifest):
    hashes = {row["path"]: row["sha256"] for row in manifest["resources"] + manifest["opening_files"] + manifest["player_files"]}
    resource = build["level"]["cues"][TAPE]["resource"]
    tape = build["level"]["resources"][resource]["path"]
    paths = [PLAYER, (OPENING / "paper_lantern_city_opening_game.ogv").as_posix(),
             (OPENING / "opening_subtitles.json").as_posix(), tape]
    actual = {path: digest(stage / path) for path in paths}
    if any(sha != hashes[path] for path, sha in actual.items()):
        raise ValueError("The staged player or cutscene media differs from the cast manifest")
    reference = read_json(REFERENCE)["audio"]
    if reference["sha256"] != actual[tape]:
        raise ValueError("The staged tape differs from the mix with the reviewed voice timings")
    with wave.open(str(stage / tape)) as stream:
        audio = {"channels": stream.getnchannels(), "sample_rate": stream.getframerate(),
                 "duration_seconds": stream.getnframes() / stream.getframerate(),
                 "sample_width_bytes": stream.getsampwidth(), "sha256": actual[tape],
                 "reviewed_voice_intervals": [{"start": row["start"], "end": row["end"], "text": row["text"]}
                                               for row in reference["lines"]]}
    return actual, audio


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", type=Path)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--font", default="C:/Windows/Fonts/msyh.ttc")
    args = parser.parse_args()
    compiled = args.stage / "level.json"
    build = read_json(compiled)
    manifest = read_json(CAST / "candidate_manifest.json")
    compiled_hash = digest(compiled)
    if manifest["build_id"] != build["build_id"] or manifest["compiled_sha256"] != compiled_hash:
        raise ValueError("The staged campaign differs from the cast manifest")
    runs = {path: read_json(args.captures / path / "checks.json") for path in ("keyboard", "udp", "natural")}
    if any(not row["passed"] or row["build_id"] != build["build_id"] or row["source_revision"] != build["source_revision"]
           or row["opening"]["path"] != path for path, row in runs.items()):
        raise ValueError("Expected passing cutscene runs from the same isolated campaign")
    media, tape = verified_media(args.stage, build, manifest)
    track = read_json(args.stage / OPENING / "opening_subtitles.json")
    natural = runs["natural"]
    opening = natural["opening"]["caption_samples"]
    if len(opening) != len(track) or any(sample["text"] != line["text"] or not line["start"] <= sample["media_seconds"] < line["end"]
                                         for sample, line in zip(opening, track, strict=True)):
        raise ValueError("The runtime opening captions differ from the staged track")
    ending = natural["natural_ending"]
    expected_voice = [time for line in tape["reviewed_voice_intervals"] for time in (line["start"], line["end"])]
    if [row["marker_seconds"] for row in ending["voice_samples"]] != expected_voice:
        raise ValueError("Expected both endpoints of both staged voice lines")
    if len(natural["skips"]) != 4 or not natural["retry"] or any(
            row["counters"] != ending["counters"] or row["result"] != ending["result"] or not row["tape_stopped"]
            for row in natural["skips"]):
        raise ValueError("The four skip routes and natural result must agree")
    args.output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(args.font, 15)
    preview = args.output / "cutscene_frames.jpg"
    sources = preview_sheet(args.captures, font, preview)
    summary = {"opening_caption_count": len(opening), "opening_skip_paths": 2, "ending_skip_paths": len(natural["skips"]),
               "voice_markers_in_caption_window": len(expected_voice), "ending_duration_seconds": ending["duration_seconds"],
               "max_sampled_drift_seconds": max(abs(row["drift_seconds"]) for row in ending["voice_samples"])}
    write_json(args.output / "checks.json", {"build_id": build["build_id"], "compiled_sha256": compiled_hash,
               "media_sha256": media, "tape": tape, "runs": runs, "summary": summary, "preview_sha256": digest(preview),
               "source_frames_sha256": sources, "physical_audio_and_lightgun": "pending"})
    print(summary)


if __name__ == "__main__":
    main()
