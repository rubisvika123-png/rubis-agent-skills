#!/usr/bin/env bash
# «Обнови защиты» — догоняет агентов ученика до защит команды Виктории (10.11.2026).
#
#   curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/update-protections/update.sh | bash
#
# Повторный запуск безопасен: что уже стоит — не трогает. По шагам:
#  1. Навыки курса (~/rubis-agent-skills) — скачивает или обновляет.
#  2. Мост в Telegram — новый из заготовки (защита от бана Telegram, длинные сообщения
#     не теряются). Только если вы его не меняли: изменённый мост не трогаем.
#  3. Сторож ответа — агент не может промолчать в Telegram.
#  4. Моды: предупреждение о лимите заранее + толкач застрявших сообщений.
#  5. Сторож агентов — проверки «слетел вход», «вход скоро кончится», «окно с вопросом»;
#     его перезапуск больше не выключает агентов.
#  6. Защита сервера от подбора пароля (fail2ban).
#  7. Перезапуск агентов по одному (разговор сохраняется) и проверка-аудит.
#
# Env для тестов: AGENTS_ROOT (/root), SKILLS_DIR (~/rubis-agent-skills), STARTER_DIR
# (готовая копия заготовки вместо скачивания), UNIT_DIR (/etc/systemd/system),
# NO_APT=1, NO_RESTART=1, NO_AUDIT=1, NO_FETCH=1.
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"

AGENTS_ROOT="${AGENTS_ROOT:-/root}"
SKILLS_DIR="${SKILLS_DIR:-$HOME/rubis-agent-skills}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
SKILLS_URL="https://github.com/rubisvika123-png/rubis-agent-skills.git"
STARTER_URL="https://github.com/rubisvika123-png/ai-victoriarubis.git"
STAMP=$(date +%Y%m%d-%H%M)
say()  { echo "• $*"; }
warn() { echo "⚠️  $*"; }

# ---- 1. course skills ----------------------------------------------------------------------
if [ -z "${NO_FETCH:-}" ]; then
  if [ -d "$SKILLS_DIR/.git" ]; then
    git -C "$SKILLS_DIR" pull -q --ff-only 2>/dev/null && say "навыки курса обновлены" \
      || warn "навыки курса в $SKILLS_DIR не обновились сами (там свои изменения) — беру новое во временную папку"
  else
    git clone -q "$SKILLS_URL" "$SKILLS_DIR" && say "навыки курса скачаны в $SKILLS_DIR"
  fi
fi
FRESH_SKILLS="$SKILLS_DIR"
if [ ! -d "$SKILLS_DIR/update-protections" ] && [ -z "${NO_FETCH:-}" ]; then
  FRESH_SKILLS=$(mktemp -d); git clone -q --depth 1 "$SKILLS_URL" "$FRESH_SKILLS"
fi
CHECKS="$FRESH_SKILLS/update-protections/watchdog-checks.sh"
[ -f "$CHECKS" ] || { echo "ОШИБКА: нет $CHECKS"; exit 1; }
# mods must sit at a stable path (start.sh points at them)
for m in limit-warn unstick; do
  if [ ! -d "$SKILLS_DIR/mods/$m" ] && [ -d "$FRESH_SKILLS/mods/$m" ]; then
    mkdir -p "$SKILLS_DIR/mods"; cp -r "$FRESH_SKILLS/mods/$m" "$SKILLS_DIR/mods/"
  fi
done

if [ -n "${STARTER_DIR:-}" ]; then STARTER="$STARTER_DIR"
else STARTER=$(mktemp -d); git clone -q --depth 1 "$STARTER_URL" "$STARTER"; fi
NEW_SRC="$STARTER/dashi-plugin-claude-code/plugin"

# ---- agents ---------------------------------------------------------------------------------
AGENT_DIRS=()
for st in "$AGENTS_ROOT"/*/start.sh "$AGENTS_ROOT"/*/*/start.sh; do
  d=$(dirname "$st"); [ -d "$d/dashi-plugin-claude-code/plugin/src" ] && AGENT_DIRS+=("$d")
done
[ ${#AGENT_DIRS[@]} -gt 0 ] || { echo "ОШИБКА: агентов в $AGENTS_ROOT не нашла"; exit 1; }
say "агенты: ${AGENT_DIRS[*]}"

for d in "${AGENT_DIRS[@]}"; do
  p="$d/dashi-plugin-claude-code/plugin"; name=$(basename "$d")

  # ---- 2. bridge --------------------------------------------------------------------------
  if diff -rq "$p/src" "$NEW_SRC/src" -x '*.bak*' >/dev/null 2>&1; then
    say "$name: мост уже новый"
  elif [ -d "$d/.git" ] && ! git -C "$d" diff --quiet HEAD -- dashi-plugin-claude-code/plugin/src 2>/dev/null; then
    warn "$name: мост изменён вручную — обновление моста пропущено, его сделает ваш техспец"
  else
    cp -a "$p/src" "$p/src.bak-$STAMP"
    cp -a "$NEW_SRC/src/." "$p/src/"
    if ! cmp -s "$p/package.json" "$NEW_SRC/package.json"; then
      cp "$NEW_SRC/package.json" "$p/package.json"
      [ -f "$NEW_SRC/bun.lock" ] && cp "$NEW_SRC/bun.lock" "$p/bun.lock"
      (cd "$p" && bun install >/dev/null 2>&1) || warn "$name: bun install не прошёл"
    fi
    say "$name: мост обновлён (старый — в src.bak-$STAMP)"
  fi

  # ---- 3. reply guard ---------------------------------------------------------------------
  mkdir -p "$d/scripts" "$p/.claude"
  cp "$STARTER/scripts/require-telegram-reply.js" "$d/scripts/require-telegram-reply.js"
  python3 - "$p/.claude/settings.json" "$NEW_SRC/.claude/settings.json" <<'PY'
import json, os, sys
dst, src = sys.argv[1], sys.argv[2]
want = json.load(open(src))["hooks"]["Stop"][0]
cur = json.load(open(dst)) if os.path.exists(dst) else {}
if "require-telegram-reply" in json.dumps(cur):
    sys.exit(0)
cur.setdefault("hooks", {}).setdefault("Stop", []).append(want)
json.dump(cur, open(dst, "w"), ensure_ascii=False, indent=2)
PY
  say "$name: сторож ответа на месте"

  # ---- 4. mods + conversation-keeping restart ----------------------------------------------
  python3 - "$d/start.sh" "$SKILLS_DIR" "$STAMP" <<'PY'
import re, shutil, sys
p, skills, stamp = sys.argv[1:4]
s = open(p).read(); orig = s
mods = [skills + "/mods/limit-warn", skills + "/mods/unstick"]
m = re.search(r'^export CLAUDE_CODE_PLUGIN_DIRS="([^"]*)"', s, re.M)
if "mods/limit-warn" in s and "mods/unstick" in s:
    pass  # already wired (the starter's own start.sh does it since 11.11.2026)
elif m:
    have = m.group(1)
    add = [x for x in mods if x.split("/mods/")[1] not in have]
    if add:
        s = s.replace(m.group(0), 'export CLAUDE_CODE_PLUGIN_DIRS="%s"' % ":".join([have] + add if have else add))
else:
    block = ('# Mods from the course skills: limit warning ahead of time, stuck-message unstick.\n'
             'export CLAUDE_CODE_PLUGIN_DIRS="%s"\n' % ":".join(mods))
    i = s.find("CONT=()")
    if i < 0:
        i = s.find("exec env IS_SANDBOX=1 claude")
    if i < 0:
        print("start.sh: no exec line"); sys.exit(1)
    s = s[:i] + block + s[i:]
if "continue-once" not in s:
    s = s.replace("exec env IS_SANDBOX=1 claude ",
        '# One-shot: a restart for an update keeps the conversation.\nCONT=()\n'
        'if [ -f "$PLUGIN_DIR/state/continue-once" ]; then rm -f "$PLUGIN_DIR/state/continue-once"; CONT=(--continue); fi\n'
        'exec env IS_SANDBOX=1 claude "${CONT[@]}" ', 1)
if s != orig:
    shutil.copy2(p, p + ".bak-" + stamp)
    open(p, "w").write(s)
PY
  bash -n "$d/start.sh" && say "$name: моды limit-warn и unstick подключены" || warn "$name: start.sh сломался — верните $d/start.sh.bak-$STAMP"
done

# ---- 5. agent watchdog -------------------------------------------------------------------------
WD_UNITS=$(ls "$UNIT_DIR"/agent-watchdog*.service 2>/dev/null)
[ -n "$WD_UNITS" ] || warn "сторожа агентов нет — поставьте его по docs/agent-watchdog-server.md из заготовки, потом запустите эту команду ещё раз"
for unit in $WD_UNITS; do
  wd=$(grep -m1 '^ExecStart=' "$unit" | grep -oE '/[^ "]*watchdog[^ "]*\.sh' | head -1)
  [ -f "$wd" ] || { warn "сторож $unit: скрипт $wd не найден"; continue; }
  if grep -q '^check_login_soon()' "$wd" && grep -q '^unblock_dialog()' "$wd" && grep -q '^check_login()' "$wd"; then
    say "сторож $(basename "$unit"): проверки уже есть"
  else
    cp -p "$wd" "$wd.bak-$STAMP"
    if python3 - "$wd" "$CHECKS" <<'PY'
import re, sys
p, chk = sys.argv[1], sys.argv[2]
s = open(p).read(); block = open(chk).read()
if "main() {" not in s or 'check_limit "$name"' not in s:
    print("старый сторож без check_limit"); sys.exit(1)
# drop functions this watchdog already has, keep the rest of the block
for fn in ("creds_expired", "check_login", "check_login_soon", "unblock_dialog"):
    if re.search(r"^%s\(\) \{" % fn, s, re.M):
        block = re.sub(r"^%s\(\) \{.*?^\}\n" % fn, "", block, flags=re.M | re.S)
s = s.replace("main() {\n", block + "\nmain() {\n", 1)
lines = s.split("\n"); out = []; in_main = False; added_loop = False
for i, ln in enumerate(lines):
    out.append(ln)
    if ln.startswith("main() {"): in_main = True
    if in_main and re.match(r'\s+check_limit "\$name"', ln):
        ind = re.match(r"(\s+)", ln).group(1)
        rest = "\n".join(lines[i + 1:i + 8])
        if 'check_login "$name"' not in rest: out.append(ind + 'check_login "$name" "${AGENTS[$name]}"')
        if 'unblock_dialog "$name"' not in rest: out.append(ind + 'unblock_dialog "$name"')
    if in_main and not added_loop and re.match(r"    done\s*$", ln) and any('check_limit "$name"' in x for x in out[-12:]):
        out.append("    check_login_soon"); added_loop = True
if not added_loop:
    print("не нашла цикл в main"); sys.exit(1)
open(p, "w").write("\n".join(out))
PY
    then
      bash -n "$wd" && say "сторож $(basename "$unit"): добавлены проверки входа и окна с вопросом" \
        || { cp -p "$wd.bak-$STAMP" "$wd"; warn "сторож $(basename "$unit"): правка не прошла проверку — вернула как было"; }
    else
      cp -p "$wd.bak-$STAMP" "$wd"; warn "сторож $(basename "$unit"): слишком старый — поставьте заново по docs/agent-watchdog-server.md"
    fi
  fi
  dropin="$unit.d/killmode.conf"
  if ! grep -qs '^KillMode=process' "$unit" "$dropin"; then
    mkdir -p "$unit.d"
    printf '[Service]\n# Перезапуск сторожа не должен выключать агентов\nKillMode=process\n' >"$dropin"
  fi
done
if [ -n "$WD_UNITS" ] && [ -z "${NO_RESTART:-}" ]; then
  systemctl daemon-reload
  for unit in $WD_UNITS; do systemctl restart "$(basename "$unit")"; done
  say "сторож перезапущен"
fi

# ---- 6. fail2ban ---------------------------------------------------------------------------------
if [ -z "${NO_APT:-}" ]; then
  if ! systemctl is-active --quiet fail2ban; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fail2ban >/dev/null 2>&1 \
      && systemctl enable --now fail2ban >/dev/null 2>&1 && say "защита от подбора пароля включена" \
      || warn "fail2ban не поставился"
  else
    say "защита от подбора пароля уже работает"
  fi
fi

# ---- 7. restart agents one by one, then audit ------------------------------------------------------
if [ -z "${NO_RESTART:-}" ]; then
  for d in "${AGENT_DIRS[@]}"; do
    p="$d/dashi-plugin-claude-code/plugin"
    sess=$(for s in $(tmux ls -F '#{session_name}' 2>/dev/null); do
             cwd=$(tmux display -p -t "$s" '#{pane_current_path}' 2>/dev/null)
             case "$cwd" in "$d"|"$d"/*) echo "$s";; esac; done | head -1)
    [ -n "$sess" ] || { warn "$(basename "$d"): комната tmux не найдена — перезапустите агента сами"; continue; }
    mkdir -p "$p/state"; touch "$p/state/continue-once"
    tmux kill-session -t "$sess"
    for _ in $(seq 1 40); do sleep 3; tmux capture-pane -p -t "$sess" 2>/dev/null | grep -q 'bypass permissions on' && break; done
    tmux has-session -t "$sess" 2>/dev/null && say "$(basename "$d"): перезапущен, разговор сохранён" \
      || warn "$(basename "$d"): после перезапуска не поднялся — проверьте сторожа"
  done
fi
if [ -z "${NO_AUDIT:-}" ]; then
  echo; echo "Проверка:"
  bash "$FRESH_SKILLS/update-protections/audit.sh" "$AGENTS_ROOT" /home
fi
