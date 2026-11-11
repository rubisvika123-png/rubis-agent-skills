#!/usr/bin/env bash
# update.sh on a synthetic student server: old bridge, old watchdog, plain start.sh.
#   test_update.sh <path to a FULL clone (with history) of the ai-victoriarubis starter>
set -u
H=$(cd "$(dirname "$0")/.." && pwd); SKILLS=$(cd "$H/.." && pwd); STARTER="$1"
T=$(mktemp -d)
pass=0; fail=0
check() { if [ "$2" = "$3" ]; then echo "PASS $1"; pass=$((pass+1)); else echo "FAIL $1: want '$2' got '$3'"; fail=$((fail+1)); fi; }

A="$T/root/ai-victoriarubis"; P="$A/dashi-plugin-claude-code/plugin"
mkdir -p "$T/root" "$T/units"
cp -r "$STARTER" "$A"; rm -rf "$A/.git" "$P/.claude" "$A/scripts/require-telegram-reply.js"
# a real old starter version of one bridge file (from the starter history)
cp "$H/tests/old-status-manager.ts" "$P/src/status/status-manager.ts"
cp "$H/tests/old-watchdog.sh" "$A/scripts/agent-watchdog.sh"
printf '[Service]\nExecStart=/bin/bash %s\nRestart=always\n' "$A/scripts/agent-watchdog.sh" > "$T/units/agent-watchdog.service"

run() { AGENTS_ROOT="$T/root" SKILLS_DIR="$SKILLS" STARTER_DIR="$STARTER" UNIT_DIR="$T/units" \
        NO_FETCH=1 NO_APT=1 NO_RESTART=1 NO_AUDIT=1 bash "$H/update.sh"; }
out=$(run 2>&1)
check "bridge replaced" 0 "$(diff -rq -x '*.bak*' "$P/src" "$STARTER/dashi-plugin-claude-code/plugin/src" >/dev/null; echo $?)"
check "old bridge kept as backup" 1 "$(ls -d "$P"/src.bak-* | wc -l)"
check "reply guard hook" 1 "$(grep -c require-telegram-reply "$P/.claude/settings.json")"
check "reply guard script" 1 "$(ls "$A/scripts/require-telegram-reply.js" | wc -l)"
check "limit-warn mod" 1 "$(grep -c 'mods/limit-warn' "$A/start.sh")"
check "unstick mod" 1 "$(grep -c 'mods/unstick' "$A/start.sh")"
check "restart keeps conversation" 1 "$(grep -c 'continue-once' "$A/start.sh")"
check "start.sh still valid" 0 "$(bash -n "$A/start.sh"; echo $?)"
WD="$A/scripts/agent-watchdog.sh"
for fn in check_login check_login_soon unblock_dialog creds_expired; do
  check "watchdog has $fn" 1 "$(grep -c "^$fn()" "$WD")"
done
check "loop calls check_login" 1 "$(grep -c '^      check_login "\$name"' "$WD")"
check "loop calls check_login_soon" 1 "$(grep -c '^    check_login_soon$' "$WD")"
check "KillMode=process" 1 "$(grep -c '^KillMode=process' "$T/units/agent-watchdog.service.d/killmode.conf")"
check "login-soon behaves" 0 "$(bash "$H/tests/test_login_soon.sh" "$WD" >/dev/null; echo $?)"
check "login/dialog behave" 0 "$(bash "$H/tests/test_login_dialog.sh" "$WD" >/dev/null; echo $?)"
check "no Vika-only wording for students" 0 "$(grep -c 'напишите Виктории' "$WD")"

# second run changes nothing
sum() { find "$T/root" "$T/units" -type f -not -name '*.bak*' -not -path '*/src.bak-*' -exec md5sum {} + | sort; }
before=$(sum); run >/dev/null 2>&1; after=$(sum)
check "second run is a no-op" "$before" "$after"

# a bridge the student changed (tracked in git) is left alone
B="$T/root2/agent"; mkdir -p "$T/root2"; cp -r "$STARTER" "$B"; rm -rf "$B/.git"
echo "// my change" >> "$B/dashi-plugin-claude-code/plugin/src/server.ts"
cp "$H/tests/old-status-manager.ts" "$B/dashi-plugin-claude-code/plugin/src/status/status-manager.ts"
out=$(AGENTS_ROOT="$T/root2" SKILLS_DIR="$SKILLS" STARTER_DIR="$STARTER" UNIT_DIR="$T/none" \
      NO_FETCH=1 NO_APT=1 NO_RESTART=1 NO_AUDIT=1 bash "$H/update.sh" 2>&1)
check "changed bridge untouched" 1 "$(grep -c '// my change' "$B/dashi-plugin-claude-code/plugin/src/server.ts")"
check "changed bridge reported" 1 "$(echo "$out" | grep -c 'свои доработки (server.ts)')"

[ $fail -eq 0 ] && echo "ALL PASS ($pass)" || { echo "FAILED $fail"; exit 1; }
