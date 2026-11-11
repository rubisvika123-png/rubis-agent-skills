#!/usr/bin/env bash
# Tests check_login_soon() in the client watchdogs (Галина klientname, Степан komanda2).
#   test_client_login_soon.sh <watchdog.sh> ...
set -u
for WD in "$@"; do
  WORK=$(mktemp -d)
  export WATCHDOG_LOG="$WORK/wd.log" WATCHDOG_CREDS="$WORK/creds.json" \
         WATCHDOG_LONG_TOKEN="$WORK/oauth-token" WATCHDOG_LOGIN_SOON_STATE="$WORK/soon.state"
  # shellcheck disable=SC1090
  source "$WD"
  NOTIFIED=()
  notify_owner() { NOTIFIED+=("$1|$2"); }
  soon_creds() { printf '{"claudeAiOauth":{"refreshTokenExpiresAt":%s}}' "$(( ($(date +%s) + $1) * 1000 ))" >"$WATCHDOG_CREDS"; }
  fail() { echo "FAIL ($WD): $1"; exit 1; }

  soon_creds $((20 * 86400)); check_login_soon
  [ ${#NOTIFIED[@]} -eq 0 ] || fail "warned 20 days ahead"
  soon_creds $((2 * 86400)); check_login_soon
  [ ${#NOTIFIED[@]} -eq 1 ] || fail "no warning 2 days ahead"
  echo "${NOTIFIED[0]}" | grep -q 'вход' || fail "text does not mention the login"
  first=$(printf '%s\n' "${!AGENTS[@]}" | sort | head -1)
  [ "${NOTIFIED[0]%%|*}" = "${AGENTS[$first]}" ] || fail "sent via the wrong agent"
  check_login_soon
  [ ${#NOTIFIED[@]} -eq 1 ] || fail "warned twice about one login"
  soon_creds $((25 * 86400)); check_login_soon; soon_creds 86400; check_login_soon
  [ ${#NOTIFIED[@]} -eq 2 ] || fail "new login did not re-arm"
  # Long-lived setup-token: fresh file = a year left, creds file ignored even if it ends soon.
  soon_creds 3600; echo tok >"$WATCHDOG_LONG_TOKEN"; check_login_soon
  [ ${#NOTIFIED[@]} -eq 2 ] || fail "warned although a fresh year token is in place"
  touch -d "@$(( $(date +%s) - 363 * 86400 ))" "$WATCHDOG_LONG_TOKEN"; check_login_soon
  [ ${#NOTIFIED[@]} -eq 3 ] || fail "no warning 2 days before the year token ends"
  echo '{}' >"$WATCHDOG_CREDS"; : >"$WATCHDOG_LONG_TOKEN"; check_login_soon
  [ ${#NOTIFIED[@]} -eq 3 ] || fail "warned with no date at all"
  echo "PASS $WD"
done
