# QuickEdit — Changelog

## 1.0.0 — Unreleased

### Production release foundation

- Renamed the installable package from `src` to `quickedit`; the `quickedit`
  command remains the supported user interface.
- Made LLM editing explicit opt-in with `--llm`; regular editing is local-first.
- Added safe output replacement with `--overwrite`, atomic rendering, cache
  clearing, FFmpeg/FFprobe preflight, and audio-stream validation.
- Migrated Gemini integration to the maintained `google-genai` SDK and made
  Anthropic/Gemini provider dependencies optional extras.
- Added reproducible Python and documentation lockfiles, automated lint/type/
  test/build checks, GitHub Pages deployment, CodeQL, and Dependabot.
- Documented source-only installation and added a Linux/macOS source installer
  script.
- Added generated-media end-to-end smoke tests and a motion-backend benchmark
  script for comparing real screen recordings.
- Made the FFmpeg motion backend the default after benchmarks showed matching
  activity detection with much faster analysis on long screen recordings.
- Fixed nested LLM cut merging, separated silent-motion frame-ratio semantics,
  and report true wall-clock pipeline duration.
- Made batch failures exit non-zero, reject duplicate destinations and malformed
  configuration before analysis, and protect every generated sidecar with
  `--overwrite`.
- Isolated and versioned per-video caches so clearing one input cannot delete a
  neighboring video's analysis.
- Added bounded FFmpeg/FFprobe execution and deterministic process cleanup, and
  changed large-timeline rendering to one codec-safe final encode.
- Publish timeline and subtitle sidecars atomically only after successful
  processing.
- Added Python 3.11/3.13 CI, package and documentation builds, dependency
  audits, and targeted regression coverage for the corrected paths.
- Added MIT licensing, contribution/community/security policies, issue forms,
  a public roadmap, and the Astro/Starlight documentation site.

## Session 3: Performance, UX, and Reliability Improvements

**Date:** 2026-05-30  
**Commits:** 2 (`1d49717`, `87dcb6a`)  
**Files changed:** 6 modified, 1 created  
**Net change:** +390 insertions, −126 deletions

---

### 🎯 Issues Addressed (from code review)

| # | Issue | Status |
|---|-------|--------|
| 1 | No progress bar during transcription (slowest step) | ✅ Fixed |
| 2 | Async detection fragile — `try/except RuntimeError` loop detection | ✅ Fixed |
| 3 | No batch processing — single file only | ✅ Fixed |
| 4 | Parallel analysis — VAD, motion, transcription run sequentially | ✅ Fixed |
| 5 | FFmpeg segment extraction runs sequentially | ✅ Fixed |
| 6 | `_validate_config` uses wrong attribute names (`margin`, `confidence`) | ✅ Fixed |

---

### ✨ New Feature: Rich Progress Bars

**File:** `src/progress.py` (new)  
**Commit:** `1d49717`

Added a `rich`-based progress bar system that shows live, per-step progress
during processing. Each pipeline step gets its own bar:

```
  🎙  Voice Detection  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 78.9% speech — 3.2s
  🎬  Motion Detection ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 45.2% activity — 8.1s
  📝  Transcription    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 842 words — 12.3s
  🤖  LLM Analysis     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 5 cuts — 4.1s
  🎞  Rendering        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% Done — 15.7s
```

**How it works:**
- `ProgressReporter` wraps `rich.progress.Progress` and manages task bars
- Pipeline callbacks `(step, progress, message)` update the corresponding bar
- Thread-safe — works correctly with parallel analysis steps
- Each bar shows: emoji icon, step name, fill bar, percentage, status message, elapsed time

**Files touched:**
- `src/progress.py` — New module with `ProgressReporter` class
- `src/cli.py` — Wires reporter as `config.progress_callback`
- `src/pipeline.py` — Reports granular progress at every step
- `pyproject.toml` — Added `rich>=13.0.0` dependency

---

### 🔧 Fix: Robust Async Event Loop Detection

**File:** `src/edit/llm.py`  
**Commit:** `1d49717`

**Problem:**  
The LLM module used a fragile `try/except RuntimeError` pattern to detect
whether an asyncio event loop was running:

```python
# BEFORE (fragile)
try:
    asyncio.get_running_loop()
    return _analyze_with_llm_sync(...)   # loses parallelism!
except RuntimeError:                      # catches ANY RuntimeError
    return asyncio.run(...)
```

Three problems:
1. `except RuntimeError` is too broad — catches unrelated errors
2. In Jupyter, loop is always running → falls back to sync → **loses parallelism**
3. Anti-pattern: exceptions for control flow

**Solution:**

```python
# AFTER (robust)
def _get_running_loop():
    """Narrow, purpose-built helper."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None

running_loop = _get_running_loop()
if running_loop is not None:
    # Jupyter/async: run in thread → own event loop → keeps parallelism
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, analyze_with_llm_async(...))
        return future.result()
else:
    return asyncio.run(analyze_with_llm_async(...))
```

- Narrow `RuntimeError` catch isolated in tiny helper
- Jupyter gets **full async parallelism** via thread with its own event loop
- Clean separation of detection vs. execution

---

### 📦 New Feature: Batch Processing

**File:** `src/cli.py`  
**Commit:** `1d49717`

**Before:** Single file only — `quickedit input.mp4`

**After:** Full batch support:

```bash
# Multiple files
quickedit video1.mp4 video2.mp4 video3.mp4

# Shell glob
quickedit *.mp4

# Batch with output directory
quickedit *.mp4 -o output_dir/
```

**Batch features:**
- Processes files sequentially, each with its own progress bars
- **Error resilience:** one failure doesn't abort the batch
- **Per-file headers:** `[2/5] lecture_02.mp4` 
- **Batch summary** at the end:
  ```
  ══════════════════════════════════════
  Batch Summary
  ══════════════════════════════════════
    Processed: 4/5
    Failed:    1
      ✗ corrupt.mp4: FFmpeg failed (exit 1)
    ✓ video1_edited.mp4
    ✓ video2_edited.mp4
    ✓ video3_edited.mp4
    ✓ video4_edited.mp4
  ```
- **Output path logic:**
  - Single file + `-o path.mp4` → exact output path (unchanged behavior)
  - Batch + `-o dir/` → output directory, auto-names as `input_edited.ext`
  - No `-o` → default `input_edited.ext` alongside source (unchanged)

---

### ⚡ Performance: Parallel Analysis (2-3x speedup)

**File:** `src/pipeline.py`  
**Commit:** `87dcb6a`

**Before** (sequential — total = sum of all steps):
```
VAD:           ████████████                         8s
Motion:                     ████████████████        15s  
Transcription:                               ████████████████████████ 25s
Wall time:     ──────────────────────────────────────────────────── 48s
```

**After** (parallel via `ThreadPoolExecutor(max_workers=3)` — total = max):
```
VAD:           ████████████                          8s
Motion:        ████████████████                     15s  
Transcription: ████████████████████████             25s
Wall time:     ──────────────────────────            25s (1.9x speedup)
```

**Why this is safe:**
- VAD reads audio energy via FFmpeg → numpy
- Motion reads video frames via OpenCV
- Transcription reads audio via faster-whisper
- None depend on each other's output
- All read from the same source file (read-only, no contention)
- Progress callbacks are thread-safe (rich handles concurrent updates)

The actual speedup is logged:
```
Parallel analysis: 25.1s wall time (vs 48.3s sequential — 1.9x speedup)
```

---

### ⚡ Performance: Parallel FFmpeg Segment Extraction

**File:** `src/render/video.py`  
**Commit:** `87dcb6a`

When using the `segments` render strategy (>50 clips), each clip was extracted
one at a time:

```python
# BEFORE
for i, clip in enumerate(timeline.clips):
    _run_ffmpeg(extract_segment_cmd, quiet=True)  # sequential
```

**Now** runs `min(cpu_count, 4)` FFmpeg processes concurrently:

```python
# AFTER
with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 4)) as executor:
    futures = {executor.submit(_extract_segment, i, clip): i ...}
    for future in as_completed(futures):
        i, seg_path = future.result()
        segment_paths[i] = seg_path  # maintain correct order
```

- Capped at 4 workers to avoid disk I/O thrashing
- Results indexed by position so concat order is preserved despite `as_completed()`
  returning in arbitrary order
- Progress logged every 10 segments

---

### 🐛 Bugfix: `_validate_config` Attribute Names

**File:** `src/cli.py`  
**Commit:** `1d49717`

Fixed validation using wrong attribute names on `PipelineConfig`:

```diff
- if config.margin < 0:
+ if config.start_margin < 0:

- if not 0.0 <= config.confidence <= 1.0:
+ if not 0.0 <= config.llm_confidence_threshold <= 1.0:
```

These would have caused `AttributeError` at runtime if validation was triggered.

---

### Summary of Files Changed

| File | Change |
|------|--------|
| `src/progress.py` | **New** — Rich progress bar reporter |
| `src/cli.py` | Batch processing, progress wiring, validation fix |
| `src/pipeline.py` | Parallel analysis, granular progress reporting |
| `src/render/video.py` | Parallel FFmpeg segment extraction |
| `src/edit/llm.py` | Robust async loop detection |
| `pyproject.toml` | Added `rich>=13.0.0` dependency |
