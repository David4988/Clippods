"""
Content-addressed stage cache.

A stage output is identified by:

    key = sha256({stage, stage_version, inputs, config})

  * inputs  — keys/hashes of what the stage consumed (e.g. the media sha256, or
              the cache key of the upstream audio stage). Chaining upstream keys
              means changing an early stage invalidates everything after it.
  * config  — every parameter that can change the output (model name, compute
              type, beam size, library version, ...).
  * stage_version — bumped by hand when the stage's code changes behaviour
              without any config change.

Layout:  <eval_dir>/cache/<stage>/<key[:2]>/<key>/
           _entry.json   written LAST; its presence marks the entry complete
           <payload files written by the stage>

Entries are built in a sibling temp directory and renamed into place, so an
interrupted 2-hour transcription never leaves a half-written entry that later
looks valid.
"""
from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evaluation.storage import cache_dir, canonical_hash, read_json, write_json

ENTRY_FILE = "_entry.json"


def stage_key(stage: str, stage_version: str, inputs: dict, config: dict) -> str:
    return canonical_hash({
        "stage": stage,
        "stage_version": stage_version,
        "inputs": inputs,
        "config": config,
    })


@dataclass
class CacheResult:
    stage: str
    key: str
    path: Path
    hit: bool
    entry: dict


class StageCache:
    def __init__(self, root: Path | None = None, enabled: bool = True):
        self.root = Path(root) if root else cache_dir()
        self.enabled = enabled

    def entry_path(self, stage: str, key: str) -> Path:
        return self.root / stage / key[:2] / key

    def lookup(self, stage: str, key: str) -> Path | None:
        path = self.entry_path(stage, key)
        return path if (path / ENTRY_FILE).exists() else None

    def get_or_build(
        self,
        stage: str,
        stage_version: str,
        inputs: dict,
        config: dict,
        build: Callable[[Path], dict],
    ) -> CacheResult:
        """
        Return the cached entry, or call build(work_dir) to produce it.
        build writes payload files into work_dir and returns a JSON-serialisable
        dict of facts about the build (timings, resource use, summary numbers),
        which is stored in _entry.json alongside the key material.
        """
        key = stage_key(stage, stage_version, inputs, config)
        final = self.entry_path(stage, key)

        if self.enabled and (final / ENTRY_FILE).exists():
            return CacheResult(stage, key, final, True, read_json(final / ENTRY_FILE))

        final.parent.mkdir(parents=True, exist_ok=True)
        work = final.parent / f".{key}.building-{uuid.uuid4().hex[:8]}"
        work.mkdir()
        try:
            facts = build(work)
            entry = {
                "stage": stage,
                "stage_version": stage_version,
                "key": key,
                "inputs": inputs,
                "config": config,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "build": facts,
            }
            write_json(work / ENTRY_FILE, entry)
            if final.exists():
                # --no-cache rebuild, or a stale incomplete entry: replace it.
                shutil.rmtree(final)
            work.rename(final)
        except BaseException:
            shutil.rmtree(work, ignore_errors=True)
            raise
        return CacheResult(stage, key, final, False, entry)
