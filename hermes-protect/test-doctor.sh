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
printf '# Стратег\n## Моя папка\nМоя рабочая папка — /root/ai-strategist. Пути\n## Проверка перед «готово»\n' > "$T/h/profiles/strateg/SOUL.md"
out=$(HERMES_DIR="$T/h" bash "$D/doctor.sh")
echo "$out" | grep -q "старая проверка" || fail "old gate not flagged"
echo "$out" | grep -q "ответ за другого агента" || fail "missing handoff rule not flagged"
echo "$out" | grep -q "ИТОГ: проблем" || fail "no problem summary"
echo "$out" | grep -q "не знает, как смотреть лимит" || fail "22.11: missing limits rule not flagged"
echo "$out" | grep -q "upgrade-all" || fail "22.11: no one-command fix shown"

# fresh setup: gate + rules + compression
cp "$D/verify-gate.py" "$T/h/hooks/verify-gate.py"
printf 'model:\n  default: gpt-5.6-sol\ncompression:\n  enabled: true\n  threshold_tokens: 120000\ndisplay:\n  interim_assistant_messages: true\n  long_running_notifications: false\nhooks:\n  pre_verify:\n    - command: %s/h/hooks/verify-gate.py\n' "$T" > "$T/h/profiles/strateg/config.yaml"
printf '# Стратег\n## Моя папка\nМоя рабочая папка — /root/ai-strategist. Пути\n## Проверка перед «готово»\n## Спросить другого агента = передать и ждать\n## Заметки — коротко и по местам\n## Длина ответа владельцу\n## Цифры владельца — сразу в файл\n## Лимиты ChatGPT\n## Договорённости по задаче\nисправляю и исходный файл\n## Попросили сделать\nне больше двух раз на одну задачу\n' > "$T/h/profiles/strateg/SOUL.md"
mkdir -p "$T/h/profiles/strateg/scripts" && echo x > "$T/h/profiles/strateg/scripts/limit_warning.py"
out=$(HERMES_DIR="$T/h" bash "$D/doctor.sh")
echo "$out" | grep -q "ИТОГ: всё в порядке" || { echo "$out"; fail "fresh setup not clean"; }
echo "doctor: ALL TESTS PASSED"
