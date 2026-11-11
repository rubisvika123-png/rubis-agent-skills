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
    bindir = os.path.join(root, "bin")
    os.makedirs(bindir)
    stub = os.path.join(bindir, "hermes")
    open(stub, "w").write('#!/bin/sh\nmkdir -p "$HOME/.hermes/profiles/$3"\n')
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


def main():
    check_effort()
    with tempfile.TemporaryDirectory() as root:
        home, agent, bindir = make_agent(root)
        pdir = os.path.join(home, ".hermes/profiles/testgpt")

        r = run(home, agent, bindir)
        assert r.returncode == 0, r.stderr
        assert "Пробный прогон" in r.stdout and "555, 777" in r.stdout, r.stdout
        assert not os.path.exists(pdir), "dry run must not write"
        assert "FAKE" not in r.stdout and "gsk_fake" not in r.stdout, "secrets must not be printed"

        r = run(home, agent, bindir, "--apply")
        assert r.returncode == 0, r.stderr
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
        assert "без эмодзи" in soul and "шум" not in soul, "only the agent's own memory"
        env = open(os.path.join(pdir, ".env")).read()
        assert "TELEGRAM_BOT_TOKEN=111:FAKE" in env
        assert "TELEGRAM_ALLOWED_USERS=555,777" in env, "live allowlist wins over channel.env"
        assert "GROQ_API_KEY=gsk_fake" in env
        assert stat.S_IMODE(os.stat(os.path.join(pdir, ".env")).st_mode) == 0o600
        cfg = yaml.safe_load(open(os.path.join(pdir, "config.yaml")))
        assert cfg["model"]["default"] == "gpt-5.6-sol"
        assert cfg["agent"] == {"reasoning_effort": "high", "max_turns": 150}
        assert cfg["compression"]["threshold_tokens"] == 100000, cfg.get("compression")
        assert os.path.join(agent, ".claude/skills") in cfg["skills"]["external_dirs"]
        assert cfg["stt"]["language"] == "ru" and cfg["stt"]["provider"] == "groq"
        assert cfg["session_reset"]["mode"] == "both" and cfg["display"]["show_commentary"] is False
        hook = os.path.join(home, ".hermes/hooks/protect-home.py")
        assert os.path.isfile(hook) and cfg["hooks"]["pre_tool_call"][0]["command"] == hook
        assert "Как я выполняю просьбы" in soul and "## Скорость" in soul
        # 05.11: self-check before «готово» — rule in the character + code gate on the way out
        assert "Проверка перед «готово»" in soul
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
        assert "task-recipes" in r.stdout, "the one-time recipes command must be printed"

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
