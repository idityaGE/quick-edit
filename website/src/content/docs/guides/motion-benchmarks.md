---
title: Motion benchmarks
description: Compare motion backends and choose settings for screen recordings.
---

QuickEdit includes three motion backends: `ffmpeg`, `opencv`, and
`opencv-parallel`. `ffmpeg` is the default because it is often faster on long
screen recordings. The fastest choice still depends on the file, codec,
resolution, storage, CPU, and how much activity is on screen. Benchmark with
recordings that look like your real work.

## Run a benchmark

Use two or three representative screen recordings. Good samples include a mostly
static lecture, a coding or writing tutorial with occasional changes, and a
scroll-heavy demo.

```bash
uv run python scripts/benchmark_motion_backends.py recordings/*.mp4 --repeat 3 --warmup
```

The script prints a table with median seconds, minimum seconds, analyzed frames
per second, and detected activity percentage for each backend.

For machine-readable output:

```bash
uv run python scripts/benchmark_motion_backends.py recordings/*.mp4 --json
```

## Example result

This benchmark was run on `demooo.mp4`, a 103.77 second screen recording:

| Property | Value |
| --- | --- |
| Video codec | H.264 |
| Resolution | 1920 x 1080 |
| Frame rate | 60 fps |
| Video frames | 6,226 |
| Audio | AAC, stereo, 48 kHz |
| File size | 16.3 MiB |
| Bitrate | 1.32 Mbps |

Command:

```bash
uv run python scripts/benchmark_motion_backends.py test-videos/demooo.mp4 --repeat 2 --warmup
```

Result:

| video | backend | median_s | min_s | frames | analyzed_fps | activity_pct |
| --- | --- | --- | --- | --- | --- | --- |
| demooo.mp4 | opencv | 37.730 | 36.800 | 6,225 | 165.0 | 2.4 |
| demooo.mp4 | opencv-parallel | 20.323 | 20.036 | 6,225 | 306.3 | 2.4 |
| demooo.mp4 | ffmpeg | 8.850 | 8.830 | 6,225 | 703.4 | 2.4 |

On this file, all three backends found the same activity percentage, while
`ffmpeg` was about 4.3x faster than `opencv` and 2.3x faster than
`opencv-parallel`. That is why `ffmpeg` is the default motion backend.

## Settings to compare

Start with the default settings:

```bash
uv run python scripts/benchmark_motion_backends.py recordings/*.mp4
```

Then test frame skipping, which often matters more than backend choice on long
recordings:

```bash
uv run python scripts/benchmark_motion_backends.py recordings/*.mp4 --motion-frame-skip 2
uv run python scripts/benchmark_motion_backends.py recordings/*.mp4 --motion-frame-skip 3
```

Use `--motion-frame-skip 1` when you need to catch short cursor movements,
single-frame transitions, or quick drawing/writing actions. Use `2` or `3` for
long videos where missing very short visual changes is acceptable.

## Recommended starting points

| Use case | Starting settings | Why |
| --- | --- | --- |
| General screen recording | `--motion-backend ffmpeg --motion-frame-skip 1` | Default path; usually fastest when decode dominates. |
| Long tutorial with slow visual changes | `--motion-backend ffmpeg --motion-frame-skip 2` | Usually cuts motion cost further without changing edit decisions much. |
| Backend mismatch or debugging | `--motion-backend opencv --motion-frame-skip 1` | Conservative fallback with OpenCV frame decoding. |
| CPU-heavy OpenCV preprocessing | `--motion-backend opencv-parallel --motion-workers 4` | Uses multiple workers for frame preprocessing. |
| Speech-first talking video | `--combine speech --subtitle-style none` | Skips motion analysis entirely. |
| Screen recording with silent work | `--combine or:speech,motion` | Keeps narration and silent visual activity. |

## Interpreting results

Prefer the backend with the lowest median time when activity percentages are
similar. If one backend reports a very different activity percentage, inspect a
dry run before trusting the speed result:

```bash
quickedit recording.mp4 --dry-run --motion-backend ffmpeg
```

Use `--clear-cache` when comparing full `quickedit` runs. The benchmark script
calls motion analysis directly, so it does not read or write QuickEdit cache
entries.
