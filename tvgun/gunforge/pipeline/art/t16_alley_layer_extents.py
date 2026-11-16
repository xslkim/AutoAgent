"""Compare the compiled alley's visible layers against approved C07b masks."""
import argparse
import json
from pathlib import Path
from pathlib import PureWindowsPath

import numpy as np
from PIL import Image
from scipy import ndimage

from artlib import GAME, digest, write_json

BASELINE = GAME / "bible/geometry/alley_extent_v1/baseline.json"
STATION = GAME / "assets/stations/g01_st_l1_01_alley/station/station.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verified(path, checksum):
    if digest(path) != checksum:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return path


def section_layers(level, section):
    return {key.rsplit(".", 1)[1]: {k: v for k, v in row.items() if k != "section"}
            for key, row in level["presentation"]["layers"].items() if row.get("section") == section}


def bounds(mask):
    y, x = np.nonzero(mask)
    return [int(x.min()), int(y.min()), int(x.max()) + 1, int(y.max()) + 1] if len(x) else None


def row_metrics(expected, depth, alpha, covered):
    exposed = expected & ~covered
    soft = exposed & (alpha < 254)
    missing = exposed & (alpha < 128)
    interior = missing & (depth > 1)
    return {"exposed_pixels": int(exposed.sum()), "below_254_pixels": int(soft.sum()),
            "below_254_interior_pixels": int((soft & (depth > 1)).sum()),
            "deepest_below_254_px": round(float(depth[soft].max(initial=0)), 3),
            "below_128_pixels": int(missing.sum()), "below_128_interior_pixels": int(interior.sum()),
            "below_128_bounds": bounds(missing), "minimum_exposed_alpha": int(alpha[exposed].min(initial=255)),
            "deepest_below_128_px": round(float(depth[missing].max(initial=0)), 3)}


def prepare(stage, level, approved, authoring, captures, capture_rows):
    layers = section_layers(level, "alley.arrival")
    sections = sorted(name for name in level["sections"] if name.startswith("alley."))
    if any(section_layers(level, section) != layers for section in sections):
        raise ValueError("Alley sections no longer share the same layers")
    origin = authoring["content_origin"]
    placement = {row["id"]: row["pos"] for row in authoring["layers"]}
    masks = {row["layer"]: row for row in approved["rows"]}
    order = sorted(layers, key=lambda key: (layers[key]["z"], key), reverse=True)
    if (set(layers) - {"lamp"} != set(masks) or set(layers) != set(placement)
            or [row["id"] for row in capture_rows] != [f"layer.alley.arrival.{key}" for key in order]):
        raise ValueError("Runtime layers differ from the approved mask inventory")
    width, height = level["layout"]["width"], level["layout"]["height"]
    left, top = origin
    if left < 0 or top < 0 or left + width > authoring["canvas"][0] or top + height > authoring["canvas"][1]:
        raise ValueError("The runtime viewport must fit inside the approved design canvas")
    prepared = []
    for identifier, capture in zip(order, capture_rows, strict=True):
        layer = layers[identifier]
        if [layer["x"] + origin[0], layer["y"] + origin[1]] != placement[identifier] or "source" in layer:
            raise ValueError(f"Compiled layer needs a new registration check: {identifier}")
        # All eleven sections share one mapping only while these layers have no parallax.
        if layer.get("parallax", 0):
            raise ValueError(f"Sample the camera route for moving layer: {identifier}")
        resource = level["resources"][layer["resource"]]
        path = (stage / resource["path"]).resolve()
        if not path.is_relative_to(stage):
            raise ValueError(f"Unexpected staged resource path: {path}")
        verified(path, resource["sha256"])
        filename = f'{capture["id"]}.png'
        if capture["file"] != filename:
            raise ValueError(f"Unexpected capture filename: {capture['file']}")
        with Image.open(verified(captures / filename, capture["sha256"])) as image:
            if image.size != (width, height) or image.mode != "RGBA":
                raise ValueError(f"Expected a transparent viewport capture: {filename}")
            alpha = np.array(image.getchannel("A"))
        mask = masks.get(identifier)
        depth = None
        if mask:
            filename = PureWindowsPath(mask["file"]).name
            with Image.open(verified(BASELINE.parent / filename, mask["sha256"])) as image:
                extent = np.array(image.convert("L")) >= 128
            if list(extent.shape[::-1]) != authoring["canvas"]:
                raise ValueError(f"Incorrect design mask canvas: {filename}")
            depth = ndimage.distance_transform_edt(extent)[top:top + height, left:left + width]
        prepared.append((identifier, layer, resource["sha256"], capture["sha256"], alpha, depth))
    return prepared, sections


def inspect(prepared, shape, diagnostics):
    covered = np.zeros(shape, dtype=bool)
    rows = {}
    control = None
    for identifier, _, _, _, alpha, depth in prepared:
        if depth is not None:
            expected = depth > 0
            rows[identifier] = row_metrics(expected, depth, alpha, covered)
            exposed = expected & ~covered
            diagnostic = np.zeros((*shape, 3), dtype=np.uint8)
            diagnostic[exposed] = (74, 86, 92)
            diagnostic[exposed & (alpha < 254)] = (239, 176, 76)
            diagnostic[exposed & (alpha < 128)] = (255, 45, 63)
            Image.fromarray(diagnostic).save(diagnostics / f"{identifier}.png")
            if identifier == "mid_left":
                solid = expected & (depth > 1) & ~covered & (alpha >= 254)
                points = np.argwhere(ndimage.binary_erosion(solid, structure=np.ones((9, 9), dtype=bool)))
                if not points.size:
                    raise ValueError("No visible solid mid-left area for the negative control")
                y, x = points[len(points) // 2]
                broken = alpha.copy()
                broken[y - 4:y + 5, x - 4:x + 5] = 0
                detected = row_metrics(expected, depth, broken, covered)
                added = detected["below_128_interior_pixels"] - rows[identifier]["below_128_interior_pixels"]
                control = {"layer": identifier, "hole_bounds_xyxy": [int(x - 4), int(y - 4), int(x + 5), int(y + 5)],
                           "added_interior_gap_pixels": added, "passed": added == 81}
        covered |= alpha >= 254
    return rows, control


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage.resolve()
    manifest = read(args.manifest)
    compiled = read(verified(stage / "level.json", manifest["compiled_sha256"]))
    level = compiled["level"]
    if compiled["build_id"] != manifest["build_id"] or level["id"] != "paper.lantern_city_cast":
        raise ValueError("Expected the staged three-chapter candidate")
    approved, authoring = read(BASELINE), read(STATION)
    captures = read(args.captures / "captures.json")
    if (captures["build_id"] != compiled["build_id"]
            or captures["compiled_sha256"] != manifest["compiled_sha256"]):
        raise ValueError("Layer captures must come from the verified compiled build")
    prepared, sections = prepare(stage, level, approved, authoring, args.captures, captures["layers"])
    shape = (level["layout"]["height"], level["layout"]["width"])
    diagnostics = args.output.parent / "layer_diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    rows, control = inspect(prepared, shape, diagnostics)
    if not control or not control["passed"]:
        raise ValueError("The C07b negative control must detect the authored hole")
    result = {"build_id": compiled["build_id"], "compiled_sha256": manifest["compiled_sha256"],
              "checker_sha256": digest(Path(__file__)), "design_version": approved["version"],
              "design_manifest_sha256": digest(BASELINE), "station_metadata_sha256": digest(STATION),
              "sections_with_identical_bindings": sections, "unique_runtime_layer_transforms": 1,
              "strict_opacity_passed": all(row["below_254_pixels"] == 0 for row in rows.values()),
              "godot": captures["godot"], "gpu": captures["gpu"],
              "viewport": list(shape[::-1]), "control": control, "layers": rows,
              "compiled_layers": {name: {"binding": layer, "texture_sha256": sha, "capture_sha256": capture_sha}
                                  for name, layer, sha, capture_sha, *_ in prepared}}
    write_json(args.output, result)
    print(json.dumps({"build_id": result["build_id"], "sections": len(sections), "layers": rows,
                      "strict_opacity_passed": result["strict_opacity_passed"], "control": control}))
    return 0 if result["strict_opacity_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
