---
title: Editing controls
description: Tune speech, motion, margin, and smoothing behavior.
---

## Keep detection

By default, QuickEdit keeps frames containing speech **or** visual activity:

```bash
quickedit tutorial.mp4 --combine or:speech,motion
```

Use `speech` for speech-only footage or `and:speech,motion` when both signals
must be active. Higher VAD and motion thresholds cut more aggressively.

## Smoother cuts

`--margin` retains padding around a kept section. `--mincut` fills very short
cut gaps, and `--minclip` removes very short keep fragments. A safe first tuning
pass is:

```bash
quickedit talk.mp4 --margin 0.3 --mincut 0.4 --minclip 0.1
```

For long screen recordings, increase `--motion-frame-skip` to reduce analysis
time. Higher values can miss very short visual changes.
