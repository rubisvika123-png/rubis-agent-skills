#!/usr/bin/env bash
# Самопроверка агентов на GPT (Hermes) — для тех-спеца ученика, без доступа к серверу снаружи.
# Вика 13.11.2026: «чтобы ученик по уроку ставил нормального агента на GPT, а не мы чинили каждого вручную».
# Только читает. Печатает по каждому агенту: ОК / ПРОБЛЕМА + что сделать. Ничего не меняет.
#   curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/doctor.sh | bash
H="${HERMES_DIR:-$HOME/.hermes}"
FIX="Отправь себе ещё раз сообщение из урока 10, шаг 9 (пункт 5 скачает свежие защиты), потом напиши агенту /new."
bad=0
say() { echo "  $1"; }
prob() { echo "  ПРОБЛЕМА: $1"; bad=$((bad+1)); }

GATE="$H/hooks/verify-gate.py"
echo "== Общие защиты"
if [ ! -f "$GATE" ]; then prob "нет проверки «перед готово». $FIX"
elif ! grep -q "ai-shared-brain" "$GATE"; then prob "старая проверка «перед готово» — агент отвечает дважды и тратит лимит вдвое. $FIX"
else say "ОК: проверка «перед готово» свежая"; fi

for home in "$H" "$H"/profiles/*; do
  [ -f "$home/config.yaml" ] || continue
  name=$(basename "$home"); [ "$home" = "$H" ] && name="основной"
  echo "== Агент: $name"
  soul="$home/SOUL.md"
  if [ -f "$soul" ]; then
    grep -q "Проверка перед «готово»" "$soul" || prob "в характере нет правила проверки перед «готово». $FIX"
    grep -q "Спросить другого агента = передать и ждать" "$soul" || prob "в характере нет запрета писать ответ за другого агента (GPT выдумывает «ответы» коллег). $FIX"
    grep -q "Заметки — коротко и по местам" "$soul" || prob "в характере нет правила «файл цифр — только цифры». $FIX"
    grep -q "## Цифры владельца — сразу в файл" "$soul" || prob "в характере нет правила «цифры владельца сразу в файл» — агент теряет цифры из разговора. $FIX"
    grep -q "## Длина ответа владельцу" "$soul" || prob "в характере нет ограничения длины — агент пишет простыни и тратит лимит. $FIX"
  else prob "нет файла характера SOUL.md"; fi
  grep -q "verify-gate.py" "$home/config.yaml" || prob "проверка «перед готово» не подключена к этому агенту. $FIX"
  grep -A6 '^compression:' "$home/config.yaml" | grep -q 'threshold_tokens: 100000' || prob "не включено раннее сжатие разговора — лимит уходит быстрее. $FIX"
  model=$(awk '/^model:/{f=1;next} f&&/default:/{print $2; exit}' "$home/config.yaml")
  [ -n "$model" ] && say "модель: $model"
  db="$home/state.db"
  if [ -f "$db" ] && command -v python3 >/dev/null; then
    python3 - "$db" <<'PY'
import sqlite3, sys, time
try:
    c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    n = c.execute("select count(*) from sessions where source='oneshot' and started_at > ?", (time.time() - 3 * 86400,)).fetchone()[0]
    if n >= 3:
        print(f"  ВНИМАНИЕ: за 3 дня агента {n} раз запускали отдельными проверками (hermes -z) — каждая тратит лимит ChatGPT. Без нужды так не проверять.")
except Exception:
    pass
PY
  fi
done

for pa in /root/ai-*/materials/point-a.md; do
  [ -f "$pa" ] || continue
  sz=$(wc -c < "$pa")
  if [ "$sz" -gt 25000 ]; then
    prob "$pa — $((sz/1000)) тысяч байт. Агент перечитывает его на каждом сообщении. Попроси агента: «оставь в point-a.md только цифры и факты, разборы и выводы перенеси отдельными файлами в долгую память и строкой в оглавление»."
  else say "ОК: $pa — $((sz/1000)) тысяч байт"; fi
done

echo
[ "$bad" = 0 ] && echo "ИТОГ: всё в порядке." || echo "ИТОГ: проблем — $bad. Сделай, что написано у каждой, и запусти проверку ещё раз."
