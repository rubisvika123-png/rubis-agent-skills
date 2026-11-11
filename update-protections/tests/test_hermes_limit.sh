#!/usr/bin/env bash
# check_hermes_limit() in a watchdog: one alert per ChatGPT-limit episode with the reset time,
# one "back" message, silence while another login still works.
#   test_hermes_limit.sh <watchdog.sh> ...
set -u
for WD in "$@"; do
  WORK=$(mktemp -d)
  export WATCHDOG_LOG="$WORK/wd.log" WATCHDOG_HERMES_TZ=3
  source "$WD"
  NOTIFIED=(); notify_owner() { NOTIFIED+=("$1|$2"); }
  fail() { echo "FAIL ($WD): $1"; exit 1; }
  pool() { printf '{"credential_pool":{"openai-codex":[%s]}}' "$1" >"$WORK/auth.json"; }
  later=$(( $(date +%s) + 3 * 3600 )); past=$(( $(date +%s) - 60 ))
  pool '{"last_status":"ok"}'; check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 0 ] || fail "alert while the login is fine"
  pool '{"last_status":"exhausted","last_error_reset_at":'$later'},{"last_status":"ok"}'; check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 0 ] || fail "alert although a second login still works"
  pool '{"last_status":"exhausted","last_error_reset_at":'$later'}'; check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 1 ] || fail "no alert when the only login ran out"
  want=$(TZ=Europe/Moscow date -d "@$later" +%H:%M)
  echo "${NOTIFIED[0]}" | grep -q "лимит ChatGPT.*$want" || fail "alert lacks the reset time $want: ${NOTIFIED[0]}"
  [ "${NOTIFIED[0]%%|*}" = "$WORK/.env" ] || fail "alert not sent from the agent's own .env"
  check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 1 ] || fail "alerted twice in one episode"
  pool '{"last_status":"exhausted","last_error_reset_at":'$past'}'; check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 2 ] || fail "no 'back' message after the reset time"
  echo "${NOTIFIED[1]}" | grep -q 'вернулся' || fail "back message wrong: ${NOTIFIED[1]}"
  check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 2 ] || fail "back message repeated"
  pool '{"last_status":"exhausted","last_error_reset_at":'$((later * 1000))'}'; check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 3 ] || fail "reset time in milliseconds not understood"
  echo 'broken' >"$WORK/auth.json"; HLIMIT_NOTIFIED=(); check_hermes_limit u "$WORK" Лиза
  [ ${#NOTIFIED[@]} -eq 3 ] || fail "alert on an unreadable auth.json"
  # Host gateway (new Hermes): one HERMES entry, every profile without its own unit is checked too.
  H="$WORK/home/.hermes"; mkdir -p "$H/profiles/a" "$H/profiles/b" "$WORK/home/.config/systemd/user"
  printf '{"credential_pool":{"openai-codex":[{"last_status":"ok"}]}}' >"$H/auth.json"
  for x in a b; do printf '{"credential_pool":{"openai-codex":[{"last_status":"exhausted","last_error_reset_at":%s}]}}' "$later" >"$H/profiles/$x/auth.json"; done
  touch "$WORK/home/.config/systemd/user/hermes-gateway-b.service"   # b runs its own (old-style) gateway
  NOTIFIED=(); HLIMIT_NOTIFIED=(); check_hermes_limit hermes-gateway.service "$H" Техспец
  [ ${#NOTIFIED[@]} -eq 1 ] || fail "host gateway: want 1 alert (profile a), got ${#NOTIFIED[@]}"
  [ "${NOTIFIED[0]%%|*}" = "$H/profiles/a/.env" ] || fail "host gateway: alert not from profile a's bot: ${NOTIFIED[0]}"
  check_hermes_limit hermes-gateway.service "$H" Техспец
  [ ${#NOTIFIED[@]} -eq 1 ] || fail "host gateway: repeated alert"
  NOTIFIED=(); HLIMIT_NOTIFIED=(); check_hermes_limit hermes-gateway-x.service "$H/profiles/a" a
  [ ${#NOTIFIED[@]} -eq 1 ] || fail "per-profile unit must check only its own profile"
  echo "PASS $WD"
done
