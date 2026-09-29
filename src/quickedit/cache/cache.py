"""
Caching layer for analysis results.

Caches expensive operations (VAD, motion detection, transcription) to disk
so re-running with different thresholds/prompts doesn't require re-analysis.

Inspired by auto-editor's caching system. Cache keys are based on:
- Source file path + modification time
- Analysis method + parameters

Cache is stored as JSON files in a .quickedit_cache directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR_NAME = ".quickedit_cache"
CACHE_SCHEMA_VERSION = 1
_ENTRY_PREFIX = "entry-"


def _source_namespace(video_path: str | Path) -> str:
    """Return a stable namespace for one source path."""
    resolved_path = str(Path(video_path).resolve())
    return hashlib.sha256(resolved_path.encode()).hexdigest()


def _source_cache_dir(video_path: str | Path) -> Path:
    video_path = Path(video_path)
    return video_path.parent / CACHE_DIR_NAME / _source_namespace(video_path)


def _cache_dir(video_path: str | Path) -> Path:
    """Return the current cache directory without creating it."""
    return _source_cache_dir(video_path) / f"v{CACHE_SCHEMA_VERSION}"


def get_cache_dir(video_path: str | Path) -> Path:
    """Get or create the current cache directory for a source video."""
    cache_dir = _cache_dir(video_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key(video_path: str | Path, method: str, params: dict) -> str:
    """
    Generate a cache key based on file identity and analysis parameters.

    Uses file path + modification time + size as identity (avoids hashing
    entire video files which would be slow).
    """
    video_path = Path(video_path)
    stat = video_path.stat()

    identity = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "path": str(video_path.resolve()),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "method": method,
        "params": params,
    }

    key_str = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(key_str.encode()).hexdigest()


def _cache_file(video_path: str | Path, method: str, params: dict, suffix: str) -> Path:
    key = _cache_key(video_path, method, params)
    return _cache_dir(video_path) / f"{_ENTRY_PREFIX}{key}{suffix}"


def _discard_corrupt(cache_file: Path, error: Exception) -> None:
    logger.warning(f"Failed to load cache {cache_file}: {error}")
    try:
        cache_file.unlink(missing_ok=True)
    except OSError as cleanup_error:
        logger.warning(f"Failed to remove corrupt cache {cache_file}: {cleanup_error}")


def save_array(
    video_path: str | Path,
    method: str,
    params: dict,
    array: np.ndarray,
) -> None:
    """Save a numpy array to cache."""
    cache_dir = get_cache_dir(video_path)
    cache_file = cache_dir / (
        f"{_ENTRY_PREFIX}{_cache_key(video_path, method, params)}.npz"
    )

    with tempfile.NamedTemporaryFile(
        dir=cache_dir, prefix=".entry-", suffix=".npz", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        np.savez_compressed(tmp_path, data=array)
        os.replace(tmp_path, cache_file)
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.debug(f"Cached {method} result to {cache_file}")


def load_array(
    video_path: str | Path,
    method: str,
    params: dict,
) -> np.ndarray | None:
    """Load a cached numpy array. Returns None if not cached."""
    cache_file = _cache_file(video_path, method, params, ".npz")

    if not cache_file.exists():
        return None

    try:
        with np.load(cache_file, allow_pickle=False) as data:
            result = data["data"]
        logger.debug(f"Loaded cached {method} from {cache_file}")
        return result
    except Exception as error:
        _discard_corrupt(cache_file, error)
        return None


def save_json(
    video_path: str | Path,
    method: str,
    params: dict,
    data: Any,
) -> None:
    """Save JSON-serializable data to cache."""
    serialized = json.dumps(data, indent=2, default=str)
    cache_dir = get_cache_dir(video_path)
    cache_file = cache_dir / (
        f"{_ENTRY_PREFIX}{_cache_key(video_path, method, params)}.json"
    )

    tmp = tempfile.NamedTemporaryFile(
        dir=cache_dir,
        prefix=".entry-",
        suffix=".json",
        mode="w",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        with tmp:
            tmp.write(serialized)
        os.replace(tmp_path, cache_file)
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.debug(f"Cached {method} result to {cache_file}")


def load_json(
    video_path: str | Path,
    method: str,
    params: dict,
) -> Any | None:
    """Load cached JSON data. Returns None if not cached."""
    cache_file = _cache_file(video_path, method, params, ".json")

    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text())
        logger.debug(f"Loaded cached {method} from {cache_file}")
        return data
    except Exception as error:
        _discard_corrupt(cache_file, error)
        return None


def clear_cache(video_path: str | Path) -> int:
    """Clear all cache entries for a video. Returns number of files removed."""
    source_cache_dir = _source_cache_dir(video_path)
    if source_cache_dir.is_symlink() or not source_cache_dir.is_dir():
        return 0

    count = 0
    for version_dir in source_cache_dir.iterdir():
        version_name = version_dir.name
        if (
            version_dir.is_symlink()
            or not version_dir.is_dir()
            or len(version_name) < 2
            or version_name[0] != "v"
            or not version_name[1:].isdigit()
        ):
            continue
        for cache_file in version_dir.iterdir():
            digest = cache_file.stem.removeprefix(_ENTRY_PREFIX)
            if (
                cache_file.is_file()
                and cache_file.stem.startswith(_ENTRY_PREFIX)
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
                and cache_file.suffix in {".npz", ".json"}
            ):
                cache_file.unlink()
                count += 1
        try:
            version_dir.rmdir()
        except OSError:
            pass

    try:
        source_cache_dir.rmdir()
        source_cache_dir.parent.rmdir()
    except OSError:
        pass

    logger.info(f"Cleared {count} cache files for {video_path}")
    return count
