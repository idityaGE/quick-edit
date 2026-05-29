# QuickEdit User Guide

## What This Tool Does

QuickEdit is an AI-powered video editor that automatically removes boring parts from your videos. It analyzes speech, motion, and meaning, then cuts out silence, filler words, mistakes, and dead air.

---

## How Editing Works (The Simple Version)

QuickEdit looks at your video and decides which parts to **keep** and which to **remove**. Think of it like highlighting the good parts.

### The Raw Timeline Problem

After analyzing speech and motion, QuickEdit might produce a rough timeline like this:

```
Raw Analysis:
KKKKKKCCCCCKKKCKKKKKCCCCCCCKKKKKKK   (K = Keep, C = Cut)
    ↑      ↑  ↑   ↑       ↑
    |      |  |   |       |
  good   gap good tiny   good
  part         blip gap
```

This looks messy! There are:
- **Tiny gaps** inside good parts → makes the video feel choppy
- **Tiny keep blips** inside cut regions → single frames that flash by
- **Rough edges** where speech starts/ends → might cut off a word

The three flags below fix these problems.

---

## `--margin 0.2` — "Give Me Some Breathing Room"

**What it does:** Adds extra padding at the start and end of every kept segment.

**Simple version:** If QuickEdit decides to keep a part from `10s` to `15s`, with `--margin 0.2` it actually keeps from `9.8s` to `15.2s` instead.

**Why it's useful:**

Imagine someone says: *(pause)* "So the main point is..."

Without margin:
```
Cut here ↑              ↑ Cut here
         |              |
   [DEAD AIR] "So the main point is..." [DEAD AIR]
```
The cut is too tight and chops off the "S" in "So".

With `--margin 0.2`:
```
        ← 0.2s →
             ↓
   "..."  "So the main point is..."  "..."
             ↑
        ← 0.2s →
```
You get a tiny bit of breathing room so words don't get clipped.

| Value | Effect |
|-------|--------|
| `0.0` | Exact cuts. Risk of chopped words. |
| `0.2` (default) | Small buffer. Usually perfect. |
| `0.5` | Half-second buffer. Safer but might keep more dead air. |
| `1.0` | One second buffer. Very safe. Might include unwanted silence. |

**When to change it:**
- Increase to `0.3`–`0.5` if words sound cut off at the start/end
- Decrease to `0.1` or `0.0` if you want absolutely tight cuts (podcast style)

---

## `--minclip 0.1` — "Ignore Micro-Keeps"

**What it does:** If a kept segment is shorter than `0.1` seconds, just throw it away and treat it as a cut.

**Simple version:** Prevents tiny "keep blips" from flashing on screen.

**Why it's useful:**

Without minclip, the timeline might look like:
```
CCCCCCCCCKCKKKKKKKKKKCCKCKKCCCCCCC
         ↑↑          ↑↑ ↑↑
         ||          || ||
     1-frame      tiny blips
     blips       (0.05s each)
```

Those single-frame or tiny keeps are probably:
- A cough or breath detected as speech
- A tiny motion flash (light change, camera shake)
- A word fragment that shouldn't stand alone

With `--minclip 0.1`:
```
CCCCCCCCCKKKKKKKKKKKKKKKKKKCCCCCCC
         ↑                ↑
         |                |
      blip removed    blips removed
```

| Value | Effect |
|-------|--------|
| `0.0` | Keep everything, even 1-frame blips. |
| `0.1` (default) | Remove keeps under 0.1 seconds. Good balance. |
| `0.3` | Remove keeps under 0.3s. Cleaner but might remove short words. |
| `0.5` | Half-second minimum. Very clean, might cut "Hi!" or "Yes." |

**When to change it:**
- Increase to `0.3` if you see tiny flashes in the output
- Decrease to `0.05` or `0.0` if short words ("Hi!", "No.", "OK!") are being removed

---

## `--mincut 0.2` — "Don't Micro-Cut"

**What it does:** If a gap (cut) is shorter than `0.2` seconds, keep it instead.

**Simple version:** Prevents rapid-fire cuts that feel jarring.

**Why it's useful:**

Without mincut, the timeline might look like:
```
KKKKCKKKCKKKCKKKCKKKKKK
     ↑   ↑   ↑
     |   |   |
   0.1s 0.1s 0.1s cuts
```

These tiny cuts feel like the video is glitching:
- "Welcome" [cut] "to" [cut] "my" [cut] "video" → feels broken
- A tiny breath pause between sentences → unnecessary cut

With `--mincut 0.2`:
```
KKKKKKKKKKKKKKKKKKKKKKK
```
The tiny gaps are filled in. The flow is smooth.

| Value | Effect |
|-------|--------|
| `0.0` | Cut everywhere the AI says to cut. Might be very choppy. |
| `0.2` (default) | Fill gaps under 0.2s. Removes micro-cuts. |
| `0.5` | Half-second minimum. Smoother flow, might keep some dead air. |
| `1.0` | One-second minimum. Very smooth. Might keep noticeable pauses. |

**When to change it:**
- Increase to `0.5` for a smoother, more relaxed pace
- Decrease to `0.1` if you want very aggressive cutting (fast-paced TikTok style)

---

## The Three Flags Working Together

Here's how they transform raw analysis into smooth output:

```
Raw Analysis:
KKCKKKKCKKKKKKKKCKCKKKKKKKCKKKCKK   (very messy)

Step 1: Apply --margin 0.2
→ Expand each K by 0.2s on both sides
KKKKCKKKKKCKKKKKKKKKCKCKKKKKKKCKKKCKKK

Step 2: Apply --mincut 0.2
→ Fill gaps under 0.2s
KKKKKKKKKKKKKKKKKKKKCKCKKKKKKKKKKKKKKK

Step 3: Apply --minclip 0.1
→ Remove tiny keeps (none in this example)
KKKKKKKKKKKKKKKKKKKKCKCKKKKKKKKKKKKKKK

Final Output:
KKKKKKKKKKKKKKKKKKKKCCCCCKKKKKKKKKKKKK   (smooth and clean)
```

---

## `--motion-frame-skip 2` — "Speed Hack for Long Videos"

**What it does:** Instead of analyzing every single frame for motion, only check every 2nd frame (or 3rd, etc.), and guess the ones in between.

**Simple version:** Makes motion detection faster by doing less work.

**How motion detection works normally:**

```
Frame 1:  Check (0.0s)     ← compare to frame 0
Frame 2:  Check (0.033s)   ← compare to frame 1
Frame 3:  Check (0.066s)   ← compare to frame 2
Frame 4:  Check (0.1s)     ← compare to frame 3
Frame 5:  Check (0.133s)   ← compare to frame 4
           ...
→ For a 10-minute video = checking 18,000 frames
→ Takes a while
```

With `--motion-frame-skip 2`:

```
Frame 1:  Check (0.0s)     ← compare to frame 0
Frame 2:  SKIP  (0.033s)   ← estimate: average of frame 1 and 3
Frame 3:  Check (0.066s)   ← compare to frame 1
Frame 4:  SKIP  (0.1s)     ← estimate: average of frame 3 and 5
Frame 5:  Check (0.133s)   ← compare to frame 3
           ...
→ For a 10-minute video = checking 9,000 frames
→ Roughly 2x faster!
```

| Value | What happens | Speed | Accuracy |
|-------|-------------|-------|----------|
| `1` (default) | Check every frame | Slowest | Most accurate |
| `2` | Check every 2nd frame | 2x faster | Slightly less accurate |
| `3` | Check every 3rd frame | 3x faster | May miss quick motions |
| `5` | Check every 5th frame | 5x faster | May miss brief actions |

**When to use it:**
- **Skip = 1:** Short videos (< 5 min), tutorials where every gesture matters, free time
- **Skip = 2:** Most videos. Good balance. Recommended default for 5–30 min videos.
- **Skip = 3:** Long videos (30+ min), podcasts, screen recordings with minimal motion
- **Skip = 5+:** Very long videos, batch processing, rough drafts

**What might be missed with higher skip values:**
- A quick hand gesture (0.1s long)
- A brief screen flash or transition
- Someone quickly nodding or pointing

For talking-head videos where mostly just mouths move, the default or skip=2 is fine.

---

## Quick Reference: Recommended Settings

| Video Type | Good Settings |
|-----------|--------------|
| **Talking head / Vlog** | `--margin 0.2 --mincut 0.2 --minclip 0.1` |
| **Podcast / Interview** | `--margin 0.3 --mincut 0.5 --minclip 0.1` |
| **Tutorial / Screen recording** | `--margin 0.2 --mincut 0.3 --minclip 0.1 --motion-frame-skip 3` |
| **Fast-paced / TikTok** | `--margin 0.1 --mincut 0.1 --motion-frame-skip 1` |
| **Long lecture (1hr+)** | `--margin 0.3 --mincut 0.5 --minclip 0.2 --motion-frame-skip 3` |
| **Quick draft preview** | `--no-llm --motion-frame-skip 3 --preset fast` |

---

## Full Flag Summary

See `REFERENCE.md` for the complete technical reference of every flag.

### Basic Usage

```bash
# Edit with all defaults
quickedit myvideo.mp4

# Save to custom filename
quickedit myvideo.mp4 -o edited.mp4

# Fast edit, no AI
quickedit myvideo.mp4 --no-llm

# Edit with smooth, relaxed cuts
quickedit myvideo.mp4 --margin 0.3 --mincut 0.5

# Edit aggressively for fast pace
quickedit myvideo.mp4 --margin 0.1 --mincut 0.1

# Speed up analysis on long video
quickedit myvideo.mp4 --motion-frame-skip 3
```

### All Options Mentioned Here

| Flag | Default | What it does |
|------|---------|-------------|
| `--margin` | `0.2` | Add breathing room around kept sections |
| `--minclip` | `0.1` | Remove tiny keep segments shorter than this |
| `--mincut` | `0.2` | Fill tiny cut gaps shorter than this |
| `--motion-frame-skip` | `1` | Only check every Nth frame for motion |
