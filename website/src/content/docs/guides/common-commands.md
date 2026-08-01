---
title: Common commands
description: Practical recipes for everyday QuickEdit runs.
---

## Preview without rendering

Use a dry run first when you are tuning settings:

```bash
quickedit recording.mp4 --dry-run
```

QuickEdit writes the timeline and subtitle sidecars but skips the final video
render.

## Render one video

```bash
quickedit recording.mp4 -o recording-edited.mp4
```

If you omit `-o`, QuickEdit writes `recording_edited.mp4` next to the input.

## Batch process a folder

```bash
quickedit recordings/*.mp4 -o edited/
```

With more than one input, `-o` is treated as an output directory.

## Fast speech-only trimming

```bash
quickedit lecture.mp4 --combine speech --subtitle-style none
```

This keeps sections with speech and skips motion analysis. Disabling subtitles
also skips transcription, so the run only needs speech detection and rendering.

## Screen recordings

For tutorials where silent visual activity matters, keep the default speech-or-
motion behavior:

```bash
quickedit tutorial.mp4 --combine or:speech,motion
```

For stricter edits that only keep moments with both narration and visual
activity:

```bash
quickedit demo.mp4 --combine and:speech,motion
```

## Faster motion analysis

Analyze fewer frames when long screen recordings spend time on motion analysis:

```bash
quickedit tutorial.mp4 --motion-frame-skip 3
```

Higher values are faster but can miss very short screen changes.

## Parallel OpenCV motion

```bash
quickedit tutorial.mp4 --motion-backend opencv-parallel --motion-workers 4
```

Use this when CPU cores are available and OpenCV decoding is the bottleneck.

## FFmpeg-backed motion

```bash
quickedit tutorial.mp4 --motion-backend ffmpeg
```

This backend decodes scaled grayscale frames with FFmpeg before computing frame
differences.

## Disable subtitles

```bash
quickedit recording.mp4 --subtitle-style none
```

Use this when you only want a rendered edit and timeline JSON.

## Simple SRT subtitles

```bash
quickedit recording.mp4 --subtitle-style simple
```

This writes a portable `.srt` sidecar instead of an ASS subtitle file.

## CPU-safe Whisper settings

```bash
quickedit recording.mp4 --whisper-model base --device cpu --whisper-compute-type int8
```

Use `tiny` for a faster first pass or `small` when your CPU has enough headroom.

## CUDA Whisper settings

```bash
quickedit recording.mp4 --whisper-model small --device cuda --whisper-compute-type float16
```

CUDA is most useful when subtitles, word-based detection, or LLM editing requires
transcription.

## Conservative cuts

```bash
quickedit recording.mp4 --margin 0.4 --mincut 0.5 --minclip 0.2
```

Larger margins keep more context around speech or motion. Larger `--mincut`
values avoid tiny jumps.

## Overwrite intentionally

```bash
quickedit recording.mp4 -o recording-edited.mp4 --overwrite
```

QuickEdit only replaces an output when this flag is present.

## Clear or reuse cache

```bash
quickedit recording.mp4
quickedit recording.mp4 --clear-cache
quickedit recording.mp4 --no-cache
```

The first command reuses cached analysis when settings match. The second clears
the input cache before running. The third avoids cache reads and writes.

## Optional LLM editing

```bash
export ANTHROPIC_API_KEY='...'
quickedit recording.mp4 --llm --llm-model claude-sonnet-4-20250514 --dry-run
```

Gemini models use `GOOGLE_API_KEY` or `GEMINI_API_KEY`:

```bash
export GEMINI_API_KEY='...'
quickedit recording.mp4 --llm --llm-model gemini-3.5-flash --prompt-template tutorial
```

LLM editing sends transcript data and prompt context to the selected provider.
Run `--dry-run` first and raise `--confidence` for more conservative semantic
cuts.
