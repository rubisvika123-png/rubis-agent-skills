#!/usr/bin/env bash
# Put the team back from the backup repo onto a (new) server.
#
#   restore.sh <folder with the cloned backup repo>
#
# Copies agents' characters, memory, skills, settings and schedules back to the
# same places. Existing files are overwritten with the backup version; nothing
# that is not in the backup is deleted. Secrets are not in the backup — the list
# of what to ask the owner for is printed at the end.
# Env (for tests): TB_HOME (default $HOME), TB_SKIP_SYSTEM=1.
set -euo pipefail

SRC="${1:?Укажи папку со скачанной резервной копией}"
SNAP="$SRC/snapshot"
H="${TB_HOME:-$HOME}"
[ -f "$SNAP/MANIFEST.txt" ] || { echo "ОШИБКА: в $SRC нет snapshot/MANIFEST.txt — это не резервная копия команды"; exit 1; }
command -v rsync >/dev/null || { echo "ОШИБКА: нет rsync (apt-get install -y rsync)"; exit 1; }

put() { [ -e "$1" ] || return 0; mkdir -p "$2"; rsync -a "$1" "$2"; }

if [ -d "$SNAP/agents" ]; then
  for a in "$SNAP"/agents/*/; do n="$(basename "$a")"; put "$a" "$H/$n/"; done
fi
[ -d "$SNAP/claude" ] && put "$SNAP/claude/" "$H/.claude/"
[ -d "$SNAP/hermes" ] && put "$SNAP/hermes/" "$H/.hermes/"

if [ "${TB_SKIP_SYSTEM:-0}" != 1 ] && [ -d "$SNAP/system" ]; then
  if [ -s "$SNAP/system/crontab.txt" ]; then
    crontab -l > "$H/crontab.before-restore.txt" 2>/dev/null || true
    crontab "$SNAP/system/crontab.txt"
  fi
  for u in "$SNAP"/system/units/*; do
    [ -f "$u" ] || continue
    if grep -q "WantedBy=default.target" "$u"; then mkdir -p "$H/.config/systemd/user"; cp "$u" "$H/.config/systemd/user/"
    else cp "$u" /etc/systemd/system/; fi
  done
  systemctl daemon-reload 2>/dev/null || true
fi

echo "Восстановлено из копии:"
sed -n '2,4p' "$SNAP/MANIFEST.txt"
echo
sed -n '/Секретов здесь НЕТ/,$p' "$SNAP/MANIFEST.txt"
echo
echo "Дальше: вписать токены ботов в secrets/channel.env каждого агента, войти в Claude, включить службы агентов и проверить каждого бота сообщением «Проверка»."
