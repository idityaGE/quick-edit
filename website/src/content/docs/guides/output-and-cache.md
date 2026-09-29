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

Video, timeline, and selected subtitle artifacts are all protected by
`--overwrite`. Sidecars are published atomically after analysis and rendering
succeed, so a failed render does not replace an existing timeline or subtitle.

## Cache

Analysis caches live beside the input video in `.quickedit_cache/`. Each source
video has an isolated, schema-versioned namespace. Cache keys include the input
identity and relevant analysis settings, so changing a render setting does not
require re-transcription while analysis changes can invalidate stale data.

```bash
quickedit recording.mp4 --clear-cache
quickedit recording.mp4 --no-cache
```

`--clear-cache` clears only the selected input's entries before processing;
neighboring videos keep their caches. `--no-cache` disables cache reads and
writes for that invocation.
