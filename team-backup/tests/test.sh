#!/usr/bin/env bash
# Self-contained test: fake server home, local bare repo instead of GitHub.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
B=scripts/backup.sh; R=scripts/restore.sh
fail() { echo "FAIL: $*"; exit 1; }
export TB_SKIP_SYSTEM=1

# Fake home: two Claude agents + one Hermes profile, with secrets planted.
H=$T/home; mkdir -p $H
for a in ai-victoriarubis ai-marketing; do
  mkdir -p $H/$a/{core/memory,secrets,state/telegram,dashi-plugin-claude-code,node_modules/x,.claude/skills/s}
  echo "# $a character" > $H/$a/CLAUDE.md; echo '#!/bin/sh' > $H/$a/start.sh
  echo "note about client" > $H/$a/core/memory/notes.md
  echo "TELEGRAM_BOT_TOKEN=1234567890:AAH_fake_token_value_abcdefghijklmn" > $H/$a/secrets/channel.env
  echo '{"allowFrom":["458929014"]}' > $H/$a/state/telegram/access.json
  echo '{"mcpServers":{"github":{"env":{"T":"github_pat_11AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}}}}' > $H/$a/.mcp.json
  echo "GROQ_API_KEY=gsk_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" > $H/$a/core/.env
  echo big > $H/$a/dashi-plugin-claude-code/server.ts; echo skill > $H/$a/.claude/skills/s/SKILL.md
done
mkdir -p $H/not-an-agent && echo x > $H/not-an-agent/file.txt
mkdir -p $H/.claude/skills/k $H/.claude/projects/-root-ai-marketing/memory
echo k > $H/.claude/skills/k/SKILL.md; echo '{}' > $H/.claude/settings.json
echo '{"claudeAiOauth":"x"}' > $H/.claude/.credentials.json
echo mem > $H/.claude/projects/-root-ai-marketing/memory/MEMORY.md
mkdir -p $H/.hermes/profiles/montazher/{skills,memories,sessions}
echo soul > $H/.hermes/profiles/montazher/SOUL.md; echo "model: x" > $H/.hermes/profiles/montazher/config.yaml
echo "OPENAI_API_KEY=sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" > $H/.hermes/profiles/montazher/.env
echo '{}' > $H/.hermes/profiles/montazher/auth.json; echo m > $H/.hermes/profiles/montazher/memories/MEMORY.md
echo s > $H/.hermes/profiles/montazher/sessions/1.json

git init -q --bare $T/remote.git; git clone -q $T/remote.git $T/repo 2>/dev/null
export TB_HOME=$H TB_REPO=$T/repo

# 1. Backup pushes and contains the right things, no secrets.
out=$($B) || fail "backup failed: $out"; echo "$out" | grep -q "Копия отправлена" || fail "no push: $out"
git clone -q $T/remote.git $T/check; S=$T/check/snapshot
for f in agents/ai-victoriarubis/CLAUDE.md agents/ai-marketing/core/memory/notes.md agents/ai-marketing/state/telegram/access.json \
         agents/ai-marketing/.claude/skills/s/SKILL.md claude/skills/k/SKILL.md claude/settings.json \
         claude/projects/-root-ai-marketing/memory/MEMORY.md hermes/profiles/montazher/SOUL.md hermes/profiles/montazher/memories/MEMORY.md MANIFEST.txt; do
  [ -f "$S/$f" ] || fail "missing $f"; done
for f in agents/ai-marketing/secrets agents/ai-marketing/.mcp.json agents/ai-marketing/dashi-plugin-claude-code agents/ai-marketing/node_modules \
         agents/ai-marketing/core/.env claude/.credentials.json hermes/profiles/montazher/.env hermes/profiles/montazher/auth.json hermes/profiles/montazher/sessions agents/not-an-agent; do
  [ ! -e "$S/$f" ] || fail "must not be copied: $f"; done
! grep -rqE "AAH_fake|github_pat_|sk-proj-|claudeAiOauth" $S || fail "secret leaked"
grep -q "ai-marketing" $S/MANIFEST.txt && grep -q "hermes:montazher" $S/MANIFEST.txt || fail "manifest agents"

# 2. Second run with no changes does not create an empty commit, and success sends nothing.
mkdir -p $T/bin0; printf '#!/bin/sh\necho called >> %s/curl0.log\n' "$T" > $T/bin0/curl; chmod +x $T/bin0/curl
printf 'TELEGRAM_BOT_TOKEN=1:x\nTELEGRAM_ALLOWED_USER_IDS=777\n' > $T/n0.env
PATH=$T/bin0:$PATH TB_NOTIFY_ENV=$T/n0.env $B | grep -q "Изменений нет" || fail "empty commit"
[ ! -e $T/curl0.log ] || fail "notified on success"

# 3. A token pasted into memory blocks the push.
echo "token 1234567890:AAH_fake_token_value_abcdefghijklmn" >> $H/ai-marketing/core/memory/notes.md
mkdir -p $T/bin; printf '#!/bin/sh\necho "$@" >> %s/curl.log\n' "$T" > $T/bin/curl; chmod +x $T/bin/curl
printf 'TELEGRAM_BOT_TOKEN=1:x\nTELEGRAM_ALLOWED_USER_IDS=777,888\n' > $T/notify.env
set +e; out=$(PATH=$T/bin:$PATH TB_NOTIFY_ENV=$T/notify.env $B); rc=$?; set -e
grep -q "chat_id=777" $T/curl.log && grep -q "НЕ сохранилась" $T/curl.log || fail "owner not notified on failure"
[ $rc = 2 ] && echo "$out" | grep -q "core/memory/notes.md" || fail "secret scan did not block (rc=$rc)"
before=$(git -C $T/remote.git rev-list --count HEAD); [ "$before" = 1 ] || fail "pushed despite secret"
sed -i '/token/d' $H/ai-marketing/core/memory/notes.md

# 4. Restore onto an empty new home gives back the same files.
N=$T/newhome; mkdir -p $N
TB_HOME=$N $R $T/check >/dev/null
diff -q $H/ai-marketing/CLAUDE.md $N/ai-marketing/CLAUDE.md && diff -q $H/ai-marketing/core/memory/notes.md $N/ai-marketing/core/memory/notes.md \
  && diff -q $H/.hermes/profiles/montazher/SOUL.md $N/.hermes/profiles/montazher/SOUL.md \
  && diff -q $H/.claude/projects/-root-ai-marketing/memory/MEMORY.md $N/.claude/projects/-root-ai-marketing/memory/MEMORY.md || fail "restore mismatch"
[ ! -e $N/ai-marketing/secrets ] || fail "restore invented secrets"

# 5. Restore refuses a folder that is not a backup.
mkdir $T/junk; ! TB_HOME=$N $R $T/junk >/dev/null 2>&1 || fail "restore accepted junk"
echo "ALL TESTS PASSED"
