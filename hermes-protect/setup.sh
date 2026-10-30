#!/usr/bin/env bash
# Hermes «как у Виктории»: защита от самоудаления + тихий режим + самообновление разговора.
#
#   curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/setup.sh | bash
#
# 1) Ставит хук protect-home.py: агент не может рекурсивно удалить ~/.hermes или
#    обнулить ключевые файлы профиля (.env, SOUL.md, config.yaml, auth.json, state.db).
# 2) Тихий режим: бот присылает только ответ, без служебных сообщений на английском.
# 3) Разговор сам начинается заново ночью и после 4 часов тишины — не раздувается и не тормозит.
# Повторный запуск безопасен. Env для тестов: HERMES_DIR (по умолчанию ~/.hermes),
# HERMES_BIN (по умолчанию hermes), PROTECT_SRC (локальный protect-home.py вместо скачивания).
set -euo pipefail

H="${HERMES_DIR:-$HOME/.hermes}"
HB="${HERMES_BIN:-hermes}"
RAW="https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/protect-home.py"
HOOK="$H/hooks/protect-home.py"

[ -f "$H/config.yaml" ] || { echo "ОШИБКА: не нашла $H/config.yaml — сначала поставьте Hermes по уроку"; exit 1; }

# 1. Хук защиты
mkdir -p "$H/hooks"
if [ -n "${PROTECT_SRC:-}" ]; then cp "$PROTECT_SRC" "$HOOK"; else curl -fsSL "$RAW" -o "$HOOK"; fi
chmod 755 "$HOOK"

for cfg in "$H/config.yaml" "$H"/profiles/*/config.yaml; do
  [ -f "$cfg" ] || continue
  if grep -q "protect-home.py" "$cfg"; then continue; fi
  if grep -q "^hooks:" "$cfg"; then
    echo "ВНИМАНИЕ: в $cfg уже есть свои hooks — защиту туда не дописала, попросите техспеца добавить её вручную"
    continue
  fi
  cp "$cfg" "$cfg.bak-before-protect"
  sed -i '/^hooks_auto_accept:/d' "$cfg"
  cat >> "$cfg" <<EOF
hooks:
  pre_tool_call:
    - matcher: terminal|execute_code
      command: $HOOK
      timeout: 10
hooks_auto_accept: true
EOF
done

# 2–3. Тихий режим и самообновление разговора (основной профиль)
for kv in \
  "display.memory_notifications off" \
  "display.file_mutation_verifier false" \
  "display.turn_completion_explainer false" \
  "display.credits_notices false" \
  "display.busy_ack_enabled false" \
  "display.interim_assistant_messages false" \
  "display.long_running_notifications false" \
  "display.show_commentary false" \
  "telegram.gateway_restart_notification false" \
  "session_reset.mode both" \
  "session_reset.at_hour 4" \
  "session_reset.idle_minutes 240" \
  "session_reset.notify false"; do
  # shellcheck disable=SC2086
  "$HB" config set $kv --force >/dev/null
done

# Проверка: хук блокирует снос дома и пропускает обычную команду
probe() { printf '{"tool_name":"terminal","cwd":"/root","tool_input":{"command":"%s"}}' "$1" | python3 "$HOOK"; }
probe "rm -rf /root/.hermes" | grep -q '"block"' || { echo "ОШИБКА: защита не сработала"; exit 1; }
if probe "ls /root/.hermes" | grep -q '"block"'; then echo "ОШИБКА: защита мешает обычным командам"; exit 1; fi

echo "Готово: защита от самоудаления, тихий режим и самообновление разговора включены."
echo "Перезапустите агента: hermes gateway restart"
