"""Google auth for the YouTube comment autoreply — reads OAuth client from
config.env next to the skill. token.json is created once by oauth_youtube.py."""
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get("YT_CONFIG", os.path.join(HERE, "..", "config.env"))
YT_TOKEN = os.path.join(HERE, "..", "token.json")


def _load_env(path):
    data = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def config():
    return _load_env(CONFIG)


def _creds():
    if not os.path.exists(YT_TOKEN):
        raise SystemExit("Нет token.json. Сначала выдай доступ: python oauth_youtube.py")
    creds = Credentials.from_authorized_user_file(YT_TOKEN)
    if not creds.valid:
        creds.refresh(Request())
        with open(YT_TOKEN, "w") as f:
            f.write(creds.to_json())
    return creds


def youtube_service():
    return build("youtube", "v3", credentials=_creds())
