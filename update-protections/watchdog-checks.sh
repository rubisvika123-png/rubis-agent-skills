# >>> rubis watchdog checks (update-protections) >>>
# Вход в Claude (общий для всех агентов на сервере) и зависшие диалоги — те же
# проверки, что у команды Виктории. Вставлено командой «обнови защиты».
CREDS="${WATCHDOG_CREDS:-$HOME/.claude/.credentials.json}"
LOGIN_FROZEN_LIMIT="${WATCHDOG_LOGIN_FROZEN_LIMIT:-10}"
declare -A LOGIN_NOTIFIED=()
declare -A LOGIN_PANE=()
declare -A LOGIN_FROZEN=()
declare -A DIALOG_SEEN=()

# creds_expired — true when the stored Claude token is actually past its expiry.
# Second signal for check_login: the screen text alone is not enough. On
# 2026-08-26 the coder agent had this script's own test fixture on screen, the
# terminal wrapped the line so the quote that marks it as source landed on the
# NEXT visual line, and Vika got a false "вход слетел" alert. The credentials
# file cannot be faked by anything on screen. Unreadable file or missing field →
# "not expired", i.e. stay silent: a false alarm costs Vika's trust, a missed
# one is still caught by pulse() when the bridge dies.
creds_expired() {
  python3 - "$CREDS" <<'PY' 2>/dev/null
import json, sys, time
try:
    exp = json.load(open(sys.argv[1])).get("claudeAiOauth", {}).get("expiresAt", 0)
except Exception:
    sys.exit(1)
sys.exit(0 if exp and exp / 1000 <= time.time() else 1)
PY
}

# check_login — «жив, но вход в Claude слетел»: пишем владельцу один раз; когда
# вход обновили (файл входа переписан) — перезапускаем агента.
check_login() {
  local name="$1" dir="$2" pane mtime msg
  tmux has-session -t "$name" 2>/dev/null || return 0
  pane=$(tmux capture-pane -t "$name" -p 2>/dev/null)
  mtime=$(stat -c %Y "$CREDS" 2>/dev/null || echo 0)

  # Self-display guard, wider than check_limit()'s: agents edit and display this
  # script AND its test (which embeds the literal screen text as a fixture), so a
  # pipe/`grep` filter alone is not enough. Real claude output is bare prose —
  # `● Login expired · Please run /login` — with no quote, backtick or `=` on the
  # line, while every quoted/source form of it carries at least one. Caught before
  # shipping: the coder's own pane held the fixture line and would have self-alerted.
  if echo "$pane" | grep -vE "\||grep|[\"'\`=]" | grep -qiE 'login expired|please run /login'; then
    if [ -z "${LOGIN_NOTIFIED[$name]:-}" ]; then
      if ! creds_expired; then
        # The file says the token is fine, the screen says it is not. Both can be
        # true at once: a token that was REVOKED (a second session logging in on
        # the same subscription) keeps a future expiresAt, so creds_expired()
        # misses it entirely. That happened to Liza on 2026-09-23 — she sat
        # blocked for seven minutes on the morning of Vika's investor talk while
        # this branch logged "NOT notifying" every six seconds.
        #
        # So do not trust the file alone: watch whether the agent is actually
        # doing anything. A blocked agent's pane freezes — same bytes pass after
        # pass. A working agent that merely has this text on screen keeps
        # redrawing, which resets the counter and keeps us quiet.
        local hash; hash=$(printf '%s' "$pane" | cksum)
        if [ "$hash" = "${LOGIN_PANE[$name]:-}" ]; then
          LOGIN_FROZEN[$name]=$(( ${LOGIN_FROZEN[$name]:-0} + 1 ))
        else
          LOGIN_PANE[$name]="$hash"
          LOGIN_FROZEN[$name]=1
        fi

        if [ "${LOGIN_FROZEN[$name]}" -lt "$LOGIN_FROZEN_LIMIT" ]; then
          # Log only the first sighting: this branch runs every pass and used to
          # bury the log under one identical line per agent per six seconds.
          [ "${LOGIN_FROZEN[$name]}" -eq 1 ] && \
            log "login-expired phrase seen for $name, token file still valid — watching whether the screen is frozen"
          return 0
        fi
        log "login-expired phrase frozen on screen for $name over ${LOGIN_FROZEN[$name]} passes — token was revoked, not expired; notifying"
      fi
      msg="У меня слетел вход в Claude (${name}) — я получаю ваши сообщения, но ответить не могу. Зайдите на сервер, наберите claude и войдите заново командой /login — как вход обновится, я поднимусь сам."
      # Remember the credentials mtime AT alert time: a newer one later means Vika
      # logged in again. Flag stays empty if the alert failed to send, so she gets
      # told on the next pass rather than never.
      notify_owner "$dir" "$msg" && LOGIN_NOTIFIED[$name]="$mtime"
      log "login expired for $name, notified owner"
    elif [ "$mtime" -gt "${LOGIN_NOTIFIED[$name]}" ]; then
      # Still stuck, but the login was refreshed — restart so the new token is
      # read; the process keeps the dead one in memory and ignores Enter.
      LOGIN_NOTIFIED[$name]=""
      tmux kill-session -t "$name" 2>/dev/null
      log "login refreshed for $name, restarting so it picks up the new token"
    fi
  else
    # No banner on screen: whatever we were watching is over. Clear the frozen
    # counter too, or the next episode inherits a full count and fires at once.
    LOGIN_PANE[$name]=""
    LOGIN_FROZEN[$name]=0
    if [ -n "${LOGIN_NOTIFIED[$name]:-}" ]; then
      # Banner gone on its own (someone restarted it by hand) — episode over.
      LOGIN_NOTIFIED[$name]=""
      log "login restored for $name"
    fi
  fi
}

# check_login_soon — warn the owner a few days BEFORE the Claude login ends, so the
# agents never go mute on "Login expired" first (Vika 10.11.2026: every team gets
# every protection; check_login() only catches it after the fact). Deadline: a
# long-lived `claude setup-token` file wins (valid one year from when it was
# written); otherwise refreshTokenExpiresAt from the credentials file. Read from
# files only, never by running claude (live probes have revoked logins before).
# One warning per login, remembered on disk; a new login re-arms it by itself.
LONG_TOKEN="${WATCHDOG_LONG_TOKEN:-$(dirname "$CREDS")/../.claude-oauth-token}"
LOGIN_SOON_STATE="${WATCHDOG_LOGIN_SOON_STATE:-$(dirname "$LOG")/login-soon.notified}"
LOGIN_WARN_DAYS="${WATCHDOG_LOGIN_WARN_DAYS:-3}"
check_login_soon() {
  local info exp left when first
  info=$(python3 - "$CREDS" "$LONG_TOKEN" "$LOGIN_WARN_DAYS" <<'PY' 2>/dev/null
import json, os, sys, time, datetime as dt
creds, token, days = sys.argv[1], sys.argv[2], float(sys.argv[3])
try:
    if os.path.isfile(token) and os.path.getsize(token) > 0:
        exp = int((os.path.getmtime(token) + 365 * 86400) * 1000)
    else:
        exp = int(json.load(open(creds))["claudeAiOauth"]["refreshTokenExpiresAt"])
except Exception:
    sys.exit(1)
left = exp / 1000 - time.time()
if not 0 < left <= days * 86400:
    sys.exit(1)
when = dt.datetime.fromtimestamp(exp / 1000, dt.timezone(dt.timedelta(hours=3))).strftime("%d.%m в %H:%M")
print(exp, max(1, round(left / 86400)), when)
PY
) || return 0
  read -r exp left when <<<"$info"
  [ "$exp" = "$(cat "$LOGIN_SOON_STATE" 2>/dev/null)" ] && return 0
  first=$(printf '%s\n' "${!AGENTS[@]}" | sort | head -1)
  if notify_owner "${AGENTS[$first]}" "Через ${left} дн. (${when} по Москве) у агентов закончится вход в Claude, и они замолчат. Заранее зайдите на сервер, наберите claude и войдите заново командой /login — тогда агенты не замолчат."; then
    echo "$exp" >"$LOGIN_SOON_STATE"
    log "login ends in ${left}d (${when}), warned owner"
  fi
}

# unblock_dialog — агент завис на окне с вопросом: несколько проверок подряд → Escape.
unblock_dialog() {
  local name="$1" screen
  screen=$(tmux capture-pane -p -t "$name" 2>/dev/null) || return 0
  if grep -qiF 'esc to interrupt' <<<"$screen" \
     || ! grep -qiE 'esc to (cancel|back)' <<<"$screen"; then
    DIALOG_SEEN[$name]=0
    return 0
  fi
  # Не с первого взгляда: диалог, который агент закрывает сам, живёт доли
  # секунды, а зависший висит все проверки подряд.
  DIALOG_SEEN[$name]=$(( ${DIALOG_SEEN[$name]:-0} + 1 ))
  [ "${DIALOG_SEEN[$name]}" -ge "${DOWN_AFTER:-3}" ] || return 0
  tmux send-keys -t "$name" Escape 2>/dev/null
  DIALOG_SEEN[$name]=0
  log "closed a blocking dialog for $name"
}
# check_hermes_limit UNIT DIR WHO — the GPT twin of check_limit (Vika's hard rule: tell the
# owner once when the plan limit runs out, with the time it comes back; say so again when it
# is back). Hermes keeps that state in the profile's auth.json: each ChatGPT login of the
# profile is marked "exhausted" with last_error_reset_at. While one login is still fine the
# pool just switches to it — no alert. Read from the file only, never by calling the model.
HERMES_TZ="${WATCHDOG_HERMES_TZ:-3}"
HERMES_TZ_LABEL="${WATCHDOG_HERMES_TZ_LABEL:-по Москве}"
declare -A HLIMIT_NOTIFIED=()
_hermes_limit_one() {
  local unit="$1" dir="$2" who="$3" back when
  back=$(python3 - "$dir/auth.json" "$HERMES_TZ" <<'PY' 2>/dev/null
import json, sys, time, datetime as dt
try:
    pool = (json.load(open(sys.argv[1])).get("credential_pool") or {}).get("openai-codex") or []
except Exception:
    sys.exit(1)
if not pool:
    sys.exit(1)
now, resets = time.time(), []
for c in pool:
    if c.get("last_status") != "exhausted":
        sys.exit(1)
    r = c.get("last_error_reset_at") or 0
    if r > 1e12:
        r /= 1000
    if r and r <= now:
        sys.exit(1)  # this login is already back
    resets.append(r)
if not all(resets):
    print("?"); sys.exit(0)
tz = dt.timezone(dt.timedelta(hours=float(sys.argv[2])))
print(dt.datetime.fromtimestamp(min(resets), tz).strftime("%H:%M"))
PY
)
  if [ -n "$back" ]; then
    [ -n "${HLIMIT_NOTIFIED[$unit]:-}" ] && return 0
    if [ "$back" = "?" ]; then when="когда вернётся, пока не видно"; else when="вернётся примерно в $back $HERMES_TZ_LABEL"; fi
    notify_owner "$dir/.env" "${who}: кончился лимит ChatGPT, пока не отвечаю — ${when}. Срочное лучше отдать другому агенту." \
      && HLIMIT_NOTIFIED[$unit]=1
    log "hermes $unit: ChatGPT limit, back ~$back, notified owner"
  elif [ -n "${HLIMIT_NOTIFIED[$unit]:-}" ]; then
    HLIMIT_NOTIFIED[$unit]=""
    notify_owner "$dir/.env" "${who}: лимит ChatGPT вернулся, снова отвечаю. Если последнее сообщение осталось без ответа — отправьте его ещё раз."
    log "hermes $unit: ChatGPT limit over, told owner"
  fi
}

# New Hermes (v0.23, 11.11.2026) serves every profile from ONE host gateway, so one HERMES entry
# stands for several agents, each with its own ChatGPT login. The host entry therefore also
# checks every profile that has no gateway unit of its own (old-style per-profile units are
# separate entries, or switched off on purpose) and alerts from that profile's own bot.
check_hermes_limit() {
  local unit="$1" dir="$2" who="$3" root home p name
  _hermes_limit_one "$unit" "$dir" "$who"
  [ "$unit" = hermes-gateway.service ] || return 0
  root="${dir%/profiles/*}"; home="${root%/.hermes}"
  for p in "$root"/profiles/*/; do
    p="${p%/}"; name="${p##*/}"
    [ "$p" = "$dir" ] && continue
    [ -e "$home/.config/systemd/user/hermes-gateway-$name.service" ] && continue
    [ -f "$p/auth.json" ] || continue
    _hermes_limit_one "$unit#$name" "$p" "$name"
  done
}

# <<< rubis watchdog checks <<<
