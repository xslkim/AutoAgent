"""Publish and build the data-only cross-theme encounter example."""
from compiler import ROOT, DEFAULT_CACHE, compile_source, read_package, write_build
from freeze_baseline import dump
from versions import publish


def build():
    design, _ = read_package(ROOT / "gunforge/level_design/examples/orbital.siege.json")
    source_path = publish(design)
    source, manifest = read_package(source_path)
    compiled = compile_source(source, source_manifest=manifest)
    output = write_build(compiled, DEFAULT_CACHE)
    dump(ROOT / "gunforge/level_design/reviews/siege_build.json", {
        "source": str(source_path), "source_revision": compiled["source_revision"],
        "build_id": compiled["build_id"], "compiled": str(output), "state": "candidate_not_adopted",
    })
    return output


if __name__ == "__main__":
    print(build())
