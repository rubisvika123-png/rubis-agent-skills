---
name: reels-montage
description: >
  Assembles vertical (1080x1920) short-form video reels from raw clips: speech-aware
  cutting (removes pauses and stumble/retakes on word boundaries, never mid-word),
  1.2x speed, styled burned-in subtitles, a branded text hook overlay for the first
  seconds, and background music. Use when the owner sends one or more video clips
  plus a hook phrase and asks to montage/edit them into a reel — triggers on
  "смонтируй", "смонтируй ролик", "собери рилс", "montage this", "edit this into a reel".
  NOT for: subtitle-only requests on an already-edited video (use subtitles_only.py
  directly for that), long-form video editing, or any request without raw clips to cut.
---

# Reels Montage

Turns raw clips into a finished vertical reel: cut → speed → subtitles → hook → music.
The pipeline logic (cutting, timing, format) is fixed and proven — don't re-derive it
per request. What's meant to change per owner is only the **look**: colors, fonts,
music track. Those are marked below.

## When to run this

Owner sends one or more video clips (as files, or a note to find them e.g. in a
Drive/Telegram folder) plus a **hook line** — the short line of text overlaid on the
first seconds of the reel — and asks to montage/edit them. If the hook text is missing,
ask for it; don't invent one. If the owner marks which part of the hook to highlight
(e.g. "выделить: 20 минут" / "highlight: 20 minutes"), wrap exactly that span in
`[brackets]` when passing the hook string to the script — that's what gets the marker
underline. No highlight given → the script auto-detects a number/price phrase.

## First-time setup (once per machine)

1. **ffmpeg** — system package. `ffmpeg -version` to check; `apt install ffmpeg` if missing.
2. **A Chrome/Chromium binary** — used only to render the hook text overlay (fonts render
   more reliably via HTML+headless-Chrome than via PIL). `apt install chromium-browser`
   is the simplest path. The script auto-detects `google-chrome`, `chromium-browser`,
   `chromium`, or a Playwright-installed Chromium under `~/.cache/ms-playwright/` — no
   config needed once one of those exists.
3. **Python deps**: `python3 -m venv venv && venv/bin/pip install -r requirements.txt`
   (pulls in `faster-whisper` and its own dependencies). The speech-to-text model
   (`large-v3`, ~2.9GB) downloads automatically on first real run and gets cached —
   the very first render will be slow while it downloads.
4. Sanity check the cutting/retake logic with no external deps needed:
   `venv/bin/python make_reel.py --selfcheck` should print `selfcheck OK: [...]`.

## Running it

```
cd <this skill's folder>
mkdir -p clips
# put the owner's clip(s) in clips/, numbered in the order they should play:
#   clips/1.mov clips/2.mov ...
venv/bin/python make_reel.py "<HOOK TEXT>" clips/1.mov clips/2.mov -o out/reel.mp4
```

A full render (transcribe + cut + subtitles + hook + compose) takes several minutes —
most of it is the one-time speech transcription. Deliver `out/reel.mp4` back to the owner.

**Fast re-render for hook/style-only tweaks** (skips the costly transcription+cut step,
reuses the last render's cut and subtitles): re-run with `--recompose` and the same or
a new hook text — only rebuilds the hook overlay + music + final compose, ~1 minute.

## What's locked (the actual editing logic — don't change without a real reason)

- **Cutting is speech-aware, on word boundaries, never loudness-based.** Transcribes
  once (word-level timestamps), then: never clips a finished word (small padding kept
  around every word, including the last); cuts silences longer than `MAX_PAUSE`
  (0.35s — the tempo knob, lower it for a tighter edit); detects and removes
  stumble/retakes (an aborted phrase immediately restarted — only the clean restart
  survives, subtitles never show the botched attempt).
- **Speed** = 1.2x on the final cut (pitch-preserved, not the "sped-up chipmunk" effect).
- **Format** = vertical 1080x1920, burned-in subtitles (lowercase, centered, no box/plate,
  positioned above the platform's bottom-safe zone), hook shown for the first 4 seconds.
- **Output** = H.264 mp4. If the file comes out ≥ ~48MB, re-encode smaller
  (`-crf 22 -b:a 160k`) before delivering through a channel with an upload size cap.

## What to customize per owner/brand (safe to change, won't break the pipeline)

- **`fonts/`** — swap `Oswald.ttf` (hook headline) and `PlexMono-SmBd.ttf` (numbers in
  the hook) for the owner's own brand fonts. Keep the filenames or update the two
  `@font-face` references inside `make_hook_png()` in `make_reel.py` to match.
- **`music/`** — swap the bundled CC0 track for the owner's own background music (must
  be a track they have rights to use — CC0 is the simplest safe default). The script
  picks up whatever `.mp3` it finds in `music/`, no code change needed if you keep one
  file there.
- **Hook colors** — inside `make_hook_png()`'s embedded CSS: `.hook` text color
  (currently a cream `#F2EFE8`) and `.mark`'s underline color (currently ruby `#9E2233`).
  `CREAM` / `RED` near the top of the file are legacy constants from an earlier design —
  the live hook styling is the CSS inside `make_hook_png()`, edit that.
- **Subtitle look** — the `[V4+ Styles]` line inside `build_ass()` (font, size, color).

## Known constraints

- Runs on Linux (Ubuntu/WSL). Not tested on macOS/Windows-native shells.
- CPU-only transcription (`device="cpu"`) — no GPU requirement, but it's the slowest
  step; that's expected, not a bug.
- One transcription per full render — it's the costly step, so batch feedback/notes
  rather than re-rendering per tiny fix; use `--recompose` for hook/style-only changes.
