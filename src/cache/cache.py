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
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR_NAME = ".quickedit_cache"


def get_cache_dir(video_path: str | Path) -> Path:
    """Get or create cache directory next to the video file."""
    video_dir = Path(video_path).parent
    cache_dir = video_dir / CACHE_DIR_NAME
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def _cache_key(
    video_path: str | Path, method: str, params: dict, hash_length: int = 16
) -> str:
    """
    Generate a cache key based on file identity and analysis parameters.

    Uses file path + modification time + size as identity (avoids hashing
    entire video files which would be slow).
    """
    video_path = Path(video_path)
    stat = video_path.stat()

    identity = {
        "path": str(video_path.resolve()),
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "method": method,
        "params": params,
    }

    key_str = json.dumps(identity, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()[:hash_length]


def save_array(
    video_path: str | Path,
    method: str,
    params: dict,
    array: np.ndarray,
) -> None:
    """Save a numpy array to cache."""
    cache_dir = get_cache_dir(video_path)
    key = _cache_key(video_path, method, params)
    cache_file = cache_dir / f"{method}_{key}.npz"

    np.savez_compressed(cache_file, data=array)
    logger.debug(f"Cached {method} result to {cache_file}")


def load_array(
    video_path: str | Path,
    method: str,
    params: dict,
) -> np.ndarray | None:
    """Load a cached numpy array. Returns None if not cached."""
    cache_dir = get_cache_dir(video_path)
    key = _cache_key(video_path, method, params)
    cache_file = cache_dir / f"{method}_{key}.npz"

    if not cache_file.exists():
        return None

    try:
        data = np.load(cache_file)
        logger.debug(f"Loaded cached {method} from {cache_file}")
        return data["data"]
    except Exception as e:
        logger.warning(f"Failed to load cache {cache_file}: {e}")
        return None


def save_json(
    video_path: str | Path,
    method: str,
    params: dict,
    data: Any,
) -> None:
    """Save JSON-serializable data to cache."""
    cache_dir = get_cache_dir(video_path)
    key = _cache_key(video_path, method, params)
    cache_file = cache_dir / f"{method}_{key}.json"

    cache_file.write_text(json.dumps(data, indent=2, default=str))
    logger.debug(f"Cached {method} result to {cache_file}")


def load_json(
    video_path: str | Path,
    method: str,
    params: dict,
) -> Any | None:
    """Load cached JSON data. Returns None if not cached."""
    cache_dir = get_cache_dir(video_path)
    key = _cache_key(video_path, method, params)
    cache_file = cache_dir / f"{method}_{key}.json"

    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text())
        logger.debug(f"Loaded cached {method} from {cache_file}")
        return data
    except Exception as e:
        logger.warning(f"Failed to load cache {cache_file}: {e}")
        return None


def clear_cache(video_path: str | Path) -> int:
    """Clear all cache files for a video. Returns number of files removed."""
    cache_dir = get_cache_dir(video_path)
    count = 0
    for f in cache_dir.iterdir():
        if f.suffix in (".npz", ".json"):
            f.unlink()
            count += 1
    logger.info(f"Cleared {count} cache files from {cache_dir}")
    return count
