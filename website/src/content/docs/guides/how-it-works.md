---
title: How it works
description: QuickEdit's processing pipeline, dependencies, and performance strategy.
---

QuickEdit turns each input video into three artifacts: an edited video, a
timeline JSON file, and optional subtitle sidecars. The standard path is local:
speech, motion, transcription, timeline building, and rendering run on your
machine unless you explicitly enable LLM editing.

## High-level flow

1. Validate the input path and confirm `ffmpeg` and `ffprobe` are available.
2. Inspect the video with FFprobe to get FPS, duration, frame count, dimensions,
   and audio availability.
3. Run only the analyses needed by the selected options.
4. Combine detector arrays into one per-frame keep/cut decision.
5. Apply margins and smoothing rules.
6. Build the timeline JSON from kept frame ranges.
7. Generate subtitle sidecars when subtitles are enabled.
8. Render the final video with FFmpeg unless `--dry-run` is set.

## Analysis pipeline

Speech detection extracts 16 kHz mono audio with FFmpeg, runs Silero VAD through
faster-whisper, and converts speech segments to a frame-aligned boolean array.

Motion detection reads video frames, downscales them, converts them to
grayscale, applies blur, compares each analyzed frame to the previous frame, and
marks activity when enough pixels change. The default `ffmpeg` backend asks
FFmpeg to decode scaled grayscale frames before QuickEdit computes differences.
The `opencv` backend does decode and preprocessing through OpenCV. The
`opencv-parallel` backend parallelizes OpenCV frame preprocessing.

Transcription uses faster-whisper word timestamps. It is needed for subtitles,
LLM editing, and the `words` combine detector. It is skipped for speech-only
runs that disable subtitles.

The optional LLM pass runs after the first timeline exists. QuickEdit sends
word-level transcript data, prompt instructions, and classified silent segments
to the provider. It filters returned cuts by `--confidence` before merging them
into the timeline.

## Combining and smoothing

Detectors produce one boolean array per video frame. `--combine` chooses how
those arrays become a keep mask:

```bash
quickedit video.mp4 --combine speech
quickedit video.mp4 --combine or:speech,motion
quickedit video.mp4 --combine and:speech,motion
```

After combination, `--margin` expands kept regions. `--minclip` removes very
short kept fragments, and `--mincut` fills very short cut gaps. The result is
converted into timeline clips and cuts.

## Rendering pipeline

QuickEdit generates subtitles under temporary names so FFmpeg can burn them
into the video without publishing partial sidecars. A single kept clip uses a
simple FFmpeg trim. Multiple clips use concat rendering, with an automatic
strategy switch for timelines with many clips. The large-timeline strategy
describes source ranges to one final FFmpeg encode instead of forcing the
selected codec through an MPEG-TS intermediate. The final video, timeline, and
subtitle are moved into place only after rendering succeeds.

## Cache strategy

Expensive analysis results are cached in `.quickedit_cache/` beside the input
video. Each source has an isolated schema-versioned namespace. Cache keys
include the input path, modification time, size, analysis method, and relevant
parameters.

Changing render settings such as `--codec` or `--crf` does not invalidate speech
or motion analysis. Changing motion settings such as `--motion-threshold`,
`--motion-pixel-threshold`, `--motion-frame-skip`, or `--motion-backend` creates
a different motion cache entry.

Use `--clear-cache` when you want to discard cached analysis for one input
without clearing sibling-video entries. Use `--no-cache` when a run should avoid
both cache reads and cache writes.

## Dependency roles

| Dependency | Role |
| --- | --- |
| FFmpeg | Audio extraction, optional motion frame decoding, and final rendering. |
| FFprobe | Video metadata and audio-stream validation. |
| faster-whisper | Whisper transcription and bundled Silero VAD. |
| OpenCV | Frame decoding and motion preprocessing for OpenCV motion backends. |
| NumPy | Per-frame detector arrays and boolean operations. |
| Click | CLI parsing, config defaults, environment variables, help, and version output. |
| Rich | Terminal progress reporting. |
| Anthropic SDK | Optional provider for `claude-*` LLM models. |
| Google GenAI SDK | Optional provider for `gemini-*` LLM models. |

## Performance strategy

QuickEdit avoids work before it tries to make work faster. If `--combine speech`
is selected and LLM editing is off, motion analysis is skipped. If subtitles are
disabled and no word detector is used, transcription is skipped. When independent
analyses are required together, QuickEdit runs them concurrently.

For motion-heavy videos, `--motion-frame-skip` reduces the number of analyzed
frames and interpolates the result back to the full frame count. The default
`--motion-backend ffmpeg` is usually fastest when decoding dominates. For
CPU-heavy OpenCV preprocessing, `--motion-backend opencv-parallel` can use
multiple workers.
