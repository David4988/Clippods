"""
tests/conftest.py — Test isolation for on-disk state.

Several modules bind TEMP_DIR / OUTPUTS_DIR at import time
(`from config import OUTPUTS_DIR`), so patching `config` alone is not enough:
each module-level alias is redirected here for the whole session. A session
guard then fails the run if anything still leaked into the real
backend/temp or backend/outputs directories.

Session scope (not function scope) is deliberate: background worker threads
started by some tests can outlive a single test, and must not fall back to the
real directories when a function-scoped patch is undone.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import config

# (module, attribute) pairs that hold a directory captured at import time.
_DIR_ALIASES = {
    "TEMP_DIR": ["config", "utils"],
    "OUTPUTS_DIR": ["config", "main", "services.clip_generation"],
}


def _snapshot(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {p.name for p in directory.iterdir() if p.name != ".gitkeep"}


@pytest.fixture(scope="session", autouse=True)
def isolated_storage(tmp_path_factory):
    import importlib

    real_dirs = {"TEMP_DIR": config.TEMP_DIR, "OUTPUTS_DIR": config.OUTPUTS_DIR}
    before = {name: _snapshot(path) for name, path in real_dirs.items()}

    root = tmp_path_factory.mktemp("clippods_storage")
    fake_dirs = {"TEMP_DIR": root / "temp", "OUTPUTS_DIR": root / "outputs"}
    for path in fake_dirs.values():
        path.mkdir()

    originals = []
    for attr, module_names in _DIR_ALIASES.items():
        for module_name in module_names:
            module = importlib.import_module(module_name)
            originals.append((module, attr, getattr(module, attr)))
            setattr(module, attr, fake_dirs[attr])

    old_eval_dir = os.environ.get("CLIPPODS_EVAL_DIR")
    os.environ["CLIPPODS_EVAL_DIR"] = str(root / "eval_data")

    yield fake_dirs

    for module, attr, value in originals:
        setattr(module, attr, value)
    if old_eval_dir is None:
        os.environ.pop("CLIPPODS_EVAL_DIR", None)
    else:
        os.environ["CLIPPODS_EVAL_DIR"] = old_eval_dir

    leaked = {
        name: sorted(_snapshot(path) - before[name])
        for name, path in real_dirs.items()
    }
    leaked = {name: entries for name, entries in leaked.items() if entries}
    if leaked:
        pytest.fail(
            f"Tests wrote into real storage directories: {leaked}. "
            "Route the write through the isolated TEMP_DIR/OUTPUTS_DIR.",
            pytrace=False,
        )
