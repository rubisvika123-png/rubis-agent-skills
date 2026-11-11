#!/usr/bin/env bash
# team-protections-audit.sh — checks a server against the protections our own team has
# (Vika 10.11.2026: «у всех учеников и клиентов — все защиты, без исключений»).
# Read-only. Prints one ✅/❌ line per check and exits 1 if anything is missing.
#
#   team-protections-audit.sh [ROOT_TO_SCAN ...]     (default: /root /home)
#
# An "agent" = a folder holding start.sh + dashi-plugin-claude-code/plugin (Claude agents
# built from the course template). Tests: test_team_protections_audit.sh.
set -u
ROOTS=("$@"); [ ${#ROOTS[@]} -eq 0 ] && ROOTS=(/root /home)
SYSTEMCTL=${AUDIT_SYSTEMCTL:-systemctl}
CRONTABS=${AUDIT_CRONTABS:-/var/spool/cron/crontabs}
FAIL=0
ok()  { echo "✅ $1"; }
bad() { echo "❌ $1"; FAIL=1; }

# ---- server level -------------------------------------------------------------------------
wd_scripts=()
wd_found=0
while IFS= read -r unit; do
  [ -n "$unit" ] || continue; wd_found=1
  restart=$($SYSTEMCTL show -p Restart --value "$unit" 2>/dev/null)
  [ "$($SYSTEMCTL is-active "$unit" 2>/dev/null)" = active ] || bad "сторож агентов $unit: не запущен"
  [ "$restart" = always ] && ok "сторож агентов $unit: перезапускается сам" || bad "сторож агентов $unit: нет Restart=always"
  s=$($SYSTEMCTL cat "$unit" 2>/dev/null | grep -m1 '^ExecStart=' | grep -oE '/[^ "]*watchdog[^ "]*\.sh' | head -1)
  [ -n "$s" ] && wd_scripts+=("$s")
done < <($SYSTEMCTL list-units --all --no-legend --plain 'agent-watchdog*' 2>/dev/null | awk '{print $1}')
for f in "${ROOTS[@]/%//}"*/.config/systemd/user/agent-watchdog.service; do
  [ -f "$f" ] || continue; wd_found=1
  grep -q '^Restart=always' "$f" && ok "сторож агентов ($f): перезапускается сам" || bad "сторож агентов ($f): нет Restart=always"
  s=$(grep -m1 '^ExecStart=' "$f" | grep -oE '/[^ "]*watchdog[^ "]*\.sh' | head -1)
  [ -n "$s" ] && wd_scripts+=("$s")
done
[ $wd_found -eq 1 ] || bad "сторож агентов: службы нет"
for s in "${wd_scripts[@]}"; do
  for fn in "ensure:упал — поднимает" "pulse:отвалилась связь с Telegram" "sweep:зависшие копии" \
            "check_limit:кончился лимит" "check_login:слетел вход в Claude" \
            "check_login_soon:вход скоро кончится" "unblock_dialog:окно с вопросом"; do
    name=${fn%%:*}; what=${fn#*:}
    grep -qE "^${name}\(\)" "$s" 2>/dev/null && ok "сторож ($s): $what" || bad "сторож ($s): нет проверки «$what» ($name)"
  done
done
$SYSTEMCTL is-active --quiet fail2ban && ok "сервер: защита от подбора пароля (fail2ban)" || bad "сервер: нет fail2ban"
if cat "$CRONTABS"/* 2>/dev/null | grep -v '^\s*#' | grep -qi 'backup'; then
  ok "сервер: резервная копия по расписанию"
else
  bad "сервер: нет резервной копии по расписанию"
fi

# ---- agent level --------------------------------------------------------------------------
found=0
while IFS= read -r start; do
  dir=$(dirname "$start"); plugin="$dir/dashi-plugin-claude-code/plugin"
  [ -d "$plugin" ] || continue
  found=1; a="агент $dir"
  owner_home=$(getent passwd "$(stat -c %U "$dir")" | cut -d: -f6)
  if [ "$(basename "$dir")" = kurator ]; then
    ok "$a: сторож ответа не нужен (куратор в групповом чате отвечает только на упоминание)"
  elif grep -qs require-telegram-reply "$owner_home/.claude/settings.json" "$plugin"/.claude/settings*.json "$dir"/.claude/settings*.json; then
    ok "$a: сторож ответа (не промолчит в Telegram)"
  else
    bad "$a: нет сторожа ответа"
  fi
  grep -rqs retry_after "$plugin/src" && ok "$a: защита от бана Telegram" || bad "$a: нет защиты от бана Telegram (старый мост)"
  [ -f "$plugin/src/telegram/fallback-text.ts" ] && ok "$a: длинные сообщения со списками не теряются" \
    || bad "$a: старый мост — сообщения со списками теряются"
  # A cron job counts only for the agents of the user who owns it: one team's job does not
  # warn about another team's subscription.
  { grep -qs 'limit-warn' "$start" || grep -v '^\s*#' "$CRONTABS/$(stat -c %U "$dir")" 2>/dev/null | grep -q 'limit-warn\|limit-alert'; } && ok "$a: предупреждение о лимите заранее" || bad "$a: нет мода limit-warn"
  if grep -qs 'mods/unstick' "$start" || grep -qsE '^has_unstick_mod\(\)' "${wd_scripts[@]:-/dev/null}"; then
    ok "$a: толкач застрявших сообщений"
  else
    bad "$a: нет толкача застрявших сообщений (мод unstick)"
  fi
done < <(
  # Only agents that are running now: the cwd of every live `claude` process is the agent's
  # plugin folder (start.sh cd's there). Old copies of the template lying around don't count.
  if [ -n "${AUDIT_AGENT_DIRS:-}" ]; then printf '%s\n' $AUDIT_AGENT_DIRS | sed 's#$#/start.sh#'
  else
    for pid in $(pgrep -x claude 2>/dev/null); do
      cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue
      case "$cwd" in */dashi-plugin-claude-code/plugin) echo "${cwd%/dashi-plugin-claude-code/plugin}/start.sh";; esac
    done | sort -u
  fi)
[ $found -eq 1 ] || bad "агенты на Claude не найдены в ${ROOTS[*]}"

[ $FAIL -eq 0 ] && echo "ИТОГ: все защиты на месте" || echo "ИТОГ: защит не хватает — см. ❌"
exit $FAIL
