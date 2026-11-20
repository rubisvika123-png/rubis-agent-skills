#!/usr/bin/env python3
"""Tests for claude-to-gpt.py on a synthetic agent: dry run writes nothing, --apply builds
SOUL/.env/config from the Claude layout. A stub `hermes` stands in for profile create."""
import re
import glob, json, os, stat, subprocess, sys, tempfile

import yaml

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-to-gpt.py")


def make_agent(root):
    home = os.path.join(root, "home")
    agent = os.path.join(home, "techspec")
    os.makedirs(os.path.join(agent, "secrets"))
    os.makedirs(os.path.join(agent, ".claude/skills"))
    os.makedirs(os.path.join(agent, "dashi-plugin-claude-code/plugin/state/telegram"))
    open(os.path.join(agent, "CLAUDE.md"), "w").write("# Техспец Тест\nОтвечаю только владельцу.\n"
        "Отвечать владельцу можно ТОЛЬКО через инструмент `reply` (плагин `dashi-channel`).\n"
        "Каждый ход ОБЯЗАН заканчиваться вызовом reply.\n- Модель: Claude Opus 5, контекст 1M\n"
        "Бриф Вике — только через `reply`.\nКаждый ход ОБЯЗАН заканчиваться вызовом `reply`.\n"
        "Перед Викой текст на проверку Денису:\n```bash\ntmux send-keys -t coder-denis -l \"ЗАДАЧА ОТ ЛИЗЫ: проверь\"\nsleep 1\ntmux send-keys -t coder-denis Enter\n```\n"
        "\n## Как передать задачу другому агенту\n\nМы живём на одном сервере, каждый в своей комнате tmux:\n"
        "- маркетолог — комната `marketing`\n\n```bash\ntmux send-keys -t КОМНАТА -l \"ЗАДАЧА ОТ <имя>: …\"\n"
        "tmux send-keys -t КОМНАТА Enter\n```\n\n**Предохранитель:** только по просьбе владельца.\n"
        "\n## Напоминания (будильник)\n\nСтавлю будильник командой `/root/ai-assistant/scripts/remind-add.sh \"2026-08-26 09:00\" \"про вебинар\"`.\n"
        "Время — всегда по часовому поясу владельца: **Europe/Moscow**.\nКогда сработает — разбудит строкой «СРАБОТАЛ БУДИЛЬНИК».\n"
        "\n## Безопасность\n- Не показываю ключи.\n")
    os.makedirs(os.path.join(agent, "state"))
    open(os.path.join(agent, "state/reminders.tsv"), "w").write("2099-01-01T10:00+00:00\tтест\n")
    open(os.path.join(agent, "prices.md"), "w").write("Курс 70 000 ₽\n")
    os.makedirs(os.path.join(home, "second-brain"))
    open(os.path.join(home, "second-brain/team-tasks.md"), "w").write("| задача | сделано |\n")
    open(os.path.join(agent, "secrets/channel.env"), "w").write(
        "TELEGRAM_BOT_TOKEN=111:FAKE\nGROQ_API_KEY=gsk_fake\nTELEGRAM_ALLOWED_USER_IDS=999\n")
    json.dump({"allowed_chat_ids": [555, 777]},
              open(os.path.join(agent, "dashi-plugin-claude-code/plugin/state/telegram/config.json"), "w"))
    enc = re.sub(r"[^A-Za-z0-9]", "-", agent)  # same rule as the converter (mkdtemp names may contain "_")
    for suffix, text in (("-dashi-plugin-claude-code-plugin", "- [Правило](r.md) — без эмодзи"),
                         ("-dashi-plugin-claude-code-plugin-state-telegram-outbox", "- [Чужое](x.md) — шум")):
        mem = os.path.join(home, ".claude/projects", enc + suffix, "memory")
        os.makedirs(mem)
        open(os.path.join(mem, "MEMORY.md"), "w").write(text + "\n")
    # 15.11: the agent's MCP connections (project file + ~/.claude.json) move to Hermes; the Telegram bridge does not
    json.dump({"mcpServers": {"chatplace": {"type": "http", "url": "https://mcp.example/x", "headers": {"Authorization": "Bearer SECRETMCP"}},
                              "dashi-channel": {"command": "bun", "args": ["server.ts"]}}},
              open(os.path.join(agent, ".mcp.json"), "w"))
    json.dump({"mcpServers": {"gcal": {"command": "npx", "args": ["-y", "gcal-mcp"], "env": {"K": "SECRETENV"}}},
               "projects": {agent: {"mcpServers": {"playwright": {"type": "stdio", "command": "npx", "args": ["-y", "@playwright/mcp"]}}}}},
              open(os.path.join(home, ".claude.json"), "w"))
    bindir = os.path.join(root, "bin")
    os.makedirs(bindir)
    stub = os.path.join(bindir, "hermes")
    open(stub, "w").write('#!/bin/sh\n'
        'if [ "$3" = "-z" ]; then echo "$2" >> "$HOME/z-calls"; r="$HOME/.hermes/profiles/$2/skills/recipes/task-recipes/RECIPES.md"; '
        'printf "## A\\nШаги: 1\\n## B\\nШаги: 1\\n## C\\nШаги: 1\\n" > "$r"; exit 0; fi\n'
        'mkdir -p "$HOME/.hermes/profiles/$3"\n')
    os.chmod(stub, stat.S_IRWXU)
    open(os.path.join(bindir, "protect-home.py"), "w").write("#!/usr/bin/env python3\n")
    return home, agent, bindir


def run(home, agent, bindir, *extra):
    env = dict(os.environ, HOME=home, PATH=bindir + ":" + os.environ["PATH"], PROTECT_SRC=os.path.join(bindir, "protect-home.py"))
    return subprocess.run([sys.executable, SCRIPT, agent, "testgpt", "--home", home, *extra],
                          env=env, capture_output=True, text=True)


def check_effort():
    # 05.11: deep thinking for the tech agent and the marketer; the rest answer faster on medium
    import importlib.util
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert m.effort_for("/root/techspec", "x") == "high"
    assert m.effort_for("/root/agent", "coder") == "high"
    assert m.effort_for("/root/marketing", "marketing") == "high"
    assert m.effort_for("/root/assistant", "tutor") == "medium"
    assert m.model_for("/root/techspec", "x") == "gpt-5.6-sol"
    assert m.model_for("/root/agent", "coder") == "gpt-5.6-sol"
    assert m.model_for("/root/marketing", "marketing") == "gpt-6.2-sol"
    assert m.model_for("/root/assistant", "tutor") == "gpt-6.2-sol"
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "ai-victoriarubis")
        os.makedirs(a)
        open(os.path.join(a, "CLAUDE.md"), "w").write("# Никита — кодер / архитектор\n\n## Правила\nмаркетолог пишет посты\n")
        assert m.model_for(a, "nikita") == "gpt-5.6-sol", "role line in CLAUDE.md"
        open(os.path.join(a, "CLAUDE.md"), "w").write("# Алина — маркетолог\n\n## Правила\nтехспец чинит сервер\n")
        assert m.model_for(a, "alina") == "gpt-6.2-sol", "a techspec mention below the title does not count"


def check_host_gateway():
    """11.11: new Hermes — one host gateway for all profiles, session resets via a plugin."""
    with tempfile.TemporaryDirectory() as root:
        home, agent, bindir = make_agent(root)
        pdir = os.path.join(home, ".hermes/profiles/testgpt")
        src = os.path.join(root, "hsrc"); os.makedirs(os.path.join(src, "hermes_cli")); os.makedirs(os.path.join(src, "gateway"))
        open(os.path.join(src, "hermes_cli/gateway.py"), "w").write("print('Profile X does not get a gateway of its own.')\n")
        open(os.path.join(src, "gateway/run.py"), "w").write("w('session_reset.mode: both is no longer applied')\n")
        # stub: `hermes -p P plugins enable N` adds N to the profile's plugins.enabled
        open(os.path.join(bindir, "hermes"), "w").write(
            '#!/bin/sh\nif [ "$3" = plugins ]; then\n'
            '  [ "$4" = install ] && mkdir -p "$HOME/.hermes/profiles/$2/plugins/$5"\n'
            '  [ "$4" = enable ] && python3 -c "import yaml,sys; p=sys.argv[1]; c=yaml.safe_load(open(p)); '
            'c.setdefault(\'plugins\',{}).setdefault(\'enabled\',[]).append(sys.argv[2]); yaml.safe_dump(c,open(p,\'w\'))" '
            '"$HOME/.hermes/profiles/$2/config.yaml" "$5"\n  exit 0\nfi\nmkdir -p "$HOME/.hermes/profiles/$3"\n')
        units = os.path.join(root, "units"); os.makedirs(units)
        # 15.11 Lunev's server: a dangling symlink in /etc/systemd/system crashed the dry run
        os.symlink(os.path.join(root, "nowhere.service"), os.path.join(units, "dbus-org.example.service"))
        wd = os.path.join(root, "agent-watchdog.sh")
        open(wd, "w").write('declare -A AGENTS=(\n  [agent]="%s"\n)\ndeclare -A HERMES=()\ndeclare -A HERMES_WHO=()\n' % agent)
        open(os.path.join(units, "agent-watchdog.service"), "w").write("[Service]\nExecStart=/bin/bash %s\n" % wd)
        os.environ.update(C2G_HERMES_SRC=src, C2G_UNIT_DIR=units, C2G_NO_SYSTEMCTL="1")
        try:
            r = run(home, agent, bindir, "--apply")
            assert r.returncode == 0, r.stderr
            assert "hermes gateway install   # один общий запуск" in r.stdout, r.stdout
            assert "--profile testgpt gateway install" not in r.stdout
            cfg = yaml.safe_load(open(os.path.join(pdir, "config.yaml")))
            assert "hermes-session-reset-policy" in cfg["plugins"]["enabled"], cfg["plugins"]
            assert "не поставился" not in r.stdout
            assert "запусти эту же команду" in r.stdout, "no host gateway yet → pending"
            os.makedirs(os.path.join(home, ".config/systemd/user"))
            open(os.path.join(home, ".config/systemd/user/hermes-gateway.service"), "w").write("[Service]\n")
            r = run(home, agent, bindir, "--apply")
            w = open(wd).read()
            assert '# [agent]="%s"' % agent in w, w
            assert '[hermes-gateway.service]="%s"' % pdir in w, w
            assert subprocess.run(["bash", "-n", wd]).returncode == 0
        finally:
            for k in ("C2G_HERMES_SRC", "C2G_UNIT_DIR", "C2G_NO_SYSTEMCTL"):
                os.environ.pop(k, None)


def check_shared_brain():
    # 15.11: students keep the team board in their own shared folder (Britenkova: ~/ai-shared-brain/tasks.md
    # + facts.md + calendar.md), not ~/second-brain/team-tasks.md — the GPT agent then invented board items.
    import importlib.util
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as home:
        shared = os.path.join(home, "ai-shared-brain")
        os.makedirs(os.path.join(shared, "messages"))
        for f in ("tasks.md", "facts.md", "calendar.md"):
            open(os.path.join(shared, f), "w").write("x\n")
        open(os.path.join(shared, "messages/old.md"), "w").write("x\n")
        agent = os.path.join(home, "ai-strategist")
        os.makedirs(os.path.join(agent, "materials"))
        open(os.path.join(agent, "materials/point-a.md"), "w").write("x\n")
        open(os.path.join(agent, "CLAUDE.md"), "w").write(f"Доска задач команды: {shared}/tasks.md\n")
        found = m.find_fact_files(agent, home)
        assert found[0] == os.path.join(shared, "tasks.md") + "|tail=40", found
        for f in ("facts.md", "calendar.md"):
            assert os.path.join(shared, f) in found, found
        assert os.path.join(agent, "materials/point-a.md") in found, found
        assert not any("messages" in f for f in found), found
        # A board in ~/second-brain still wins when there is one.
        os.makedirs(os.path.join(home, "second-brain"))
        open(os.path.join(home, "second-brain/team-tasks.md"), "w").write("x\n")
        assert m.find_fact_files(agent, home)[0] == os.path.join(home, "second-brain/team-tasks.md") + "|tail=40"


def check_schedules():
    # 15.11: the team routine wakes Claude agents by cron → tmux send-keys into their room. On GPT there is
    # no room, so these wake-ups die silently — the converter must list them with a ready hermes cron command.
    import importlib.util
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as root:
        agent = os.path.join(root, "ai-marketing")
        os.makedirs(agent)
        units = os.path.join(root, "units"); os.makedirs(units)
        open(os.path.join(units, "agent-marketing.service"), "w").write(
            f"[Service]\nWorkingDirectory={agent}\nExecStart=/bin/sh -c '/usr/bin/tmux new-session -d -s agent-marketing ./start.sh'\n")
        script = os.path.join(root, "morning.sh")
        open(script, "w").write('tmux send-keys -t agent-marketing -l "Пришли план контента на день"\nsleep 1\ntmux send-keys -t agent-marketing Enter\n')
        cron = os.path.join(root, "crontab")
        open(cron, "w").write(f"0 6 * * * {script}\n"
                              "0 15 * * 1-5 tmux send-keys -t =agent-marketing: -l 'Собери цифры за день' && tmux send-keys -t =agent-marketing: Enter\n"
                              "0 7 * * * tmux send-keys -t agent -l 'Это техспец, не маркетолог'\n"
                              "30 20 * * * tmux send-keys -t \"=agent-marketing:\" \"Итоги дня\" Enter\n"
                              "*/5 * * * * /root/ai-marketing/scripts/backup.sh\n")
        os.environ["C2G_UNIT_DIR"], os.environ["C2G_CRONTAB"] = units, cron
        try:
            found = m.find_schedules(agent)
        finally:
            del os.environ["C2G_UNIT_DIR"], os.environ["C2G_CRONTAB"]
        assert found == [("0 6 * * *", "Пришли план контента на день"), ("0 15 * * 1-5", "Собери цифры за день"), ("30 20 * * *", "Итоги дня")], found
        # 15.11 Lunev: a script that builds the text in a variable and gates the hour inside
        # («0 * * * *» + case "$1" … msg=…; send-keys "$msg») must NOT become an hourly job with the text "$msg"
        dyn = os.path.join(root, "sales-schedule.sh")
        open(dyn, "w").write('H=$(date +%H)\ncase "$1" in daily) [ "$H" = 10 ] || exit 0 ;; esac\n'
                             'case "$1" in daily) msg="ПРОВЕРКА CRM" ;; esac\n'
                             'tmux send-keys -t agent-marketing -l "$msg"; sleep 1; tmux send-keys -t agent-marketing Enter\n')
        open(cron, "a").write(f"0 * * * * {dyn} daily\n")
        os.environ["C2G_UNIT_DIR"], os.environ["C2G_CRONTAB"] = units, cron
        try:
            found2 = m.find_schedules(agent)
            manual = m.find_manual_schedules(agent)
        finally:
            del os.environ["C2G_UNIT_DIR"], os.environ["C2G_CRONTAB"]
        assert not any("$" in t for _, t in found2), found2
        assert any("sales-schedule.sh daily" in x for x in manual), manual
        # --apply turns them into Hermes cron jobs in the server's zone, once (a re-run adds nothing)
        pdir = os.path.join(root, "profile"); os.makedirs(os.path.join(pdir, "cron"))
        calls = []
        made = m.create_schedules("marketing", pdir, found, "UTC", run=lambda cmd, **kw: calls.append(cmd))
        assert made == 3 and len(calls) == 3, calls
        assert calls[0][:6] == ["hermes", "-p", "marketing", "cron", "create", "0 6 * * *"], calls[0]
        assert calls[0][6] == "Пришли план контента на день" and "--timezone" in calls[0] and "UTC" in calls[0], calls[0]
        json.dump({"jobs": [{"name": calls[0][calls[0].index("--name") + 1]}]}, open(os.path.join(pdir, "cron/jobs.json"), "w"))
        calls.clear()
        assert m.create_schedules("marketing", pdir, found, "UTC", run=lambda cmd, **kw: calls.append(cmd)) == 2
        # 19.11: a job more often than every 2 h runs on the light model, a daily one on the main model
        calls.clear()
        m.create_schedules("x", os.path.join(root, "none"), [("12 8-23 * * *", "тихая проверка"), ("0 9 * * *", "утро")],
                           "UTC", run=lambda cmd, **kw: calls.append(cmd))
        assert calls[0][-4:] == ["--model", m.LIGHT_MODEL, "--provider", "openai-codex"], calls[0]
        assert "--model" not in calls[1], calls[1]
        assert m.runs_per_day("12 8-23 * * *") == 16 and m.runs_per_day("12 9-21/3 * * *") == 5


def check_owner_tz_from_memory():
    # 15.11 live run: CLAUDE.md said «Europe/Moscow», the memory index said the owner is in Thailand (UTC+7).
    # GPT set «10 утра по моему времени» at 10:00 Moscow = 14:00 for the owner. Memory wins.
    import importlib.util
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as root:
        agent = os.path.join(root, "agent"); mem = os.path.join(root, "mem")
        os.makedirs(agent); os.makedirs(mem)
        open(os.path.join(agent, "CLAUDE.md"), "w").write(
            "# Аня\n\n## Напоминания (будильник)\n\nСтавлю будильник `remind-add.sh`.\n"
            "Время — всегда по часовому поясу владельца: **Europe/Moscow**.\n")
        open(os.path.join(mem, "MEMORY.md"), "w").write("- [Вика в Таиланде, UTC+7](tz.md) — время называть по её местному\n")
        assert m.owner_tz(agent) == 3
        assert m.owner_tz(agent, [mem]) == 7
        soul = m.build_soul(agent, [mem])
        assert "--timezone Asia/Bangkok" in soul and "Europe/Moscow" not in soul, soul[:1500]
    # 19.11 (Ольга Мирай): the GPT agent must know its old Claude talks and the owner's ongoing work folders
    with tempfile.TemporaryDirectory() as home:
        agent = os.path.join(home, "ai-tech"); os.makedirs(os.path.join(agent, "state/ddu-gorny"))
        os.makedirs(os.path.join(agent, "core")); os.makedirs(os.path.join(agent, "node_modules/x"))
        open(os.path.join(agent, "CLAUDE.md"), "w").write("# Техспец\n")
        open(os.path.join(agent, "state/ddu-gorny/01-pismo.txt"), "w").write("x")
        open(os.path.join(agent, "core/notes.md"), "w").write("x")
        open(os.path.join(agent, "node_modules/x/a.js"), "w").write("x")
        enc = re.sub(r"[^A-Za-z0-9]", "-", agent)
        for suffix in ("-dashi-plugin-claude-code-plugin", "-outbox"):
            d = os.path.join(home, ".claude/projects", enc + suffix); os.makedirs(d)
            open(os.path.join(d, "s.jsonl"), "w").write("{}")
        soul = m.build_soul(agent, [], "tech", home)
        assert "Моя работа до переезда на GPT" in soul, soul[-800:]
        assert enc + "-dashi-plugin-claude-code-plugin/*.jsonl" in soul and "-outbox" not in soul
        assert os.path.join(agent, "state/ddu-gorny") + " (1)" in soul
        assert "node_modules" not in soul.split("Моя работа до переезда")[1] and "/core " not in soul
        assert "ОДИН уточняющий вопрос" in soul
        empty = os.path.join(home, "ai-empty"); os.makedirs(empty)
        open(os.path.join(empty, "CLAUDE.md"), "w").write("# Пусто\n")
        assert "Моя работа до переезда" not in m.build_soul(empty, [], "e", home)
        # 20.11 (Лаптев): no handoff section in CLAUDE.md -> the kanban rule is still added; skills-only + owner-waiting rules
        soul_e = m.build_soul(empty, [], "e", home)
        assert "## Как передать задачу другому агенту" in soul_e and "hermes kanban create" in soul_e, soul_e[-600:]
        assert "делаю ТОЛЬКО через него" in soul_e and "ждут твоего ответа" in soul_e
        soul_h = m.build_soul(agent, [], "tech", home)
        open(os.path.join(agent, "CLAUDE.md"), "w").write("# Техспец\n\n## Как передать задачу другому агенту\nкомнаты\n")
        soul_h = m.build_soul(agent, [], "tech", home)
        assert soul_h.count("## Как передать задачу другому агенту") == 1, "handoff section duplicated"


def check_history_and_recipes():
    # 15.11 (Vika): recipes must be built FRESH at migration from the agent's real Claude work
    # (what the owner asked, which commands/files Claude used, the answer she accepted, where she corrected),
    # automatically — not a manual step after the move that nobody runs.
    import importlib.util
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as home:
        agent = os.path.join(home, "ai-marketing"); os.makedirs(agent)
        enc = re.sub(r"[^A-Za-z0-9]", "-", agent)
        tdir = os.path.join(home, ".claude/projects", enc + "-dashi-plugin-claude-code-plugin"); os.makedirs(tdir)
        def u(text, ts): return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        def a(blocks, ts): return {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": blocks}}
        lines = [
            u('<channel source="telegram" chat_id="1" ts="2026-11-10T10:00:00Z">Сделай пост в Threads про агентов</channel>', "2026-11-10T10:00:00Z"),
            a([{"type": "tool_use", "name": "Read", "input": {"file_path": "/root/ai-marketing/formats.md"}},
               {"type": "tool_use", "name": "Bash", "input": {"command": "python3 scripts/post.py --token=SECRET123 --dry"}}], "2026-11-10T10:01:00Z"),
            a([{"type": "tool_use", "name": "mcp__dashi-channel__reply", "input": {"chat_id": "1", "text": "Вот пост: агенты работают ночью."}}], "2026-11-10T10:02:00Z"),
            u('<channel source="telegram" chat_id="1" ts="2026-11-10T10:05:00Z">Нет, короче и без слова ночью</channel>', "2026-11-10T10:05:00Z"),
            a([{"type": "tool_use", "name": "mcp__dashi-channel__reply", "input": {"chat_id": "1", "text": "Короче: агенты работают, пока вы спите."}}], "2026-11-10T10:06:00Z"),
            u('<channel source="telegram" chat_id="1" ts="2026-11-10T10:07:00Z">Ок, публикуй</channel>', "2026-11-10T10:07:00Z"),
        ]
        with open(os.path.join(tdir, "s1.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")
        out = os.path.join(home, "hist.md")
        n = m.export_claude_history(agent, home, out)
        h = open(out, encoding="utf-8").read()
        assert n == 3, (n, h)
        for must in ("Сделай пост в Threads", "/root/ai-marketing/formats.md", "post.py", "Вот пост: агенты работают ночью.",
                     "Нет, короче и без слова ночью", "Ок, публикуй"):
            assert must in h, (must, h)
        assert "SECRET123" not in h, "secrets must be redacted from the history"
        assert h.index("Ок, публикуй") < h.index("Сделай пост"), "newest first"
        # the skill points at the history as the MAIN source
        pdir = os.path.join(home, "prof")
        m.install_recipes_skill(pdir, agent, [], out)
        sk = open(os.path.join(pdir, "skills/recipes/task-recipes/SKILL.md"), encoding="utf-8").read()
        assert out in sk and "дословно" in sk and "те же команды" in sk, sk
        # 15.11 (Vika): students tune the course templates; Claude's own working files must be reused, not rewritten
        assert "своими файлами" in sk and "своё не пиши" in sk, sk
        # 19.11 (Ольга Мирай): skill_manage refuses RECIPES.md at the skill root — the skill must say to write it as a file
        assert os.path.join(pdir, "skills/recipes/task-recipes/RECIPES.md") in sk and "НЕ через skill_manage" in sk, sk
        # 19.11 (Ольга Мирай): skills kept in <agent>/skills/ must be registered too; empty dirs are skipped
        vid = os.path.join(home, "ai-video"); os.makedirs(os.path.join(vid, "skills/reels-montage"))
        open(os.path.join(vid, "skills/reels-montage/SKILL.md"), "w").write("---\nname: reels-montage\n---\n")
        os.makedirs(os.path.join(vid, ".claude/skills"))
        assert m.skill_dirs(vid, os.path.join(home, "nohome")) == [os.path.join(vid, ".claude/skills"), os.path.join(vid, "skills")]
        os.makedirs(os.path.join(home, "ai-empty/skills"))
        assert m.skill_dirs(os.path.join(home, "ai-empty"), os.path.join(home, "nohome")) == [], "skills/ without SKILL.md is not a skills dir"
        # validation of the built RECIPES.md
        rp = os.path.join(pdir, "skills/recipes/task-recipes/RECIPES.md")
        assert m.recipes_ok(pdir) == 0
        open(rp, "w", encoding="utf-8").write("## Пост\nШаги: 1\n## Рилс\nШаги: 1\n## Отчёт\nШаги: 1\n")
        assert m.recipes_ok(pdir) == 3
        # 15.11 (Vika): «меньше трёх» is too blunt — the minimum grows with the volume of real work
        assert m.recipes_needed(out) == 3, "small history → floor of 3"
        big = os.path.join(home, "big.md")
        open(big, "w", encoding="utf-8").write("".join(f"\n## 2026-11-{i % 28 + 1:02d} 10:00\nВладелец: задача {i}\n" for i in range(150)))
        assert m.recipes_needed(big) == 10, m.recipes_needed(big)
        huge = os.path.join(home, "huge.md")
        open(huge, "w", encoding="utf-8").write("".join(f"\n## 2026-11-01 10:00\nЗадача (расписание или другой агент): x{i}\n" for i in range(900)))
        assert m.recipes_needed(huge) == 15, "capped"


def check_core_memory():
    # 15.11 Lunev: course agents keep memory in <agent>/core/memory/ (CLAUDE.md says so), often without
    # MEMORY.md — 7 of 10 agents showed «память: НЕТ» and their notes would not reach GPT.
    import importlib.util
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as home:
        agent = os.path.join(home, "ai-marketing"); cm = os.path.join(agent, "core/memory")
        os.makedirs(cm)
        open(os.path.join(agent, "CLAUDE.md"), "w").write("# Маркетолог\n")
        open(os.path.join(cm, "tone.md"), "w").write("---\nname: tone\ndescription: Пишем без канцелярита\n---\nтекст\n")
        open(os.path.join(cm, "clients.md"), "w").write("# Клиенты агентства\nсписок\n")
        dirs = m.find_memory_dirs(agent, home)
        assert dirs == [cm], dirs
        block = m.memory_block(dirs)
        assert "tone.md" in block and "Пишем без канцелярита" in block and "clients.md" in block, block


def check_pending_reminders():
    # 15.11: reminders already queued in the course alarm clock (state/reminders.tsv) fire through the tmux
    # room — after the move they would be lost. Future ones become one-shot Hermes cron jobs, past ones are skipped.
    import importlib.util, datetime
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as root:
        agent = os.path.join(root, "ai-assistant"); os.makedirs(os.path.join(agent, "state"))
        open(os.path.join(agent, "state/reminders.tsv"), "w").write(
            "2099-03-05T07:30:00+07:00\tоплатить сервер\n2001-01-01T10:00:00+00:00\tстарое\n")
        pdir = os.path.join(root, "prof"); os.makedirs(os.path.join(pdir, "cron"))
        calls = []
        n = m.migrate_reminders(agent, "assistant", pdir, run=lambda cmd, **kw: calls.append(cmd))
        assert n == 1 and len(calls) == 1, calls
        c = calls[0]
        assert c[:6] == ["hermes", "-p", "assistant", "cron", "create", "30 0 5 3 *"], c  # 07:30 +07 = 00:30 UTC
        assert "оплатить сервер" in c[6] and "--repeat" in c and "UTC" in c, c


def check_self_check():
    # 16.11 (Лаптев): move «passed» a CLI test, but in Telegram the agent had no terminal and asked Allow/Deny on every check
    import importlib.util, socket, types
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    good = {"platform_toolsets": {"telegram": ["hermes-telegram"]}, "model": {"provider": "openai-codex"}, "approvals": {"mode": "smart"},
            "compression": {"threshold_tokens": 120000},
            "auxiliary": {"compression": {"model": "gpt-5.6-luna", "reasoning_effort": "none"}, "background_review": {"model": "gpt-5.6-luna"}}}
    assert m.audit_config(good) == [], m.audit_config(good)
    bad = {"platform_toolsets": {"telegram": ["memory", "todo"]}, "model": {"provider": "openai-codex", "base_url": "https://api.groq.com/openai/v1"}}
    probs = " ".join(m.audit_config(bad))
    assert "нет команд" in probs and "чужой адрес" in probs and "Allow/Deny" in probs, probs
    # 17.11 (Лаптев): late compression and side calls on the main model burned the owner's ChatGPT limit
    assert "сжимается слишком поздно" in probs and "background_review" in probs and "compression идёт" in probs, probs
    slow = dict(good, auxiliary={"compression": {"model": "gpt-5.6-luna"}, "background_review": {"model": "gpt-5.6-luna"}})
    assert any("сжатие с раздумьями" in p for p in m.audit_config(slow)), m.audit_config(slow)
    seen = {}
    def fake(cmd, **kw):
        seen["t"] = cmd[cmd.index("-t") + 1]
        return types.SimpleNamespace(stdout=socket.gethostname() if "terminal" in seen["t"] else "нет инструмента", stderr="")
    assert m.live_check("x", good, run=fake) and seen["t"] == "terminal,file", seen
    assert not m.live_check("x", {"platform_toolsets": {"telegram": ["memory", "todo"]}}, run=fake) and seen["t"] == "memory,todo"


def check_recipes_kept_on_failed_rebuild():
    # 16.11 (Лаптев): a re-run hit the ChatGPT limit mid-rebuild — the old RECIPES.md was moved aside and the agent
    # was left with 0 recipes. A failed or weaker rebuild must keep the previous recipes.
    import importlib.util, types
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, "skills/recipes/task-recipes"); os.makedirs(d)
        old = "".join(f"## Задача {i}\nШаги: 1) сделать\n\n" for i in range(5))
        open(os.path.join(d, "RECIPES.md"), "w").write(old)
        open(os.path.join(d, "claude-history.md"), "w").write("## 2026-11-16\nВладелец: новая просьба\n")
        limit = lambda *a, **k: types.SimpleNamespace(stdout="HTTP 429: The usage limit has been reached", stderr="")
        n, rebuilt = m.build_recipes("x", root, run=limit)
        assert open(os.path.join(d, "RECIPES.md")).read() == old, "old recipes must survive a failed rebuild"
        assert n == 5, n


def check_rebuild_only_on_growth():
    # 16.11 (Лаптев): a re-run for a config tweak rebuilt recipes for 3 agents and burned the owner's ChatGPT limit.
    # Rebuild only when the Claude history has >=5 new owner requests (or recipes are missing).
    import importlib.util, types
    spec = importlib.util.spec_from_file_location("c2g", SCRIPT); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, "skills/recipes/task-recipes"); os.makedirs(d)
        open(os.path.join(d, "RECIPES.md"), "w").write("".join(f"## З{i}\nШаги: 1) x\n\n" for i in range(4)))
        hist = os.path.join(d, "claude-history.md")
        reqs = lambda n: "".join(f"## 2026-11-1{i % 9}\nВладелец: просьба {i}\n\n" for i in range(n))
        calls = []
        run = lambda *a, **k: calls.append(1) or types.SimpleNamespace(stdout="", stderr="")
        open(hist, "w").write(reqs(30))
        open(os.path.join(d, ".history-sha256"), "w").write("old-style-digest\n")   # mark from an older converter
        assert m.build_recipes("x", root, run=run) == (4, False) and not calls, "recipes present, no growth → no rebuild"
        open(hist, "w").write(reqs(33))
        assert m.build_recipes("x", root, run=run)[1] is False and not calls, "3 new requests → still no rebuild"
        open(hist, "w").write(reqs(36))
        m.build_recipes("x", root, run=run)
        assert calls, "6 new requests → rebuild"


def main():
    check_rebuild_only_on_growth()
    check_recipes_kept_on_failed_rebuild()
    check_self_check()
    check_effort()
    check_pending_reminders()
    check_core_memory()
    check_history_and_recipes()
    check_owner_tz_from_memory()
    check_schedules()
    check_shared_brain()
    check_host_gateway()
    with tempfile.TemporaryDirectory() as root:
        home, agent, bindir = make_agent(root)
        pdir = os.path.join(home, ".hermes/profiles/testgpt")

        r = run(home, agent, bindir)
        assert r.returncode == 0, r.stderr
        assert "Пробный прогон" in r.stdout and "555, 777" in r.stdout, r.stdout
        assert not os.path.exists(pdir), "dry run must not write"
        assert "FAKE" not in r.stdout and "gsk_fake" not in r.stdout, "secrets must not be printed"
        assert "подключения (MCP): chatplace, gcal, playwright" in r.stdout, r.stdout
        assert "SECRETMCP" not in r.stdout and "SECRETENV" not in r.stdout, "MCP secrets must not be printed"

        # 16.11 (Лаптев): the profile was cloned from a server config whose Telegram had only [memory, todo]
        # (a free backup agent) — the moved agent could not run a single command on its own server.
        os.makedirs(pdir)
        open(os.path.join(pdir, "config.yaml"), "w").write("model:\n  default: qwen\n  provider: custom:groq\n  base_url: https://api.groq.com/openai/v1\n"
                                                             "platform_toolsets:\n  cli: [hermes-cli]\n  telegram: [memory, todo]\n")
        r = run(home, agent, bindir, "--apply")
        assert r.returncode == 0, r.stderr
        c = yaml.safe_load(open(os.path.join(pdir, "config.yaml")))
        assert c["platform_toolsets"]["telegram"] == ["hermes-telegram"]
        # 16.11 (Лаптев): a leftover Groq base_url sent the approval check to Groq (401) → every heredoc asked the owner
        assert "base_url" not in c["model"], c["model"]
        assert c["approvals"]["mode"] == "smart", c.get("approvals")
        assert c["approvals"]["destructive_slash_confirm"] is False, "/new must not ask Approve/Cancel (Лаптев 16.11)"
        # 10.11: facts-inject puts board/reminders/prices on every message
        facts = open(os.path.join(pdir, "plugins/facts-inject/facts.txt")).read().splitlines()
        assert facts[0] == "tz=3", facts
        assert facts[1] == os.path.join(home, "second-brain/team-tasks.md") + "|tail=40", facts
        assert os.path.join(agent, "state/reminders.tsv") in facts and os.path.join(agent, "prices.md") in facts, facts
        assert "facts-inject" in yaml.safe_load(open(os.path.join(pdir, "config.yaml")))["plugins"]["enabled"]
        assert os.path.isfile(os.path.join(pdir, "plugins/facts-inject/__init__.py"))
        soul = open(os.path.join(pdir, "SOUL.md")).read()
        assert soul.startswith("# Техспец Тест"), soul[:80]
        assert "Как я довожу работу до конца" in soul
        # 20.11: the photo rule lived only in a hand-patched SOUL and was lost on re-run; long tasks show progress
        assert "## Фото без текста" in soul and "What do you see in this image?" in soul
        assert "## Долгая задача — владелец видит ход" in soul
        # 20.11: full course-chat review — short owner questions, voice = raw material, no yes-man strategist
        for h in ("## Короткий вопрос владельца — понимаю по смыслу", "## Голосовое владельца — сырьё, а не диктовка", "## Думаю сам, а не поддакиваю"):
            assert h in soul, h
        assert "без эмодзи" in soul and "шум" not in soul, "only the agent's own memory"
        env = open(os.path.join(pdir, ".env")).read()
        assert "TELEGRAM_BOT_TOKEN=111:FAKE" in env
        assert "TELEGRAM_ALLOWED_USERS=555,777" in env, "live allowlist wins over channel.env"
        assert "GROQ_API_KEY=gsk_fake" in env
        assert stat.S_IMODE(os.stat(os.path.join(pdir, ".env")).st_mode) == 0o600
        cfg = yaml.safe_load(open(os.path.join(pdir, "config.yaml")))
        assert cfg["model"]["default"] == "gpt-5.6-sol"
        assert cfg["auxiliary"]["approval"] == {"provider": "openai-codex", "model": "gpt-5.6-luna", "reasoning_effort": "none"}
        assert cfg["agent"] == {"reasoning_effort": "high", "max_turns": 150}
        assert cfg["compression"]["threshold_tokens"] == 120000 and cfg["compression"]["protect_last_n"] == 8 and cfg["compression"]["threshold"] == 0.5, cfg.get("compression")
        assert cfg["compression"]["proactive_prune_tokens"] == 48000, cfg.get("compression")
        assert cfg["compression"]["codex_gpt55_autoraise"] is False, cfg.get("compression")
        assert cfg["file_read_max_chars"] == 20000 and cfg["tool_output"]["max_bytes"] == 12000, cfg.get("tool_output")
        for task in ("compression", "background_review"):
            assert cfg["auxiliary"][task]["provider"] == "openai-codex", cfg.get("auxiliary")
            assert cfg["auxiliary"][task]["model"] == "gpt-5.6-luna", cfg.get("auxiliary")
        # 17.11 (Лаптев): compression ran with reasoning on — 21 passes × ~2 min a day; «none» = Hermes fast lane
        assert cfg["auxiliary"]["compression"]["reasoning_effort"] == "none", cfg.get("auxiliary")
        assert os.path.join(agent, ".claude/skills") in cfg["skills"]["external_dirs"]
        assert cfg["stt"]["language"] == "ru" and cfg["stt"]["provider"] == "groq"
        assert cfg["session_reset"]["mode"] == "both" and cfg["display"]["show_commentary"] is False
        hook = os.path.join(home, ".hermes/hooks/protect-home.py")
        assert os.path.isfile(hook) and cfg["hooks"]["pre_tool_call"][0]["command"] == hook
        assert "Как я выполняю просьбы" in soul and "## Скорость" in soul
        assert "## Скрипты — только файлом" in soul and "python3 - <<" in soul, "inline scripts trigger Allow/Deny (Лаптев 16.11)"
        # 05.11: self-check before «готово» — rule in the character + code gate on the way out
        assert "Проверка перед «готово»" in soul
        assert "Спросить другого агента = передать и ждать" in soul and "Заметки — коротко и по местам" in soul and "## Длина ответа владельцу" in soul and "## Цифры владельца — сразу в файл" in soul
        # 07.11: on Дарья's server GPT took ~10 steps per message vs ~3 on Claude; each step resends the whole chat
        assert "## Экономлю шаги" in soul and "не перечитываю" in soul and "одним шагом" in soul
        assert "раздаю помощникам параллельно" not in soul, "delegate_task only for really big tasks"
        assert soul.count("Что важнее, если правила спорят") == 1 and "Как я пишу владельцу — пример" in soul
        gate = os.path.join(home, ".hermes/hooks/verify-gate.py")
        assert os.path.isfile(gate) and cfg["hooks"]["pre_verify"][0]["command"] == gate
        # 05.11: Claude-only lines are stripped (GPT took them literally)
        assert "dashi-channel" not in soul and "вызовом reply" not in soul and "Claude Opus" not in soul
        assert "Отвечаю только владельцу." in soul
        assert os.path.isfile(os.path.join(pdir, "plugins/media-check/__init__.py"))
        assert "media-check" in cfg["plugins"]["enabled"]
        # 05.11: a message sent mid-task is steered in (not killing the work) + Russian «Принял»
        assert cfg["display"]["busy_input_mode"] == "steer" and cfg["display"]["busy_steer_ack_enabled"] is False
        assert os.path.isfile(os.path.join(pdir, "plugins/busy-ack-ru/__init__.py"))
        assert "busy-ack-ru" in cfg["plugins"]["enabled"]
        # 09.11 test (Сухов: GPT is critically literal): a skill that makes the agent write one recipe per
        # typical task from its own Claude files, then follow it; the finished text always goes into the reply.
        rs = os.path.join(pdir, "skills/recipes/task-recipes/SKILL.md")
        assert os.path.isfile(rs), "recipes skill missing"
        rtxt = open(rs).read()
        assert rtxt.startswith("---\nname: task-recipes\n")
        for part in ("Результат:", "Данные:", "Шаги:", "Хорошо, когда:", "Пример хорошего результата:",
                     "Частые ошибки:", "Проверка перед сдачей:", "RECIPES.md"):
            assert part in rtxt, part
        assert agent in rtxt, "recipes must point at the agent's own Claude folder"
        assert "## Рецепты задач" in soul and "RECIPES.md" in soul
        assert "целиком в ответе" in soul, "the reel was hidden in a file on 09.11"
        # Blind GPT-vs-Claude test 10.11: GPT invented prices, answered "send numbers first", repeated stale statuses.
        assert "только из файлов владельца" in soul, "invented prices 250/350k"
        assert "всё равно даю план" in soul, "answered only with a question"
        assert "сверяю с источником" in soul, "repeated stale board statuses as facts"
        # 15.11: --apply builds fresh recipes itself (one hermes -z), and a re-run with the same history does not rebuild
        assert os.path.isfile(os.path.join(pdir, "skills/recipes/task-recipes/claude-history.md"))
        assert open(os.path.join(home, "z-calls")).read().split() == ["testgpt"], "recipes not built on --apply"
        assert "рецепты: 3" in r.stdout, r.stdout
        mcp = yaml.safe_load(open(os.path.join(pdir, "config.yaml")))["mcp_servers"]
        assert set(mcp) == {"chatplace", "gcal", "playwright"}, mcp
        assert mcp["chatplace"] == {"url": "https://mcp.example/x", "headers": {"Authorization": "Bearer SECRETMCP"}}, mcp
        assert mcp["playwright"] == {"command": "npx", "args": ["-y", "@playwright/mcp"]}, mcp
        assert mcp["gcal"]["env"] == {"K": "SECRETENV"}, mcp
        # 15.11: Hermes runs from the home dir, so relative paths from CLAUDE.md (core/…, materials/…) must be anchored
        assert f"Моя рабочая папка — {agent}" in soul, "SOUL does not say where relative paths start"
        # 15.11 Lunev: tasks say «пришли Михаилу (chat_id 292395941)» — on Hermes that is `hermes -p <profile> send`
        assert "hermes -p testgpt send -t telegram:<chat_id>" in soul, "no way to message another person"
        # Fable 5.1 blind verdict 10.11
        assert "ровно N шагов" in soul and "командой date" in soul and "сортирую по риску" in soul
        assert "предложение, нужно твоё да" in soul and "ни имён файлов" in soul
        # Fable round 2: GPT answered from memory (0 lookups on SSH, skipped the Hiddify card)
        assert "Исключение — проверка фактов" in soul and "course-errors" in soul
        assert "ждёт владельца / ждёт внешних / ждёт агента" in soul and "не повторяю как факт" in soul
        # 09.11: Hermes agents have no tmux rooms — handoffs go through the shared Hermes kanban board
        assert "tmux send-keys" not in soul and "комнате tmux" not in soul
        assert "hermes kanban create" in soul and "--assignee" in soul and "hermes profile list" in soul
        assert "Предохранитель" in soul, "the owner-only safety rule survives"
        assert "## Безопасность" in soul and "Не показываю ключи." in soul, "next section intact"
        # 09.11: the course alarm clock wakes the agent through its tmux room — gone on Hermes; native cron instead
        assert "remind-add.sh" not in soul and "СРАБОТАЛ БУДИЛЬНИК" not in soul
        assert "hermes cron create" in soul and "--deliver telegram" in soul and "Europe/Moscow" in soul
        assert "вызовом `reply`" not in soul
        assert 'hermes kanban create "ЗАДАЧА ОТ ЛИЗЫ: проверь" --assignee <профиль coder-denis>' in soul
        assert "через `reply`" not in soul and "Бриф Вике — только в Telegram." in soul
        assert "рецепты задач уже собраны" in r.stdout, "the run must say recipes are built, not ask for a manual step"

        # Re-run keeps one token line and backs up the previous SOUL without losing the very first backup
        # (10.11: students re-run the converter to get new rules).
        first = os.path.join(pdir, "SOUL.md.bak-before-claude-to-gpt")
        open(first, "w").write("ORIGINAL BEFORE GPT")
        r = run(home, agent, bindir, "--apply")
        assert r.returncode == 0, r.stderr
        assert open(os.path.join(pdir, ".env")).read().count("TELEGRAM_BOT_TOKEN=") == 1
        assert open(first).read() == "ORIGINAL BEFORE GPT", "first backup overwritten on re-run"
        assert glob.glob(os.path.join(pdir, "SOUL.md.bak-rerun-*")), "previous GPT SOUL not backed up"

        # 10.11: hand the agent over to the watchdog — only once its gateway service exists.
        units = os.path.join(root, "units"); os.makedirs(units)
        wd = os.path.join(root, "agent-watchdog.sh")
        open(wd, "w").write('#!/usr/bin/env bash\ndeclare -A AGENTS=(\n  [agent]="%s"\n  [agent-other]="/root/other"\n)\n'
                            'declare -A HERMES=()\ndeclare -A HERMES_WHO=()\n' % agent)
        open(os.path.join(units, "agent-watchdog.service"), "w").write("[Service]\nExecStart=/bin/bash %s\n" % wd)
        os.environ.update(C2G_UNIT_DIR=units, C2G_NO_SYSTEMCTL="1")
        before = open(wd).read()
        r = run(home, agent, bindir, "--apply")
        assert r.returncode == 0, r.stderr
        assert open(wd).read() == before, "watchdog touched before the gateway service exists"
        assert "запусти эту же команду с --apply ещё раз" in r.stdout, r.stdout
        os.makedirs(os.path.join(home, ".config/systemd/user"))
        open(os.path.join(home, ".config/systemd/user/hermes-gateway-testgpt.service"), "w").write("[Service]\n")
        r = run(home, agent, bindir, "--apply")
        assert r.returncode == 0, r.stderr
        w = open(wd).read()
        assert '# [agent]="%s"' % agent in w and '  [agent-other]="/root/other"' in w, w
        assert '[hermes-gateway-testgpt.service]="%s"' % pdir in w and '[hermes-gateway-testgpt.service]="testgpt"' in w, w
        assert subprocess.run(["bash", "-n", wd]).returncode == 0
        assert "под его присмотром" in r.stdout, r.stdout
        r = run(home, agent, bindir, "--apply")
        assert open(wd).read() == w, "second handover changed the watchdog again"
        del os.environ["C2G_UNIT_DIR"], os.environ["C2G_NO_SYSTEMCTL"]

        # No token → refuse.
        open(os.path.join(agent, "secrets/channel.env"), "w").write("")
        r = run(home, agent, bindir)
        assert r.returncode != 0 and "TELEGRAM_BOT_TOKEN" in (r.stderr + r.stdout)
    print("OK: claude-to-gpt tests passed")


if __name__ == "__main__":
    main()
