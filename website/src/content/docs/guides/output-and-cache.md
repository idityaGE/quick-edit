---
title: Subtitles, output, and cache
description: Understand generated files and repeatable processing.
---

## Output files

For `recording.mp4`, QuickEdit writes:

- `recording_edited.mp4` — rendered video.
- `recording_edited.ass` or `.srt` — subtitle sidecar, unless subtitles are disabled.
- `recording_edited.timeline.json` — cut and clip metadata.

Use `--subtitle-style fancy`, `simple`, or `none`. Fancy subtitles are ASS files
with word highlighting; simple subtitles are portable SRT files.

## Cache

Analysis caches live beside the input video in `.quickedit_cache/`. Cache keys
include the input identity and relevant analysis settings, so changing a render
setting does not require re-transcription.

```bash
quickedit recording.mp4 --clear-cache
quickedit recording.mp4 --no-cache
```

`--clear-cache` clears entries before processing; `--no-cache` disables cache
reads and writes for that invocation.
