---
title: Security and privacy
description: How QuickEdit treats local media, API keys, and vulnerabilities.
---

## Media and transcripts

Speech, motion, rendering, and subtitle generation run locally. Enabling
`--llm` sends the transcript, edit prompt, and silent-segment metadata to the
selected provider; it does not send the source video. Do not enable an LLM for
material you are not authorized to share with that provider.

## Secrets

Use environment variables for provider keys. `.env` files are ignored by the
repository and must never be committed or included in issue reports.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Follow the
[security policy](https://github.com/idityaGE/quick-edit/security/policy) for
private reporting instructions.
