---
title: Your first edit
description: Preview an edit before creating a video.
---

## Preview the cut list

```bash
quickedit recording.mp4 --dry-run
```

The dry run performs analysis and atomically writes the timeline/subtitle
sidecars, but does not render an output video. Review the terminal cut list and
tune settings before rendering. Existing sidecars require `--overwrite`.

## Render the result

```bash
quickedit recording.mp4 -o recording-edited.mp4
```

QuickEdit refuses to replace an existing video or sidecar. Use `--overwrite`
only when you intentionally want to replace every generated artifact.

## Process several recordings

```bash
quickedit recordings/*.mp4 -o edited/
```

Each input is processed independently. A failure is reported in the batch
summary without preventing remaining files from running; the completed batch
still exits non-zero so scripts can detect the failure.
