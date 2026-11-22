#!/usr/bin/env bash
# Самопроверка агентов на GPT (Hermes) — для тех-спеца ученика, без доступа к серверу снаружи.
# Вика 13.11.2026: «чтобы ученик по уроку ставил нормального агента на GPT, а не мы чинили каждого вручную».
# Только читает. Печатает по каждому агенту: ОК / ПРОБЛЕМА + что сделать. Ничего не меняет.
#   curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/doctor.sh | bash
H="${HERMES_DIR:-$HOME/.hermes}"
FIX="Обнови агентов одной командой (2 строки ниже в ИТОГ) и запусти проверку ещё раз."
UPD='curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/claude-to-gpt/claude-to-gpt.py -o ~/claude-to-gpt.py && python3 ~/claude-to-gpt.py --upgrade-all && hermes gateway restart' 
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
  # 22.11: проверяем только агентов, перенесённых переносчиком (в характере есть «Моя рабочая папка»)
  grep -q "Моя рабочая папка" "$home/SOUL.md" 2>/dev/null || continue
  echo "== Агент: $name"
  soul="$home/SOUL.md"
  if [ -f "$soul" ]; then
    grep -q "Проверка перед «готово»" "$soul" || prob "в характере нет правила проверки перед «готово». $FIX"
    grep -q "Спросить другого агента = передать и ждать" "$soul" || prob "в характере нет запрета писать ответ за другого агента (GPT выдумывает «ответы» коллег). $FIX"
    grep -q "Заметки — коротко и по местам" "$soul" || prob "в характере нет правила «файл цифр — только цифры». $FIX"
    grep -q "## Цифры владельца — сразу в файл" "$soul" || prob "в характере нет правила «цифры владельца сразу в файл» — агент теряет цифры из разговора. $FIX"
    grep -q "## Длина ответа владельцу" "$soul" || prob "в характере нет ограничения длины — агент пишет простыни и тратит лимит. $FIX"
    # 22.11: ночные починки качества
    grep -q "## Лимиты ChatGPT" "$soul" || prob "агент не знает, как смотреть лимит, — отвечает «система не показывает». $FIX"
    grep -q "## Договорённости по задаче" "$soul" || prob "агент не записывает договорённости из чата — теряет их при сжатии памяти. $FIX"
    grep -q "исправляю и исходный файл" "$soul" || prob "поправленный факт агент не исправляет в исходном файле — старое всплывает снова. $FIX"
    grep -q "## Попросили сделать" "$soul" || prob "агент отвечает «дашь да?» вместо результата. $FIX"
    grep -q "не больше двух раз на одну задачу" "$soul" || prob "агент может бесконечно гонять проверки и не сдавать итог. $FIX"
  else prob "нет файла характера SOUL.md"; fi
  python3 - "$home/config.yaml" "$soul" <<'PY' || bad=$((bad+1))
import sys, re
try:
    import yaml
    c = yaml.safe_load(open(sys.argv[1])) or {}
except Exception:
    sys.exit(0)
d = c.get("display") or {}
ok = True
if d.get("interim_assistant_messages") is False or d.get("long_running_notifications") is False:
    print("  ПРОБЛЕМА: выключены сообщения по ходу работы — ученик видит тишину по полчаса. Обнови агентов (команда в ИТОГ)."); ok = False
head = ""
try:
    head = open(sys.argv[2], encoding="utf-8").readline()
except Exception:
    pass
if re.search(r"(?i)tech|spec|coder|dev|market|техспец|кодер|маркет", head) and (c.get("agent") or {}).get("reasoning_effort") not in ("high", "xhigh"):
    print("  ПРОБЛЕМА: техспец/маркетолог думает на средней глубине. Обнови агентов (команда в ИТОГ)."); ok = False
sys.exit(0 if ok else 1)
PY
  grep -q "verify-gate.py" "$home/config.yaml" || prob "проверка «перед готово» не подключена к этому агенту. $FIX"
  grep -A40 '^compression:' "$home/config.yaml" | grep -Eq 'threshold_tokens: (6|10|12)0000' || prob "не включено раннее сжатие разговора — лимит уходит быстрее. $FIX"
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
ls "$H"/profiles/*/scripts/*limit_warning.py >/dev/null 2>&1 || ls "$H"/scripts/*limit_warning.py >/dev/null 2>&1 || prob "нет предупреждения о лимите ChatGPT — агент просто замолчит, когда лимит кончится. $FIX"

echo
if [ "$bad" = 0 ]; then echo "ИТОГ: всё в порядке."; else
  echo "ИТОГ: проблем — $bad. Обнови всех агентов одной командой в терминале сервера (характер, память и бот сохранятся):"
  echo "  $UPD"
  echo "Потом запусти эту проверку ещё раз."
fi
