"""Answer every new top-level comment on the owner's YouTube videos with one
fixed reply. Stateless by design: a comment counts as "already handled" if
ANY reply under it already comes from the channel owner — so restarting this
script never causes duplicate replies, no local tracking file needed.

Usage:
  python autoreply.py                 -> one pass over recent videos, live
  python autoreply.py --dry-run       -> print what it WOULD reply, no writes
  python autoreply.py --video VIDEO_ID -> only that one video
"""
import argparse
import os
import sys
import time
from gauth import youtube_service, config

MAX_VIDEOS = 15          # how many of the channel's most recent videos to scan
MAX_THREADS_PER_VIDEO = 100


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


def _needs_reply(thread, my_channel_id):
    top = thread["snippet"]["topLevelComment"]
    if top["snippet"]["authorChannelId"]["value"] == my_channel_id:
        return False  # don't reply to our own comment
    replies = thread.get("replies", {}).get("comments", [])
    already_replied = any(
        r["snippet"]["authorChannelId"]["value"] == my_channel_id for r in replies
    )
    return not already_replied


def process_video(youtube, video_id, my_channel_id, reply_text, dry_run):
    replied = 0
    page = None
    scanned = 0
    while scanned < MAX_THREADS_PER_VIDEO:
        resp = youtube.commentThreads().list(
            part="snippet,replies", videoId=video_id,
            maxResults=min(100, MAX_THREADS_PER_VIDEO - scanned),
            pageToken=page, textFormat="plainText",
        ).execute()
        for thread in resp["items"]:
            scanned += 1
            if not _needs_reply(thread, my_channel_id):
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

    video_ids = [args.video] if args.video else _recent_video_ids(youtube, my_channel_id, MAX_VIDEOS)

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
