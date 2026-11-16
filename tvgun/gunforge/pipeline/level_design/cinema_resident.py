"""Bind the approved cinema paper cuts to the player's existing puppet format."""
from PIL import Image

from compiler import read
from freeze_baseline import dump


RESCUE_INK_SIZE = (252, 224)


def build_resident(folder, ink_path, output, *, ink_size=RESCUE_INK_SIZE):
    source = read(folder / "puppet.json")
    by_id = {part["id"]: part for part in source["parts"]}
    with Image.open(folder / "pose_idle.png") as idle:
        # The art proof places the root at y=180 with a .74 scale.
        foot = (idle.getchannel("A").getbbox()[3] - 180) / .74
    bones, sprites = [], []
    for part in source["parts"]:
        parent = part["parent"]
        if parent:
            px, py = by_id[parent]["pivot"]
            x, y = part["attach"][0] - px, py - part["attach"][1]
        else:
            x, y = 0, foot
        bones.append({"id": part["id"], "parent": parent or "", "x": x, "y": y, "a": -part["rest_deg"]})
        with Image.open(folder / part["file"]) as image:
            sprites.append((part["z"], part["id"], part["pivot"], image.convert("RGBA")))

    px, py = by_id["torso"]["pivot"]
    x, y = source["ink_anchor"]
    bones.append({"id": "rescue_ink", "parent": "torso", "x": x - px, "y": py - y, "a": 0})
    with Image.open(ink_path) as image:
        mark = image.convert("RGBA").resize(ink_size, Image.Resampling.LANCZOS)
    sprites.append((100, "rescue_ink", (mark.width / 2, mark.height / 2), mark))

    padding = 4
    columns = 4
    cell_width = max(image.width for _, _, _, image in sprites) + 2 * padding
    cell_height = max(image.height for _, _, _, image in sprites) + 2 * padding
    rows = (len(sprites) + columns - 1) // columns
    atlas = Image.new("RGBA", (columns * cell_width, rows * cell_height))
    attachments = []
    for index, (_, part, (px, py), image) in enumerate(sorted(sprites)):
        x = (index % columns) * cell_width + padding
        y = (index // columns) * cell_height + padding
        atlas.paste(image, (x, y))
        attachments.append({"part": part, "bone": part, "rect": [x, y, *image.size],
                            "size": list(image.size), "pivot": [px / image.width, py / image.height], "a": 0})

    prefix = f"{source['id']}_rig"
    image_path = output / f"{prefix}.png"
    character_path = output / f"{prefix}.json"
    atlas.save(image_path)
    dump(character_path, {"rig": {"height": source["assembled_height_target"], "bones": bones,
                                 "attachments": attachments}})
    return character_path, image_path


def frame(lift=0, **angles):
    pose = {part: [0, 0, -angle] for part, angle in angles.items()}
    pose.setdefault("torso", [0, 0, 0])[1] = lift
    return pose


def build_rescue_clips(output):
    struggle_left = frame(torso=5, head=-8, upper_arm_l=18, upper_arm_r=-12, forearm_l=21)
    struggle_right = frame(torso=-5, head=6, upper_arm_l=9, upper_arm_r=-20, forearm_r=-24)
    thankful = frame(head=7, forearm_l=12, forearm_r=-19)
    clips = {
        "struggle": (1.5, True, [struggle_left, frame(), struggle_right, frame(), struggle_left]),
        "rescued": (.6, False, [frame(), frame(38, thigh_l=8, thigh_r=-8, shin_l=-9, shin_r=9,
                                              upper_arm_l=16, upper_arm_r=-16), thankful]),
        "thank": (1.25, True, [thankful, frame(head=-6, forearm_l=20, forearm_r=-25), thankful]),
    }
    paths = {}
    for name, (duration, loop, frames) in clips.items():
        meta = {"loop": loop}
        if name != "struggle":
            meta["attachment_keys"] = {"rescue_ink": [{"time": 0, "visible": False}]}
        path = output / f"resident_{name}.json"
        dump(path, {"duration": duration, "meta": meta, "frames": frames})
        paths[name] = path
    return paths
