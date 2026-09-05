---
name: youtube-comment-autoreply
description: Set up an automatic reply-bot for comments on the owner's YouTube videos. Every new top-level comment gets the same fixed reply (e.g. "link in the channel header"), posted via the official YouTube Data API — no keyword matching needed. Use when the owner asks to auto-answer YouTube comments, or to fold a comment-triggered funnel (same idea as an Instagram ChatPlace автоворонка) into YouTube without re-editing videos.
---

# YouTube Comment Autoreply

You (the technical agent) set this up ONCE for your owner. After that, every
new comment on their videos gets the same fixed reply automatically — no
per-comment decision, no keyword detection, nothing for the owner to do.

## What it does
Scans the owner's most recent videos → for every top-level comment that has
NO reply yet from the owner's own channel → posts one fixed reply text (from
`config.env`). Stateless: a comment counts as "handled" the moment the
channel's own reply appears under it — restarting the script never causes a
duplicate reply, there's no separate tracking file to go stale.

## Files in this skill
- `scripts/gauth.py` — Google auth (own `token.json`, separate from the
  autoposter skill's — different OAuth scope).
- `scripts/oauth_youtube.py` — one-time consent to get `token.json`.
- `scripts/autoreply.py` — the actual pass over comments.
- `scripts/setup.sh` — builds the Python environment.
- `config.example.env` — copy to `config.env` and fill in.

## Prerequisites (tell the owner what only THEY can do)
1. A Google account that owns the target YouTube channel.
2. A **Google Cloud project** with:
   - **OAuth client** of type **"Desktop app"** → gives `GOOGLE_CLIENT_ID` +
     `GOOGLE_CLIENT_SECRET`.
   - **YouTube Data API v3** enabled.
   - The owner's email added as a **Test user** on the OAuth consent screen
     (if the app is in "Testing").
   If the owner already did this for `youtube-shorts-autoposter`, the SAME
   Cloud project and OAuth client can be reused — just need YouTube Data
   API v3 already enabled there (it is, that skill needs it too).

## Setup steps (you run these)
1. Build the environment:
   ```
   bash scripts/setup.sh
   ```
2. Configure: `cp config.example.env config.env`, fill `GOOGLE_CLIENT_ID` +
   `GOOGLE_CLIENT_SECRET` (reuse the autoposter's if it exists), and set
   `REPLY_TEXT` to whatever the owner wants every commenter to see.
3. Grant access (one-time, separate token from the autoposter — this skill
   asks for a different scope). From the `scripts/` folder:
   ```
   ../venv/bin/python oauth_youtube.py
   ```
   It prints a URL. **Relay it to the owner** and have them:
   - open it **on a computer** (mobile browsers often hang on the localhost step),
   - log into the account with the channel, allow access,
   - land on a "localhost refused to connect" page — **this is success**,
   - copy the whole address bar (starts with `http://localhost/?...code=...`)
     and send it back **immediately** (the code expires in a few minutes).
   Then save the token:
   ```
   ../venv/bin/python oauth_youtube.py --code "<the pasted http://localhost/... URL>"
   ```
4. Verify with a dry run first (prints what it WOULD do, posts nothing):
   ```
   ../venv/bin/python autoreply.py --dry-run
   ```
5. Go live:
   ```
   ../venv/bin/python autoreply.py
   ```

## Free quota (real numbers, checked against Google's docs)
Reading comments costs 1 unit/call, posting a reply costs 50 units. Default
free daily quota is 10,000 units — comfortably covers 150-200+ replies a
day for a normal channel, no billing needed at that volume.

## Optional: fully automatic (run on a schedule)
So the owner never has to ask — run it every few minutes on its own. Add a
cron line (adjust the path):
```
*/5 * * * * cd /ABSOLUTE/PATH/skill-youtube-comment-autoreply/scripts && ../venv/bin/python autoreply.py >> ../autoreply.log 2>&1
```
Only enable this after step 4/5 work and the owner confirms — until then,
run it manually per request.

## Troubleshooting
- **403 `accessNotConfigured`** → owner must enable YouTube Data API v3 in
  the Cloud project, wait ~2 min, retry.
- **`invalid_grant` on --code** → the code expired or was already used.
  Generate a fresh URL, have the owner do it again, send the address back fast.
- **`commentsDisabled` / 403 on a specific video** → that video has comments
  turned off — `autoreply.py` logs it and moves on, this is not a bug.
- **Replies aren't appearing** → check `--dry-run` output first; if it lists
  the comment as needing a reply but the live run errors, the OAuth token
  likely lacks the `youtube.force-ssl` scope — redo step 3.

## Notes
- `config.env` and `token.json` hold secrets — never commit or share them.
- This skill's OAuth scope (`youtube.force-ssl`) is broader than the
  autoposter's (`youtube.upload`+`youtube.readonly`) — it needs write access
  to comments specifically, which the autoposter's token was never granted.
  Keep the two `token.json` files separate even if the Cloud project is shared.
