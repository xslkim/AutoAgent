"""Run C13 on verified Godot display frames using the current TVGun tracker."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

import cv2
import numpy as np

from tracker_screen import QUADS, ROOT, acquire_edges
from guntrack import SCREEN_CORNERS, TrackerParams, _geo_valid, _hollow_check


CAMERA_SIZE = (640, 360)
SEED = 1316
PROJECTIONS = ("frontal", "oblique", "far", "steep_oblique")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def variants():
    random = np.random.default_rng(SEED)
    for name, points in zip(PROJECTIONS, QUADS, strict=True):
        quad = np.float32(points)
        yield name, "nominal", quad, .6, 1.0, 0, None
        jitter = random.uniform(-2, 2, quad.shape).astype(np.float32) if name != "steep_oblique" else 0
        noise = random.normal(0, 1.4, CAMERA_SIZE[::-1]).astype(np.float32)
        yield name, "softened", quad + jitter, .75, .88, 5, noise


def corners(rect):
    x, y, width, height = rect
    return np.float32([[x, y], [x + width, y], [x + width, y + height], [x, y + height]])


def transform(points, homography):
    return cv2.perspectiveTransform(points.reshape(-1, 1, 2), homography).reshape(-1, 2)


def raster_border(frame, logical):
    # Godot's canvas stretch can make the logical rectangle larger than the read-back pixels.
    height, width = frame.shape
    columns = np.flatnonzero(frame[height // 2, :] == 255)
    rows = np.flatnonzero(frame[:, width // 2] == 255)
    if len(columns) < 4 or len(rows) < 4:
        raise ValueError("Full display capture does not contain a white border")
    left, right, top, bottom = map(int, (columns[0], columns[-1], rows[0], rows[-1]))
    size = [right - left + 1, bottom - top + 1]
    expected_width = size[1] * logical[2] / logical[3]
    corner_pixels = frame[[top + 1, top + 1, bottom - 1, bottom - 1],
                          [left + 1, right - 1, right - 1, left + 1]]
    if abs(size[0] - expected_width) > 3 or not np.all(corner_pixels == 255):
        raise ValueError("Raster white border disagrees with the Godot screen rectangle")
    return [left - .5, top - .5, *size]


def screen_sample(frame, metadata, variant):
    name, camera, quad, blur, gain, offset, noise = variant
    height, width = frame.shape
    projection = cv2.getPerspectiveTransform(corners((0, 0, width - 1, height - 1)), quad)
    gray = cv2.warpPerspective(frame, projection, CAMERA_SIZE)
    gray = cv2.GaussianBlur(gray, (3, 3), blur)
    if noise is not None:
        gray = np.rint(np.clip(gray.astype(np.float32) * gain + offset + noise, 0, 255)).astype(np.uint8)
    expected = transform(corners(metadata["white_outer_raster_rect"]), projection)
    params = TrackerParams()
    params.frame_white = metadata["white_norm_px"]
    params.frame_dark = metadata["dark_norm_px"]
    pose, edges, low = acquire_edges(gray, params)
    hollow = bool(_hollow_check(gray, expected, low, params.acq_dark_frac))
    error = None
    if pose is not None:
        measured = transform(SCREEN_CORNERS, np.linalg.inv(pose))
        error = float(np.max(np.linalg.norm(measured - expected, axis=1)))
    admissible = bool(_geo_valid(expected))
    same_screen = error is not None and error <= params.band
    return {"projection": name, "camera": camera, "within_tracker_geometry_contract": admissible,
            "acquired": pose is not None, "edges": edges, "hollow": hollow, "low_threshold": low,
            "max_corner_error_camera_px": round(error, 3) if error is not None else None,
            "passed": hollow and edges == 4 and same_screen if admissible else None}


def controls():
    absent = np.zeros(CAMERA_SIZE[::-1], dtype=np.uint8)
    filled = absent.copy()
    cv2.fillConvexPoly(filled, np.int32(QUADS[0]), 255)
    return {name: acquire_edges(frame)[0] is None for name, frame in
            (("missing_border_rejected", absent), ("solid_white_rectangle_rejected", filled))}


def run(captures, gallery_path):
    source = read(captures / "frames.json")
    gallery = read(gallery_path)
    if not source["passed"] or source["build_id"] != gallery["build_id"] or source["gallery_checks_sha256"] != digest(gallery_path):
        raise ValueError("Display frames must use the verified gallery build")
    content = {f"{profile}_{name}" for name, item in gallery["frames"].items()
               if not item["capture"].startswith("display/") for profile in ("monitor", "tv")}
    required = content | {"monitor_display_setup", "tv_display_setup", "tv_calibration_target", "monitor_opening", "tv_opening"}
    if {row["id"] for row in source["samples"]} != required or len(source["samples"]) != len(required):
        raise ValueError("Incomplete or duplicated display frame set")
    cases = []
    camera_variants = tuple(variants())
    for meta in source["samples"]:
        path = captures / meta["file"]
        if meta["profile"] != meta["id"].split("_", 1)[0]:
            raise ValueError(f"Display capture has the wrong profile: {path.name}")
        if digest(path) != meta["sha256"]:
            raise ValueError(f"Display capture changed: {path.name}")
        if meta["id"] in content:
            name = meta["id"].split("_", 1)[1]
            item = gallery["frames"][name]
            if meta["provenance"] != {"capture": item["capture"], "sha256": item["source_png_sha256"]}:
                raise ValueError(f"Display capture does not match the gallery pose: {path.name}")
        frame = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if frame is None or list(frame.shape[::-1]) != meta["window"]:
            raise ValueError(f"Unreadable display frame: {path.name}")
        meta = {**meta, "white_outer_raster_rect": raster_border(frame, meta["white_outer_rect"])}
        cases.append({**meta, "projections": [screen_sample(frame, meta, variant) for variant in camera_variants]})
    projections = [row for case in cases for row in case["projections"]]
    admissible = [row for row in projections if row["within_tracker_geometry_contract"]]
    failures = [{"capture": case["id"], **row} for case in cases for row in case["projections"] if row["passed"] is False]
    negatives = controls()
    return {"build_id": source["build_id"], "gallery_checks_sha256": source["gallery_checks_sha256"],
            "tracker_sha256": digest(ROOT / "scripts/guntrack.py"), "opencv": cv2.__version__, "seed": SEED,
            "camera_variants": [{"projection": name, "camera": camera, "window_quad": quad.tolist(),
                                 "blur_sigma_px": blur, "exposure_gain": gain, "exposure_offset": offset,
                                 "noise_sigma": 1.4 if noise is not None else 0}
                                for name, camera, quad, blur, gain, offset, noise in camera_variants],
            "camera_pixels": list(CAMERA_SIZE), "display_frames": len(cases), "projections": len(projections),
            "admissible": len(admissible), "passed_projections": sum(row["passed"] for row in admissible),
            "outside_geometry_contract": len(projections) - len(admissible), "failed_projections": failures,
            "max_admissible_corner_error_camera_px": max(row["max_corner_error_camera_px"] or 0 for row in admissible),
            "negative_controls": negatives, "passed": bool(admissible) and not failures and all(negatives.values()),
            "physical_capture": "pending", "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--gallery-checks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = run(args.captures, args.gallery_checks)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: results[key] for key in ("display_frames", "projections", "admissible", "passed_projections",
                                                    "outside_geometry_contract", "passed")}))
    raise SystemExit(0 if results["passed"] else 1)


if __name__ == "__main__":
    main()
