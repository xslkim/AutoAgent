"""Produce and verify opaque RGBA8 copies for the three-chapter cast candidate."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from compiler import canonical, digest, read


COPIES = Path("gunforge/level_design/generated/lantern_city_cast/rgba8")
OPERATION = "opaque_rgb8_to_rgba8"
PNG_IHDR = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"


def png_encoding(header):
    return header[24:26] if header.startswith(PNG_IHDR) else None


def copy_path(directory, source, rgba_sha256):
    key = digest({"source": source, "rgba8_sha256": rgba_sha256})
    return directory / key / Path(source["path"]).name


def source_snapshot(root, directory, checksum):
    return root / directory / "sources" / f"{checksum}.png"


def is_data_binding(reference):
    return reference.startswith("/queries/") or reference.endswith(("/hit_resource", "/mask_permission/resource"))


def normalize_color_images(root, resources, references):
    for identifier, resource in resources.items():
        uses = references[identifier]
        if resource["kind"] != "image" or not uses or any(map(is_data_binding, uses)):
            continue
        path = root / resource["path"]
        with path.open("rb") as stream:
            # PNG IHDR with 8-bit truecolor. Tagged images need a separate conversion review.
            if png_encoding(stream.read(26)) != b"\x08\x02":
                continue
            stream.seek(0)
            data = stream.read()
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or image.mode != "RGB" or image.info:
                continue
            converted = image.convert("RGBA")
        publish_image_copy(root, COPIES, OPERATION, resource, data, converted)


def publish_image_copy(root, directory, operation, resource, data, image):
    source = {"path": resource["path"], "sha256": resource["sha256"], "operation": operation}
    if sha256(data).hexdigest() != source["sha256"]:
        raise ValueError(f"Color source changed while assembling the candidate: {source['path']}")
    buffer = BytesIO()
    image.save(buffer, format="PNG", icc_profile=image.info.get("icc_profile"))
    payload = buffer.getvalue()
    snapshot = source_snapshot(root, directory, source["sha256"])
    # Station builders can regenerate the working input while older copies are under review.
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot.exists():
        with TemporaryDirectory(dir=snapshot.parent) as temporary:
            work = Path(temporary) / snapshot.name
            work.write_bytes(data)
            work.replace(snapshot)
    if snapshot.read_bytes() != data:
        raise ValueError(f"Color source snapshot differs from its immutable contents: {snapshot}")
    checksum = sha256(payload).hexdigest()
    relative = copy_path(directory, source, checksum)
    output = root / relative
    record = output.with_name("source.json")
    record_bytes = canonical(source) + b"\n"
    if not output.parent.exists():
        with TemporaryDirectory(dir=output.parent.parent, prefix=".copy-") as temporary:
            work = Path(temporary) / "image"
            work.mkdir()
            (work / output.name).write_bytes(payload)
            (work / record.name).write_bytes(record_bytes)
            try:
                work.rename(output.parent)
            except OSError:
                if not output.parent.exists():
                    raise
    if output.read_bytes() != payload or record.read_bytes() != record_bytes:
        raise ValueError(f"Color copy differs from its immutable contents: {output}")
    resource.update(path=relative.as_posix(), sha256=checksum)


def read_copy_source(root, directory, operation, relative, checksum, source):
    if source is None:
        source = read((root / relative).with_name("source.json"))
    original = (root / source["path"]).resolve()
    if (source["operation"] != operation or relative != copy_path(directory, source, checksum)
            or not original.is_relative_to(root.resolve())):
        raise ValueError(f"Invalid color source record: {relative}")
    data = source_snapshot(root, directory, source["sha256"]).read_bytes()
    if sha256(data).hexdigest() != source["sha256"]:
        raise ValueError(f"Color source snapshot differs from its recorded checksum: {original}")
    return source, data


def verify_rgba8_source(root, relative, staged_file, checksum, source=None):
    source, data = read_copy_source(root, COPIES, OPERATION, relative, checksum, source)
    with staged_file.open("rb") as stream:
        if png_encoding(data) != b"\x08\x02" or png_encoding(stream.read(26)) != b"\x08\x06":
            raise ValueError(f"Expected RGB8 source and RGBA8 copy: {relative}")
        stream.seek(0)
        with Image.open(BytesIO(data)) as rgb, Image.open(stream) as rgba:
            if rgb.info or rgb.size != rgba.size or rgba.tobytes() != rgb.convert("RGBA").tobytes():
                raise ValueError(f"RGBA8 copy differs in RGB values or opacity: {relative}")
    return source
