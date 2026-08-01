"""Benchmark QuickEdit motion backends on local video files."""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from quickedit.analyze.motion import analyze_motion

BACKENDS = ("opencv", "opencv-parallel", "ffmpeg")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare QuickEdit motion detection backends on local videos. "
            "Use real screen recordings for meaningful numbers."
        )
    )
    parser.add_argument("videos", nargs="+", type=Path, help="Video files to measure")
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=BACKENDS,
        default=list(BACKENDS),
        help="Backends to compare",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="Measured runs per backend and video",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Run each backend once before measuring",
    )
    parser.add_argument(
        "--motion-threshold",
        type=float,
        default=0.02,
        help="Motion threshold passed to analyze_motion",
    )
    parser.add_argument(
        "--motion-pixel-threshold",
        type=int,
        default=10,
        help="Pixel change threshold passed to analyze_motion",
    )
    parser.add_argument(
        "--motion-frame-skip",
        type=int,
        default=1,
        help="Analyze every Nth frame",
    )
    parser.add_argument(
        "--motion-workers",
        type=int,
        default=4,
        help="Worker count for opencv-parallel",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a Markdown table",
    )
    return parser.parse_args()


def _require_tools(backends: list[str]) -> None:
    if "ffmpeg" in backends and shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg backend requested, but ffmpeg was not found on PATH")


def _validate_args(args: argparse.Namespace) -> None:
    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    if args.motion_frame_skip < 1:
        raise SystemExit("--motion-frame-skip must be >= 1")
    if args.motion_workers < 1:
        raise SystemExit("--motion-workers must be >= 1")
    for video in args.videos:
        if not video.is_file():
            raise SystemExit(f"Video does not exist: {video}")


def _measure(video: Path, backend: str, args: argparse.Namespace) -> dict[str, Any]:
    durations = []
    result = None
    if args.warmup:
        analyze_motion(
            video,
            threshold=args.motion_threshold,
            pixel_threshold=args.motion_pixel_threshold,
            frame_skip=args.motion_frame_skip,
            backend=backend,
            workers=args.motion_workers,
        )

    for _ in range(args.repeat):
        started = time.perf_counter()
        result = analyze_motion(
            video,
            threshold=args.motion_threshold,
            pixel_threshold=args.motion_pixel_threshold,
            frame_skip=args.motion_frame_skip,
            backend=backend,
            workers=args.motion_workers,
        )
        durations.append(time.perf_counter() - started)

    assert result is not None
    return {
        "video": str(video),
        "backend": backend,
        "repeat": args.repeat,
        "seconds_min": min(durations),
        "seconds_median": statistics.median(durations),
        "seconds_mean": statistics.fmean(durations),
        "frames": result.total_frames,
        "fps": result.fps,
        "activity_pct": float(np.mean(result.activity_frames) * 100),
        "analyzed_fps_median": result.total_frames / statistics.median(durations),
    }


def _print_table(rows: list[dict[str, Any]]) -> None:
    headers = [
        "video",
        "backend",
        "median_s",
        "min_s",
        "frames",
        "analyzed_fps",
        "activity_pct",
    ]
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print(
            "| "
            + " | ".join(
                [
                    Path(row["video"]).name,
                    row["backend"],
                    f"{row['seconds_median']:.3f}",
                    f"{row['seconds_min']:.3f}",
                    str(row["frames"]),
                    f"{row['analyzed_fps_median']:.1f}",
                    f"{row['activity_pct']:.1f}",
                ]
            )
            + " |"
        )


def main() -> int:
    args = _parse_args()
    _validate_args(args)
    _require_tools(args.backends)

    rows = []
    for video in args.videos:
        for backend in args.backends:
            rows.append(_measure(video, backend, args))

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
