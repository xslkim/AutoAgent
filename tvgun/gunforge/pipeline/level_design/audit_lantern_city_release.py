"""Inventory and stage the compiled Paper Lantern City candidate for T16 review."""
import argparse
from collections import Counter
import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import wave

from PIL import Image

from cast_color_images import COPIES as CAST_RGBA8_COPIES, verify_rgba8_source
from cast_edge_fill import COPIES as CAST_EDGE_COPIES, verify_edge_fill_source
from compiler import ROOT, digest, payload_digest, read, read_package
from freeze_baseline import dump


GAME = Path("gunforge/games/g01")
ASSETS = GAME / "assets"
ART_REPORTS = GAME / "reports/art"
OPENING = GAME / "cinematics/opening_original"
FRAMEWORK = Path("gunforge/framework")
GENERATED = Path("gunforge/level_design/generated")
CATALOG = Path("gunforge/level_design/specs/capabilities-v1.json")
PACKAGE = "paper.lantern_city_epilogue"
OPENING_FILES = {"paper_lantern_city_opening_game.ogv": "video", "opening_subtitles.json": "metadata"}
ALLEY_MANIFEST = ASSETS / "stations/g01_st_l1_01_alley/manifest.json"
GODOT_REFERENCES = re.compile(r'(?:preload\(|load\(|extends\s+)\s*"res://([^"\n]+)"')


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def local_file(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in str(path) or ":" in str(path):
        raise ValueError(f"Invalid inventory path: {relative}")
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f"Missing file or path outside the repository: {relative}")
    return target


def file_record(root, relative, expected=None):
    path = local_file(root, relative)
    checksum = sha256(path)
    if expected is not None and checksum != expected:
        raise ValueError(f"SHA-256 mismatch: {relative}")
    return {"path": Path(relative).as_posix(), "sha256": checksum, "bytes": path.stat().st_size}


def verify_build(compiled, package=PACKAGE):
    if compiled.get("format") != "gunforge-compiled-level-v1" or compiled["level"]["id"] != package:
        raise ValueError(f"Expected a compiled {package} candidate")
    if compiled.get("payload_algorithm") != "numeric-f64le-v1":
        raise ValueError("Unrecognized payload checksum algorithm")
    payload = {key: compiled[key] for key in ("level", "source_map", "source_manifest")}
    identity = {key: compiled[key] for key in ("source_revision", "tool_lock", "payload_sha256")}
    if (payload_digest(payload) != compiled["payload_sha256"]
            or digest(compiled["source_manifest"]) != compiled["source_revision"]
            or digest(identity) != compiled["build_id"]):
        raise ValueError("Compiled identity or payload checksum mismatch")


def file_format(path, kind):
    if kind == "image":
        with Image.open(path) as image:
            image.load()
            return {"format": image.format, "mode": image.mode, "pixels": list(image.size)}
    if kind == "audio":
        with wave.open(str(path), "rb") as audio:
            frames, rate, width, channels = (audio.getnframes(), audio.getframerate(),
                                             audio.getsampwidth(), audio.getnchannels())
            if frames <= 0 or len(audio.readframes(frames)) != frames * width * channels:
                raise ValueError(f"Truncated WAV: {path}")
            return {"format": "WAV PCM", "channels": channels, "sample_rate": rate,
                    "bits_per_sample": width * 8, "seconds": frames / rate}
    if kind == "metadata":
        data = read(path)
        if not isinstance(data, (dict, list)):
            raise ValueError(f"Expected structured metadata: {path}")
        return {"format": "JSON"}
    raise ValueError(f"Unrecognized compiled resource kind: {kind}")


def bindings(level):
    found = {key: [] for key in level["resources"]}

    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}/{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}/{index}")
        elif isinstance(value, str) and value in found:
            found[value].append(path)

    for key, value in level.items():
        if key != "resources":
            visit(value, "/" + key)
    return found


def provenance(relative):
    if relative.is_relative_to(ART_REPORTS):
        task = relative.relative_to(ART_REPORTS).parts[0]
        return ART_REPORTS / task / "report.md"
    if relative.is_relative_to(GENERATED):
        group = relative.relative_to(GENERATED).parts[0]
        names = {"audio": "combat_cues.py", "workbench_boss": "build_workbench_boss.py",
                 "platform_contrast": "build_platform.py", "green_car_contrast": "build_green_car.py",
                 "waiting_room_contrast": "build_waiting_room.py"}
        if group == "audio" and relative.name.startswith("station_"):
            names[group] = "station_audio.py"
        if group == "workbench_boss" and relative.name.startswith("ending_"):
            names[group] = "build_workbench_ending.py"
        return Path("gunforge/pipeline/level_design") / names.get(group, f"build_{group}.py")
    if relative.is_relative_to(FRAMEWORK / "runtime") or relative.is_relative_to(ALLEY_MANIFEST.parent):
        return ALLEY_MANIFEST
    if relative.is_relative_to(OPENING):
        return OPENING / "asset_manifest.json"
    if relative == ASSETS / "cutscenes/epilogue/city_wide_v1.png":
        return ART_REPORTS / "T15/city_wide_generation.json"
    if relative == ASSETS / "cutscenes/epilogue/ending_wide_tape.wav":
        return ART_REPORTS / "T15/wide_checks.json"
    if relative == ASSETS / "cutscenes/epilogue/ending_tape.wav":
        return ART_REPORTS / "T15/audio_checks.json"
    if relative.is_relative_to(Path("art2d/assets/paper_lantern_video")):
        return ART_REPORTS / "T10/report.md"
    if relative == ASSETS / "ui/hud_layout.json":
        return Path("docs/ART_PLAN_PAPER_LANTERN_CITY.md")
    return None


def opening_inventory(root):
    records = []
    origin = OPENING / "asset_manifest.json"
    manifest = read(root / origin)
    entries = {entry["path"]: entry for entry in manifest["files"]}
    captions = read(local_file(root, OPENING / "opening_subtitles.json"))
    if not isinstance(captions, list) or not captions:
        raise ValueError("Opening requires a nonempty subtitle list")
    previous_end = 0
    for caption in captions:
        start, end, text = (caption[key] for key in ("start", "end", "text"))
        if not (previous_end <= start < end <= 90 and text.strip()):
            raise ValueError("Opening subtitle order or interval is invalid")
        previous_end = end
    for name, kind in OPENING_FILES.items():
        record = file_record(root, OPENING / name, entries[name]["sha256"])
        if record["bytes"] != entries[name]["bytes"]:
            raise ValueError(f"Opening size mismatch: {name}")
        records.append({**record, "kind": kind, "source_evidence": origin.as_posix()})
    return records


def player_inventory(root, lock):
    locked = {**lock["core_files"], **lock["profile_files"],
              CATALOG.as_posix(): lock["capability_catalog_sha256"],
              (FRAMEWORK / "core/level_runtime.gd").as_posix(): lock["runtime_sha256"]}
    pending = [FRAMEWORK / "tools/level_player.gd"]
    visited = set()
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        script = local_file(root, relative).read_text(encoding="utf-8-sig")
        pending.extend(FRAMEWORK / name for name in GODOT_REFERENCES.findall(script))
    paths = set(locked) | {path.as_posix() for path in visited} | {(FRAMEWORK / "project.godot").as_posix()}
    return [file_record(root, path, locked.get(path)) for path in sorted(paths)]


def repository_assets(root, selected):
    official = read(root / ASSETS / "manifest.json")
    offline = read(root / ALLEY_MANIFEST)
    known = {(ALLEY_MANIFEST.parent / entry["file"]).as_posix(): entry["sha256"] for entry in offline["files"]}
    matches = set()
    source_packages = {}
    for revision in (root / "gunforge/level_design/packages").glob("*/revisions/*/level.json"):
        source, _ = read_package(revision)
        for resource in source["resources"].values():
            if Path(resource["path"]).is_relative_to(ASSETS):
                source_packages.setdefault(resource["path"], set()).add(source["id"])
    files = []
    for path in sorted((root / ASSETS).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        checksum = sha256(path)
        if known.get(relative) == checksum:
            matches.add(relative)
        source = provenance(Path(relative))
        files.append({"path": relative, "sha256": checksum, "in_current_build": relative in selected,
                      "matches_alley_offline_manifest": relative in matches,
                      "source_packages": sorted(source_packages.get(relative, [])),
                      "source_evidence": source.as_posix() if source is not None and (root / source).is_file() else None})
    return {"files": files, "frozen": official["frozen"], "official_records": len(official["assets"]),
            "alley_offline_records_matched": len(matches), "alley_offline_records_unverified": sorted(set(known) - matches)}


def inventory(root, build_path, *, package=PACKAGE):
    compiled = read(build_path)
    verify_build(compiled, package)
    level = compiled["level"]
    links = bindings(level)
    resources = []
    for identifier, resource in sorted(level["resources"].items()):
        relative = Path(resource["path"])
        record = file_record(root, relative, resource["sha256"])
        original = relative
        if relative.is_relative_to(CAST_RGBA8_COPIES):
            record["derived_from"] = verify_rgba8_source(root, relative, root / relative, record["sha256"])
            original = Path(record["derived_from"]["path"])
        elif relative.is_relative_to(CAST_EDGE_COPIES):
            record["derived_from"] = verify_edge_fill_source(root, relative, root / relative, record["sha256"])
            original = Path(record["derived_from"]["path"])
        source = provenance(original)
        evidence = source.as_posix() if source is not None and (root / source).is_file() else None
        resources.append({**record, "id": identifier, "kind": resource["kind"],
                          "decoded": file_format(root / relative, resource["kind"]),
                          "level_field_matches": links[identifier], "source_evidence": evidence})
    opening = opening_inventory(root)
    player = player_inventory(root, compiled["tool_lock"])
    selected = {item["path"] for item in resources}
    return {"schema_version": 1, "package": package, "status": "candidate_pending_A7", "frozen": False,
            "build_id": compiled["build_id"], "source_revision": compiled["source_revision"],
            "payload_sha256": compiled["payload_sha256"], "engine": compiled["tool_lock"]["godot"],
            "compiled_sha256": sha256(build_path), "resource_counts": dict(Counter(row["kind"] for row in resources)),
            "resources": resources, "opening_files": opening, "player_files": player,
            "repository_assets": repository_assets(root, selected)}


def stage_files(root, build_path, manifest, destination):
    if destination.exists():
        raise ValueError(f"Staging destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="candidate-", dir=destination.parent) as temp:
        work = Path(temp) / "runtime"
        rows = manifest["resources"] + manifest["opening_files"] + manifest["player_files"]
        for record in rows:
            target = work / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / record["path"], target)
            if sha256(target) != record["sha256"]:
                raise ValueError(f"File changed while staging: {record['path']}")
        shutil.copyfile(build_path, work / "level.json")
        if sha256(work / "level.json") != manifest["compiled_sha256"]:
            raise ValueError("Compiled build changed while staging")
        work.rename(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default=PACKAGE, help="expected package ID in the compiled level")
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    manifest = inventory(ROOT, args.build, package=args.package)
    if args.stage:
        stage_files(ROOT, args.build, manifest, args.stage)
    dump(args.output, manifest)
    print(f"Verified {len(manifest['resources'])} compiled assets and {len(manifest['opening_files'])} opening files")


if __name__ == "__main__":
    main()
