# External Integrations

**Analysis Date:** 2026-04-01

## APIs & External Services

**Anthropic Claude API:**
- Purpose: Semantic analysis of transcripts to identify filler words, false starts, tangents, repetitions
- SDK/Client: `anthropic` Python package
- Auth: `ANTHROPIC_API_KEY` environment variable (auto-read by SDK)
- Usage: `src/edit/llm.py`
- Models: `claude-sonnet-4-20250514` (default), configurable via `--llm-model`
- Features used:
  - `client.messages.create()` with system prompt and user messages
  - Max tokens: 4096
  - Chunked processing for long transcripts (3000 words/chunk with 200-word overlap)

**Silero VAD (PyTorch Hub):**
- Purpose: Voice activity detection
- Client: PyTorch Hub download (`snakers4/silero-vad`)
- Auth: None required (public model)
- Usage: `src/analyze/vad.py`
- Fallback: Uses faster-whisper's bundled Silero VAD if PyTorch not available

**Whisper (via faster-whisper):**
- Purpose: Speech-to-text transcription with word-level timestamps
- Client: `faster-whisper.WhisperModel`
- Auth: None required (local model download)
- Usage: `src/analyze/transcribe.py`
- Models downloaded from Hugging Face Hub on first use

## External CLI Tools

**FFmpeg (Required):**
- Purpose: Video/audio processing, rendering, subtitle burning
- Called via: `subprocess.run()` in multiple modules
- Usage locations:
  - `src/analyze/vad.py` - Audio extraction (`ffmpeg -vn -acodec pcm_s16le`)
  - `src/render/video.py` - Video rendering with filter_complex concat
- Features used:
  - Audio extraction to 16kHz mono WAV
  - Video trimming and concatenation
  - ASS/SRT subtitle burning
  - H.264/AAC encoding with CRF quality control

**FFprobe (Required):**
- Purpose: Video metadata extraction (fps, duration, dimensions, frame count)
- Called via: `subprocess.run()` with JSON output
- Usage: `src/analyze/vad.py` - `get_video_info()` function

## Data Storage

**Databases:**
- None - No database integration

**File Storage:**
- Local filesystem only
- Input: Video files (any FFmpeg-supported format)
- Output: Edited video, timeline JSON, subtitle files (ASS/SRT)

**Caching:**
- Custom file-based cache in `.quickedit_cache/` directory
- Location: Same directory as input video
- Format: NPZ (numpy arrays) and JSON files
- Cache key: SHA256 hash of file path + mtime + size + method + params
- Implementation: `src/cache/cache.py`
- Cached operations:
  - VAD results (speech frame arrays)
  - Motion detection results (motion frame arrays)
  - Transcription results (word-level timestamps)

## Authentication & Identity

**Auth Provider:**
- None - CLI tool with no user authentication

**API Authentication:**
- Anthropic: API key via `ANTHROPIC_API_KEY` environment variable

## Monitoring & Observability

**Error Tracking:**
- None - No external error tracking service

**Logs:**
- Python `logging` module to stdout
- Configurable verbosity via `-v/--verbose` flag
- Format: `%(asctime)s [%(levelname)s] %(message)s`

## CI/CD & Deployment

**Hosting:**
- N/A - Local CLI tool, not a hosted service

**CI Pipeline:**
- Not detected (no `.github/workflows/`, `.gitlab-ci.yml`, etc.)

## Environment Configuration

**Required env vars:**
- `ANTHROPIC_API_KEY` - For LLM semantic analysis (optional if using `--no-llm`)

**Optional env vars:**
- None detected

**Secrets location:**
- Environment variables only
- No `.env` file present

## Webhooks & Callbacks

**Incoming:**
- None - Not a web service

**Outgoing:**
- None - No webhook integrations

## API Usage Patterns

**Anthropic API Request Format:**
```python
client = Anthropic(api_key=api_key)
response = client.messages.create(
    model=model,
    max_tokens=4096,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_message}],
)
```

**Response Parsing:**
- Expects JSON response with `{"decisions": [...]}` structure
- Handles markdown code blocks in response
- Each decision contains: `start_time`, `end_time`, `reason`, `confidence`, `transcript`, `note`

## Rate Limiting & Quotas

**Anthropic:**
- No explicit rate limiting implemented
- Long transcripts chunked to stay within context limits
- Chunk size: 3000 words with 200-word overlap

---

*Integration audit: 2026-04-01*
