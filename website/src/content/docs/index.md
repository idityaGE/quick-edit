---
title: QuickEdit
description: Local-first, AI-assisted video editing from the command line.
template: splash
hero:
  title: Edit recordings without a timeline
  tagline: QuickEdit finds speech and visual activity, removes inactive sections, and creates subtitles. Semantic LLM cuts are strictly opt-in.
  actions:
    - text: Get started
      link: /quick-edit/getting-started/install/
      icon: right-arrow
    - text: View on GitHub
      link: https://github.com/idityaGE/quick-edit
      icon: external
---

## Local-first by default

A standard edit uses speech and motion analysis on your machine and does not
require an API key.

## Built for video workflows

QuickEdit produces an edited video, subtitles, and a machine-readable timeline
sidecar.

## Optional semantic cuts

Enable Anthropic or Gemini only when you want transcript-aware cuts and accept
the provider's data handling terms.

## What QuickEdit does

QuickEdit combines voice activity detection, frame-motion analysis, transcript
timestamps, smoothing, and FFmpeg rendering. It is designed for talking-head
videos, tutorials, lectures, screen recordings, and batches of recordings.

Start with a dry run, inspect the cuts, then render when you are happy with the
settings.
