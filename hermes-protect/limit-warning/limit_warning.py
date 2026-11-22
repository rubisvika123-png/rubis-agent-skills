#!/usr/bin/env python3
"""Warn the owner when the weekly Hermes limit crosses set thresholds."""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

THRESHOLDS = (40, 30, 20, 10)
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "__PDIR__"))
STATE_PATH = Path(
    os.environ.get(
        "LIMIT_WARNING_STATE",
        str(HERMES_HOME / "cache" / "weekly_limit_warning_state.json"),
    )
)


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def format_moscow_reset(raw_value: str) -> str:
    # 22.11: `hermes usage` prints the server's zone abbreviation (CET, CEST, MSK, UTC…); strptime %Z only knows a few
    stamp, abbr = raw_value.rsplit(" ", 1)
    zones = {"MSK": "Europe/Moscow", "CET": "Europe/Paris", "CEST": "Europe/Paris", "EET": "Europe/Helsinki",
             "EEST": "Europe/Helsinki", "UTC": "UTC", "GMT": "UTC", "BST": "Europe/London"}
    reset_dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    reset_dt = reset_dt.replace(tzinfo=ZoneInfo(zones.get(abbr, "Europe/Moscow"))).astimezone(ZoneInfo("Europe/Moscow"))
    months = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    return f"{reset_dt.day} {months[reset_dt.month - 1]} в {reset_dt:%H:%M} по Москве"


SESSION_STATE = HERMES_HOME / "cache" / "session_limit_warning_state.json"


def session_warning(text: str) -> None:
    """Warn once per session window at <=20% left and once when it is used up."""
    m = re.search(r"Session:\s*(\d+)% remaining.*?\((\d{4}-\d{2}-\d{2} \d{2}:\d{2} [A-Z]+)\)", text)
    if not m:
        return
    left, reset_raw = int(m.group(1)), m.group(2)
    level = 0 if left <= 0 else (20 if left <= 20 else None)
    if level is None:
        return
    try:
        st = json.loads(SESSION_STATE.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("reset") == reset_raw and isinstance(st.get("level"), int) and st["level"] <= level:
        return
    when = format_moscow_reset(reset_raw)
    if level == 0:
        print(f"Лимит ChatGPT на ближайшие часы закончился — пока я не смогу отвечать. Снова заработаю {when}.")
    else:
        print(f"Внимание: лимит ChatGPT на ближайшие часы почти закончился (осталось {left}%). Обновится {when}. Тяжёлые задачи лучше отложить.")
    SESSION_STATE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE.write_text(json.dumps({"reset": reset_raw, "level": level}), encoding="utf-8")


def main() -> None:
    result = subprocess.run(
        ["hermes", "usage"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return
    session_warning(result.stdout)  # 21.11 Денис: 5-часовой лимит тоже (Ольга: «просто замолчал»)

    match = re.search(
        r"Weekly:\s*(\d+)% remaining.*?\((\d{4}-\d{2}-\d{2} \d{2}:\d{2} [A-Z]+)\)",
        result.stdout,
    )
    if not match:
        return

    remaining = int(match.group(1))
    reset_raw = match.group(2)
    crossed = [threshold for threshold in THRESHOLDS if remaining <= threshold]
    if not crossed:
        save_state({"reset": reset_raw, "last_threshold": None})
        return

    threshold = min(crossed)
    state = load_state()
    if state.get("reset") == reset_raw:
        previous = state.get("last_threshold")
        if isinstance(previous, int) and threshold >= previous:
            return

    reset_text = format_moscow_reset(reset_raw)
    print(
        f"Внимание: недельный лимит - {remaining}%. "
        f"Обновится {reset_text}. "
        "Сейчас лучше не запускать тяжёлые задачи."
    )
    save_state({"reset": reset_raw, "last_threshold": threshold})


if __name__ == "__main__":
    main()
