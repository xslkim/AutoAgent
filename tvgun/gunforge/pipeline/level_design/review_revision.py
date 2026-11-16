"""Bind a saved reviewer annotation to an Agent task and reopen its proposal."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from combat_cues import ensure_combat_cues
from compiler import ROOT, DEFAULT_CACHE, CompileError, compile_source, digest, payload_digest, read, write_build
from cues import ensure_cues
from station_audio import ensure_station_audio
from versions import STORE, immutable, resolve


def review_context(note_path, store=STORE, cache=DEFAULT_CACHE):
    note_path = note_path.resolve()
    note = read(note_path)
    build_id = note.get("build_id", "")
    if note.get("status") != "open" or not note.get("text", "").strip():
        raise CompileError("expected an open annotation saved by the reviewer")
    if not re.fullmatch(r"[a-f0-9]{64}", build_id):
        raise CompileError("invalid reviewed build ID")
    build = read(cache / "builds" / build_id / "level.json")
    package = build["level"]["id"]
    revision = note["source_revision"]
    if note.get("package", package) != package:
        raise CompileError("annotation package differs from reviewed build")
    _, _, manifest = resolve(package, revision, store)
    payload = {name: build[name] for name in ("level", "source_map", "source_manifest")}
    identity = {"source_revision": revision, "tool_lock": build["tool_lock"], "payload_sha256": payload_digest(payload)}
    if (build["source_manifest"] != manifest or build["source_revision"] != revision
            or build["payload_sha256"] != identity["payload_sha256"]
            or build["build_id"] != build_id or digest(identity) != build_id):
        raise CompileError("annotation does not match the archived build and source")
    tick = note["tick"]
    if type(tick) is not int or tick < 0:
        raise CompileError("invalid annotation tick")
    evidence = []
    roles = ["player", "alpha", "recording"]
    if "spatial" in note["evidence"]:
        roles.append("spatial")
    for role in roles:
        artifact = note["evidence"][role]
        path = Path(artifact["path"]).resolve()
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != artifact["sha256"]:
            raise CompileError("changed review evidence: " + role)
        evidence.append({"role": role, "path": str(path), "sha256": checksum})
    anchor = note.get("anchor")
    source_pointer = build["source_map"].get(anchor, {}).get("pointer") if isinstance(anchor, str) else None
    context = {
        "comment_id": note["comment_id"], "author": note["author"], "path": str(note_path),
        "sha256": hashlib.sha256(note_path.read_bytes()).hexdigest(),
        "package": package, "base_revision": revision, "build_id": build_id, "tick": tick,
        "anchor": anchor, "source_pointer": source_pointer, "request": note["text"], "evidence": evidence,
    }
    if "view" in note:
        context["view"] = note["view"]
    return context


def prepare(note_path, output, allowed_paths, preserve, store=STORE, cache=DEFAULT_CACHE):
    review = review_context(note_path, store, cache)
    if not allowed_paths or any(not path.startswith("/") or path == "/" for path in [*allowed_paths, *preserve]):
        raise CompileError("explicit ID-addressed scope and valid preserved paths are required")
    task = {
        "package": review["package"], "base_revision": review["base_revision"],
        "request": review["request"], "evidence": review["evidence"], "review": review,
        "allowed_paths": list(allowed_paths), "preserve": list(preserve),
    }
    immutable(output, task)
    return task


def proposal_package(proposal):
    if "package" in proposal:
        return proposal["package"]
    # Older receipts stored an absolute source path but did not include a package ID.
    source = proposal.get("source", "").replace("\\", "/")
    match = re.search(r"(?:^|/)packages/([\w.-]+)/revisions/([a-f0-9]{64})/level\.json$", source)
    if match is None or match[2] != proposal.get("source_revision"):
        raise CompileError("cannot identify the proposal package")
    return match[1]


def preview(proposal_path, store=STORE, cache=DEFAULT_CACHE):
    proposal = read(proposal_path)
    package = proposal_package(proposal)
    paths = {}
    for label, field in (("base", "base_revision"), ("candidate", "source_revision")):
        _, source, manifest = resolve(package, proposal[field], store)
        missing = [resource["path"] for resource in source["resources"].values()
                   if not (ROOT / resource["path"]).is_file()]
        if any(path.startswith("gunforge/level_design/generated/audio/combat_") for path in missing):
            ensure_combat_cues()
        if any(path.startswith("gunforge/level_design/generated/audio/station_") for path in missing):
            ensure_station_audio()
        if any(path.startswith("gunforge/framework/runtime/audio/") for path in missing):
            ensure_cues()
        paths[label] = str(write_build(compile_source(source, source_manifest=manifest), cache))
    return {"package": package, **paths, "tick": proposal.get("review", {}).get("tick", 0)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("note", type=Path)
    make.add_argument("output", type=Path)
    make.add_argument("--allow", action="append", required=True)
    make.add_argument("--preserve", action="append", default=[])
    view = commands.add_parser("preview")
    view.add_argument("proposal", type=Path)
    package = commands.add_parser("package")
    package.add_argument("proposal", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "package":
            print(proposal_package(read(args.proposal)))
        elif args.command == "prepare":
            print(json.dumps(prepare(args.note, args.output, args.allow, args.preserve)))
        else:
            print(json.dumps(preview(args.proposal)))
    except (CompileError, KeyError, TypeError, AttributeError, OSError) as error:
        raise SystemExit(str(error))
