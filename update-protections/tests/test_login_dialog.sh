#!/usr/bin/env bash
# check_login + unblock_dialog with a fake tmux.
set -u
WD="$1"; WORK=$(mktemp -d)
export WATCHDOG_LOG="$WORK/wd.log" WATCHDOG_CREDS="$WORK/creds.json"
source "$WD"
PANE=""; KEYS=(); KILLED=0; NOTIFIED=()
tmux() { case "$1" in has-session) return 0;; capture-pane) printf '%s\n' "$PANE";; send-keys) KEYS+=("${@: -1}");; kill-session) KILLED=1;; esac; }
notify_owner() { NOTIFIED+=("$2"); }
fail() { echo "FAIL: $1"; exit 1; }
past=$(( ($(date +%s) - 60) * 1000 ))
printf '{"claudeAiOauth":{"expiresAt":%s}}' $past >"$WATCHDOG_CREDS"
PANE='● Login expired · Please run /login'
check_login a /x; [ ${#NOTIFIED[@]} -eq 1 ] || fail "no alert on expired login"
check_login a /x; [ ${#NOTIFIED[@]} -eq 1 ] || fail "alerted twice"
touch -d '+5 sec' "$WATCHDOG_CREDS"; check_login a /x; [ $KILLED -eq 1 ] || fail "no restart after re-login"
PANE='Do you want to proceed?
❯ 1. Yes
Esc to cancel'
for i in 1 2; do unblock_dialog a; done; [ ${#KEYS[@]} -eq 0 ] || fail "pressed Escape too early"
unblock_dialog a; [ "${KEYS[0]:-}" = Escape ] || fail "dialog not closed"
PANE='working… (esc to interrupt)'; KEYS=(); for i in 1 2 3 4; do unblock_dialog a; done
[ ${#KEYS[@]} -eq 0 ] || fail "touched a working agent"
echo "PASS check_login/unblock_dialog"
