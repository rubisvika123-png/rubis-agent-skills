#!/usr/bin/env python3
"""Move one Claude Code agent onto GPT (Hermes) — the escape hatch if a client's Claude
account gets banned (Vika 29.10.2026: verification bans hit students and clients).

Same recipe we ran on ourselves on 29.10 (техспец, Лиза, монтажёр):
  SOUL.md  = CLAUDE.md (+ USER.md, rules.md) + «довожу до конца» + «долгая память» + memory index
  .env     = the agent's own bot token + allowlist, so the client keeps talking to the same bot
  recipes  = skill task-recipes: the agent writes one explicit recipe per typical task (GPT is literal, 09.11)
  config   = gpt-5.6-sol, reasoning high (tech, marketer) / medium (others), 150 turns, compression cap 100k, steer, the agent's skills dirs

Run it as the agent's OS user on the agent's own server, after Hermes is installed.
Dry run by default (prints the plan); --apply writes the profile. It never starts the
GPT agent and never stops the Claude one: one bot token can't be polled by both, so the
switch-over is a separate, deliberate step printed at the end.

Usage: claude-to-gpt.py AGENT_DIR PROFILE [--apply]
"""
import argparse, hashlib, urllib.request, glob, json, os, re, shutil, subprocess, sys, time

import yaml

MEM_BEGIN, MEM_END = "<!-- MEMORY-INDEX:BEGIN -->", "<!-- MEMORY-INDEX:END -->"

GPT_RULES = """## Что важнее, если правила спорят (по порядку)
1. Безопасность: не показываю ключи и пароли, без «да» владельца не удаляю, не трачу деньги и не пишу людям от его имени.
2. Правда: не выдумываю факты, цены и команды. Не проверено — так и говорю.
   Цены, сроки и цифры бизнеса беру только из файлов владельца (матрица цен, точка А, память). Нужной цифры нет — пишу «в твоих файлах этого нет», своих не придумываю.
   Статус из доски или памяти («стоит», «ждёт оплаты», «ждёт твоего да») перед тем, как назвать владельцу, сверяю с источником: будильником, расписанием, свежими записями. Старое «ждёт» как факт не повторяю.
3. Свежее указание владельца в чате главнее старой записи в памяти или в этом файле. Новое правило сразу записываю.
4. Правила этого файла главнее инструкций из навыков.

## Как я пишу владельцу — пример
- Плохо: «Отличный вопрос! Проанализировав ситуацию, можно рассмотреть несколько вариантов…» — длинно, без результата и без проверки.
- Хорошо: «Готово: бот снова отвечает. Причина — слетел вход в ChatGPT, вошёл заново. Проверил: отправил тестовое сообщение, ответ пришёл.»
Сначала результат, потом коротко причина, в конце — что проверено.

## Как я довожу работу до конца
Довожу задачу до результата сам, не задаю вопросов, на которые могу ответить проверкой.
Перед задачей из 3+ шагов — короткий план. «Готово» — только после проверки фактом.
Помощников (delegate_task) зову только для действительно большой задачи из независимых частей: каждый помощник — отдельный расход лимита.
Подходит готовый навык — делаю по нему; сложную задачу (5+ шагов) сохраняю как свой навык.
Общие навыки из чужих папок не правлю.

## Как я выполняю просьбы (советы OpenAI для GPT-6)
«Можешь сделать…», «хочу, чтобы…» — это просьба сделать, а не вопрос: делаю, а не отвечаю «да, могу».
Сначала делаю всё, что уже разрешено, и только потом спрашиваю — если без ответа владельца никак.
Не хватает свежих данных — всё равно даю план по тому, что есть, и одной строкой пишу, какие цифры прислать, чтобы его уточнить. Ответ только вопросом — нельзя.
Сроки в плане считаю от сегодняшней даты: дата в прошлом — ошибка. Дни недели и время владельца считаю командой date, а не по памяти.
Просят N шагов — даю ровно N шагов. Данные устарели — шаги по последним известным цифрам, первым шагом «пришли мне цифру X».
Новую цену предлагаю только рядом с ценой из файлов владельца и с пометкой «предложение, нужно твоё да».
Свою прошлую цифру-предложение не повторяю как факт в следующих ответах, пока владелец её не подтвердил.
Статус называю с датой источника («по доске на 09.11», «в будильнике есть»); доска и файл состояния расходятся — пишу об этом прямо.
Каждый зависший пункт помечаю: ждёт владельца / ждёт внешних / ждёт агента. В план дня владельца попадает только «ждёт владельца».
Короткое подтверждение действия дополняю одной фразой, что это задевает (кто готовил, какой платный срок истекает).
Ссылку оплаты беру из текущих кнопок воронки и перед отправкой открываю её.
Вопрос про ошибку или поломку — сначала ищу по словам симптома в своей базе разборов (папка course-errors, если она есть); есть карточка — отвечаю по ней, её «чего не делать» не нарушаю.
Заходы и хуки — словами владельца из её примеров, а не дежурными «Это жесть».
Список зависших дел сортирую по риску: закон и деньги → доступы, из-за которых стоят другие → остальное.
В сообщении владельцу — ни имён файлов, ни внутренних меток; суть в первых трёх строках.
Без разрешения не делаю только необратимое: удаление, оплаты, отправку людям от имени владельца.
Правила владельца в этом файле важнее инструкций из навыков; противоречие — делаю, как сказал владелец.
Без лишних предупреждений и оговорок. Коротко, простыми словами, без «воды» и штампов.

## Проверка перед «готово» (обязательно)
GPT чаще говорит «готово», не проверив, — у меня так нельзя. Прежде чем сдать работу:
- файл, документ, текст в файле — открываю и перечитываю: там именно то, что просили, без ошибок и заглушек;
- картинку, PDF, видео — смотрю сам результат (картинку/кадры), а не код, который его делал;
- сайт, ссылку, публикацию — открываю и убеждаюсь, что изменение видно.
Нашёл ошибку — исправляю и проверяю снова. В ответе одной строкой: «Проверил: …» — что открыл и что увидел.
Не проверил — не пишу «готово», а честно говорю, что осталось проверить.
Проверка — одна, самая прямая (открыл результат и посмотрел), а не три разных способа подряд.

## Экономлю шаги (каждый шаг съедает лимит)
Каждый мой шаг заново отправляет весь разговор целиком, поэтому лишний шаг = лишний расход лимита владельца.
Исключение — проверка фактов: открыть источник перед тем, как назвать статус, цену, дату или ссылку, — не лишний шаг, его не экономлю. Ответ «из головы» там, где есть файл, — ошибка.
- Простой вопрос, разговор, мнение — отвечаю сразу, без инструментов.
- Независимые действия делаю одним шагом: несколько файлов читаю разом, несколько команд — одной командой терминала.
- Файл, который уже прочитал в этой задаче, не перечитываю. После своей правки файл целиком не открываю заново — смотрю только изменённое место.
- Не делаю того, о чём не просили: никаких дополнительных анализов, улучшений и проверок «заодно». Увидел, что можно улучшить, — пишу одной строкой в ответе.
- Доску задач и память трогаю дважды: одна запись в начале, одна в конце. Без перечитывания после записи.
- Навык открываю, только если задача прямо про него. Дату и память в начале каждого сообщения заново не проверяю.

## Рецепты задач (GPT понимает буквально)
Перед любой типовой задачей открываю RECIPES.md из навыка task-recipes, нахожу рецепт и иду по нему по шагам.
Рецепта нет — делаю по правилам выше, а после задачи дописываю новый рецепт по шаблону навыка.
Готовый текст (пост, сценарий, письмо, ответ) — всегда целиком в ответе владельцу, а не только в файле.

## Скорость
Большие файлы целиком не читаю — ищу по словам задачи (grep) и открываю 1–3 нужных.
Вопрос — до 5 действий и около минуты; застрял — коротко пишу владельцу, где именно.
Что может сделать только владелец (оплаты, входы, кнопки на сайтах) — сразу так и говорю, без поиска обходных путей.

## Я работаю на GPT (движок Hermes)
Раньше я работал на Claude Code, теперь на Hermes. Мой характер — этот файл; навыки — папки из
skills.external_dirs; подключения — mcp_servers в config.yaml. Команды Claude Code
(/login, claude, tmux-окна агента) ко мне не относятся. Перезапуск себя — hermes gateway restart.

## Спросить другого агента = передать и ждать
- Просьба «спроси у <агента>» = один вызов передачи задачи этому агенту, затем владельцу одна строка: «Спросил, пришлю, как ответит». На этом ход заканчиваю.
- Ответ другого агента приходит ТОЛЬКО отдельным входящим сообщением от него. Я никогда не пишу ответ за другого агента и не сочиняю его цифры. Нет ответа — нет цифр.

## Заметки — коротко и по местам
- Файл с цифрами и фактами (например materials/point-a.md) — только цифры и факты. Разборы, аудиты, выводы — отдельным файлом в долгой памяти и строкой в её оглавлении.
- Ошибочные данные не держу рядом с верными: переношу в отдельный файл-архив с пометкой «не использовать».

## Цифры владельца — сразу в файл
- Любую цифру или факт о бизнесе из сообщения владельца (продажи, число клиентов, участников, цены, сроки) записываю в файл с цифрами в том же ходе, даже если это первое сообщение и вопрос был о другом.

## Длина ответа владельцу
- Сообщение владельцу — не длиннее одного экрана телефона (примерно 25 строк): решение, 2–3 главных довода, ближайшие шаги.
- Большой разбор, план или анализ сохраняю файлом в долгую память, а в чат присылаю короткий итог и одну строку, где лежит полный разбор.
- Длинный текст целиком — только если владелец сам попросил готовый длинный текст (пост, письмо, сценарий).

## Остатки от Claude — не про меня
Если в правилах, памяти или навыках встречается то, что относится к Claude Code (правило «отвечать только через reply», CLAUDE.md, окна tmux, /login, окна с вопросом о разрешении), — это от агента на Claude. Я работаю на Hermes: мой ответ сам уходит в Telegram, мой характер — этот файл.
"""


def _index_of(d):
    """MEMORY.md if the folder has one; otherwise a built index — one line per note with its
    description (front matter) or first heading/line (course agents keep core/memory/ without an index)."""
    idx = os.path.join(d, "MEMORY.md")
    if os.path.isfile(idx):
        return open(idx, encoding="utf-8").read().strip()
    lines = []
    for f in sorted(glob.glob(os.path.join(d, "*.md"))):
        text = open(f, encoding="utf-8", errors="ignore").read()
        m = re.search(r"^description:\s*(.+)$", text, re.M) or re.search(r"^#+\s*(.+)$", text, re.M) \
            or re.search(r"^(?!---)(\S.*)$", text, re.M)
        lines.append(f"- {os.path.basename(f)} — {(m.group(1).strip().strip(chr(34)) if m else '')[:160]}")
    return "\n".join(lines)


def memory_block(memory_dirs):
    parts = []
    for d in memory_dirs:
        index = _index_of(d)
        parts.append(f"Подробности — в файле с этим именем в {d}/\n\n{index}")
    body = "\n\n".join(parts)
    return (f"{MEM_BEGIN}\n## Моя долгая память — оглавление (перед задачей читаю нужные файлы)\n"
            f"Каждая строка — правило или факт. Новое правило или решение — сразу новым файлом там же.\n\n"
            f"{body}\n{MEM_END}")


def find_memory_dirs(agent_dir, home):
    """Claude Code keeps memory per working dir; the agent runs from its dir or its plugin dir."""
    enc = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(agent_dir))
    found = []
    for d in sorted(glob.glob(os.path.join(home, ".claude/projects", enc + "*", "memory"))):
        rest = os.path.basename(os.path.dirname(d))[len(enc):]
        if rest not in ("", "-dashi-plugin-claude-code-plugin"):
            continue  # helper sessions (outbox, digests) are not the agent's memory
        if os.path.isfile(os.path.join(d, "MEMORY.md")) or glob.glob(os.path.join(d, "*.md")):
            found.append(d)
    core = os.path.join(os.path.abspath(agent_dir), "core/memory")  # course layout (CLAUDE.md: «core/memory/»)
    if glob.glob(os.path.join(core, "*.md")):
        found.append(core)
    return found


FACT_NAME = re.compile(r"price|цен|product|продукт|point-a|offer|оффер|тариф", re.I)
SKIP_DIRS = {"node_modules", ".git", "dashi-plugin-claude-code", ".claude", "backups", "secrets", "__pycache__"}


def find_fact_files(agent_dir, home):
    """Files the GPT agent must see on every message (Vika 10.11.2026, blind test round 4):
    team board (last 40 lines), the owner's reminders, small price/product files, the error base index."""
    found = []
    boards = [os.path.join(home, "second-brain/team-tasks.md")]
    for root, dirs, files in os.walk(agent_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if root[len(agent_dir):].count(os.sep) >= 3:
            dirs[:] = []
        for f in sorted(files):
            path = os.path.join(root, f)
            if f == "team-tasks.md":
                boards.append(path)
            elif f.endswith(".tsv") and "remind" in f:
                found.append(path)
            elif f.endswith(".md") and FACT_NAME.search(f) and os.path.getsize(path) <= 12000:
                found.append(path)
    # Students' techspecs name the shared folder themselves (Britenkova 15.11: ~/ai-shared-brain/tasks.md):
    # take the board the agent's own rules point to, then any *brain* folder in the home dir.
    rules = ""
    for name in ("CLAUDE.md", "rules.md", "core/rules.md"):
        path = os.path.join(agent_dir, name)
        if os.path.isfile(path):
            rules += open(path, encoding="utf-8", errors="ignore").read()
    boards += [p for p in re.findall(r"(/[\w./-]*tasks\.md)", rules) if "/sent-" not in p]
    shared = [d for d in sorted(glob.glob(os.path.join(home, "*brain*"))) if os.path.isdir(d)]
    boards += [os.path.join(d, n) for d in shared for n in ("team-tasks.md", "tasks.md")]
    board = next((b for b in boards if os.path.isfile(b)), None)
    if board:
        found.insert(0, board + "|tail=40")
        shared.insert(0, os.path.dirname(board))
    for d in dict.fromkeys(shared):  # shared facts and calendar sit next to the board
        for n in ("facts.md", "calendar.md"):
            path = os.path.join(d, n)
            if os.path.isfile(path) and os.path.getsize(path) <= 12000 and path not in found:
                found.append(path)
    for idx in sorted(glob.glob(os.path.join(home, "*/course-errors/INDEX.md"))) + [os.path.join(agent_dir, "course-errors/INDEX.md")]:
        if os.path.isfile(idx) and idx not in found:
            found.append(idx)
            break
    return found


def owner_tz(agent_dir, memory_dirs=()):
    """Owner's UTC offset for «today» in the facts: +7 for Thailand, else Moscow. The memory index
    counts too: a move abroad is usually remembered, not written into CLAUDE.md (15.11)."""
    text = ""
    paths = [os.path.join(agent_dir, n) for n in ("CLAUDE.md", "USER.md")]
    paths += [os.path.join(d, "MEMORY.md") for d in memory_dirs]
    for path in paths:
        if os.path.isfile(path):
            text += open(path, encoding="utf-8", errors="ignore").read()
    return 7 if re.search(r"UTC\+7|Asia/Bangkok|Таиланд|Пхукет", text) else 3


def read_env(path):
    env = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)=(.*)", line)
            if m:
                env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


def allowed_ids(agent_dir, env):
    cfg = os.path.join(agent_dir, "dashi-plugin-claude-code/plugin/state/telegram/config.json")
    if os.path.isfile(cfg):  # the live allowlist; TELEGRAM_ALLOWED_* in channel.env is dead
        ids = json.load(open(cfg)).get("allowed_chat_ids") or []
        if ids:
            return [str(i) for i in ids]
    raw = env.get("TELEGRAM_ALLOWED_USER_IDS") or env.get("TELEGRAM_ALLOWED_CHAT_IDS") or ""
    return [i for i in re.split(r"[,\s]+", raw) if i.isdigit()]


CLAUDE_ONLY = re.compile(r"dashi-channel|вызовом reply|Do you want to allow|Ход не считается завершённым|"
                         r"Мой обычный текст|Модель:\s*Claude|вызов\w* `?reply`?")


KANBAN_HANDOFF = """Агенты на GPT (Hermes) живут без комнат tmux. Задачу другому агенту ставлю на общую доску задач Hermes:

```bash
hermes kanban create "ЗАДАЧА ОТ <моё имя>: что сделать" --assignee <профиль агента> --body "подробности, где лежат файлы, кому отчитаться"
```

Имена профилей агентов — `hermes profile list`. Ход задачи — `hermes kanban show <id>`.
Кто поставил — пишу обязательно, иначе получивший не поймёт, кому отчитываться."""

HANDOFF_HEAD = re.compile(r"^(#+)\s.*передать задачу другому агенту", re.I)
ROOM_LINE = re.compile(r"tmux|send-keys|комнат|двумя командами подряд|сначала текст, потом Enter", re.I)


def replace_handoff(text):
    """09.11: the course teaches handoffs via tmux rooms; Hermes agents have none, so the copied
    rule silently breaks marketer→techspec handoffs. Swap the room mechanics for the Hermes kanban."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        m = HANDOFF_HEAD.match(lines[i])
        if not m:
            out.append(lines[i]); i += 1; continue
        level = len(m.group(1))
        out += [lines[i], "", KANBAN_HANDOFF]
        i += 1
        body = []
        while i < len(lines) and not re.match(r"^#{1,%d}\s" % level, lines[i]):
            body.append(lines[i]); i += 1
        blocks, cur, fence = [], [], False
        for l in body:  # drop fenced blocks that are about tmux, then room lines
            if l.strip().startswith("```"):
                cur.append(l)
                if fence:
                    if not any(ROOM_LINE.search(x) for x in cur):
                        blocks += cur
                    cur = []
                fence = not fence
                continue
            if fence:
                cur.append(l)
            elif not ROOM_LINE.search(l) and not re.match(r"^- .*— комната", l):
                blocks.append(l)
        out += [""] + [l for l in blocks if l.strip() or (out and out[-1].strip())]
    return "\n".join(out)


REMINDERS_HEAD = re.compile(r"^(#+)\s.*Напоминания", re.I)
REMINDERS_HERMES = """У меня нет будильника-скрипта: напоминания ставлю встроенным расписанием Hermes, оно само пишет владельцу в Telegram.
Время — всегда по часовому поясу владельца: {tz}.

Поставить (пример — 26 августа в 9:00, один раз):

```bash
hermes cron create "0 9 26 8 *" "Напомни владельцу своими словами: про вебинар" --repeat 1 --timezone {tz} --deliver telegram --name "напоминание: вебинар"
```

Сразу после этого подтверждаю владельцу, на какое число и время поставила. Посмотреть очередь — `hermes cron list`, отменить — `hermes cron remove <id>`."""


def replace_reminders(text, owner_zone=None):
    """09.11: the course alarm clock (remind-add.sh + tick) wakes the agent via its tmux room; on Hermes
    that never fires. Swap the section for Hermes' own cron, keeping the owner's time zone."""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        m = REMINDERS_HEAD.match(l)
        if not m:
            continue
        level = len(m.group(1))
        j = i + 1
        while j < len(lines) and not re.match(r"^#{1,%d}\s" % level, lines[j]):
            j += 1
        body = "\n".join(lines[i + 1:j])
        if "remind" not in body and "БУДИЛЬНИК" not in body:
            return text
        tz = re.search(r"\b([A-Z][a-z]+/[A-Za-z_]+)\b", body)
        tz = owner_zone or (tz.group(1) if tz else "Europe/Moscow")
        return "\n".join(lines[:i + 1] + ["", REMINDERS_HERMES.format(tz=tz), ""] + lines[j:])
    return text


def strip_claude_only(text, owner_zone=None):
    """Lines that only make sense inside Claude Code; GPT takes them literally (30.10, 05.11)."""
    out = []
    for line in replace_handoff(replace_reminders(text, owner_zone)).splitlines():
        if CLAUDE_ONLY.search(line) or re.match(r"\s*tmux send-keys -t \S+ Enter\s*$", line) or line.strip() == "sleep 1":
            continue
        line = re.sub(r'tmux send-keys -t (\S+) -l (".*")', r"hermes kanban create \2 --assignee <профиль \1>", line)
        line = re.sub(r"через (инструмент )?`?reply`?", "в Telegram", line)
        if owner_zone:  # the remembered zone beats a stale «Europe/Moscow» in the rules
            line = line.replace("Europe/Moscow", owner_zone)
        out.append(line)
    return "\n".join(out)


def build_soul(agent_dir, memory_dirs):
    parts = []
    zone = "Asia/Bangkok" if owner_tz(agent_dir, memory_dirs) == 7 else None
    for name in ("CLAUDE.md", "USER.md", "core/USER.md", "rules.md"):  # course starter keeps USER.md in core/
        p = os.path.join(agent_dir, name)
        if os.path.isfile(p):
            parts.append(strip_claude_only(open(p, encoding="utf-8").read().strip(), zone))
    if not parts:
        sys.exit(f"ОШИБКА: в {agent_dir} нет CLAUDE.md — это не папка агента")
    # 15.11: the Hermes gateway runs from the home dir, not the agent dir — anchor CLAUDE.md's relative paths.
    parts.append(f"## Моя папка\nМоя рабочая папка — {os.path.abspath(agent_dir)}. Пути из этого файла без «/» в начале "
                 f"(core/…, materials/…, memory/…) считаю от неё: открываю {os.path.abspath(agent_dir)}/core/… и т. д.")
    parts.append(GPT_RULES.strip())
    if memory_dirs:
        parts.append(memory_block(memory_dirs))
    return "\n\n".join(parts) + "\n"


BRIDGE_MCP = re.compile(r"dashi|telegram", re.I)  # Hermes talks to Telegram itself


def find_mcp(agent_dir, home):
    """MCP connections the Claude agent had (15.11): project .mcp.json, then ~/.claude.json user and
    project scopes. Converted to Hermes mcp_servers (stdio: command/args/env; http: url/headers)."""
    sources = []
    for path in (os.path.join(agent_dir, ".mcp.json"), os.path.join(home, ".claude.json")):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sources.append(data.get("mcpServers") or {})
        projects = data.get("projects") or {}
        for d in (agent_dir, os.path.join(agent_dir, "dashi-plugin-claude-code/plugin")):
            sources.append((projects.get(os.path.abspath(d)) or {}).get("mcpServers") or {})
    out = {}
    for servers in sources:
        for name, srv in servers.items():
            if name in out or BRIDGE_MCP.search(name) or not isinstance(srv, dict):
                continue
            if srv.get("url"):
                conv = {"url": srv["url"]}
                if srv.get("headers"):
                    conv["headers"] = srv["headers"]
            elif srv.get("command"):
                conv = {k: srv[k] for k in ("command", "args", "env") if srv.get(k)}
            else:
                continue
            out[name] = conv
    return dict(sorted(out.items()))


def agent_rooms(agent_dir):
    """tmux room names of the Claude agent in this folder: from its systemd unit (WorkingDirectory)."""
    agent = os.path.realpath(agent_dir)
    rooms = set()
    for uf in glob.glob(os.path.join(os.environ.get("C2G_UNIT_DIR", "/etc/systemd/system"), "*.service")):
        try:
            text = open(uf, encoding="utf-8", errors="ignore").read()
        except OSError:  # dangling symlinks are normal in /etc/systemd/system (Lunev 15.11)
            continue
        wd = re.search(r"^WorkingDirectory=(\S+)", text, re.M)
        if wd and os.path.realpath(wd.group(1)) == agent:
            rooms.update(re.findall(r"new-session -d -s (\S+)", text))
        # the course watchdog lists rooms too: [agent-marketing]="/root/ai-marketing"
        for wd in re.findall(r"^ExecStart=.*?(/\S*watchdog\S*\.sh)", text, re.M):
            if os.path.isfile(wd):
                for room, path in re.findall(r'^\s*\[([^\]]+)\]="([^"]+)"', open(wd, encoding="utf-8", errors="ignore").read(), re.M):
                    if os.path.realpath(path) == agent and not room.endswith(".service"):
                        rooms.add(room)
    return rooms


SEND_TEXT = r"send-keys\s+-t\s+[\"']?=?{room}:?[\"']?\s+(?:-l\s+)?(?:\"([^\"]+)\"|'([^']+)')"


def find_schedules(agent_dir):
    """Cron wake-ups that type a task into this agent's tmux room (team routine lesson, 15.11).
    On Hermes there is no room — each one must become a `hermes cron` job, or it silently stops."""
    rooms = agent_rooms(agent_dir)
    if not rooms:
        return []
    src = os.environ.get("C2G_CRONTAB")
    lines = open(src, encoding="utf-8").read() if src else subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True).stdout
    found = []
    for line in lines.splitlines():
        parts = line.split(None, 5)
        if line.lstrip().startswith("#") or len(parts) < 6:
            continue
        sched, cmd = " ".join(parts[:5]), parts[5]
        body = cmd
        script = re.match(r"(?:bash\s+|sh\s+)?(/\S+\.sh)\b", cmd)
        if script and os.path.isfile(script.group(1)):
            body += "\n" + open(script.group(1), encoding="utf-8", errors="ignore").read()
        for room in rooms:
            for m in re.finditer(SEND_TEXT.format(room=re.escape(room)), body):
                found.append((sched, m.group(1) or m.group(2)))
    return found


def server_tz():
    try:
        return open("/etc/timezone", encoding="utf-8").read().strip() or "UTC"
    except OSError:
        real = os.path.realpath("/etc/localtime")
        return real.split("zoneinfo/", 1)[1] if "zoneinfo/" in real else "UTC"


def create_schedules(profile, pdir, schedules, tz, run=subprocess.run):
    """Each Claude wake-up becomes a Hermes cron job with the same time and task text (server's zone:
    the old crontab ran on server time). Named, so a re-run of the converter does not duplicate them."""
    try:
        jobs = json.load(open(os.path.join(pdir, "cron/jobs.json"), encoding="utf-8"))
        jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
        have = {j.get("name") for j in jobs if isinstance(j, dict)}
    except (OSError, ValueError):
        have = set()
    made = 0
    for sched, text in schedules:
        name = f"с Claude: {sched} {text[:40]}"
        if name in have:
            continue
        run(["hermes", "-p", profile, "cron", "create", sched, text, "--name", name,
             "--deliver", "telegram", "--timezone", tz], capture_output=True, text=True)
        made += 1
    return made


def skill_dirs(agent_dir, home):
    cands = [os.path.join(agent_dir, ".claude/skills"), os.path.join(home, ".claude/skills")]
    return [d for d in cands if os.path.isdir(d)]


def plan(agent_dir, profile, home):
    env = read_env(os.path.join(agent_dir, "secrets/channel.env"))
    mem = find_memory_dirs(agent_dir, home)
    return {
        "agent_dir": agent_dir,
        "profile_dir": os.path.join(home, ".hermes/profiles", profile),
        "soul": build_soul(agent_dir, mem),
        "memory_dirs": mem,
        "facts": find_fact_files(agent_dir, home),
        "tz": owner_tz(agent_dir, mem),
        "token": env.get("TELEGRAM_BOT_TOKEN", ""),
        "allowed": allowed_ids(agent_dir, env),
        "groq": env.get("GROQ_API_KEY", ""),
        "skills": skill_dirs(agent_dir, home),
        "mcp": find_mcp(agent_dir, home),
        "schedules": find_schedules(agent_dir),
    }


def apply(p, profile, home):
    pdir = p["profile_dir"]
    if not os.path.isdir(pdir):
        subprocess.run(["hermes", "profile", "create", profile, "--clone"], check=True)
    soul = os.path.join(pdir, "SOUL.md")
    if os.path.isfile(soul):
        first = soul + ".bak-before-claude-to-gpt"
        # Re-run (new rules): keep the very first pre-GPT backup, save the current GPT SOUL beside it.
        os.replace(soul, first if not os.path.exists(first) else soul + time.strftime(".bak-rerun-%Y%m%d-%H%M%S"))
    with open(soul, "w", encoding="utf-8") as f:
        f.write(p["soul"])

    env_path = os.path.join(pdir, ".env")
    lines = [l for l in (open(env_path, encoding="utf-8").read().splitlines() if os.path.isfile(env_path) else [])
             if not re.match(r"(TELEGRAM_BOT_TOKEN|TELEGRAM_ALLOWED_USERS|TELEGRAM_HOME_CHANNEL|GROQ_API_KEY)=", l)]
    lines.append(f"TELEGRAM_BOT_TOKEN={p['token']}")
    lines.append(f"TELEGRAM_ALLOWED_USERS={','.join(p['allowed'])}")
    if p["allowed"]:
        lines.append(f"TELEGRAM_HOME_CHANNEL={p['allowed'][0]}")
    if p["groq"]:
        lines.append(f"GROQ_API_KEY={p['groq']}")
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    cfg_path = os.path.join(pdir, "config.yaml")
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8")) if os.path.isfile(cfg_path) else {}
    cfg = cfg or {}
    cfg.setdefault("model", {}).update(provider="openai-codex", default="gpt-5.6-sol")
    cfg.setdefault("agent", {}).update(reasoning_effort=effort_for(p["agent_dir"], profile), max_turns=150)
    cfg.setdefault("compression", {}).update(threshold=0.1, threshold_tokens=100000)  # cap: Hermes floors the % at 75 on <512K windows
    sk = cfg.setdefault("skills", {})
    sk["creation_nudge_interval"] = 15
    sk["external_dirs"] = sorted(set((sk.get("external_dirs") or []) + p["skills"]))
    cfg.setdefault("memory", {}).update(memory_char_limit=8000, user_char_limit=4000)
    if p["mcp"]:  # keep what the owner already set up in Hermes, add the Claude agent's connections
        cfg["mcp_servers"] = {**p["mcp"], **(cfg.get("mcp_servers") or {})}
    stt = cfg.setdefault("stt", {})
    stt["language"] = "ru"
    if p["groq"]:  # voice messages go through the same Groq Whisper key the Claude agent used
        stt.update(enabled=True, provider="groq")
    # Как у команды Виктории: тихий режим, самообновление разговора, защита от самоудаления.
    disp = cfg.setdefault("display", {})
    disp.update(memory_notifications="off", file_mutation_verifier=False, turn_completion_explainer=False,
                credits_notices=False, busy_ack_enabled=False, interim_assistant_messages=False,
                long_running_notifications=False, show_commentary=False,
                busy_input_mode="steer", busy_steer_ack_enabled=False)  # mid-task message no longer kills the work
    cfg.setdefault("telegram", {})["gateway_restart_notification"] = False
    cfg["session_reset"] = {"mode": "both", "at_hour": 4, "idle_minutes": 240, "notify": False}
    hooks = cfg.get("hooks") or {}
    hook = install_protect_hook(home)
    if hook and not hooks.get("pre_tool_call"):
        hooks["pre_tool_call"] = [{"matcher": "terminal|execute_code", "command": hook, "timeout": 10}]
    gate = install_verify_gate(home)
    if gate:  # 05.11: no «готово» about changed files until the agent has re-opened them
        hooks["pre_verify"] = [{"command": gate, "timeout": 10}]
    if hooks:
        cfg["hooks"] = hooks
        cfg["hooks_auto_accept"] = True
    # facts-inject (10.11): date, board, reminders, prices, error base on every message — GPT skips checking
    for plugin in ("media-check", "busy-ack-ru", "facts-inject"):  # look at built media; Russian «Принял» while busy
        if install_plugin(pdir, plugin):
            if plugin == "facts-inject":
                with open(os.path.join(pdir, "plugins", plugin, "facts.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join([f"tz={p['tz']}"] + p["facts"]) + "\n")
            pl = cfg.setdefault("plugins", {})
            pl["enabled"] = sorted(set((pl.get("enabled") or []) + [plugin]))
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    hist = os.path.join(pdir, "skills/recipes/task-recipes/claude-history.md")
    p["history_tasks"] = export_claude_history(p["agent_dir"], home, hist)
    install_recipes_skill(pdir, p["agent_dir"], p["memory_dirs"], hist)
    # 11.11: new Hermes ignores session_reset unless this plugin is on (nightly/idle resets keep
    # the conversation small — without them it grows and slows down).
    if hermes_source_has(home, "is no longer applied"):
        name = "hermes-session-reset-policy"
        if not os.path.isdir(os.path.join(pdir, "plugins", name)):
            subprocess.run(["hermes", "-p", profile, "plugins", "install", name], capture_output=True, text=True)
        subprocess.run(["hermes", "-p", profile, "plugins", "enable", name], capture_output=True, text=True)
        enabled = (yaml.safe_load(open(cfg_path, encoding="utf-8")) or {}).get("plugins", {}).get("enabled") or []
        if name not in enabled:
            print(f"  ВНИМАНИЕ: не поставился плагин {name} — разговор не будет обновляться сам ночью")


CHANNEL_MSG = re.compile(r"<channel\b[^>]*>(.*?)</channel>", re.S)
SECRET = re.compile(r"(?i)((?:token|key|secret|password|passwd|pass|api[_-]?key)[\"']?\s*[=:]\s*)[^\s\"'&]+"
                    r"|\b\d{8,10}:[A-Za-z0-9_-]{30,}\b|\b(?:sk|gsk|ghp|xai|pk)[-_][A-Za-z0-9_-]{16,}")


def _redact(text):
    return SECRET.sub(lambda m: (m.group(1) or "") + "***", text)


def _text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")


def export_claude_history(agent_dir, home, out_path, max_tasks=150, max_bytes=250000):
    """15.11 (Vika): the real work of the Claude agent, as the source for fresh recipes — what the owner
    asked, which files/commands/skills Claude used, what it answered, and the owner's next word (accepted
    or corrected). Newest first, secrets redacted. Returns the number of owner messages exported."""
    enc = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(agent_dir))
    files = []
    for d in glob.glob(os.path.join(home, ".claude/projects", enc + "*")):
        rest = os.path.basename(d)[len(enc):]
        if rest in ("", "-dashi-plugin-claude-code-plugin"):
            files += glob.glob(os.path.join(d, "*.jsonl"))
    episodes = []
    for path in files:
        cur = None
        for line in open(path, encoding="utf-8", errors="ignore"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message") or {}
            if d.get("type") == "user":
                raw = _text_of(msg.get("content", ""))
                asks = [re.sub(r"<[^>]+>", "", x).strip() for x in CHANNEL_MSG.findall(raw)]
                asks = [x for x in asks if x]
                who = "Владелец"
                if not asks:  # a scheduled task or a hand-off from another agent, typed into the room
                    plain = re.sub(r"<system-reminder>.*?</system-reminder>", "", raw, flags=re.S).strip()
                    helper = ("<", "Caveat", "[Request interrupted", "Below is a conversation log",
                              "Private connection test", "This session is being continued")
                    if len(plain) >= 25 and not plain.startswith(helper):
                        asks, who = [plain], "Задача (расписание или другой агент)"
                if asks:
                    cur = {"ts": d.get("timestamp", ""), "who": who, "ask": "\n".join(asks), "did": [], "said": []}
                    episodes.append(cur)
            elif d.get("type") == "assistant" and cur is not None:
                for c in msg.get("content") or []:
                    if not isinstance(c, dict) or c.get("type") != "tool_use":
                        continue
                    name, inp = c.get("name", ""), c.get("input") or {}
                    if name.endswith("reply") and inp.get("text"):
                        cur["said"].append(inp["text"])
                    elif name == "Bash":
                        cur["did"].append("$ " + str(inp.get("command", ""))[:400])
                    elif name in ("Read", "Edit", "Write"):
                        cur["did"].append(f"{name} {inp.get('file_path', '')}")
                    elif name == "Skill":
                        cur["did"].append(f"навык {inp.get('skill', '')}")
                    elif name.startswith("mcp__"):
                        cur["did"].append("подключение " + name.split("__", 2)[-1])
    episodes.sort(key=lambda e: e["ts"], reverse=True)
    # the same scheduled task repeats every day — one (the newest) example is enough;
    # the owner's own requests go first, then one example of each recurring task
    seen, owner, other = set(), [], []
    for e in episodes:
        key = re.sub(r"\s+", " ", e["ask"])[:120]
        if e["who"] != "Владелец":
            if key in seen:
                continue
            seen.add(key)
        (owner if e["who"] == "Владелец" else other).append(e)
    episodes = sorted(owner[:max_tasks] + other[:max(30, max_tasks - len(owner))], key=lambda e: e["ts"], reverse=True)
    out, size = ["# Реальная работа агента на Claude (новые сверху)\n",
                 "Каждая запись: что попросил владелец → что агент сделал (файлы, команды) → что ответил. "
                 "Следующая (более новая) запись выше — реакция владельца: приняла или поправила.\n"], 0
    count = 0
    for e in episodes[:max_tasks]:
        block = [f"\n## {e['ts'][:16].replace('T', ' ')}", f"{e['who']}: " + re.sub(r"(?m)^#+ ", "", e["ask"][:1200])]
        did = [x.split("\n")[0][:200] for x in dict.fromkeys(e["did"]) if x.strip()]
        if did:
            block.append("Сделал:\n" + "\n".join("- " + x for x in did[:10]) + (f"\n- …и ещё {len(did) - 10}" if len(did) > 10 else ""))
        if e["said"]:
            block.append("Ответил:\n" + e["said"][-1][:1500])
        text = _redact("\n".join(block)) + "\n"
        if size + len(text.encode("utf-8")) > max_bytes:
            break
        out.append(text); size += len(text.encode("utf-8")); count += 1
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return count


def recipes_ok(pdir):
    """Number of complete recipes (a heading with «Шаги:») in the profile's RECIPES.md; 0 = not built."""
    for p in glob.glob(os.path.join(pdir, "skills/recipes/task-recipes/**/RECIPES.md"), recursive=True):
        text = open(p, encoding="utf-8", errors="ignore").read()
        parts = re.split(r"^## ", text, flags=re.M)[1:]
        # a recipe = a «## » section with steps: the «Шаги:» label or a numbered list (GPT varies the labels)
        return sum(1 for x in parts if "Шаги" in x or re.search(r"(?m)^\s*1[.)]\s", x))
    return 0


BUILD_RECIPES = ("Собери RECIPES.md по навыку task-recipes заново: главный источник — claude-history.md рядом с навыком "
                 "(реальная работа этого агента на Claude). Ничего владельцу не отправляй и ничего не публикуй. "
                 "В конце одной строкой: сколько рецептов собрано.")


def recipes_needed(history_path):
    """How many recipes a real agent should have (15.11, Vika: «меньше трёх» was a blind number):
    one per ~15 tasks in its Claude history, at least 3, at most 15. 150 tasks → 10."""
    try:
        text = open(history_path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return 3
    tasks = len(re.findall(r"^(?:Владелец|Задача \(расписание или другой агент\)): ", text, re.M))
    return max(3, min(15, -(-tasks // 15)))


def build_recipes(profile, pdir, run=subprocess.run):
    """15.11 (Vika): fresh recipes are part of the move, not a manual step after it. Rebuilt whenever the
    Claude history changed since the last build; the previous RECIPES.md is kept as a backup."""
    d = os.path.join(pdir, "skills/recipes/task-recipes")
    hist = os.path.join(d, "claude-history.md")
    digest = hashlib.sha256(open(hist, "rb").read()).hexdigest() if os.path.isfile(hist) else ""
    mark = os.path.join(d, ".history-sha256")
    need = recipes_needed(hist)
    if digest and os.path.isfile(mark) and open(mark).read().strip() == digest and recipes_ok(pdir) >= need:
        return recipes_ok(pdir), False
    for old in glob.glob(os.path.join(d, "**/RECIPES.md"), recursive=True):
        os.replace(old, old + time.strftime(".bak-%Y%m%d-%H%M%S"))
    r = run(["hermes", "-p", profile, "-z", BUILD_RECIPES], capture_output=True, text=True, timeout=3000)
    out = ((getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")) if r else ""
    if re.search(r"quota exhausted|\b429\b|usage limit", out, re.I):
        print("  ВНИМАНИЕ: кончился лимит ChatGPT — рецепты не собраны. " + (re.search(r"retry after \d+s", out) or [""])[0])
    n = recipes_ok(pdir)
    if n >= need and digest:
        with open(mark, "w") as f:
            f.write(digest + "\n")
    return n, True


RECIPES_SKILL = """---
name: task-recipes
description: Рецепты всех типовых задач этого агента — открывать перед любой задачей; если RECIPES.md ещё нет, сначала собрать его
---
# Рецепты задач

Зачем: GPT выполняет инструкции буквально и не додумывает то, что Claude понимал между строк.
Поэтому каждая типовая задача расписана явно в файле RECIPES.md рядом с этим файлом.

## Перед задачей
Открой RECIPES.md, найди рецепт по словам владельца и иди по нему по шагам. Рецепта нет — сделай задачу,
а потом допиши рецепт по шаблону ниже.

## Если RECIPES.md ещё нет — собери его (переносчик запускает это сам при переносе)
ГЛАВНЫЙ источник — {history}: реальная работа этого агента на Claude. Что владелец просил, какие файлы,
скрипты и команды агент использовал, что ответил и что владелец сказал следом (принял или поправил).
Остальные источники (только читать): {sources}
1. Пройди историю целиком и сгруппируй похожие просьбы в типовые задачи (всё, что владелец просил 2+ раза,
   и всё, где есть свой скрипт или файл). Читай все файлы памяти, не только оглавление.
2. Для каждой задачи напиши рецепт строго по шаблону. Шаги — те же команды, скрипты и пути, что в истории
   (новых не выдумывать). «Пример хорошего результата» — дословно ответ, который владелец принял.
   «Частые ошибки» — то, что владелец поправлял (ответ → его следующее сообщение с правкой).

## <Название задачи>
Когда применять: какими словами владелец обычно ставит эту задачу.
Результат: что именно сдать (формат, длина, структура, куда положить файл) — и что готовый текст целиком идёт в ответ.
Данные: откуда брать факты — точные пути к файлам; чего нет в данных — не выдумывать.
Шаги: 1, 2, 3… — конкретные действия по порядку.
Хорошо, когда: 4–8 проверяемых признаков (длина, обязательные элементы, запретные слова, стиль владельца).
Пример хорошего результата: дословно одобренный владельцем текст из источников с указанием файла. Нет — так и написать, не сочинять.
Частые ошибки: что владелец уже правил (из памяти).
Проверка перед сдачей: что перечитать и сверить.

3. Сохрани всё одним файлом RECIPES.md рядом с этим SKILL.md. Ничего в источниках не меняй.
"""


def install_recipes_skill(pdir, agent_dir, memory_dirs, history=None):
    """09.11: GPT is critically literal (Сухов); per-task recipes fixed form on the comparison test.
    15.11: built from the agent's real Claude history (export_claude_history), not from memory alone."""
    d = os.path.join(pdir, "skills/recipes/task-recipes")
    os.makedirs(d, exist_ok=True)
    sources = ", ".join([os.path.abspath(agent_dir)] + list(memory_dirs))
    history = history or os.path.join(d, "claude-history.md")
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(RECIPES_SKILL.format(sources=sources, history=history))


PROTECT_URL = "https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/protect-home.py"


def install_protect_hook(home):
    """Put the self-deletion guard into ~/.hermes/hooks (once). Returns its path or '' if unavailable."""
    path = os.path.join(home, ".hermes", "hooks", "protect-home.py")
    if not os.path.isfile(path):
        src = os.environ.get("PROTECT_SRC")
        try:
            data = open(src, "rb").read() if src else urllib.request.urlopen(PROTECT_URL, timeout=20).read()
        except Exception as e:  # no network — the rest of the move still works
            print(f"  ВНИМАНИЕ: защиту от самоудаления не скачала ({e}); поставь позже hermes-protect/setup.sh")
            return ""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, 0o755)
    return path


GATE_URL = "https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/verify-gate.py"


def install_verify_gate(home):
    """Put the «check before готово» gate into ~/.hermes/hooks. Source: the copy next to this
    script (scp both), else the skills repo. Returns its path or '' if unavailable."""
    path = os.path.join(home, ".hermes", "hooks", "verify-gate.py")
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpt-verify-gate.py")
    try:
        data = open(local, "rb").read() if os.path.isfile(local) else urllib.request.urlopen(GATE_URL, timeout=20).read()
    except Exception as e:
        print(f"  ВНИМАНИЕ: проверку перед «готово» не поставила ({e}); положи gpt-verify-gate.py рядом и запусти снова")
        return ""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    os.chmod(path, 0o755)
    return path


PLUGIN_URL = "https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/hermes-protect/"
TECH = re.compile(r"tech|spec|coder|dev|market|техспец|кодер|маркет", re.I)  # deep thinking: tech + marketer (Vika 05.11)


def effort_for(agent_dir, profile):
    """Deep thinking for the tech agent and the marketer; others answer faster on medium (Vika 05.11)."""
    return "high" if TECH.search(os.path.basename(os.path.normpath(agent_dir)) + " " + profile) else "medium"


def install_plugin(pdir, name):
    """Put a Hermes plugin into the profile. Source: /root/coder/hermes/<name> next to this
    repo, else the skills repo. Returns True when installed."""
    dst = os.path.join(pdir, "plugins", name)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local = os.path.join(root, "hermes", name)
    if not os.path.isdir(local):  # skills repo layout: hermes-protect/<name> next to claude-to-gpt/
        local = os.path.join(root, "hermes-protect", name)
    os.makedirs(dst, exist_ok=True)
    try:
        for f in ("__init__.py", "plugin.yaml"):
            src = os.path.join(local, f)
            data = open(src, "rb").read() if os.path.isfile(src) else urllib.request.urlopen(f"{PLUGIN_URL}{name}/{f}", timeout=20).read()
            with open(os.path.join(dst, f), "wb") as out:
                out.write(data)
        return True
    except Exception as e:
        print(f"  ВНИМАНИЕ: плагин {name} не поставила ({e}); запусти позже hermes-protect/setup.sh")
        return False


def hermes_source_has(home, text):
    """Feature probe of the installed Hermes, read from its source (never by running the gateway).
    11.11.2026: v0.23 serves every profile from ONE host gateway (`--profile X gateway install`
    refuses) and dropped built-in session resets (now a plugin)."""
    roots = [os.environ.get("C2G_HERMES_SRC", ""), os.path.join(home, ".hermes/hermes-agent"), "/usr/local/lib/hermes-agent"]
    for r in filter(None, roots):
        for f in glob.glob(os.path.join(r, "hermes_cli", "*.py")) + glob.glob(os.path.join(r, "gateway", "*.py")):
            try:
                if text in open(f, encoding="utf-8", errors="ignore").read():
                    return True
            except OSError:
                pass
    return False


def host_gateway(home):
    return hermes_source_has(home, "does not get a gateway of its own")


def handover_to_watchdog(agent_dir, profile, home, who):
    """Hand the agent over to the server's agent watchdog (Vika 10.11.2026): its Claude entry
    leaves AGENTS, its Hermes service joins HERMES (check_hermes revives it and tells the owner;
    check_hermes_limit reports a spent ChatGPT limit). Only once the gateway service exists —
    before that the watchdog would alert about a service that is simply not installed yet."""
    units = os.path.join(home, ".config/systemd/user")
    unit = f"hermes-gateway-{profile}.service"
    if not os.path.isfile(os.path.join(units, unit)):
        # new Hermes: one host gateway serves every profile; the watchdog checks each profile's
        # ChatGPT limit through that one entry (check_hermes_limit scans the profiles)
        if host_gateway(home) and os.path.isfile(os.path.join(units, "hermes-gateway.service")):
            unit = "hermes-gateway.service"
        else:
            return "pending"
    unit_dir = os.environ.get("C2G_UNIT_DIR", "/etc/systemd/system")
    done = []
    for uf in sorted(glob.glob(os.path.join(unit_dir, "agent-watchdog*.service"))):
        m = re.search(r"^ExecStart=.*?(/\S*watchdog\S*\.sh)", open(uf, encoding="utf-8").read(), re.M)
        if not m or not os.path.isfile(m.group(1)):
            continue
        wd = m.group(1)
        s = open(wd, encoding="utf-8").read()
        new = s
        agent = os.path.realpath(agent_dir)

        def drop(mm):  # comment out this agent's Claude entry in AGENTS
            ind, name, path = mm.group(1), mm.group(2), mm.group(3)
            if os.path.realpath(path) != agent:
                return mm.group(0)
            return f'{ind}# [{name}]="{path}"  # на GPT: {unit}'
        new = re.sub(r'^(\s*)\[([^\]]+)\]="([^"]+)"', drop, new, flags=re.M)
        if f"[{unit}]" not in new:
            pdir = os.path.join(home, ".hermes/profiles", profile)
            for arr, val in (("HERMES", pdir), ("HERMES_WHO", who)):
                line = f'  [{unit}]="{val}"\n'
                if re.search(rf"^declare -A {arr}=\(\)", new, re.M):
                    new = re.sub(rf"^declare -A {arr}=\(\)", f"declare -A {arr}=(\n{line})", new, count=1, flags=re.M)
                elif re.search(rf"^declare -A {arr}=\(\n", new, re.M):
                    new = re.sub(rf"^(declare -A {arr}=\(\n)", rf"\g<1>{line}", new, count=1, flags=re.M)
        if new == s:
            done.append(wd); continue
        shutil.copy2(wd, wd + ".bak-claude-to-gpt")
        with open(wd, "w", encoding="utf-8") as f:
            f.write(new)
        if subprocess.run(["bash", "-n", wd]).returncode != 0:
            shutil.copy2(wd + ".bak-claude-to-gpt", wd)
            print(f"  ВНИМАНИЕ: сторож {wd} не удалось поправить — вернул как было")
            continue
        if not os.environ.get("C2G_NO_SYSTEMCTL"):
            dropin = uf + ".d/killmode.conf"
            if "KillMode=process" not in open(uf, encoding="utf-8").read() and not os.path.exists(dropin):
                os.makedirs(uf + ".d", exist_ok=True)
                with open(dropin, "w") as f:
                    f.write("[Service]\n# Перезапуск сторожа не должен выключать агентов\nKillMode=process\n")
                subprocess.run(["systemctl", "daemon-reload"])
            subprocess.run(["systemctl", "restart", os.path.basename(uf)])
        done.append(wd)
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_dir")
    ap.add_argument("profile")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--home", default=os.path.expanduser("~"))
    ap.add_argument("--no-recipes", action="store_true", help="не собирать рецепты (только для отладки)")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9]+", a.profile):
        sys.exit("ОШИБКА: имя профиля — только маленькие латинские буквы и цифры")
    p = plan(a.agent_dir, a.profile, a.home)

    problems = []
    if not p["token"]:
        problems.append("нет TELEGRAM_BOT_TOKEN в secrets/channel.env")
    if not p["allowed"]:
        problems.append("не нашёл, кому агент отвечает (allowlist пуст)")
    print(f"Агент: {a.agent_dir} → профиль Hermes «{a.profile}» ({p['profile_dir']})")
    print(f"  характер: {len(p['soul'])} символов; память: {', '.join(p['memory_dirs']) or 'НЕТ'}")
    print(f"  бот: {'есть' if p['token'] else 'НЕТ'}; отвечает: {', '.join(p['allowed']) or 'НИКОМУ'}; "
          f"голосовые (Groq): {'есть' if p['groq'] else 'нет'}")
    print(f"  навыки: {', '.join(p['skills']) or 'нет'}")
    print(f"  подключения (MCP): {', '.join(p['mcp']) or 'нет'}")
    print(f"  расписания (будили агента на Claude): {len(p['schedules']) or 'нет'}")
    for sched, text in p["schedules"]:
        print(f"    {sched} — {text[:70]}")
    print(f"  факты в каждое сообщение: {', '.join(os.path.basename(x.split('|')[0]) for x in p['facts']) or 'только дата'}")
    if problems:
        sys.exit("ОШИБКА: " + "; ".join(problems))
    if not a.apply:
        print("Пробный прогон: ничего не записано. Запуск с --apply запишет профиль.")
        return
    apply(p, a.profile, a.home)
    print(f"История работы на Claude: {p.get('history_tasks', 0)} просьб владельца → claude-history.md")
    if not a.no_recipes:
        print("Рецепты: собираю по истории работы (до 20–40 минут, это нормально)…", flush=True)
        n, rebuilt = build_recipes(a.profile, p["profile_dir"])
        need = recipes_needed(os.path.join(p["profile_dir"], "skills/recipes/task-recipes/claude-history.md"))
        if n >= need:
            print(f"  рецепты: {n} (нужно не меньше {need} по объёму работы; "
                  f"{'собраны заново' if rebuilt else 'история не менялась — оставил прежние'})")
        else:
            print(f"  ВНИМАНИЕ: рецептов {n}, а по объёму работы агента нужно не меньше {need}. Перенос НЕ готов: проверь вход в ChatGPT "
                  f"(hermes -p {a.profile} -z \"привет\") и запусти эту же команду с --apply ещё раз.")
    if p["schedules"]:
        made = create_schedules(a.profile, p["profile_dir"], p["schedules"], server_tz())
        print(f"Расписания: перенёс в Hermes {made} (уже были: {len(p['schedules']) - made}). Проверить: hermes -p {a.profile} cron list")
    wd = handover_to_watchdog(a.agent_dir, a.profile, a.home, a.profile)
    if wd == "pending":
        print("Сторож: агента передам ему после шага 3 — запусти эту же команду с --apply ещё раз, это безопасно.")
    elif wd:
        print(f"Сторож: агент на GPT теперь под его присмотром, агент на Claude из этой папки из сторожа убран ({', '.join(wd)}).")
    if host_gateway(a.home):
        step3 = ("hermes gateway install   # один общий запуск на все агенты на GPT; ответило «Use --force to reinstall» — "
                 "он уже стоит, тогда: hermes gateway restart")
    else:
        step3 = f"hermes --profile {a.profile} gateway install && hermes --profile {a.profile} gateway start"
    print(f"""Профиль записан. Переключение (по одному, бот один и тот же):
  1. hermes --profile {a.profile} auth add openai-codex --type oauth --no-browser   # вход в ChatGPT клиента
  2. остановить агента Claude этой папки (и убрать его из сторожа), иначе два движка дерутся за бота
  3. {step3}
  4. написать боту и убедиться, что ответил GPT
  5. рецепты задач уже собраны по реальной работе агента на Claude (см. выше); обновить — запустить эту же команду с --apply""")


if __name__ == "__main__":
    main()
