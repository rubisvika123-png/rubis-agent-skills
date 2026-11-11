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
import argparse, urllib.request, glob, json, os, re, shutil, subprocess, sys, time

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

## Остатки от Claude — не про меня
Если в правилах, памяти или навыках встречается то, что относится к Claude Code (правило «отвечать только через reply», CLAUDE.md, окна tmux, /login, окна с вопросом о разрешении), — это от агента на Claude. Я работаю на Hermes: мой ответ сам уходит в Telegram, мой характер — этот файл.
"""


def memory_block(memory_dirs):
    parts = []
    for d in memory_dirs:
        index = open(os.path.join(d, "MEMORY.md"), encoding="utf-8").read().strip()
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
        if os.path.isfile(os.path.join(d, "MEMORY.md")):
            found.append(d)
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
    board = next((b for b in boards if os.path.isfile(b)), None)
    if board:
        found.insert(0, board + "|tail=40")
    for idx in sorted(glob.glob(os.path.join(home, "*/course-errors/INDEX.md"))) + [os.path.join(agent_dir, "course-errors/INDEX.md")]:
        if os.path.isfile(idx) and idx not in found:
            found.append(idx)
            break
    return found


def owner_tz(agent_dir):
    """Owner's UTC offset for «today» in the facts: +7 for Thailand, else Moscow."""
    text = ""
    for name in ("CLAUDE.md", "USER.md"):
        path = os.path.join(agent_dir, name)
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


def replace_reminders(text):
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
        tz = tz.group(1) if tz else "Europe/Moscow"
        return "\n".join(lines[:i + 1] + ["", REMINDERS_HERMES.format(tz=tz), ""] + lines[j:])
    return text


def strip_claude_only(text):
    """Lines that only make sense inside Claude Code; GPT takes them literally (30.10, 05.11)."""
    out = []
    for line in replace_handoff(replace_reminders(text)).splitlines():
        if CLAUDE_ONLY.search(line) or re.match(r"\s*tmux send-keys -t \S+ Enter\s*$", line) or line.strip() == "sleep 1":
            continue
        line = re.sub(r'tmux send-keys -t (\S+) -l (".*")', r"hermes kanban create \2 --assignee <профиль \1>", line)
        line = re.sub(r"через (инструмент )?`?reply`?", "в Telegram", line)
        out.append(line)
    return "\n".join(out)


def build_soul(agent_dir, memory_dirs):
    parts = []
    for name in ("CLAUDE.md", "USER.md", "core/USER.md", "rules.md"):  # course starter keeps USER.md in core/
        p = os.path.join(agent_dir, name)
        if os.path.isfile(p):
            parts.append(strip_claude_only(open(p, encoding="utf-8").read().strip()))
    if not parts:
        sys.exit(f"ОШИБКА: в {agent_dir} нет CLAUDE.md — это не папка агента")
    parts.append(GPT_RULES.strip())
    if memory_dirs:
        parts.append(memory_block(memory_dirs))
    return "\n\n".join(parts) + "\n"


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
        "tz": owner_tz(agent_dir),
        "token": env.get("TELEGRAM_BOT_TOKEN", ""),
        "allowed": allowed_ids(agent_dir, env),
        "groq": env.get("GROQ_API_KEY", ""),
        "skills": skill_dirs(agent_dir, home),
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
    install_recipes_skill(pdir, p["agent_dir"], p["memory_dirs"])
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

## Если RECIPES.md ещё нет — собери его один раз
Источники (только читать): {sources}
1. Найди в источниках все типовые задачи (то, что владелец поручает регулярно). Читай все файлы памяти, не только оглавление.
2. Для каждой задачи напиши рецепт строго по шаблону:

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


def install_recipes_skill(pdir, agent_dir, memory_dirs):
    """09.11: GPT is critically literal (Сухов); per-task recipes fixed form on the comparison test."""
    d = os.path.join(pdir, "skills/recipes/task-recipes")
    os.makedirs(d, exist_ok=True)
    sources = ", ".join([os.path.abspath(agent_dir)] + list(memory_dirs))
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(RECIPES_SKILL.format(sources=sources))


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
    print(f"  факты в каждое сообщение: {', '.join(os.path.basename(x.split('|')[0]) for x in p['facts']) or 'только дата'}")
    if problems:
        sys.exit("ОШИБКА: " + "; ".join(problems))
    if not a.apply:
        print("Пробный прогон: ничего не записано. Запуск с --apply запишет профиль.")
        return
    apply(p, a.profile, a.home)
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
  5. один раз написать агенту: «Собери RECIPES.md по навыку task-recipes» — он распишет рецепт под каждую свою задачу
     (долго, до 20 минут, и ощутимо тратит лимит ChatGPT — делать по одному агенту)""")


if __name__ == "__main__":
    main()
