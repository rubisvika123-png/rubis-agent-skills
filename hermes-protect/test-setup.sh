#!/usr/bin/env bash
# Test setup.sh on a fake Hermes home with a stub `hermes`: hook installed, config gets
# hooks once (re-run safe), existing hooks are not overwritten, settings are applied.
set -euo pipefail
cd "$(dirname "$0")"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*"; exit 1; }
mkdir -p "$T/h/profiles/second" "$T/bin"
printf 'model:\n  default: x\nhooks_auto_accept: false\n' > "$T/h/config.yaml"
printf 'hooks:\n  pre_tool_call: []\n' > "$T/h/profiles/second/config.yaml"
printf '#!/bin/sh\necho "$*" >> %s/calls\n' "$T" > "$T/bin/hermes"; chmod +x "$T/bin/hermes"
run() { HERMES_DIR="$T/h" HERMES_BIN="$T/bin/hermes" PROTECT_SRC="$PWD/protect-home.py" bash setup.sh; }
out=$(run) || fail "setup failed: $out"
[ -x "$T/h/hooks/protect-home.py" ] || fail "hook not installed"
grep -q "command: $T/h/hooks/protect-home.py" "$T/h/config.yaml" || fail "hook not in config"
[ "$(grep -c '^hooks_auto_accept: true' "$T/h/config.yaml")" = 1 ] || fail "auto_accept"
grep -q "protect-home" "$T/h/profiles/second/config.yaml" && fail "overwrote existing hooks"
echo "$out" | grep -q "ВНИМАНИЕ" || fail "no warning for existing hooks"
grep -q "session_reset.mode both --force" "$T/calls" && grep -q "display.show_commentary false --force" "$T/calls" || fail "settings not applied"
run >/dev/null
[ "$(grep -c '^hooks:' "$T/h/config.yaml")" = 1 ] || fail "re-run duplicated hooks"
echo "ALL TESTS PASSED"
