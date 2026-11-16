#!/usr/bin/env python3
"""Summarize on-device tracking grades and manually marked return frames."""
import argparse
import csv
import json
from pathlib import Path

FRAME_BYTES = 640 * 360
GRADES = ("DEAD", "GYRO", "EDGE", "PARTIAL", "FULL")


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def monotonic(values):
    return all(before < after for before, after in zip(values, values[1:]))


def read_recording(directory, expected_version):
    meta = dict(line.split("=", 1) for line in (directory / "meta.txt").read_text(encoding="utf-8-sig").splitlines()
                if "=" in line)
    if not meta.get("appVersion") or (expected_version and meta["appVersion"] != expected_version):
        raise ValueError("Recording appVersion is missing or differs from the expected phone build")
    frames = [(int(row["seq"]), int(row["tsNs"])) for row in csv_rows(directory / "frames_idx.csv")]
    if len(frames) < 2 or not monotonic([seq for seq, _ in frames]) or not monotonic([ts for _, ts in frames]):
        raise ValueError("Frame sequences and timestamps must strictly increase")
    if (directory / "frames.bin").stat().st_size != len(frames) * FRAME_BYTES:
        raise ValueError("frames.bin must contain one 640×360 grayscale frame per index row")
    gyro = [int(row["tsNs"]) for row in csv_rows(directory / "gyro.csv")]
    if not gyro or any(left > right for left, right in zip(gyro, gyro[1:])) or gyro[-1] < frames[0][1] or gyro[0] > frames[-1][1]:
        raise ValueError("Gyro timestamps must increase and overlap the camera recording")
    detections = {}
    for row in csv_rows(directory / "detect.csv"):
        ts, grade, locked = int(row["tsNs"]), int(row["failStage"]), int(row["locked"])
        if not 0 <= grade < len(GRADES) or locked != int(grade >= 2) or ts in detections:
            raise ValueError("detect.csv must use the current 0–4 grade format and unique timestamps")
        detections[ts] = grade
    if not monotonic(list(detections)):
        raise ValueError("Detection timestamps must strictly increase")
    return frames, detections, meta


def summarize(frames, detections, returns):
    by_seq = dict(frames)
    seconds = 1e-9
    grades_ns = [0] * len(GRADES)
    observed = 0
    dead_start = None
    losses = []
    for (seq, start), (next_seq, end) in zip(frames, frames[1:]):
        grade = detections.get(start)
        known = next_seq == seq + 1 and grade is not None and end in detections
        if known:
            grades_ns[grade] += end - start
            observed += end - start
        if known and grade == 0:
            if dead_start is None:
                dead_start = start
        elif dead_start is not None:
            losses.append((dead_start, start))
            dead_start = None
    if dead_start is not None:
        losses.append((dead_start, frames[-1][1]))
    if not observed:
        raise ValueError("No adjacent camera frames have matched detection rows")
    reacquisitions = []
    for seq in returns:
        if seq not in by_seq:
            raise ValueError(f"Marked return frame {seq} is missing from frames_idx.csv")
        start = by_seq[seq]
        first = next(((number, ts) for number, ts in frames if ts >= start and detections.get(ts, -1) >= 3), None)
        reacquisitions.append({"return_frame": seq, "first_visual_frame": first[0] if first else None,
                              "milliseconds_to_first_visual_grade": (first[1] - start) / 1e6 if first else None})
    duration = frames[-1][1] - frames[0][1]
    return {"frame_count": len(frames),
            "missing_detection_rows": sum(ts not in detections for _, ts in frames),
            "duration_seconds": duration * seconds,
            "unknown_interval_seconds": (duration - observed) * seconds,
            "grade_seconds": {name: value * seconds for name, value in zip(GRADES, grades_ns, strict=True)},
            "full_or_partial_time_fraction": sum(grades_ns[3:]) / observed,
            "longest_observed_dead_seconds": max((end - start for start, end in losses), default=0) * seconds,
            "reacquisitions": reacquisitions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--app-version", help="expected appVersion from the phone HUD")
    parser.add_argument("--return-frame", type=int, action="append", default=[],
                        help="repeat for camera seq numbers where the screen returned into view")
    args = parser.parse_args()
    try:
        frames, detections, meta = read_recording(args.recording, args.app_version)
        result = summarize(frames, detections, args.return_frame)
    except (OSError, KeyError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps({"recording": args.recording.name, "appVersion": meta["appVersion"], **result},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
