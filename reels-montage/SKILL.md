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

## Installation — you (the technical agent) do this, not the owner

The owner needs almost nothing: no keys, no accounts, no signup. The only thing
that's ever theirs to do is drop their own raw clips into `clips/` if they want
to hand you footage directly instead of sending it another way.

**You install and verify this skill yourself, without asking the owner anything:**

1. `git clone https://github.com/rubisvika123-png/rubis-agent-skills.git`
2. `cp -r rubis-agent-skills/reels-montage ~/.claude/skills/`
3. Install system deps: `apt install -y ffmpeg chromium-browser` (chromium renders
   the hook text overlay — fonts render more reliably via HTML+headless-Chrome
   than via PIL). If `chromium-browser` isn't the right package name on this
   box, the script also auto-detects `google-chrome`, `chromium`, or a
   Playwright-installed Chromium under `~/.cache/ms-playwright/` — no config
   needed once one of those exists instead.
4. Build the Python env: `cd ~/.claude/skills/reels-montage && python3 -m venv venv
   && venv/bin/pip install -r requirements.txt`.
5. First run, to confirm it's wired up: `venv/bin/python make_reel.py --selfcheck`
   → should print `selfcheck OK: [...]`. This also silently triggers the ~2.9GB
   whisper model download on the *next* real render, not on selfcheck itself.

Restart the agent (`./start.sh`) once this is done — the skill is picked up
automatically, no further setup step and no announcement to the owner needed
unless something above actually failed (see Troubleshooting).

## When this triggers itself

Owner sends one or more video clips plus a hook line and asks to montage/edit
them — matches phrases like "смонтируй", "смонтируй ролик", "собери рилс",
"montage this", "edit this into a reel" (full trigger list in the front-matter
`description` above). Do NOT trigger on a subtitle-only request on an
already-edited video (use `subtitles_only.py` directly for that), long-form
video editing, or any request with no raw clips to cut.

Owner marks which part of the hook to highlight (e.g. "выделить: 20 минут" /
"highlight: 20 minutes") → wrap exactly that span in `[brackets]` when passing
the hook string to the script — that's what gets the marker underline. No
highlight given → the script auto-detects a number/price phrase.

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

## Limits (tell the owner about these up front, before the first render)

- **First real render is slow** — it downloads the whisper `large-v3` speech
  model (~2.9GB) once and caches it. Every render after that is fast to *start*;
  the transcription step itself still takes a few minutes (CPU-only).
- **Delivery channels cap file size** — e.g. Telegram bots reject uploads over
  ~48MB. If `out/reel.mp4` comes out bigger, re-encode before sending
  (`-crf 22 -b:a 160k`, see "What's locked" above).
- **A hook phrase is required** — the owner must supply the text overlaid on
  the first seconds. Never invent one; ask and wait if it's missing.
- **`--recompose` cache is single-slot** — it only remembers the *last* full
  render's cut/subtitles. To re-hook a reel that wasn't the most recent one,
  you need a full re-render (the cache was already overwritten by a later one).

## If something's off

- **`selfcheck` fails or errors on import** — `venv/pip install -r requirements.txt`
  didn't complete; rerun it and check for a network/pip error in the output.
- **No chromium/chrome found** (hook overlay step fails) — `apt install
  chromium-browser`, or point it at a Playwright-installed Chromium under
  `~/.cache/ms-playwright/` if that's already on the box; no code change needed
  once a binary exists at one of the auto-detected paths.
- **First render feels "stuck" for several minutes** — normal if it's the very
  first render on this machine; it's downloading the 2.9GB model in the
  background. Not a bug. Subsequent renders don't re-download it.
- **Rendered file rejected by the delivery channel ("too big"/"file too large")**
  — re-encode smaller (`-crf 22 -b:a 160k`) before resending, don't re-render
  from scratch.
- **Owner never sent a hook line** — ask for it explicitly; don't guess or
  auto-generate one.
- **Agent got restarted mid-render** (watchdog, crash, usage limit) — check for
  an unfinished render before telling the owner nothing happened: look for a
  live `ffmpeg`/`whisper` process, leftover `out/_last*` cache files, or a
  half-written `out/reel.mp4`; resume/re-render rather than assuming failure.
- **A rendered reel's cut/subtitles look right but the hook text or music is
  wrong** — don't do a full re-render; use `--recompose` (see "Running it")
  to fix just that in ~1 minute.
