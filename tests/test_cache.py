from __future__ import annotations

from pathlib import Path

import numpy as np

from quickedit.cache import cache


def _video(path: Path, contents: bytes) -> Path:
    path.write_bytes(contents)
    return path


def _only_entry(video_path: Path, suffix: str) -> Path:
    entries = list(cache.get_cache_dir(video_path).glob(f"*{suffix}"))
    assert len(entries) == 1
    return entries[0]


def test_sibling_videos_have_isolated_cache_entries(tmp_path: Path) -> None:
    video_a = _video(tmp_path / "a.mp4", b"video a")
    video_b = _video(tmp_path / "b.mp4", b"video b")
    params = {"threshold": 0.25}

    cache.save_array(video_a, "motion", params, np.array([1, 2]))
    cache.save_array(video_b, "motion", params, np.array([3, 4]))

    np.testing.assert_array_equal(
        cache.load_array(video_a, "motion", params), np.array([1, 2])
    )
    np.testing.assert_array_equal(
        cache.load_array(video_b, "motion", params), np.array([3, 4])
    )

    assert cache.clear_cache(video_a) == 1
    assert cache.load_array(video_a, "motion", params) is None
    np.testing.assert_array_equal(
        cache.load_array(video_b, "motion", params), np.array([3, 4])
    )
    assert cache.clear_cache(video_b) == 1


def test_schema_version_changes_key_and_namespace(tmp_path: Path, monkeypatch) -> None:
    video = _video(tmp_path / "video.mp4", b"video")
    params = {"threshold": 0.1}
    cache.save_json(video, "vad", params, {"version": "old"})
    original_key = cache._cache_key(video, "vad", params)
    original_dir = cache._cache_dir(video)

    monkeypatch.setattr(cache, "CACHE_SCHEMA_VERSION", cache.CACHE_SCHEMA_VERSION + 1)

    assert cache._cache_key(video, "vad", params) != original_key
    assert cache._cache_dir(video) != original_dir
    assert cache.load_json(video, "vad", params) is None

    cache.save_json(video, "vad", params, {"version": "new"})
    assert cache.load_json(video, "vad", params) == {"version": "new"}
    assert cache.clear_cache(video) == 2


def test_missing_loads_do_not_create_cache_directories(tmp_path: Path) -> None:
    video = _video(tmp_path / "video.mp4", b"video")

    assert cache.load_array(video, "motion", {}) is None
    assert cache.load_json(video, "transcript", {}) is None
    assert not (tmp_path / cache.CACHE_DIR_NAME).exists()
    assert cache.clear_cache(video) == 0
    assert not (tmp_path / cache.CACHE_DIR_NAME).exists()


def test_corrupt_array_entry_is_removed(tmp_path: Path) -> None:
    video = _video(tmp_path / "video.mp4", b"video")
    cache.save_array(video, "motion", {}, np.array([1, 2]))
    entry = _only_entry(video, ".npz")
    entry.write_bytes(b"not a numpy archive")

    assert cache.load_array(video, "motion", {}) is None
    assert not entry.exists()


def test_corrupt_json_entry_is_removed(tmp_path: Path) -> None:
    video = _video(tmp_path / "video.mp4", b"video")
    cache.save_json(video, "transcript", {}, {"text": "hello"})
    entry = _only_entry(video, ".json")
    entry.write_text("{not json")

    assert cache.load_json(video, "transcript", {}) is None
    assert not entry.exists()


def test_array_cache_never_loads_pickled_data(tmp_path: Path) -> None:
    video = _video(tmp_path / "video.mp4", b"video")
    cache.save_array(video, "objects", {}, np.array([{"unsafe": True}], dtype=object))
    entry = _only_entry(video, ".npz")

    assert cache.load_array(video, "objects", {}) is None
    assert not entry.exists()


def test_clear_cache_preserves_unrelated_files(tmp_path: Path) -> None:
    video = _video(tmp_path / "video.mp4", b"video")
    cache.save_array(video, "motion", {}, np.array([1]))
    cache.save_json(video, "transcript", {}, {"text": "hello"})

    version_dir = cache.get_cache_dir(video)
    source_dir = version_dir.parent
    cache_root = source_dir.parent
    unrelated_root_file = cache_root / "unrelated.json"
    unrelated_source_file = source_dir / "notes.txt"
    unrelated_version_file = version_dir / "result.json"
    unrelated_root_file.write_text("root")
    unrelated_source_file.write_text("source")
    unrelated_version_file.write_text("version")

    assert cache.clear_cache(video) == 2
    assert unrelated_root_file.read_text() == "root"
    assert unrelated_source_file.read_text() == "source"
    assert unrelated_version_file.read_text() == "version"
