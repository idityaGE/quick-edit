# QuickEdit CLI Reference

## Configuration priority

```
CLI flag  >  environment variable  >  config file  >  built-in default
```

## Config file

Pass `--config path/to/settings.json`. Keys use **underscores** (not hyphens).

```json
{
  "whisper_model": "small",
  "device": "cuda",
  "vad_threshold": 0.35,
  "motion_threshold": 0.015,
  "motion_frame_skip": 2,
  "no_llm": false,
  "llm_model": "claude-opus-4-6",
  "confidence": 0.75,
  "subtitle_style": "fancy",
  "subtitle_silence_gap": 0.5,
  "codec": "libx265",
  "crf": 22,
  "preset": "fast",
  "audio_bitrate": "256k"
}
```

Any flag below has a matching env var: `QUICKEDIT_<FLAG_NAME_UPPERCASED>`.
Example: `--vad-threshold` → `QUICKEDIT_VAD_THRESHOLD`.

---

## Flags

### I/O

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `INPUT_PATH` (arg) | — | *(required)* | Input video file |
| `-o / --output` | `QUICKEDIT_OUTPUT` | `<input>_edited.mp4` | Output file path |
| `--config FILE` | `QUICKEDIT_CONFIG` | — | JSON config file (see above) |

---

### Analysis — Speech (VAD)

Voice activity detection uses the Silero VAD model (via torch.hub, falls back to faster-whisper).
Produces a per-frame boolean array: `True` = speech detected.

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--whisper-model` | `QUICKEDIT_WHISPER_MODEL` | `base` | Whisper model size for transcription: `tiny` `base` `small` `medium` `large-v3`. Larger = more accurate, slower. |
| `--device` | `QUICKEDIT_DEVICE` | `cpu` | Compute device: `cpu` or `cuda`. Affects Whisper transcription. |
| `--whisper-compute-type` | `QUICKEDIT_WHISPER_COMPUTE_TYPE` | auto | Whisper quantization: `int8` `float16` `float32` `int8_float16`. Default: `int8` on CPU, `float16` on CUDA. |
| `--language` | `QUICKEDIT_LANGUAGE` | auto-detect | Language code, e.g. `en`, `fr`. Skip auto-detection for a speed boost. |
| `--vad-threshold` | `QUICKEDIT_VAD_THRESHOLD` | `0.5` | Silero VAD confidence threshold `0.0–1.0`. Lower = more sensitive (keeps more audio), higher = stricter. |

---

### Analysis — Motion

Detects visual activity via OpenCV frame differencing.
Produces a per-frame boolean array: `True` = motion detected.

Pipeline per frame: resize → grayscale → Gaussian blur → abs-diff against previous frame → threshold pixel count.

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--motion-threshold` | `QUICKEDIT_MOTION_THRESHOLD` | `0.02` | Fraction of pixels that must change for a frame to count as "active" (0.0–1.0, i.e. 2% of pixels). Lower = more sensitive. |
| `--motion-pixel-threshold` | `QUICKEDIT_MOTION_PIXEL_THRESHOLD` | `10` | Per-pixel brightness change magnitude (0–255) required to count a pixel as "changed". |
| `--motion-frame-skip` | `QUICKEDIT_MOTION_FRAME_SKIP` | `1` | Analyze every Nth frame. `1` = all frames, `2` = every other frame. Intermediate frames are linearly interpolated. Use `2`–`3` to speed up long videos. |

---

### Detection combination

After VAD and motion produce two bool arrays, a combine expression merges them into one `keep_frames` array.

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--combine` | `QUICKEDIT_COMBINE` | `or:speech,motion` | Boolean expression over named arrays. |

**Expression syntax:**

```
or:speech,motion          keep if speech OR motion
and:speech,motion         keep only if both
not:speech                invert speech array
xor:speech,motion         keep if exactly one is active
speech                    use speech array alone
motion                    use motion array alone
or:speech,words           speech OR word-timestamps (when transcription runs)
```

Named arrays available: `speech`, `motion`, `words` (word-timestamp array from Whisper, present when LLM or subtitles are enabled).

---

### Edit — Margin and smoothing

After combining, the raw `keep_frames` array is refined.

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--margin` | `QUICKEDIT_MARGIN` | `0.2` | Expand every keep-region by this many seconds at both ends. Prevents cutting off word starts/ends. |
| `--minclip` | `QUICKEDIT_MINCLIP` | `0.1` | Remove keep segments shorter than this (seconds). Eliminates single-frame blips. |
| `--mincut` | `QUICKEDIT_MINCUT` | `0.2` | Fill cut gaps shorter than this (seconds). Prevents choppy micro-cuts. |

---

### LLM semantic pass

Optional second pass: sends the transcript + silent segment metadata to an LLM.
The LLM returns timestamped cut decisions (filler words, tangents, dead air, etc.).
These are merged into the timeline on top of the VAD+motion cuts.

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--no-llm` | `QUICKEDIT_NO_LLM` | off | Disable the LLM pass entirely. Faster; relies only on VAD + motion. |
| `--llm-model` | `QUICKEDIT_LLM_MODEL` | `claude-sonnet-4-20250514` | Model ID. Prefix `claude-*` uses Anthropic API (`ANTHROPIC_API_KEY`). Prefix `gemini-*` uses Google API (`GOOGLE_API_KEY`). |
| `--prompt` | `QUICKEDIT_PROMPT` | built-in rules | Custom editing instructions sent to the LLM instead of the default prompt. |
| `--prompt-template` | `QUICKEDIT_PROMPT_TEMPLATE` | — | Use a built-in template: `dsa` (algorithm tutorials), `tutorial` (coding tutorials), `lecture` (educational lectures). |
| `--prompt-file` | `QUICKEDIT_PROMPT_FILE` | — | Read custom prompt from a file. Overridden by `--prompt`. |
| `--confidence` | `QUICKEDIT_CONFIDENCE` | `0.7` | Minimum LLM confidence score `0.0–1.0` to apply a suggested cut. Higher = fewer, more certain cuts. |
| `--silent-segment-min-duration` | `QUICKEDIT_SILENT_SEGMENT_MIN_DURATION` | `0.5` | Minimum silent segment length (seconds) to send to the LLM for classification. Shorter silences are ignored by the LLM pass. |

**Prompt resolution order:** `--prompt` → `--prompt-file` → `--prompt-template` → built-in default.

**API keys (env vars, not CLI flags):**

| Model prefix | Required env var |
|---|---|
| `claude-*` | `ANTHROPIC_API_KEY` |
| `gemini-*` | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |

---

### Subtitles

Subtitles are generated from Whisper word-level timestamps, remapped to output timeline positions. Words inside cut segments are dropped.

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--subtitle-style` | `QUICKEDIT_SUBTITLE_STYLE` | `fancy` | `fancy` = ASS word-by-word highlight (Instagram/TikTok style). `simple` = plain SRT. `none` = no subtitles. |
| `--subtitle-font` | `QUICKEDIT_SUBTITLE_FONT` | `Arial` | Font family name for subtitles. |
| `--subtitle-size` | `QUICKEDIT_SUBTITLE_SIZE` | `20` | Font size in points. |
| `--subtitle-silence-gap` | `QUICKEDIT_SUBTITLE_SILENCE_GAP` | `0.7` | Gap between words (seconds) that forces a new subtitle group. Smaller = more, shorter subtitles. |

---

### Rendering (FFmpeg)

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--codec` | `QUICKEDIT_CODEC` | `libx264` | Video codec. `libx264` (H.264), `libx265` (H.265, smaller files), `libvpx-vp9`, `copy` (remux only). |
| `--crf` | `QUICKEDIT_CRF` | `18` | Constant Rate Factor `0–51`. Lower = better quality, larger file. `18` ≈ visually lossless. `23` = default x264 quality. |
| `--preset` | `QUICKEDIT_PRESET` | `medium` | Encoding speed vs compression: `ultrafast` `superfast` `veryfast` `faster` `fast` `medium` `slow` `slower` `veryslow`. Slower = smaller file at same quality. |
| `--audio-codec` | `QUICKEDIT_AUDIO_CODEC` | `aac` | Audio codec. `aac`, `libmp3lame`, `copy` (keep original). |
| `--audio-bitrate` | `QUICKEDIT_AUDIO_BITRATE` | `192k` | Audio bitrate. `128k` (small), `192k` (default), `256k` or `320k` (high quality). |

**Strategy:** 1 clip → simple trim. 2–50 clips → `filter_complex` concat. 50+ clips → segment files then concat demuxer.

---

### Caching

Analysis results (VAD, motion, transcription) are cached to `.quickedit_cache/` next to the video file. Cache keys include file path + mtime + size + method + parameters. Re-running with the same video and same parameters hits the cache; changing any parameter invalidates only that step's cache.

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--no-cache` | `QUICKEDIT_NO_CACHE` | off | Disable cache reads and writes. Forces full re-analysis every run. |

---

### Misc

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--dry-run` | `QUICKEDIT_DRY_RUN` | off | Run all analysis steps, build timeline, generate subtitles — but skip FFmpeg render. Prints the full cut list with timestamps and reasons. |
| `-v / --verbose` | `QUICKEDIT_VERBOSE` | off | Enable DEBUG logging (model loading, frame counts, cache hits, FFmpeg commands). |

---

## Examples

```bash
# Basic — all defaults
quickedit lecture.mp4

# Fast pass — no LLM, skip every other frame, small whisper
quickedit lecture.mp4 --no-llm --motion-frame-skip 2 --whisper-model small

# GPU acceleration
quickedit lecture.mp4 --device cuda --whisper-compute-type float16

# Aggressive cuts — stricter VAD, more silence removed
quickedit lecture.mp4 --vad-threshold 0.7 --mincut 0.5 --margin 0.1

# Speech only (ignore motion)
quickedit screencast.mp4 --combine speech

# Keep only segments with BOTH speech and activity
quickedit screencast.mp4 --combine and:speech,motion

# DSA tutorial preset with high-quality output
quickedit tutorial.mp4 --prompt-template dsa --preset slow --crf 16

# Custom prompt from file
quickedit podcast.mp4 --prompt-file my_rules.txt --confidence 0.8

# H.265 output, smaller file
quickedit lecture.mp4 --codec libx265 --crf 24

# Simple SRT subtitles, tighter groups
quickedit talk.mp4 --subtitle-style simple --subtitle-silence-gap 0.4

# Dry run — see what would be cut without rendering
quickedit lecture.mp4 --dry-run --verbose

# Config file + override one flag
quickedit lecture.mp4 --config production.json --preset ultrafast

# Full env-var driven (CI/automation)
QUICKEDIT_WHISPER_MODEL=small \
QUICKEDIT_NO_LLM=1 \
QUICKEDIT_PRESET=fast \
QUICKEDIT_SUBTITLE_STYLE=none \
quickedit "$INPUT" -o "$OUTPUT"
```

---

## Pipeline steps (in order)

1. **Video info** — FFprobe extracts fps, duration, frame count, dimensions.
2. **VAD** *(cached)* — Silero VAD → `speech_frames[bool]`
3. **Motion** *(cached)* — OpenCV frame diff → `motion_frames[bool]`
4. **Transcription** *(cached, conditional)* — faster-whisper → word timestamps
5. **Combine** — evaluate `--combine` expression → `keep_frames[bool]`
6. **Margin + smooth** — expand regions by `--margin`, remove short clips/gaps
7. **LLM pass** *(optional)* — classify silent segments, get cut decisions, merge into timeline
8. **Build timeline** — `keep_frames` → `Timeline` of `Clip` + `CutSegment` objects
9. **Subtitles** *(conditional)* — remap word timestamps to output time → `.ass` or `.srt`
10. **Render** — FFmpeg concat → output video + `.timeline.json`
