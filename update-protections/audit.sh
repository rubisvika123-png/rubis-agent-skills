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
            "check_login_soon:вход скоро кончится" "unblock_dialog:окно с вопросом" \
            "check_hermes_limit:кончился лимит ChatGPT"; do
    name=${fn%%:*}; what=${fn#*:}
    # the ChatGPT-limit check only matters for a watchdog that looks after GPT agents at all
    [ "$name" = check_hermes_limit ] && ! grep -qE '^check_hermes\(\)' "$s" 2>/dev/null && continue
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
  # Year-long login (claude setup-token, 10.11.2026): the ordinary login has to be redone
  # about once a month, and every agent goes mute when it lapses.
  tok_home=${AUDIT_TOKEN_HOME:-$owner_home}
  if [ -n "${AUDIT_SKIP_YEAR_TOKEN:-}" ]; then
    :  # students: no lesson step for the year-long login yet
  elif grep -qs 'CLAUDE_CODE_OAUTH_TOKEN' "$start" && [ -s "$tok_home/.claude-oauth-token" ]; then
    ok "$a: вход в Claude на год (не слетит через месяц)"
  else
    bad "$a: нет годового входа в Claude — обычный вход надо обновлять примерно раз в месяц (claude setup-token)"
  fi
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

# ---- GPT agents (Hermes) ------------------------------------------------------------------
# An enabled hermes-gateway*.service of any user = a live GPT agent. Disabled ones are agents
# switched off on purpose and are skipped. AUDIT_HERMES="unit=profile_dir ..." for tests.
hermes_agents() {
  if [ "${AUDIT_HERMES+set}" = set ]; then printf '%s\n' $AUDIT_HERMES; return; fi
  for home in /root /home/*; do
    for w in "$home"/.config/systemd/user/default.target.wants/hermes-gateway*.service; do
      [ -e "$w" ] || continue
      u=$(basename "$w"); p=${u#hermes-gateway}; p=${p%.service}; p=${p#-}
      if [ -n "$p" ]; then echo "$u=$home/.hermes/profiles/$p"; continue; fi
      # host gateway: the root profile if it is an agent, plus (new Hermes, one gateway for all)
      # every profile with a bot and no gateway unit of its own
      grep -qs '^TELEGRAM_BOT_TOKEN=.' "$home/.hermes/.env" && echo "$u=$home/.hermes"
      grep -qs "does not get a gateway of its own" "$home/.hermes/hermes-agent/hermes_cli/gateway.py" ${HERMES_SRC_PROBE:-/usr/local/lib/hermes-agent/hermes_cli/gateway.py} || continue   # old Hermes: profiles have their own gateways
      for pd in "$home"/.hermes/profiles/*/; do
        pd=${pd%/}; [ -e "$home/.config/systemd/user/hermes-gateway-${pd##*/}.service" ] && continue
        grep -qs '^TELEGRAM_BOT_TOKEN=.' "$pd/.env" && echo "$u=$pd"
      done
    done
  done
}
while IFS='=' read -r unit pdir; do
  [ -n "$unit" ] || continue
  user=$(stat -c %U "$pdir" 2>/dev/null || echo root); h="агент на GPT ${pdir##*/} ($unit)"
  [ "$($SYSTEMCTL --user -M "$user@" is-active "$unit" 2>/dev/null)" = active ] && ok "$h: работает" || bad "$h: не запущен"
  grep -qsF "[$unit]" "${wd_scripts[@]:-/dev/null}" && ok "$h: под присмотром сторожа" || bad "$h: сторож за ним не следит (нет в HERMES)"
  [ -e "${AUDIT_LINGER_DIR:-/var/lib/systemd/linger}/$user" ] && ok "$h: переживёт перезагрузку" || bad "$h: не переживёт перезагрузку сервера (нет linger)"
  grep -qs 'facts-inject' "$pdir/config.yaml" && [ -d "$pdir/plugins/facts-inject" ] \
    && ok "$h: факты в каждом сообщении" || bad "$h: нет фактов в каждом сообщении (плагин facts-inject)"
  grep -qs 'protect-home' "$pdir/config.yaml" && ok "$h: защита от самоудаления" || bad "$h: нет защиты от самоудаления (hermes-protect)"
done < <(hermes_agents)

[ $FAIL -eq 0 ] && echo "ИТОГ: все защиты на месте" || echo "ИТОГ: защит не хватает — см. ❌"
exit $FAIL
