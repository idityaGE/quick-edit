---
title: Troubleshooting
description: Resolve common environment and processing errors.
---

## FFmpeg or FFprobe not found

Install FFmpeg with your operating system's package manager, then verify both
commands are available:

```bash
ffmpeg -version
ffprobe -version
```

## Output already exists

QuickEdit never overwrites a video by accident. Choose another output name or
add `--overwrite` after checking the target.

## No audio track

QuickEdit needs an audio stream for voice detection and output rendering. Add
or mux an audio track before processing this version of QuickEdit.

## CUDA problems

Start with CPU mode to isolate your environment:

```bash
quickedit recording.mp4 --device cpu --whisper-compute-type int8
```

Then confirm that your CUDA driver and faster-whisper runtime support the
selected compute type.

## LLM provider errors

Confirm you installed the matching optional provider dependency group with the
source installer, set the matching API key, and selected a supported model
identifier. `--no-llm` returns to local-only editing.
