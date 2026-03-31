# Codebase Concerns

**Analysis Date:** 2026-04-01

## Tech Debt

**No Test Suite:**
- Issue: No unit tests, integration tests, or test directory exist in the project
- Files: N/A - tests are entirely missing
- Impact: No automated verification of functionality; regressions go undetected; refactoring is risky
- Fix approach: Create `tests/` directory with pytest fixtures and tests for each module. Priority: test `combine.py` boolean logic, `smoothing.py` frame processing, and `llm.py` JSON parsing

**Hard-coded Silero VAD Fallback Logic:**
- Issue: The VAD module has a try/except import fallback from `torch.hub` to `faster_whisper.vad` without explicit documentation of when each is used
- Files: `src/analyze/vad.py` (lines 156-187)
- Impact: Behavior differs silently depending on installed packages; debugging VAD issues is harder
- Fix approach: Make the VAD backend explicit via config option, or document the fallback chain clearly

**Magic Numbers in Motion Detection:**
- Issue: Pixel change threshold (10) and silence gap duration (0.7s in subtitles) are hard-coded
- Files: `src/analyze/motion.py` (line 111), `src/render/subtitle.py` (line 193)
- Impact: Tuning requires code changes; different video types may need different thresholds
- Fix approach: Extract to configuration parameters in `PipelineConfig`

**Assertion-Based Validation in WAV Reader:**
- Issue: Uses `assert` statements for input validation which can be disabled with `-O` flag
- Files: `src/analyze/vad.py` (lines 132-133)
- Impact: Invalid audio could cause cryptic downstream errors in production
- Fix approach: Replace `assert` with explicit `if` checks that raise `ValueError`

**Cache Key Collision Risk:**
- Issue: Cache key uses 16-character truncated SHA-256 hash; while unlikely, collisions possible at scale
- Files: `src/cache/cache.py` (line 57)
- Impact: Different videos with same params could return wrong cached data
- Fix approach: Use full hash or longer prefix (32+ chars)

## Known Bugs

**LLM Chunk Overlap May Drop Decisions:**
- Symptoms: Edit decisions near chunk boundaries may be deduplicated incorrectly
- Files: `src/edit/llm.py` (lines 306-339)
- Trigger: Transcripts longer than CHUNK_SIZE_WORDS (3000 words) with edits near chunk boundaries
- Workaround: Set confidence threshold lower to retain borderline decisions

**Frame Count Mismatch Between Video and Audio:**
- Symptoms: Arrays get silently padded/truncated when VAD/motion frame counts don't match video metadata
- Files: `src/pipeline.py` (lines 382-387, 422-426)
- Trigger: Variable frame rate videos, or videos where ffprobe metadata differs from actual frame count
- Workaround: None; silent data truncation occurs

**Timeline Merge Cut Index Not Reset:**
- Symptoms: In `merge_timelines`, `cut_idx` is incremented but never reset when iterating clips, potentially skipping LLM cuts that span multiple clips
- Files: `src/timeline/timeline.py` (lines 234-246)
- Trigger: LLM cuts that end before the start of a later clip
- Workaround: Ensure LLM cuts don't span across multiple kept segments

## Security Considerations

**Subprocess Command Injection Risk:**
- Risk: FFmpeg/FFprobe commands use string interpolation for file paths; paths with shell metacharacters could cause issues
- Files: `src/analyze/vad.py` (lines 35-48, 57-67, 81-93), `src/render/video.py` (lines 97-132, 175-222)
- Current mitigation: Uses `subprocess.run()` with list arguments (not shell=True), which is relatively safe
- Recommendations: Validate/sanitize file paths before use; ensure no shell metacharacters are interpreted

**API Key Handling:**
- Risk: Anthropic API key passed through config and environment variable
- Files: `src/pipeline.py` (line 77), `src/edit/llm.py` (lines 141, 157)
- Current mitigation: Reads from `ANTHROPIC_API_KEY` env var, doesn't log the key
- Recommendations: Document that API key should never be committed; add `.env` to `.gitignore` if not present

**Uncapped LLM Response Processing:**
- Risk: LLM response is parsed without size limits; malicious/malformed response could cause memory issues
- Files: `src/edit/llm.py` (lines 266-302)
- Current mitigation: None
- Recommendations: Add response size validation before JSON parsing

## Performance Bottlenecks

**Full Video Frame Iteration for Motion Detection:**
- Problem: Motion detection reads and processes every frame sequentially
- Files: `src/analyze/motion.py` (lines 76-121)
- Cause: No frame skipping or multi-threaded processing
- Improvement path: Add frame skip option (e.g., analyze every Nth frame); use multiprocessing for frame processing

**Repeated Timeline Iteration in Subtitle Remapping:**
- Problem: For each word, iterates through all clips to find containing clip
- Files: `src/render/subtitle.py` (lines 154-172)
- Cause: Linear search instead of binary search or index
- Improvement path: Build a time-indexed data structure for O(log n) clip lookup

**FFmpeg Filter Complex for Many Clips:**
- Problem: Rendering many clips creates huge filter_complex strings that FFmpeg processes slowly
- Files: `src/render/video.py` (lines 139-223)
- Cause: All trim/concat operations in single filter
- Improvement path: Use `render_segments_then_concat()` for timelines with >50 clips (already implemented but not auto-selected)

**Synchronous LLM API Calls:**
- Problem: Each transcript chunk is sent to Claude synchronously, blocking until response
- Files: `src/edit/llm.py` (lines 179-198)
- Cause: Sequential chunk processing
- Improvement path: Use async Anthropic client; process chunks in parallel with rate limiting

## Fragile Areas

**LLM JSON Response Parsing:**
- Files: `src/edit/llm.py` (lines 266-302)
- Why fragile: Relies on LLM returning exact JSON format; markdown code blocks are stripped heuristically; no schema validation
- Safe modification: Add JSON schema validation; use structured output if Anthropic supports it; add retry logic
- Test coverage: None

**Boolean Expression Parser:**
- Files: `src/analyze/combine.py` (lines 89-171)
- Why fragile: Custom string parsing for expressions like "or:speech,motion"; no formal grammar; nested expressions use list format
- Safe modification: Consider using a proper parser library; add comprehensive tests for edge cases
- Test coverage: None

**ASS Subtitle Formatting:**
- Files: `src/render/subtitle.py` (lines 254-277)
- Why fragile: Hard-coded ASS format with manual string interpolation; color codes in specific format (&HAABBGGRR)
- Safe modification: Use a subtitle library or template system; add format validation
- Test coverage: None

## Scaling Limits

**In-Memory Frame Arrays:**
- Current capacity: Works for videos up to ~4 hours at 30fps (~432,000 frames as bool array ≈ 54KB, acceptable)
- Limit: Memory issues possible with float32 motion_values array for very long videos (4hr @ 30fps = ~1.7MB, still acceptable)
- Scaling path: Current approach is memory-efficient; no immediate concern

**LLM Token Limits:**
- Current capacity: Chunks transcripts at 3000 words; Claude handles up to 200K tokens
- Limit: Very dense transcripts with long words could exceed chunk token limits
- Scaling path: Add token counting instead of word counting for chunk boundaries

**FFmpeg Filter Complexity:**
- Current capacity: Works for ~100 clips without issue
- Limit: Timelines with 500+ clips may cause FFmpeg to be slow or fail
- Scaling path: Auto-switch to segment-then-concat approach (`render_segments_then_concat()`) for large timelines

## Dependencies at Risk

**torch (Optional):**
- Risk: Large dependency (~2GB) only used for Silero VAD; falls back to faster-whisper's bundled VAD
- Impact: Unnecessary disk/download time if torch installed but faster-whisper VAD sufficient
- Migration plan: Make torch truly optional; document that faster-whisper VAD is preferred for lighter installs

**anthropic:**
- Risk: External API dependency; rate limits, pricing changes, or API deprecation could break LLM features
- Impact: Core editing workflow degraded without LLM pass
- Migration plan: Add support for alternative LLM providers (OpenAI, local models via Ollama); make LLM pass optional (already is via `--no-llm`)

## Missing Critical Features

**No Progress Callbacks:**
- Problem: Long-running operations (transcription, motion analysis, render) don't report progress
- Blocks: Integration with GUI wrappers; user feedback during processing
- Location: `src/pipeline.py` (entire `run_pipeline` function)

**No Resume/Checkpoint Support:**
- Problem: If pipeline fails mid-way (e.g., during render), must restart from beginning
- Blocks: Reliable processing of large videos; recovery from crashes

**No Video Format Validation:**
- Problem: Assumes input video has audio track; no validation of codec compatibility
- Blocks: Clear error messages for unsupported formats
- Location: `src/pipeline.py` (line 154 only checks existence)

## Test Coverage Gaps

**Core Editing Logic Untested:**
- What's not tested: `src/edit/smoothing.py`, `src/edit/margin.py`, `src/edit/edl.py`
- Files: All files in `src/edit/`
- Risk: Frame array manipulation bugs could cause incorrect cuts; off-by-one errors common in this domain
- Priority: High

**Timeline Manipulation Untested:**
- What's not tested: `frames_to_timeline()`, `merge_timelines()`, clip boundary handling
- Files: `src/timeline/timeline.py`
- Risk: Wrong output timestamps, missing clips, or duplicated content
- Priority: High

**LLM Response Parsing Untested:**
- What's not tested: Edge cases in `_parse_llm_response()`, `_deduplicate_decisions()`
- Files: `src/edit/llm.py`
- Risk: Malformed LLM responses could crash pipeline or produce wrong edits
- Priority: Medium

**Subtitle Generation Untested:**
- What's not tested: ASS/SRT formatting, timestamp remapping, word grouping
- Files: `src/render/subtitle.py`
- Risk: Subtitles out of sync, formatting errors, encoding issues
- Priority: Medium

---

*Concerns audit: 2026-04-01*
