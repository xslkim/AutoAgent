"""Fill invisible texture edges without changing cast geometry or visible source pixels."""
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from cast_color_images import is_data_binding, png_encoding, publish_image_copy, read_copy_source
from compiler import read


COPIES = Path("gunforge/level_design/generated/lantern_city_cast/edge_fill")
OPERATION = "nearest_edge_rgb_within_8px"
RADIUS = 8
OFFSETS = sorted((dx * dx + dy * dy, dy, dx)
                 for dy in range(-RADIUS, RADIUS + 1) for dx in range(-RADIUS, RADIUS + 1)
                 if 0 < dx * dx + dy * dy <= RADIUS * RADIUS)


def fill_edges(source):
    result = source.copy()
    solid = source[..., 3] != 0
    colored = (source[..., :3] != 0).any(axis=2)
    best = np.where(solid, 0, RADIUS * RADIUS + 1).astype(np.uint8)
    best_colored = colored.copy()
    height, width = solid.shape
    for distance, dy, dx in OFFSETS:
        if abs(dy) >= height or abs(dx) >= width:
            continue
        top, bottom = max(0, dy), min(height, height + dy)
        left, right = max(0, dx), min(width, width + dx)
        destination = np.s_[top:bottom, left:right]
        neighbor = np.s_[top - dy:bottom - dy, left - dx:right - dx]
        closest = best[destination]
        # Equally near colored samples close gaps that touch both a black and a colored texel.
        preferred_tie = (closest == distance) & colored[neighbor] & ~best_colored[destination]
        available = solid[neighbor] & ((closest > distance) | preferred_tie)
        result[destination][available, :3] = source[neighbor][available, :3]
        closest[available] = distance
        best_colored[destination][available] = colored[neighbor][available]
    return result


def fill_atlas(source, attachments):
    result = fill_edges(source)
    occupied = np.zeros(source.shape[:2], dtype=bool)
    height, width = occupied.shape
    for x, y, w, h in attachments:
        if min(x, y) < 0 or min(w, h) < 1 or x + w > width or y + h > height:
            raise ValueError(f"Attachment outside atlas: {(x, y, w, h)} in {(width, height)}")
        region = np.s_[y:y + h, x:x + w]
        if occupied[region].any():
            raise ValueError(f"Overlapping atlas attachments: {(x, y, w, h)}")
        # Sample padding outside the binding from the atlas, and isolate each rendered rect.
        result[region] = fill_edges(source[region])
        occupied[region] = True
    return result


def adjacent_color_gaps(pixels):
    transparent = pixels[..., 3] == 0
    if not transparent.any():
        return np.zeros_like(transparent)
    black = (pixels[..., :3] == 0).all(axis=2)
    visible_color = ~transparent & ~black
    neighbor = np.zeros_like(visible_color)
    neighbor[1:] |= visible_color[:-1]
    neighbor[:-1] |= visible_color[1:]
    neighbor[:, 1:] |= visible_color[:, :-1]
    neighbor[:, :-1] |= visible_color[:, 1:]
    return transparent & black & neighbor


def repair_cast_edges(root, level, references):
    resources = level["resources"]
    atlases = {}
    for binding in level["presentation"]["puppets"].values():
        metadata = resources[binding["character"]]
        character = read(root / metadata["path"])
        rects = [attachment["rect"] for attachment in character["rig"]["attachments"]]
        if atlases.setdefault(binding["atlas"], rects) != rects:
            raise ValueError(f"Multiple layouts share atlas {binding['atlas']}")

    for identifier, resource in resources.items():
        if resource["kind"] != "image" or not any(not is_data_binding(ref) for ref in references[identifier]):
            continue
        data = (root / resource["path"]).read_bytes()
        if png_encoding(data) != b"\x08\x06":
            continue
        with Image.open(BytesIO(data)) as image:
            pixels = np.asarray(image)
            if identifier not in atlases and not adjacent_color_gaps(pixels).any():
                continue
            filled = fill_atlas(pixels, atlases[identifier]) if identifier in atlases else fill_edges(pixels)
            result = Image.fromarray(filled)
            result.info.update(image.info)
        publish_image_copy(root, COPIES, OPERATION, resource, data, result)


def verify_edge_fill_source(root, relative, staged_file, checksum, source=None):
    source, data = read_copy_source(root, COPIES, OPERATION, relative, checksum, source)
    with Image.open(BytesIO(data)) as before, Image.open(staged_file) as after:
        with staged_file.open("rb") as stream:
            if png_encoding(data) != b"\x08\x06" or png_encoding(stream.read(26)) != b"\x08\x06":
                raise ValueError(f"Expected RGBA8 input and filled copy: {relative}")
        if before.size != after.size or before.info.get("icc_profile") != after.info.get("icc_profile"):
            raise ValueError(f"Edge fill changed the raster size or color profile: {relative}")
        left, right = np.asarray(before), np.asarray(after)
        alpha = left[..., 3]
        if not np.array_equal(alpha, right[..., 3]) or not np.array_equal(left[alpha > 0], right[alpha > 0]):
            raise ValueError(f"Edge fill changed alpha or visible RGB: {relative}")
    return source
