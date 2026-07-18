---
title: Optional LLM editing
description: Enable transcript-aware cuts with clear privacy and cost boundaries.
---

## Local-first behavior

QuickEdit does not call an LLM unless you pass `--llm`. Standard speech and
motion analysis remains local, although faster-whisper may download its model
weights on first use.

## Enable a provider

```bash
export ANTHROPIC_API_KEY='...'
quickedit recording.mp4 --llm --llm-model claude-sonnet-4-20250514
```

Or, after installing the Gemini extra:

```bash
export GEMINI_API_KEY='...'
quickedit recording.mp4 --llm --llm-model gemini-3.5-flash
```

QuickEdit sends word-level transcript data, your selected editing prompt, and
silent-segment classifications to the selected provider. It does not upload the
source video itself. Provider usage can incur charges; review your provider's
current policies, retention terms, and pricing before use.

## Make conservative cuts

Use `--confidence` to require higher-confidence suggestions. `--prompt`,
`--prompt-file`, and `--prompt-template` provide domain-specific instructions.
When in doubt, run `--dry-run` first.
