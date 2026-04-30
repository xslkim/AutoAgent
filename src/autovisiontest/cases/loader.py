"""Load :class:`TestCase` from JSON or from a Python module on disk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from autovisiontest.cases.schema import TestCase


def load_case_file(path: str | Path) -> TestCase:
    """Load a test case from ``.json`` or ``.py``.

    Python modules must expose exactly one of:

    - ``build_case()`` — callable returning :class:`TestCase` or a dict
      accepted by :meth:`TestCase.model_validate`
    - module-level ``case`` — same types as above
    - module-level ``CASE`` — same types as above
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Case file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".json":
        return TestCase.model_validate_json(p.read_text(encoding="utf-8"))
    if suffix == ".py":
        return _load_case_from_python(p)
    raise ValueError(
        f"Unsupported case extension {suffix!r}; use .json or .py ({p})"
    )


def _load_case_from_python(path: Path) -> TestCase:
    mod_name = f"_autovt_user_case_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load Python case module: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw = None
    if hasattr(module, "build_case") and callable(module.build_case):
        raw = module.build_case()
    elif hasattr(module, "case"):
        raw = module.case
    elif hasattr(module, "CASE"):
        raw = module.CASE
    else:
        raise ValueError(
            f"{path}: define build_case(), or module-level `case` / `CASE` "
            "returning a TestCase"
        )

    if isinstance(raw, TestCase):
        return raw
    return TestCase.model_validate(raw)
