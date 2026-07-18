---
title: Timeline JSON
description: The machine-readable sidecar written for each edit.
---

## Purpose

QuickEdit writes a `.timeline.json` file beside its output. It records the
source media properties, kept clips, cut regions, and source-to-output timing.
It is suitable for inspection and downstream tooling, not a substitute for a
Premiere or DaVinci project file.

## Shape

```json
{
  "source": "/absolute/path/recording.mp4",
  "fps": 30.0,
  "duration": 60.0,
  "width": 1920,
  "height": 1080,
  "clips": [{ "src_start": 0.0, "src_end": 12.4, "dst_start": 0.0 }],
  "cuts": [{ "src_start": 12.4, "src_end": 15.0, "reason": "silence" }]
}
```

The 1.0 schema is versioned as part of QuickEdit's public compatibility
contract. Consumers must ignore unknown keys and preserve timestamp precision.
