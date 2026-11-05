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
printf "# Агент\n" > "$T/h/SOUL.md"
run() { HERMES_DIR="$T/h" HERMES_BIN="$T/bin/hermes" PROTECT_SRC="$PWD/protect-home.py" GATE_SRC="$PWD/verify-gate.py" MC_SRC="$PWD/media-check" bash setup.sh; }
out=$(run) || fail "setup failed: $out"
[ -x "$T/h/hooks/protect-home.py" ] || fail "hook not installed"
grep -q "command: $T/h/hooks/protect-home.py" "$T/h/config.yaml" || fail "hook not in config"
[ "$(grep -c '^hooks_auto_accept: true' "$T/h/config.yaml")" = 1 ] || fail "auto_accept"
grep -q "protect-home" "$T/h/profiles/second/config.yaml" && fail "overwrote existing hooks"
echo "$out" | grep -q "ВНИМАНИЕ" || fail "no warning for existing hooks"
grep -q "session_reset.mode both --force" "$T/calls" && grep -q "display.show_commentary false --force" "$T/calls" || fail "settings not applied"
[ -x "$T/h/hooks/verify-gate.py" ] || fail "gate not installed"
grep -q "verify-gate.py" "$T/h/config.yaml" || fail "gate not in main config"
grep -q "verify-gate.py" "$T/h/profiles/second/config.yaml" || fail "gate not added next to existing hooks"
grep -q "Проверка перед «готово»" "$T/h/SOUL.md" || fail "rule not in SOUL"
[ -f "$T/h/plugins/media-check/__init__.py" ] && [ -f "$T/h/profiles/second/plugins/media-check/plugin.yaml" ] || fail "media-check not installed"
grep -q "plugins enable media-check" "$T/calls" && grep -q -- "--profile second plugins enable media-check" "$T/calls" || fail "media-check not enabled"
run >/dev/null
[ "$(grep -c 'verify-gate.py' "$T/h/config.yaml")" = 1 ] || fail "re-run duplicated gate"
[ "$(grep -c 'Проверка перед «готово»' "$T/h/SOUL.md")" = 1 ] || fail "re-run duplicated rule"
[ "$(grep -c '^hooks:' "$T/h/config.yaml")" = 1 ] || fail "re-run duplicated hooks"
echo "ALL TESTS PASSED"
