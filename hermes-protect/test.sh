#!/usr/bin/env bash
# Проверка hermes-protect-home.sh: блокирует то, чем 2026-08-26 снесли дом
# Эрмеса, и не мешает обычной работе. Хук читает JSON со stdin и печатает
# {"decision": "block", ...} только когда команду надо остановить.
set -uo pipefail
HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/protect-home.py"

fail=0

# check EXPECT("block"|"allow") CWD COMMAND DESCRIPTION
check() {
  local expect="$1" cwd="$2" cmd="$3" what="$4" out
  out=$(python3 -c '
import json, sys
print(json.dumps({"tool_name": "terminal", "cwd": sys.argv[1], "tool_input": {"command": sys.argv[2]}}))
' "$cwd" "$cmd" | python3 "$HOOK")
  if [ "$expect" = "block" ]; then
    echo "$out" | grep -q '"block"' || { echo "FAIL: пропустил — $what: $cmd"; fail=1; }
  else
    echo "$out" | grep -q '"block"' && { echo "FAIL: заблокировал лишнее — $what: $cmd"; fail=1; }
  fi
  return 0
}

# --- то, что должно блокироваться -------------------------------------------
check block /root  'rm -rf /root/.hermes'                       "снос всего дома"
check block /root  'rm -rf /root/.hermes/profiles/olya'         "снос профиля Оли"
check block /root  'rm -rf ~/.hermes/profiles'                  "снос всех профилей через ~"
check block /root  'rm -rf "$HERMES_HOME"'                      "снос через переменную"
check block /root  'python3 -c "import shutil; shutil.rmtree(\"/root/.hermes/profiles/olya\")"' "rmtree из кода"
check block /root  'find /root/.hermes -type f -delete'         "find -delete"
check block /root  'find /root/.hermes -name "*" -exec rm {} +' "find -exec rm"
check block /root/.hermes/profiles/olya 'rm -rf .'              "относительный путь из папки профиля"
check block /root/.hermes               'rm -rf ./profiles'     "относительный путь из дома"
check block /root  'rm /root/.hermes/profiles/olya/.env'        "удаление доступа к боту"
check block /root  'rm -f /root/.hermes/profiles/olya/SOUL.md'  "удаление характера"
check block /root  'mv /root/.hermes/config.yaml /tmp/'         "унос настроек"
check block /root  'truncate -s 0 /root/.hermes/.env'           "обнуление доступов"

# --- то, что должно проходить ------------------------------------------------
check allow /root  'ls -la /root/.hermes/profiles/olya'         "просмотр"
check allow /root  'cat /root/.hermes/profiles/olya/SOUL.md'    "чтение характера"
check allow /root  'rm -rf /root/.hermes/cache'                 "чистка кэша"
check allow /root  'rm -rf /root/.hermes/profiles/olya/logs'    "чистка логов профиля"
check allow /root  'rm -rf /tmp/build'                          "удаление вне дома Эрмеса"
check allow /root  'rm -rf /root/coder/node_modules'            "удаление в чужом проекте"
check allow /root  'rm /root/.hermes/profiles/olya/knowledge/lessons/01-01.md' "удаление обычного файла базы"
check allow /root  'systemctl --user restart hermes-gateway-olya.service'      "перезапуск службы"
check allow /root  'echo "разговор про rm -rf и .env, просто текст"'           "текст про удаление, а не удаление"
check allow /root/.hermes/profiles/olya 'ls -la'                "обычная работа из папки профиля"

[ "$fail" -eq 0 ] && echo "PASS"
exit "$fail"
