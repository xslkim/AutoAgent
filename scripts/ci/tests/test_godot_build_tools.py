"""TASK-0304/0305: Tests for Godot build tools and editor plugin.

Tests the ClassDB cache generator and release self-check scripts offline.

godot_cache_classdb.py
  · scan_classes() extracts class names from GDScript source
  · generate_cache() emits valid GDScript with CACHED_CLASSES array
  · BASELINE_CLASSES covers all ControlReflector-required types
  · CLI --dry-run prints to stdout, exit 0

godot_release_selfcheck.py
  · parse_cache() correctly reads the generated .gd file
  · Self-check passes when all REQUIRED_CLASSES present
  · Self-check fails (exit 1) when a required class is missing
  · Self-check fails (exit 2) when cache file not found
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent  # scripts/ci
sys.path.insert(0, str(SCRIPT_DIR))

import godot_cache_classdb as gcc  # noqa: E402
import godot_release_selfcheck as grs  # noqa: E402

CACHE_PATH = (
    Path(__file__).resolve().parents[3]
    / "adapters" / "godot" / "addons" / "autoagent" / "runtime" / "class_db_cache.gd"
)


# ===========================================================================
# godot_cache_classdb — scan_classes()
# ===========================================================================


class TestScanClasses:
    def test_scan_extracts_extends_class(self, tmp_path: Path) -> None:
        gd = tmp_path / "my_controller.gd"
        gd.write_text("extends Control\n", encoding="utf-8")
        found = gcc.scan_classes([tmp_path])
        assert "Control" in found

    def test_scan_extracts_is_expression(self, tmp_path: Path) -> None:
        gd = tmp_path / "reflector.gd"
        gd.write_text("if node is LineEdit:\n    pass\n", encoding="utf-8")
        found = gcc.scan_classes([tmp_path])
        assert "LineEdit" in found

    def test_scan_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.gd").write_text("extends Button\n", encoding="utf-8")
        (tmp_path / "b.gd").write_text("if x is Label:\n    pass\n", encoding="utf-8")
        found = gcc.scan_classes([tmp_path])
        assert "Button" in found
        assert "Label" in found

    def test_scan_skips_unreadable(self, tmp_path: Path) -> None:
        # Non-existing directory should just return empty without crash.
        found = gcc.scan_classes([tmp_path / "nonexistent"])
        assert isinstance(found, set)

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        found = gcc.scan_classes([tmp_path])
        assert len(found) == 0


# ===========================================================================
# godot_cache_classdb — generate_cache()
# ===========================================================================


class TestGenerateCache:
    def test_output_contains_gdscript_header(self) -> None:
        content = gcc.generate_cache(set())
        assert "extends RefCounted" in content
        assert "CACHED_CLASSES" in content

    def test_output_contains_baseline_classes(self) -> None:
        content = gcc.generate_cache(set())
        for cls in ["Control", "Button", "LineEdit", "Label"]:
            assert f'"{cls}"' in content, f"Baseline class {cls!r} missing from cache"

    def test_output_contains_extra_classes(self) -> None:
        content = gcc.generate_cache({"MyCustomWidget", "AnotherClass"})
        assert '"MyCustomWidget"' in content
        assert '"AnotherClass"' in content

    def test_class_exists_cached_function_present(self) -> None:
        content = gcc.generate_cache(set())
        assert "class_exists_cached" in content

    def test_get_cached_class_list_function_present(self) -> None:
        content = gcc.generate_cache(set())
        assert "get_cached_class_list" in content

    def test_output_sorted_alphabetically(self) -> None:
        content = gcc.generate_cache({"Zzz", "Aaa"})
        lines = content.splitlines()
        class_lines = [l.strip().strip('",') for l in lines if l.strip().startswith('"')]
        # Sorted iff each class comes before the next alphabetically.
        assert class_lines == sorted(class_lines)


# ===========================================================================
# godot_cache_classdb — baseline coverage for ControlReflector
# ===========================================================================


class TestBaselineClassesCoverage:
    """BASELINE_CLASSES must cover all types ControlReflector checks."""

    REFLECTOR_REQUIRED = [
        "Control",
        "BaseButton",
        "Button",
        "LineEdit",
        "TextEdit",
        "Label",
        "TextureRect",
        "CanvasLayer",
        "ScrollContainer",
    ]

    def test_all_reflector_types_in_baseline(self) -> None:
        for cls in self.REFLECTOR_REQUIRED:
            assert cls in gcc.BASELINE_CLASSES, (
                f"ControlReflector checks {cls!r} but it's not in BASELINE_CLASSES"
            )


# ===========================================================================
# godot_cache_classdb — CLI
# ===========================================================================


class TestCacheCLI:
    def test_dry_run_prints_content(self, tmp_path: Path, capsys) -> None:
        rc = gcc.main(["--dry-run",
                       "--project", str(tmp_path),
                       "--adapter", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "CACHED_CLASSES" in out

    def test_write_creates_file(self, tmp_path: Path) -> None:
        out_file = tmp_path / "class_db_cache.gd"
        rc = gcc.main([
            "--out", str(out_file),
            "--project", str(tmp_path),
            "--adapter", str(tmp_path),
        ])
        assert rc == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "CACHED_CLASSES" in content


# ===========================================================================
# godot_release_selfcheck — parse_cache()
# ===========================================================================


class TestParseCache:
    def _make_cache(self, tmp_path: Path, classes: list[str]) -> Path:
        lines = [
            'extends RefCounted',
            'const CACHED_CLASSES: PackedStringArray = [',
        ]
        for cls in classes:
            lines.append(f'\t"{cls}",')
        lines += [']', '']
        p = tmp_path / "class_db_cache.gd"
        p.write_text("\n".join(lines), encoding="utf-8")
        return p

    def test_parse_extracts_classes(self, tmp_path: Path) -> None:
        p = self._make_cache(tmp_path, ["Control", "Button", "Label"])
        found = grs.parse_cache(p)
        assert "Control" in found
        assert "Button" in found
        assert "Label" in found

    def test_parse_empty_array(self, tmp_path: Path) -> None:
        p = self._make_cache(tmp_path, [])
        found = grs.parse_cache(p)
        assert len(found) == 0

    def test_real_cache_file_parseable(self) -> None:
        if not CACHE_PATH.exists():
            pytest.skip("class_db_cache.gd not generated yet")
        found = grs.parse_cache(CACHE_PATH)
        assert len(found) > 10, "Real cache should have many entries"


# ===========================================================================
# godot_release_selfcheck — main()
# ===========================================================================


class TestReleaseSelfCheck:
    def _make_complete_cache(self, tmp_path: Path) -> Path:
        classes = list(grs.REQUIRED_CLASSES) + ["Button", "Label"]
        lines = ['extends RefCounted', 'const CACHED_CLASSES: PackedStringArray = [']
        for cls in classes:
            lines.append(f'\t"{cls}",')
        lines += [']', '']
        p = tmp_path / "class_db_cache.gd"
        p.write_text("\n".join(lines), encoding="utf-8")
        return p

    def test_complete_cache_passes(self, tmp_path: Path) -> None:
        cache = self._make_complete_cache(tmp_path)
        rc = grs.main(["--cache", str(cache)])
        assert rc == 0

    def test_missing_class_fails(self, tmp_path: Path) -> None:
        # Only put non-required classes in cache.
        lines = ['extends RefCounted', 'const CACHED_CLASSES: PackedStringArray = [',
                 '\t"SomeOtherClass",', ']', '']
        p = tmp_path / "class_db_cache.gd"
        p.write_text("\n".join(lines), encoding="utf-8")
        rc = grs.main(["--cache", str(p)])
        assert rc == 1

    def test_missing_file_exit2(self, tmp_path: Path) -> None:
        rc = grs.main(["--cache", str(tmp_path / "nonexistent.gd")])
        assert rc == 2

    def test_real_generated_cache_passes(self) -> None:
        if not CACHE_PATH.exists():
            pytest.skip("class_db_cache.gd not generated yet")
        rc = grs.main(["--cache", str(CACHE_PATH)])
        assert rc == 0
