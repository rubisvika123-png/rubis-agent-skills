"""Answer every new top-level comment on the owner's YouTube Shorts with one
fixed reply. A comment counts as "already handled" if its id is in our own
replied.txt, or if any reply under it already comes from the channel owner.

The local file is not optional. This script used to rely on the API check
alone, and that produced real duplicates under Vika's videos (screenshot
22.09.2026: the same reply twice, a day apart) — commentThreads.list returns
only a PARTIAL list of replies, so our own answer can simply be missing from
the response and the thread looks unanswered.

Only Shorts are touched: long-form uploads (meetings, recordings) are
skipped by duration, since they can sit at the top of "recent uploads" and
crowd out the actual Shorts (own channel checked 2026-09-05: meeting
recordings run 20-75 minutes, real Shorts run 12s-64s).

Usage:
  python autoreply.py                 -> one pass over recent videos, live
  python autoreply.py --dry-run       -> print what it WOULD reply, no writes
  python autoreply.py --video VIDEO_ID -> only that one video (skips the Shorts filter)
"""
import argparse
import re
import sys
import time
from pathlib import Path
from gauth import youtube_service, config

MAX_VIDEOS = 50           # scan this many recent uploads to FIND Shorts among them
MAX_THREADS_PER_VIDEO = 100
SHORT_MAX_SECONDS = 180   # YouTube's own extended Shorts ceiling


def _duration_seconds(iso8601):
    # PT1H2M3S -> 3723. No external lib needed for this narrow a format.
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso8601)
    h, mnt, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mnt * 60 + s


def _filter_to_shorts(youtube, video_ids):
    shorts = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = youtube.videos().list(part="contentDetails", id=",".join(batch)).execute()
        for item in resp["items"]:
            if _duration_seconds(item["contentDetails"]["duration"]) <= SHORT_MAX_SECONDS:
                shorts.append(item["id"])
    return shorts


def _reply_text():
    return config().get("REPLY_TEXT") or "Спасибо за комментарий! Ссылка — в шапке профиля 🙌"


def _my_channel_id(youtube):
    resp = youtube.channels().list(part="id", mine=True).execute()
    return resp["items"][0]["id"]


def _recent_video_ids(youtube, channel_id, limit):
    resp = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    uploads_playlist = resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while len(ids) < limit:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_playlist,
            maxResults=min(50, limit - len(ids)), pageToken=page,
        ).execute()
        ids += [item["contentDetails"]["videoId"] for item in resp["items"]]
        page = resp.get("nextPageToken")
        if not page:
            break
    return ids


# Comment ids we have already answered. This file is the ONLY dependable guard
# against double replies: asking YouTube "did I already reply?" is not, because
# commentThreads.list returns a PARTIAL `replies` block — documented as a limited
# subset, and it sometimes comes back without our own reply in it. When that
# happens the old code saw an unanswered thread and replied a second time.
# Vika hit this more than once; on 22.09.2026 she sent a screenshot with the same
# reply sitting under one comment twice, a day apart.
STATE_FILE = Path(__file__).resolve().parent.parent / "replied.txt"


def _load_replied():
    try:
        return {
            line.strip()
            for line in STATE_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except FileNotFoundError:
        return set()


def _remember_replied(comment_id):
    with STATE_FILE.open("a", encoding="utf-8") as f:
        f.write(comment_id + "\n")


def _needs_reply(thread, my_channel_id, replied_ids):
    top = thread["snippet"]["topLevelComment"]
    if top["snippet"]["authorChannelId"]["value"] == my_channel_id:
        return False  # don't reply to our own comment
    if top["id"] in replied_ids:
        return False  # our own record wins over what the API chose to return
    replies = thread.get("replies", {}).get("comments", [])
    already_replied = any(
        r["snippet"]["authorChannelId"]["value"] == my_channel_id for r in replies
    )
    return not already_replied


def process_video(youtube, video_id, my_channel_id, reply_text, dry_run):
    replied = 0
    page = None
    scanned = 0
    replied_ids = _load_replied()
    while scanned < MAX_THREADS_PER_VIDEO:
        resp = youtube.commentThreads().list(
            part="snippet,replies", videoId=video_id,
            maxResults=min(100, MAX_THREADS_PER_VIDEO - scanned),
            pageToken=page, textFormat="plainText",
        ).execute()
        for thread in resp["items"]:
            scanned += 1
            if not _needs_reply(thread, my_channel_id, replied_ids):
                continue
            parent_id = thread["snippet"]["topLevelComment"]["id"]
            author = thread["snippet"]["topLevelComment"]["snippet"]["authorDisplayName"]
            if dry_run:
                print(f"[dry-run] video={video_id} would reply to {author} (comment {parent_id})")
            else:
                youtube.comments().insert(
                    part="snippet",
                    body={"snippet": {"parentId": parent_id, "textOriginal": reply_text}},
                ).execute()
                # Remember it BEFORE anything else can fail: a crash after the
                # reply is posted but before we record it would bring the
                # duplicate straight back on the next run.
                _remember_replied(parent_id)
                replied_ids.add(parent_id)
                print(f"replied to {author} on video {video_id}")
                time.sleep(1)  # stay well under quota bursts
            replied += 1
        page = resp.get("nextPageToken")
        if not page:
            break
    return replied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--video", help="only process this one video id")
    args = ap.parse_args()

    youtube = youtube_service()
    my_channel_id = _my_channel_id(youtube)
    reply_text = _reply_text()

    if args.video:
        video_ids = [args.video]
    else:
        candidates = _recent_video_ids(youtube, my_channel_id, MAX_VIDEOS)
        video_ids = _filter_to_shorts(youtube, candidates)
        print(f"Просмотрел {len(candidates)} последних видео, из них Shorts: {len(video_ids)}")

    total = 0
    for vid in video_ids:
        try:
            total += process_video(youtube, vid, my_channel_id, reply_text, args.dry_run)
        except Exception as e:
            # Comments disabled on a video (403) shouldn't kill the whole run.
            print(f"skip video {vid}: {e}", file=sys.stderr)

    print(f"Готово: {'нашёл бы' if args.dry_run else 'ответил на'} {total} новых комментариев.")


if __name__ == "__main__":
    main()
