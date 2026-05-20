"""Baseline image storage helpers.

Baselines are named PNG files stored under ``~/.autoagent/baselines/``.
The directory is created on first use.

Usage::

    from autoagent_mcp.vision.baseline import save_baseline, load_baseline_path

    save_baseline("login_screen", "/path/to/screenshot.png")
    path = load_baseline_path("login_screen")   # Path object
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_BASELINE_DIR: Path = Path.home() / ".autoagent" / "baselines"


def baseline_path(name: str, baseline_dir: str | os.PathLike | None = None) -> Path:
    """Return the expected on-disk path for the baseline named *name*.

    The file may or may not exist.  Use :func:`save_baseline` to create it.
    """
    base = Path(baseline_dir) if baseline_dir else DEFAULT_BASELINE_DIR
    # Sanitise name — strip path separators so callers can't traverse directories.
    safe = name.replace("/", "_").replace("\\", "_").strip("._")
    if not safe:
        raise ValueError(f"Invalid baseline name: {name!r}")
    return base / f"{safe}.png"


def save_baseline(
    name: str,
    source: str | os.PathLike,
    *,
    baseline_dir: str | os.PathLike | None = None,
    overwrite: bool = True,
) -> Path:
    """Copy *source* to the baselines directory as *name*.png.

    Args:
        name:          Logical baseline identifier (must not be empty or
                       contain only dots/separators).
        source:        Path to the PNG that will become the baseline.
        baseline_dir:  Override the default baselines directory.
        overwrite:     When ``False`` and the baseline already exists, raise
                       :class:`FileExistsError`.

    Returns:
        The path where the baseline was written.

    Raises:
        FileNotFoundError: *source* does not exist.
        FileExistsError:   Baseline exists and *overwrite* is ``False``.
        ValueError:        *name* is invalid.
    """
    src = Path(source)
    if not src.exists():
        raise FileNotFoundError(f"Source image not found: {src}")

    dest = baseline_path(name, baseline_dir)
    if dest.exists() and not overwrite:
        raise FileExistsError(f"Baseline already exists: {dest}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dest))
    return dest


def load_baseline_path(
    name: str,
    *,
    baseline_dir: str | os.PathLike | None = None,
) -> Path:
    """Return the path of an existing baseline, or raise if absent.

    Args:
        name:         Logical baseline identifier.
        baseline_dir: Override the default baselines directory.

    Returns:
        :class:`~pathlib.Path` pointing to the baseline PNG.

    Raises:
        FileNotFoundError: No baseline with *name* has been saved yet.
        ValueError:        *name* is invalid.
    """
    path = baseline_path(name, baseline_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Baseline '{name}' not found. "
            f"Call save_baseline first (expected path: {path})"
        )
    return path


def list_baselines(
    baseline_dir: str | os.PathLike | None = None,
) -> list[str]:
    """Return the names of all saved baselines (without the ``.png`` suffix).

    Returns an empty list when the directory does not exist yet.
    """
    base = Path(baseline_dir) if baseline_dir else DEFAULT_BASELINE_DIR
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.png"))


def delete_baseline(
    name: str,
    *,
    baseline_dir: str | os.PathLike | None = None,
) -> bool:
    """Delete the baseline file for *name*.

    Returns:
        ``True`` if the file was deleted, ``False`` if it did not exist.
    """
    path = baseline_path(name, baseline_dir)
    if path.exists():
        path.unlink()
        return True
    return False
