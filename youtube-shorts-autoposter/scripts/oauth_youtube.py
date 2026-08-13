"""One-time: grant this server permission to read Drive + upload to YouTube.

Usage:
  1) python oauth_youtube.py            -> prints a URL for the owner to open
  2) Owner logs into THEIR Google account (the one with the YouTube channel),
     allows access. Browser redirects to http://localhost/?code=... — the page
     WON'T load (normal). Owner copies that whole address and sends it back.
     NOTE: the code expires in a few minutes — exchange it promptly.
  3) python oauth_youtube.py --code "<pasted-url-or-code>"  -> saves token.json
"""
import os
# Google returns all already-granted scopes for the account (can be more than we
# asked) — oauthlib rejects that by default; allow it.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
import sys
import urllib.parse
from google_auth_oauthlib.flow import Flow
from gauth import config, YT_TOKEN

# Drive (to download source videos) + YouTube (to upload). One token for both.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/drive",
]
REDIRECT = "http://localhost"


def _flow():
    env = config()
    cfg = {
        "installed": {
            "client_id": env["GOOGLE_CLIENT_ID"],
            "client_secret": env["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT],
        }
    }
    # No PKCE: the browser step and the --code exchange are two separate processes,
    # so a per-process code_verifier can't survive between them. The client_secret
    # already authenticates the exchange, so PKCE isn't needed.
    return Flow.from_client_config(
        cfg, scopes=SCOPES, redirect_uri=REDIRECT, autogenerate_code_verifier=False
    )


def _extract_code(raw):
    raw = raw.strip()
    if raw.startswith("http"):
        q = urllib.parse.urlparse(raw).query
        return urllib.parse.parse_qs(q)["code"][0]
    return raw


def main():
    flow = _flow()
    if len(sys.argv) >= 3 and sys.argv[1] == "--code":
        flow.fetch_token(code=_extract_code(sys.argv[2]))
        with open(YT_TOKEN, "w") as f:
            f.write(flow.credentials.to_json())
        print("OK: token.json сохранён, доступ к Drive+YouTube выдан.")
    else:
        url, _ = flow.authorization_url(
            access_type="offline", prompt="consent", include_granted_scopes="false"
        )
        print(url)


if __name__ == "__main__":
    main()
