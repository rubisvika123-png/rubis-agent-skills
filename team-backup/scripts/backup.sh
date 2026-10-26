#!/usr/bin/env bash
# Nightly backup of the whole agent team into the owner's PRIVATE GitHub repo.
# Copies characters, memory, skills, settings and schedules of every agent.
# Never copies secrets: bot tokens, API keys, logins. A secret scan aborts the
# push if anything token-like slipped through.
#
#   backup.sh            make a snapshot and push it
#   backup.sh --dry-run  make the snapshot, scan it, but do not commit or push
#
# Env: TB_NOTIFY_ENV=<agent>/secrets/channel.env — if the backup fails, the owner
# gets a Telegram message from that agent's bot (so a broken backup is never silent).
# For tests: TB_HOME (default $HOME), TB_REPO (default ~/.agents-backup-repo),
# TB_SKIP_SYSTEM=1 skips crontab/systemd.
set -euo pipefail

LOG=$(mktemp); exec > >(tee "$LOG") 2>&1
notify_on_fail() {
  rc=$?
  if [ "$rc" != 0 ] && [ -f "${TB_NOTIFY_ENV:-}" ]; then
    tok=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$TB_NOTIFY_ENV" | cut -d= -f2- | tr -d '"' || true)
    to=$(grep -m1 '^TELEGRAM_ALLOWED_USER_IDS=' "$TB_NOTIFY_ENV" | cut -d= -f2- | tr -d '"' | cut -d, -f1 || true)
    if [ -n "$tok" ] && [ -n "$to" ]; then
      curl -s -m 20 "https://api.telegram.org/bot$tok/sendMessage" --data-urlencode "chat_id=$to" \
        --data-urlencode "text=Резервная копия команды сегодня НЕ сохранилась. Напиши своему техспецу: «Почини резервную копию». Что случилось: $(tail -c 600 "$LOG")" >/dev/null || true
    fi
  fi
  rm -f "$LOG"
}
trap notify_on_fail EXIT

H="${TB_HOME:-$HOME}"
REPO="${TB_REPO:-$H/.agents-backup-repo}"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
MAX_FILE=20M

command -v rsync >/dev/null || { echo "ОШИБКА: нет rsync (apt-get install -y rsync)"; exit 1; }
[ -d "$REPO/.git" ] || { echo "ОШИБКА: нет папки $REPO с хранилищем. Сначала: git clone <адрес закрытого хранилища> $REPO"; exit 1; }

SNAP="$REPO/snapshot"
rm -rf "$SNAP"; mkdir -p "$SNAP"

# Everything secret or heavy that must never leave the server.
EXCL=(
  --exclude=.git/ --exclude=node_modules/ --exclude=dashi-plugin-claude-code/
  --exclude=secrets/ --exclude='.env' --exclude='.env.*' --exclude='*.env'
  --exclude='*.key' --exclude='*.pem' --exclude='*.token' --exclude=.mcp.json
  --exclude=.credentials.json --exclude=auth.json --exclude='*.db' --exclude='*.db-*'
  --exclude='*.sqlite*' --exclude=sessions/ --exclude=logs/ --exclude='*.log'
  --exclude=__pycache__/ --exclude=venv/ --exclude=.venv/ --exclude=cache/
  --exclude='*.mp4' --exclude='*.mov' --exclude='*.mp3' --exclude='*.wav' --exclude='*.ogg'
  --exclude='*.jpg' --exclude='*.jpeg' --exclude='*.png' --exclude='*.zip' --exclude='*.tar*'
  --max-size="$MAX_FILE"
)
copy() { # copy <source> <dest-inside-snapshot>
  [ -e "$1" ] || return 0
  mkdir -p "$SNAP/$(dirname "$2")"
  rsync -a "${EXCL[@]}" "$1" "$SNAP/$2"
}

agents=()
# Claude Code agents: folders in home with CLAUDE.md and start.sh.
for d in "$H"/*/; do
  d="${d%/}"; n="$(basename "$d")"
  [ -f "$d/CLAUDE.md" ] && [ -f "$d/start.sh" ] || continue
  agents+=("$n")
  for f in CLAUDE.md AGENTS.md USER.md rules.md settings.json start.sh; do copy "$d/$f" "agents/$n/$f"; done
  for sub in core scripts docs .claude .agents; do copy "$d/$sub/" "agents/$n/$sub/"; done
  # Telegram allowlist (who the bot answers) — ids only, no token.
  for f in "$d"/state/telegram/*.json; do [ -e "$f" ] && copy "$f" "agents/$n/state/telegram/$(basename "$f")"; done
done

# Claude Code shared settings, skills and per-project memory.
copy "$H/.claude/settings.json" "claude/settings.json"
copy "$H/.claude/CLAUDE.md" "claude/CLAUDE.md"
copy "$H/.claude/skills/" "claude/skills/"
for m in "$H"/.claude/projects/*/memory/; do
  [ -d "$m" ] || continue
  p="$(basename "$(dirname "$m")")"; copy "$m" "claude/projects/$p/memory/"
done

# Hermes agents (second engine): character, settings, skills, memory.
if [ -d "$H/.hermes" ]; then
  for f in SOUL.md config.yaml; do copy "$H/.hermes/$f" "hermes/$f"; done
  for sub in skills memories plugins; do copy "$H/.hermes/$sub/" "hermes/$sub/"; done
  for p in "$H"/.hermes/profiles/*/; do
    [ -d "$p" ] || continue
    n="$(basename "$p")"; agents+=("hermes:$n")
    for f in SOUL.md config.yaml; do copy "$p$f" "hermes/profiles/$n/$f"; done
    for sub in skills memories plugins knowledge; do copy "$p$sub/" "hermes/profiles/$n/$sub/"; done
  done
fi

# Schedules: cron and services that keep agents alive.
if [ "${TB_SKIP_SYSTEM:-0}" != 1 ]; then
  mkdir -p "$SNAP/system"
  crontab -l > "$SNAP/system/crontab.txt" 2>/dev/null || true
  for u in /etc/systemd/system/*.service /etc/systemd/system/*.timer "$H"/.config/systemd/user/*.service "$H"/.config/systemd/user/*.timer; do
    [ -f "$u" ] || continue
    grep -qE "$H/|hermes|agent|claude|watchdog" "$u" 2>/dev/null || continue
    copy "$u" "system/units/$(basename "$u")"
  done
fi

{
  echo "Резервная копия команды агентов"
  echo "Дата (UTC): $(date -u '+%Y-%m-%d %H:%M')"
  echo "Сервер: $(hostname)"
  echo "Агенты: ${agents[*]:-нет}"
  echo
  echo "Секретов здесь НЕТ. При восстановлении понадобятся заново:"
  echo "- токен бота каждого агента (@BotFather → /mybots → бот → API Token)"
  echo "- вход в Claude (и в ChatGPT, если есть агенты на Hermes)"
  echo "- ключи сервисов (GitHub-токен и другие), которые агенты просили раньше"
} > "$SNAP/MANIFEST.txt"

# Secret scan: Telegram bot tokens, Anthropic/OpenAI/GitHub/Groq/Google keys, private keys.
PAT='[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-(proj-)?[A-Za-z0-9_-]{32,}|github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
if hits=$(grep -rIlE "$PAT" "$SNAP" 2>/dev/null); [ -n "$hits" ]; then
  echo "СТОП: в копию попало что-то похожее на секрет, ничего не отправлено:"
  echo "$hits" | sed "s|$SNAP/|  |"
  exit 2
fi

size=$(du -sh "$SNAP" | cut -f1); files=$(find "$SNAP" -type f | wc -l)
if [ "$DRY" = 1 ]; then echo "Проверка ок: $files файлов, $size, секретов нет. Агенты: ${agents[*]:-нет}"; exit 0; fi

cd "$REPO"
git add -A snapshot
if git diff --cached --quiet; then echo "Изменений нет, копия актуальна ($files файлов, $size)"; exit 0; fi
git -c user.name="agents-backup" -c user.email="backup@localhost" commit -qm "Резервная копия $(date -u '+%Y-%m-%d %H:%M') UTC"
git push -q origin HEAD
echo "Копия отправлена: $files файлов, $size. Агенты: ${agents[*]:-нет}"
