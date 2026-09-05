#!/usr/bin/env bash
# One-time setup: build the Python environment for the comment autoreply skill.
# Run from the skill folder:  bash scripts/setup.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

command -v python3 >/dev/null || { echo "Нет python3."; exit 1; }

python3 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q google-auth-oauthlib google-api-python-client
echo "OK: окружение готово."
echo "Дальше: скопируй config.example.env -> config.env, заполни ключи, потом"
echo "  cd scripts && ../venv/bin/python oauth_youtube.py   (выдать доступ, см. SKILL.md)"
