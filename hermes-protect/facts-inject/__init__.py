"""facts-inject — put fresh facts in front of a GPT agent on every owner message (Vika 10.11.2026).

Blind tests: GPT answered from memory instead of opening files (stale statuses, invented prices).
Rules did not fix it; injecting the facts did (round 4: wins 3 -> 5 of 19, no invented facts).
pre_llm_call adds today's date and weekday in the owner's time zone, a short rule, and the files
listed in facts.txt next to this file, one per line:  /abs/path   or   /abs/path|tail=40
(relative names are looked up in FACTS_DIR); a line "tz=7" sets the owner's UTC offset. Any *reminders*.tsv is filtered to future rows.
Never raises; missing files are skipped; each file is capped so the context stays small.
"""
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FACTS_DIR = os.environ.get("FACTS_DIR") or os.path.expanduser("~/facts")
TZ_HOURS = float(os.environ.get("FACTS_TZ_HOURS", "3"))  # owner's UTC offset; a "tz=7" line in facts.txt wins
MAX_CHARS = 12000
TITLES = {
    "prices.md": "ЦЕНЫ",
    "board-tail.md": "ДОСКА ЗАДАЧ — последние строки (свежие внизу)",
    "team-tasks.md": "ДОСКА ЗАДАЧ — последние строки (свежие внизу)",
    "reminders.tsv": "НАПОМИНАНИЯ ВЛАДЕЛЬЦА (будущие, время UTC)",
    "course-errors-index.md": "БАЗА РАЗБОРОВ ОШИБОК (оглавление; карточки — ~/facts/course-errors/cards/)",
    "INDEX.md": "БАЗА РАЗБОРОВ ОШИБОК (оглавление; карточки лежат рядом, в папке cards/)",
}
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
RULE = ("ПРАВИЛО: цены, даты, статусы («сделано», «стоит», «активно») бери только из блоков ниже или из "
        "файла, который открыл в этом ходе. Нет в источнике — так и пиши: «не проверено» или «предложение». "
        "Статус задачи — по САМОЙ НИЖНЕЙ строке доски об этой задаче.")


def _entries():
    for name in ("facts.txt", "files.txt"):
        try:
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
        except OSError:
            continue
    return []


def _read(entry, now):
    path, _, opt = entry.partition("|")
    path = os.path.expanduser(path.strip())
    if not os.path.isabs(path):
        path = os.path.join(FACTS_DIR, path)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if opt.strip().startswith("tail="):
        lines = lines[-int(opt.strip()[5:]):]
    name = os.path.basename(path)
    if "reminders" in name and name.endswith(".tsv"):
        keep = []
        for line in lines:
            try:
                when = datetime.fromisoformat(line.split("\t", 1)[0])
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if when >= now:
                    keep.append(line)
            except ValueError:
                continue
        lines = keep or ["(будущих напоминаний нет)"]
    text = "\n".join(lines).strip()
    if len(text) > MAX_CHARS:
        text = text[-MAX_CHARS:]
    return TITLES.get(name, name), text


def build_context(now=None):
    now = now or datetime.now(timezone.utc)
    entries, tz = [], TZ_HOURS
    for e in _entries():
        if e.startswith("tz="):
            try:
                tz = float(e[3:])
            except ValueError:
                pass
        else:
            entries.append(e)
    local = now + timedelta(hours=tz)
    msk = now + timedelta(hours=3)
    parts = [f"СВЕЖИЕ ФАКТЫ (подложены автоматически). Сейчас у владельца: {local:%d.%m.%Y %H:%M}, "
             f"{WEEKDAYS[local.weekday()]}; Москва {msk:%H:%M}.", RULE]
    for entry in entries:
        try:
            title, text = _read(entry, now)
            parts.append(f"=== {title} ===\n{text}")
        except Exception:
            continue
    return "\n\n".join(parts)


def on_pre_llm_call(**_):
    try:
        return {"context": build_context()}
    except Exception:
        return None


def register(ctx):
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
