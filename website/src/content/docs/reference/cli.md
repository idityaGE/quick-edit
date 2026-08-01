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

## Input and output

| Argument or option | Default | Purpose |
| --- | --- | --- |
| `INPUT_PATHS` | required | One or more input video files. Multiple inputs run as a batch. |
| `-o, --output PATH` | `<input>_edited.ext` | Output video path for one input, or output directory for a batch. |
| `--overwrite` | off | Replace an existing output video intentionally. |
| `--dry-run` | off | Analyze, build the timeline, and write sidecars without rendering. |

QuickEdit refuses to replace an existing output unless `--overwrite` is set.
In batch mode, a failed file is reported and the remaining inputs continue.

## Configuration and environment

| Option | Default | Purpose |
| --- | --- | --- |
| `--config FILE` | none | Read a JSON config file. Keys use underscores, such as `whisper_model`. |

Every CLI option can also be set as a `QUICKEDIT_` environment variable by
uppercasing the option name and replacing dashes with underscores. For example,
`QUICKEDIT_WHISPER_MODEL=small` sets the same value as `--whisper-model small`.

## Configuration file

Pass `--config settings.json`. Keys use underscores, for example:

```json
{
  "whisper_model": "small",
  "motion_frame_skip": 2,
  "motion_backend": "opencv-parallel",
  "motion_workers": 4,
  "subtitle_style": "simple",
  "use_llm": false,
  "preset": "fast"
}
```

## Speech and transcription

| Option | Default | Purpose |
| --- | --- | --- |
| `--whisper-model TEXT` | `base` | Whisper model size. Common values are `tiny`, `base`, `small`, `medium`, and `large-v3`. |
| `--device TEXT` | `cpu` | Device for faster-whisper, usually `cpu` or `cuda`. |
| `--whisper-compute-type VALUE` | auto | Compute type: `int8`, `float16`, `float32`, or `int8_float16`. If omitted, QuickEdit uses `int8` on CPU and `float16` on CUDA. |
| `--language TEXT` | auto | Language code such as `en`. Leave unset to auto-detect. |
| `--vad-threshold FLOAT` | `0.5` | Voice activity sensitivity from `0.0` to `1.0`. Lower values are more sensitive. |

Transcription runs when subtitles, LLM editing, or a `words` combine detector
needs word timestamps. Speech detection uses VAD and does not require subtitles.

## Motion analysis

| Option | Default | Purpose |
| --- | --- | --- |
| `--motion-threshold FLOAT` | `0.02` | Fraction of changed pixels required for a frame to count as active. |
| `--motion-pixel-threshold INTEGER` | `10` | Pixel brightness change from `0` to `255` required before a pixel counts as changed. |
| `--motion-frame-skip INTEGER` | `1` | Analyze every Nth frame. Higher values are faster but can miss short changes. |
| `--motion-backend VALUE` | `opencv` | Motion backend: `opencv`, `opencv-parallel`, or `ffmpeg`. |
| `--motion-workers INTEGER` | `4` | Worker count for `--motion-backend opencv-parallel`. |

Motion analysis is skipped when `--combine` does not reference `motion` and LLM
editing is disabled.

## Editing logic

| Option | Default | Purpose |
| --- | --- | --- |
| `--combine TEXT` | `or:speech,motion` | Combine detector arrays. Examples: `speech`, `or:speech,motion`, `and:speech,motion`, `xor:speech,motion`, `not:motion`. |
| `--margin FLOAT` | `0.2` | Add padding before and after kept regions, in seconds. |
| `--minclip FLOAT` | `0.1` | Remove keep segments shorter than this many seconds. |
| `--mincut FLOAT` | `0.2` | Fill cut gaps shorter than this many seconds. |

The available detector names are `speech`, `motion`, and `words`. `words` uses
transcribed word timestamps, so it requires transcription.

## Optional LLM editing

| Option | Default | Purpose |
| --- | --- | --- |
| `--llm` | off | Enable semantic LLM editing. Transcript data and prompt context are sent to the selected provider. |
| `--no-llm` | on | Disable semantic LLM editing. This is the default. |
| `--llm-model TEXT` | `claude-sonnet-4-20250514` | LLM model name. `claude-*` uses Anthropic; `gemini-*` uses Google. |
| `--prompt TEXT` | none | Inline custom editing instructions for the LLM. |
| `--prompt-template VALUE` | none | Built-in prompt template: `dsa`, `tutorial`, or `lecture`. |
| `--prompt-file PATH` | none | Read custom editing instructions from a file. |
| `--confidence FLOAT` | `0.7` | Minimum confidence for LLM-suggested cuts from `0.0` to `1.0`. |
| `--silent-segment-min-duration FLOAT` | `0.5` | Minimum silence duration, in seconds, before a silent segment is classified for LLM context. |

For Anthropic models, set `ANTHROPIC_API_KEY`. For Gemini models, set
`GOOGLE_API_KEY` or `GEMINI_API_KEY`.

## Subtitles

| Option | Default | Purpose |
| --- | --- | --- |
| `--subtitle-style VALUE` | `fancy` | Subtitle style: `fancy` for ASS word highlighting, `simple` for SRT, or `none`. |
| `--subtitle-font TEXT` | `Arial` | Font name used for ASS subtitles. |
| `--subtitle-size INTEGER` | `20` | Font size used for ASS subtitles. |
| `--subtitle-silence-gap FLOAT` | `0.7` | Silence gap, in seconds, that starts a new subtitle group. |

Subtitle sidecars are written next to the output path. Fancy subtitles use
`.ass`; simple subtitles use `.srt`.

## Rendering

| Option | Default | Purpose |
| --- | --- | --- |
| `--codec TEXT` | `libx264` | FFmpeg video codec. |
| `--crf INTEGER` | `18` | Constant rate factor from `0` to `51`; lower means higher quality and larger files. |
| `--preset VALUE` | `medium` | FFmpeg encoding preset: `ultrafast`, `superfast`, `veryfast`, `faster`, `fast`, `medium`, `slow`, `slower`, or `veryslow`. |
| `--audio-codec TEXT` | `aac` | FFmpeg audio codec. |
| `--audio-bitrate TEXT` | `192k` | FFmpeg audio bitrate. |

Rendering requires both `ffmpeg` and `ffprobe` on `PATH`.

## Cache and logging

| Option | Default | Purpose |
| --- | --- | --- |
| `--no-cache` | off | Disable cache reads and writes for this run. |
| `--clear-cache` | off | Clear cached analysis for each input before processing it. |
| `-v, --verbose` | off | Show verbose logging and exception details. |
| `--version` | n/a | Print the installed QuickEdit version and exit. |
| `--help` | n/a | Print command help and exit. |

Analysis caches live in `.quickedit_cache/` beside each input video.
