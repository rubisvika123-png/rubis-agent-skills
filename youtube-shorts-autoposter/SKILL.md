---
name: youtube-shorts-autoposter
description: Set up an automatic YouTube Shorts autoposter for the owner's channel. The owner drops vertical videos into a Google Drive folder; this pipeline downloads each one, transcribes it, writes an SEO-optimized title + description with an LLM, uploads it to the owner's channel as a public Short, then moves the file to a "done" subfolder. Use when the owner asks to auto-publish their videos to YouTube from a Drive folder.
---

# YouTube Shorts Autoposter

You (the technical agent) set this up ONCE for your owner. After that, the owner
just drops a vertical video into their Drive folder and the pipeline publishes it.

## What it does
Drive folder **«Для Ютуба»** → download new video → extract audio (ffmpeg) →
transcribe (Groq Whisper, ru) → LLM writes a catchy, algorithm-friendly title +
description → upload to the owner's channel as a **Short** → move the file into
subfolder **«Опубликовано»** (so nothing posts twice).

## Files in this skill
- `scripts/gauth.py` — Google auth (one `token.json` covers Drive + YouTube).
- `scripts/oauth_youtube.py` — one-time consent to get `token.json`.
- `scripts/autoposter.py` — the pipeline.
- `scripts/setup.sh` — builds the Python environment.
- `config.example.env` — copy to `config.env` and fill in.

## Prerequisites (tell the owner what only THEY can do)
1. A Google account that owns the target YouTube channel.
2. A **Google Cloud project** with:
   - **OAuth client** of type **"Desktop app"** → gives `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`.
   - **YouTube Data API v3** enabled, and **Google Drive API** enabled.
   - The owner's email added as a **Test user** on the OAuth consent screen (if the app is in "Testing").
3. A **Groq API key** (console.groq.com) → `GROQ_API_KEY`.
4. `ffmpeg` installed on the server (`apt install -y ffmpeg`).
5. In the owner's Google Drive: a folder named **«Для Ютуба»** (create subfolder
   **«Опубликовано»** inside it, or the script creates it on first run).

## Setup steps (you run these)
1. Build the environment:
   ```
   bash scripts/setup.sh
   ```
2. Configure: `cp config.example.env config.env`, then fill `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `GROQ_API_KEY` (folder names/privacy have sane defaults).
3. Grant access (one-time). From the `scripts/` folder:
   ```
   ../venv/bin/python oauth_youtube.py
   ```
   It prints a URL. **Relay it to the owner** and have them:
   - open it **on a computer** (mobile browsers often hang on the localhost step),
   - log into the account with the channel, allow access,
   - land on a "localhost refused to connect" page — **this is success**,
   - copy the whole address bar (starts with `http://localhost/?...code=...`) and
     send it back **immediately** (the code expires in a few minutes).
   Then save the token:
   ```
   ../venv/bin/python oauth_youtube.py --code "<the pasted http://localhost/... URL>"
   ```
4. Verify it works (prints the channel name):
   ```
   ../venv/bin/python -c "from gauth import youtube_service; print(youtube_service().channels().list(part='snippet',mine=True).execute()['items'][0]['snippet']['title'])"
   ```
5. Post: put a vertical video in «Для Ютуба», then:
   ```
   ../venv/bin/python autoposter.py --once    # first run: verify one video
   ../venv/bin/python autoposter.py           # process all pending
   ```
   Tip for the very first run, set `YT_PRIVACY=unlisted` in `config.env` to check
   the result before it goes public, then switch back to `public`.

## Optional: fully automatic (auto-schedule)
So the owner never has to ask — check the folder every N minutes and post on its
own. Add a cron line (adjust the path), e.g. every 10 minutes:
```
*/10 * * * * cd /ABSOLUTE/PATH/skill-youtube-shorts-autoposter/scripts && ../venv/bin/python autoposter.py >> ../autopost.log 2>&1
```
(Or a systemd timer if you prefer.) Only enable this after step 4 works and the
owner confirms they want it — until then, run it manually.

## Troubleshooting
- **403 `accessNotConfigured` / "API has not been used"** → the owner must enable
  **YouTube Data API v3** (and Drive API) in the Cloud project, wait ~2 min, retry.
- **`invalid_grant` on --code** → the code expired or was already used. Generate a
  fresh URL and have the owner do it again, sending the address back fast.
- **Owner's browser "hangs" after Allow** → use a desktop browser; the localhost
  page is *meant* to fail to load — the code is in the address bar regardless.
- **Title looks generic** → the video had almost no speech; with real speech the
  title/description are rich. Not a bug.
- **Nothing posted, "Новых роликов нет"** → the video isn't a `video/*` file
  directly in «Для Ютуба», or it's already in «Опубликовано».

## Notes
- `config.env` and `token.json` hold secrets — never commit or share them.
- YouTube is throttled in some regions (e.g. Russia); uploads from a server there
  may occasionally be slow or flaky — retry.
