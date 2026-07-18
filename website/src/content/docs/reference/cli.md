---
title: CLI reference
description: Stable 1.0 command-line interface.
---

## Command shape

```text
quickedit INPUT_PATHS... [OPTIONS]
```

Configuration priority is CLI option, environment variable, JSON config file,
then built-in default. Environment variables use the `QUICKEDIT_` prefix.

## Frequently used options

| Option | Default | Purpose |
| --- | --- | --- |
| `-o, --output PATH` | `<input>_edited.ext` | Output video, or output directory for a batch. |
| `--dry-run` | off | Analyze and write sidecars without rendering. |
| `--overwrite` | off | Replace an existing output intentionally. |
| `--llm / --no-llm` | off | Enable or disable semantic LLM editing. |
| `--subtitle-style` | `fancy` | `fancy`, `simple`, or `none`. |
| `--margin` | `0.2` | Padding around kept sections, in seconds. |
| `--minclip` | `0.1` | Remove shorter keep fragments. |
| `--mincut` | `0.2` | Fill shorter cut gaps. |
| `--clear-cache` | off | Clear input cache before processing. |
| `--no-cache` | off | Avoid cache reads and writes. |

## Configuration file

Pass `--config settings.json`. Keys use underscores, for example:

```json
{
  "whisper_model": "small",
  "motion_frame_skip": 2,
  "subtitle_style": "simple",
  "use_llm": false,
  "preset": "fast"
}
```

Run `quickedit --help` for the complete option list. The release workflow
checks this page against the Click command contract before publishing.
