#!/usr/bin/env bash
# Hermes «как у Виктории»: защита от самоудаления + тихий режим + самообновление разговора.
#
#   curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/setup.sh | bash
#
# 1) Ставит хук protect-home.py: агент не может рекурсивно удалить ~/.hermes или
#    обнулить ключевые файлы профиля (.env, SOUL.md, config.yaml, auth.json, state.db).
# 2) Тихий режим: бот присылает только ответ, без служебных сообщений на английском.
# 3) Разговор сам начинается заново ночью и после 4 часов тишины — не раздувается и не тормозит.
# 4) Проверка перед «готово» (05.11.2026): агент на GPT не сдаёт изменённые файлы, не перечитав их
#    (хук verify-gate.py + правило в SOUL.md). GPT чаще говорит «готово», не проверив.
# Повторный запуск безопасен. Env для тестов: HERMES_DIR (по умолчанию ~/.hermes),
# HERMES_BIN (по умолчанию hermes), PROTECT_SRC / GATE_SRC / MC_SRC (локальные файлы вместо скачивания).
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

# 2–3. Тихий режим и самообновление разговора — во всех профилях.
#      busy_input_mode steer: сообщение, присланное во время работы, агент учитывает по ходу,
#      а не бросает начатую задачу (раньше «ну что там?» обрывало длинную работу).
profile_args() { [ "$1" = "$H" ] && return 0; printf -- '--profile\n%s\n' "$(basename "$1")"; }
SETTINGS=(
  "display.memory_notifications off"
  "display.file_mutation_verifier false"
  "display.turn_completion_explainer false"
  "display.credits_notices false"
  "display.busy_ack_enabled false"
  "display.interim_assistant_messages false"
  "display.long_running_notifications false"
  "display.show_commentary false"
  "telegram.gateway_restart_notification false"
  "session_reset.mode both"
  "session_reset.at_hour 4"
  "session_reset.idle_minutes 240"
  "session_reset.notify false"
  "display.busy_input_mode steer"
  "display.busy_steer_ack_enabled false"
)
for home in "$H" "$H"/profiles/*; do
  [ -f "$home/config.yaml" ] || continue
  mapfile -t PA < <(profile_args "$home")
  for kv in "${SETTINGS[@]}"; do
    # shellcheck disable=SC2086
    "$HB" "${PA[@]}" config set $kv --force >/dev/null
  done
done

# 3б. Раннее сжатие разговора во всех профилях: без него один длинный разговор разрастается
#     до сотен тысяч токенов, агент пересылает их на каждом шаге — лимит ChatGPT кончается
#     за утро, ответы идут минутами (ученица 05.11.2026). Главное — потолок threshold_tokens:
#     для окон меньше 512 тыс. Hermes сам поднимает процентный порог до 75%, потолок — нет.
in_block() { sed -n '/^compression:/,/^[^ ]/p' "$2" | grep -q "^  $1:"; }
for cfg in "$H/config.yaml" "$H"/profiles/*/config.yaml; do
  [ -f "$cfg" ] || continue
  grep -q "^compression:" "$cfg" || printf 'compression:\n  enabled: true\n' >> "$cfg"
  for kv in "threshold 0.1" "threshold_tokens 100000"; do
    # shellcheck disable=SC2086
    set -- $kv
    if in_block "$1" "$cfg"; then
      sed -i "/^compression:/,/^[^ ]/ s/^  $1: .*/  $1: $2/" "$cfg"
    else
      sed -i "/^compression:/a\\  $1: $2" "$cfg"
    fi
  done
done

# 4. Проверка перед «готово»: хук verify-gate.py во всех профилях + правило в характере
GATE_RAW="https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/verify-gate.py"
GATE="$H/hooks/verify-gate.py"
if [ -n "${GATE_SRC:-}" ]; then cp "$GATE_SRC" "$GATE"; else curl -fsSL "$GATE_RAW" -o "$GATE"; fi
chmod 755 "$GATE"
for cfg in "$H/config.yaml" "$H"/profiles/*/config.yaml; do
  [ -f "$cfg" ] || continue
  grep -q "verify-gate.py" "$cfg" && continue
  [ -f "$cfg.bak-before-verify" ] || cp "$cfg" "$cfg.bak-before-verify"
  if grep -q "^hooks:" "$cfg"; then
    sed -i "/^hooks:/a\\  pre_verify:\\n    - command: $GATE\\n      timeout: 10" "$cfg"
  else
    printf 'hooks:\n  pre_verify:\n    - command: %s\n      timeout: 10\n' "$GATE" >> "$cfg"
  fi
  grep -q "^hooks_auto_accept: true" "$cfg" || { sed -i '/^hooks_auto_accept:/d' "$cfg"; echo "hooks_auto_accept: true" >> "$cfg"; }
done
for soul in "$H/SOUL.md" "$H"/profiles/*/SOUL.md; do
  [ -f "$soul" ] || continue
  grep -q "Проверка перед «готово»" "$soul" && continue
  cat >> "$soul" <<'RULE'

## Проверка перед «готово» (обязательно)
Прежде чем сдать работу, проверяю её сам:
- файл, документ, текст в файле — открываю и перечитываю: там именно то, что просили, без ошибок и заглушек;
- картинку, PDF, видео — смотрю сам результат (картинку/кадры), а не код, который его делал;
- сайт, ссылку, публикацию — открываю и убеждаюсь, что изменение видно.
Нашёл ошибку — исправляю и проверяю снова. В ответе одной строкой: «Проверил: …» — что открыл и что увидел.
Не проверил — не пишу «готово», а честно говорю, что осталось проверить.
RULE
done

# 5. Третья ступень: видео/PDF/картинки, собранные программой, агент обязан посмотреть сам (плагин media-check)
#    + плагин busy-ack-ru: написал агенту, пока он занят, — он коротко отвечает «Принял» по-русски
RAW="https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect"
for plugin in media-check busy-ack-ru; do
  case "$plugin" in media-check) SRC="${MC_SRC:-}";; busy-ack-ru) SRC="${BA_SRC:-}";; esac
  for home in "$H" "$H"/profiles/*; do
    [ -f "$home/config.yaml" ] || continue
    mkdir -p "$home/plugins/$plugin"
    for f in __init__.py plugin.yaml; do
      if [ -n "$SRC" ]; then cp "$SRC/$f" "$home/plugins/$plugin/$f"; else curl -fsSL "$RAW/$plugin/$f" -o "$home/plugins/$plugin/$f"; fi
    done
    mapfile -t PA < <(profile_args "$home")
    "$HB" "${PA[@]}" plugins enable "$plugin" >/dev/null 2>&1 || true
  done
done

# Проверка: хук блокирует снос дома и пропускает обычную команду
probe() { printf '{"tool_name":"terminal","cwd":"/root","tool_input":{"command":"%s"}}' "$1" | python3 "$HOOK"; }
probe "rm -rf /root/.hermes" | grep -q '"block"' || { echo "ОШИБКА: защита не сработала"; exit 1; }
if probe "ls /root/.hermes" | grep -q '"block"'; then echo "ОШИБКА: защита мешает обычным командам"; exit 1; fi

echo "Готово: защита от самоудаления, тихий режим, самообновление разговора и проверка перед «готово» включены."
echo "Перезапустите агента: hermes gateway restart"
