#!/usr/bin/env bash
# Test for doctor.sh (13.11.2026): an old setup is flagged, a fresh setup is clean.
set -u
D="$(cd "$(dirname "$0")" && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*"; exit 1; }

# old setup: old gate, no new rules
mkdir -p "$T/h/hooks" "$T/h/profiles/strateg"
echo 'OWN = re.compile(r"/second-brain/")' > "$T/h/hooks/verify-gate.py"
printf 'model:\n  default: gpt-5.6-sol\n' > "$T/h/profiles/strateg/config.yaml"
echo "## Проверка перед «готово»" > "$T/h/profiles/strateg/SOUL.md"
out=$(HERMES_DIR="$T/h" bash "$D/doctor.sh")
echo "$out" | grep -q "старая проверка" || fail "old gate not flagged"
echo "$out" | grep -q "ответ за другого агента" || fail "missing handoff rule not flagged"
echo "$out" | grep -q "ИТОГ: проблем" || fail "no problem summary"

# fresh setup: gate + rules + compression
cp "$D/verify-gate.py" "$T/h/hooks/verify-gate.py"
printf 'model:\n  default: gpt-5.6-sol\ncompression:\n  enabled: true\n  threshold_tokens: 100000\nhooks:\n  pre_verify:\n    - command: %s/h/hooks/verify-gate.py\n' "$T" > "$T/h/profiles/strateg/config.yaml"
printf '## Проверка перед «готово»\n## Спросить другого агента = передать и ждать\n## Заметки — коротко и по местам\n## Длина ответа владельцу\n' > "$T/h/profiles/strateg/SOUL.md"
out=$(HERMES_DIR="$T/h" bash "$D/doctor.sh")
echo "$out" | grep -q "ИТОГ: всё в порядке" || { echo "$out"; fail "fresh setup not clean"; }
echo "doctor: ALL TESTS PASSED"
