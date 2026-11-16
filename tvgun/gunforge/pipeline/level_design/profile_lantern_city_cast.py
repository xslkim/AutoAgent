"""Summarize complete Godot route captures against the Paper Lantern City asset budgets."""
import argparse
import hashlib
import json
from math import ceil
from pathlib import Path


MIB = 1024 * 1024
LIMITS = {"stage_and_lighting": 48 * MIB, "actors_and_props": 32 * MIB, "effects_and_ui": 16 * MIB,
          "resident_total": 96 * MIB, "transition_total": 160 * MIB}
FEATURE_CUTS = (
    "puddle.puddle", "footbridge.footbridge", "cinema.projection_booth", "cinema.screen_stage",
    "platform.platform", "lantern_base.workbench", "lantern_base.ending_light", "lantern_base.ending_city",
    "lantern_base.ending_wide", "lantern_base.ending_quote",
)
FRAME_FIELDS = ("tick", "section", "station", "frame_us", "draw_calls", "texture_upload_count", "texture_upload_us")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def frame_record(frame):
    return {field: frame[field] for field in FRAME_FIELDS}


def elapsed_over_budget(frame):
    return frame["frame_us"] * 60 > 1_000_000


def time_summary(samples):
    times = sorted(frame["frame_us"] for frame in samples)
    result = {f"p{p}_us": times[ceil(len(times) * p / 100) - 1] for p in (50, 95, 99)}
    return dict(result, max_us=times[-1], over_60hz=sum(elapsed_over_budget(frame) for frame in samples))


def cuts(samples):
    return [(previous, current) for previous, current in zip(samples, samples[1:])
            if previous["section"] != current["section"]]


def validate(path, build_id):
    profile = read(path)
    log = path.with_suffix(".log").read_text(encoding="utf-8-sig").splitlines()
    route = [json.loads(line) for line in log if line.startswith("{")][-1]
    samples = profile["samples"]
    if profile["build_id"] != build_id or route["build_id"] != build_id:
        raise ValueError(f"Profile and route log must use the selected build: {path.name}")
    if (not route["passed"] or route["result"] != "clear" or not route["texture_restart_checked"]
            or route["reached"] != list(range(1, 16)) or route["replay"]["inputs"] < route["counters"]["shots"]
            or route["replay"]["counters"] != route["counters"]
            or len(profile["screen_sweep_spawns"]) != 3 or not route["ending"]["city_texture_preloaded"]
            or not route["ending"]["wide_texture_preloaded"]):
        raise ValueError(f"Incomplete replay, cut, restart, or epilogue coverage: {path.name}")
    if [frame["tick"] for frame in samples] != list(range(1, route["end_tick"] + 1)):
        raise ValueError(f"Expected a rendered sample for every fixed tick: {path.name}")
    return profile


def summarize(path, build_id):
    profile = validate(path, build_id)
    if profile.get("asset_accounting") != "rgba8_with_mipmaps":
        raise ValueError(f"Expected RGBA8 accounting with HUD textures: {path.name}")
    samples = profile["samples"]
    ui = profile["effects_ui_texture_bytes"]
    if ui <= 0:
        raise ValueError("The paper HUD must contribute to the asset budget")

    def resident(frame):
        return frame["stage_texture_bytes"] + frame["actor_prop_texture_bytes"] + ui

    def transition(frame):
        preloaded = frame["preloaded_stage_texture_bytes"] + frame["preloaded_actor_prop_texture_bytes"]
        return max(resident(frame) + preloaded, frame["handoff_asset_upper_bound_bytes"])

    measurements = {"stage_and_lighting": lambda frame: frame["stage_texture_bytes"],
                    "actors_and_props": lambda frame: frame["actor_prop_texture_bytes"], "effects_and_ui": lambda _: ui,
                    "resident_total": resident, "transition_total": transition}
    budgets = {}
    for category, measure in measurements.items():
        peak = max(samples, key=measure)
        size = measure(peak)
        budgets[category] = {"bytes": size, "limit_bytes": LIMITS[category], "passed": size <= LIMITS[category],
                             "tick": peak["tick"], "section": peak["section"]}

    changes = [dict(frame_record(current), from_section=previous["section"],
                    preloaded_section_before_cut=previous["preloaded_section"],
                    handoff_asset_upper_bound_bytes=current["handoff_asset_upper_bound_bytes"])
               for previous, current in cuts(samples)]
    features = {row["section"]: row for row in changes if row["section"] in FEATURE_CUTS}
    if set(features) != set(FEATURE_CUTS):
        raise ValueError(f"Missing feature handoff: {set(FEATURE_CUTS) - set(features)}")
    stations = {}
    for number in range(1, 16):
        rows = [frame for frame in samples if frame["station"] == number]
        stations[str(number)] = dict(time_summary(rows), samples=len(rows), resident_peak_bytes=max(map(resident, rows)))
    return {"profile": path.name, "profile_sha256": digest(path), "gpu": profile["gpu"],
            "renderer": profile["rendering_method"], "viewport": profile["viewport"], "window": profile["window"],
            "open_us": profile["open_us"], "samples": len(samples), "asset_budgets": budgets,
            "engine_texture_peak_bytes": max(frame["texture_bytes"] for frame in samples),
            "engine_video_peak_bytes": max(frame["video_bytes"] for frame in samples),
            "frame_time": time_summary(samples), "stations": stations, "section_cuts": changes, "feature_cuts": features,
            "slow_frames": [frame_record(frame) for frame in samples if elapsed_over_budget(frame)],
            "screen_sweep_spawns": profile["screen_sweep_spawns"]}


def puppet_atlases(manifest, build_id):
    if manifest["package"] != "paper.lantern_city_cast" or manifest["build_id"] != build_id:
        raise ValueError("The asset inventory must match the measured candidate")
    atlases = [{"resource": row["id"], "pixels": row["decoded"]["pixels"],
                "passed": max(row["decoded"]["pixels"]) <= 2048}
               for row in manifest["resources"]
               if any(path.startswith("/presentation/puppets/") and path.endswith("/atlas")
                      for path in row["level_field_matches"])]
    if not atlases:
        raise ValueError("The candidate inventory has no paper puppet atlases")
    return atlases


def span(values):
    values = list(values)
    return [min(values), max(values)]


def compare_reference(path, current):
    reference = read(path)
    earlier, latest = reference["runs"], current["runs"]
    if reference["package"] != current["package"] or not earlier:
        raise ValueError("The reference must be a complete Paper Lantern City performance report")
    fields = ("gpu", "renderer", "viewport", "window", "samples")
    conditions = {key: latest[0][key] for key in fields}
    station_samples = {station: row["samples"] for station, row in latest[0]["stations"].items()}
    for run in earlier + latest:
        if (any(run[key] != value for key, value in conditions.items())
                or {station: row["samples"] for station, row in run["stations"].items()} != station_samples
                or run["screen_sweep_spawns"] != latest[0]["screen_sweep_spawns"]):
            raise ValueError("Reference and current runs must use the same GPU, viewports, and full route")

    def metrics(runs):
        return {"runs": len(runs), "samples": sum(run["samples"] for run in runs),
                "asset_peaks_bytes": {key: max(run["asset_budgets"][key]["bytes"] for run in runs) for key in LIMITS},
                "frame_p95_us": span(run["frame_time"]["p95_us"] for run in runs),
                "frame_p99_us": span(run["frame_time"]["p99_us"] for run in runs),
                "frame_max_us": span(run["frame_time"]["max_us"] for run in runs),
                "frames_over_60hz": sum(run["frame_time"]["over_60hz"] for run in runs),
                "slow_section_cuts": sum(elapsed_over_budget(cut) for run in runs for cut in run["section_cuts"]),
                "loader_open_us": span(run["open_us"] for run in runs),
                "engine_texture_peak_bytes": max(run["engine_texture_peak_bytes"] for run in runs),
                "engine_video_peak_bytes": max(run["engine_video_peak_bytes"] for run in runs),
                "feature_cuts": {section: {"frame_us": span(run["feature_cuts"][section]["frame_us"] for run in runs),
                                           "texture_upload_count": span(run["feature_cuts"][section]["texture_upload_count"]
                                                                        for run in runs)}
                                 for section in FEATURE_CUTS}}

    before, after = metrics(earlier), metrics(latest)
    return {"reference_build_id": reference["build_id"], "reference_sha256": digest(path),
            "matched_conditions": conditions, "reference": before, "current": after,
            "asset_peak_delta_bytes": {key: after["asset_peaks_bytes"][key] - before["asset_peaks_bytes"][key] for key in LIMITS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--baseline", type=Path, help="Earlier timing-only profile of the same build")
    parser.add_argument("--reference-report", type=Path, help="Earlier comparable performance summary for cross-build comparison")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("profiles", nargs="+", type=Path)
    args = parser.parse_args()
    receipt = read(args.receipt)
    build_id = receipt["build_id"]
    runs = [summarize(path, build_id) for path in args.profiles]
    atlases = puppet_atlases(read(args.manifest), build_id)
    result = {"package": "paper.lantern_city_cast", "build_id": build_id, "source_revision": receipt["source_revision"],
              "method": "One Godot Compatibility draw per fixed simulation tick with VSync off and dummy audio. "
                        "Scene and actual paper HUD textures use RGBA8 with mipmaps, deduplicated per texture. "
                        "The transition limit uses active plus preloaded images and the union across adjacent sections. "
                        "Engine totals separately include render targets, font textures and backend resources.",
              "asset_budget_passed": all(row["passed"] for run in runs for row in run["asset_budgets"].values())
                                     and all(row["passed"] for row in atlases),
              "whole_route_60hz_passed": all(run["frame_time"]["over_60hz"] == 0 for run in runs),
              "section_cuts_60hz_passed": all(not elapsed_over_budget(row) for run in runs for row in run["section_cuts"]),
              "puppet_atlases": atlases, "runs": runs}
    if args.baseline:
        samples = validate(args.baseline, build_id)["samples"]
        result["baseline_timing"] = {"profile_sha256": digest(args.baseline), "samples": len(samples),
                                     "frame_time": time_summary(samples),
                                     "slow_frames": [frame_record(frame) for frame in samples if elapsed_over_budget(frame)]}
    if args.reference_report:
        result["reference_comparison"] = compare_reference(args.reference_report, result)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("asset_budget_passed", "whole_route_60hz_passed", "section_cuts_60hz_passed")}))
    if not result["asset_budget_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
