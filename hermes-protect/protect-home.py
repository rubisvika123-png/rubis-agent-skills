#!/usr/bin/env python3
"""pre_tool_call hook: не даёт агенту Эрмеса снести собственный дом.

2026-08-26 техспец одной командой стёр /root/.hermes целиком — вместе со своей
памятью, настройками, журналом (по которому можно было бы понять, что именно он
сделал) и профилем куратора Оли внутри. Восстановить удалось не всё.

Хук получает на stdin JSON вида
    {"tool_name": "terminal", "tool_input": {"command": "..."}, "cwd": "..."}
и, если команда рекурсивно удаляет что-то в доме Эрмеса или трогает ключевой
файл профиля, печатает {"decision": "block", "reason": ...} — Эрмес отменяет
вызов и показывает агенту причину.

Разрешено то, что безопасно и нужно в работе: чистка кэшей, логов и песочниц,
удаление отдельных обычных файлов, любые операции вне дома Эрмеса.
"""
import json
import re
import sys

HOME_PATTERNS = (r"/root/\.hermes", r"~/\.hermes", r"\$HERMES_HOME", r"\$\{HERMES_HOME\}")
HOME_RE = re.compile("|".join(HOME_PATTERNS))

# Чистка этих подпапок — обычная работа, не катастрофа.
SAFE_SUBDIRS = re.compile(
    r"(/root/\.hermes|~/\.hermes|\$HERMES_HOME|\$\{HERMES_HOME\})"
    r"(/profiles/[^/\s]+)?/(cache|logs|sandboxes|audio_cache|image_cache|pending_messages)\b"
)

# Рекурсивное удаление в любом виде, включая питоний rmtree из execute_code.
RECURSIVE_DELETE = re.compile(
    r"\brm\b[^|;&\n]*?\s-[a-zA-Z]*[rR]"      # rm -r, rm -rf, rm -fr, rm -Rf
    r"|shutil\.rmtree|\brmtree\s*\("            # python
    r"|os\.removedirs"
    r"|\bfind\b[^|;&\n]*-delete"
    r"|\bfind\b[^|;&\n]*-exec\s+rm"
)

# Файлы, без которых профиль не поднимется: доступ к боту, характер, настройки,
# память. Их нельзя ни удалить, ни обнулить — даже по одному.
KEY_FILE = re.compile(
    r"(/root/\.hermes|~/\.hermes|\$HERMES_HOME|\$\{HERMES_HOME\})[^\s'\"]*/"
    r"(\.env|SOUL\.md|config\.yaml|auth\.json|state\.db)\b"
)
KEY_FILE_HARM = re.compile(
    r"\brm\b|\bmv\b|\btruncate\b|\bshred\b|>\s*[^>|]*(\.env|SOUL\.md|config\.yaml|auth\.json|state\.db)"
    r"|os\.remove|os\.unlink|\bunlink\s*\("
)

REASON = (
    "Заблокировано защитой: это удаляет или обнуляет файлы дома Эрмеса "
    "({what}). Так однажды агент стёр сам себя вместе с "
    "памятью и настройками. Восстановление из резервной копии делает только владелец "
    "сам — попроси его, не обходи запрет."
)


def verdict(command: str, cwd: str) -> str:
    """Вернуть текст причины блокировки или '' если команда безопасна."""
    if not command.strip():
        return ""

    touches_home = bool(HOME_RE.search(command))
    # Относительный путь в доме Эрмеса опаснее абсолютного: `rm -rf .` из
    # рабочей папки профиля выглядит безобидно и сносит всё. Именно в таком
    # положении (cwd внутри профиля) работает гейтвей.
    in_home = cwd.startswith("/root/.hermes")

    if RECURSIVE_DELETE.search(command):
        if SAFE_SUBDIRS.search(command):
            return ""
        if touches_home:
            return REASON.format(what="рекурсивное удаление")
        if in_home:
            return REASON.format(
                what="рекурсивное удаление по относительному пути, "
                     "рабочая папка — внутри дома Эрмеса"
            )

    if KEY_FILE.search(command) and KEY_FILE_HARM.search(command):
        return REASON.format(what="ключевой файл профиля")

    return ""


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # непонятный вход — молчим, хук не имеет права ломать агента

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    # terminal кладёт команду в command, execute_code — код в code/script.
    command = " ".join(
        str(tool_input.get(k, "")) for k in ("command", "code", "script", "input")
    )
    reason = verdict(command, str(payload.get("cwd") or ""))
    if reason:
        json.dump({"decision": "block", "reason": reason}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
