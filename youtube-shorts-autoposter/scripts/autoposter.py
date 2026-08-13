"""YouTube autoposter: Drive folder -> transcribe -> AI title/desc -> upload Short.

One pass over the source folder:
  1. find video files directly in it (the "done" subfolder is separate)
  2. download -> extract audio (ffmpeg) -> transcribe (Groq Whisper, ru)
  3. LLM writes a catchy YouTube-Shorts title + description from the transcript
  4. upload to the channel as a Short (privacy from config: public/unlisted/private)
  5. move the Drive file into the "done" subfolder so it never posts twice

Run:  ./venv/bin/python autoposter.py           # all pending videos
      ./venv/bin/python autoposter.py --once    # only the first one
"""
import os
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
import sys
import json
import subprocess
import tempfile

from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from groq import Groq

from gauth import drive_service, youtube_service, config

TRANSCRIBE_MODEL = "whisper-large-v3-turbo"
TEXT_MODEL = "llama-3.3-70b-versatile"


def _groq(cfg):
    key = cfg.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not key:
        raise SystemExit("Нет GROQ_API_KEY в config.env")
    return Groq(api_key=key)


def _find_folder(drive, name, parent=None):
    q = (f"mimeType='application/vnd.google-apps.folder' and trashed=false "
         f"and name='{name}'")
    if parent:
        q += f" and '{parent}' in parents"
    items = drive.files().list(q=q, fields="files(id,name)").execute().get("files", [])
    return items[0]["id"] if items else None


def _pending_videos(drive, folder_id):
    q = f"'{folder_id}' in parents and trashed=false"
    files = drive.files().list(
        q=q, fields="files(id,name,mimeType)", pageSize=200
    ).execute().get("files", [])
    return [f for f in files if f["mimeType"].startswith("video/")]


def _download(drive, file_id, dest):
    req = drive.files().get_media(fileId=file_id)
    with open(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()


def _extract_audio(video_path, audio_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
         "-b:a", "64k", audio_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _transcribe(groq, audio_path):
    with open(audio_path, "rb") as f:
        r = groq.audio.transcriptions.create(
            file=(os.path.basename(audio_path), f.read()), model=TRANSCRIBE_MODEL)
    return r.text.strip()


def _title_and_desc(groq, transcript):
    prompt = (
        "Ты SEO-редактор YouTube Shorts. По расшифровке короткого вертикального "
        "ролика придумай цепляющие заголовок и описание на русском, заточенные "
        "под алгоритмы YouTube, чтобы ролик залетел. Заголовок: до 90 символов, "
        "интрига/польза, без обмана. Описание: 2-4 живые строки + 5-8 релевантных "
        "хэштегов, обязательно #shorts. Верни СТРОГО JSON: "
        '{"title": "...", "description": "..."}\n\nРасшифровка:\n' + transcript[:6000]
    )
    r = groq.chat.completions.create(
        model=TEXT_MODEL, messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}, temperature=0.7,
    )
    data = json.loads(r.choices[0].message.content)
    title = data["title"].strip()[:100]
    desc = data["description"].strip()
    if "#shorts" not in desc.lower():
        desc += "\n\n#shorts"
    return title, desc


def _upload(youtube, video_path, title, desc, privacy):
    body = {
        "snippet": {"title": title, "description": desc, "categoryId": "22"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    return youtube.videos().insert(
        part="snippet,status", body=body, media_body=media).execute()["id"]


def _move_to_done(drive, file_id, from_id, to_id):
    drive.files().update(
        fileId=file_id, addParents=to_id, removeParents=from_id, fields="id").execute()


def main():
    once = "--once" in sys.argv
    cfg = config()
    folder_name = cfg.get("YT_FOLDER", "Для Ютуба")
    done_name = cfg.get("YT_DONE", "Опубликовано")
    privacy = cfg.get("YT_PRIVACY", "public")

    drive, youtube, groq = drive_service(), youtube_service(), _groq(cfg)

    folder_id = _find_folder(drive, folder_name)
    if not folder_id:
        raise SystemExit(f"Не нашёл папку «{folder_name}» на Диске")
    done_id = _find_folder(drive, done_name, parent=folder_id) or drive.files().create(
        body={"name": done_name, "mimeType": "application/vnd.google-apps.folder",
              "parents": [folder_id]}, fields="id").execute()["id"]

    videos = _pending_videos(drive, folder_id)
    if not videos:
        print("Новых роликов нет.")
        return
    if once:
        videos = videos[:1]

    results = []
    for vid in videos:
        print(f"→ {vid['name']}")
        with tempfile.TemporaryDirectory() as tmp:
            vpath = os.path.join(tmp, vid["name"])
            apath = os.path.join(tmp, "audio.mp3")
            _download(drive, vid["id"], vpath)
            _extract_audio(vpath, apath)
            transcript = _transcribe(groq, apath)
            title, desc = _title_and_desc(groq, transcript)
            vid_id = _upload(youtube, vpath, title, desc, privacy)
            _move_to_done(drive, vid["id"], folder_id, done_id)
            url = f"https://youtube.com/shorts/{vid_id}"
            print(f"   {title}\n   {url}")
            results.append({"title": title, "url": url})
    print("\nГОТОВО:", json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
