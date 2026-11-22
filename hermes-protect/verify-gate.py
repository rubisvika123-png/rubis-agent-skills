#!/usr/bin/env python3
"""Hermes `pre_verify` shell hook: a GPT agent may not hand over work it just changed
until it has checked it (Vika 05.11.2026: «чтобы агент сам себя проверял, а не
ученик переделывал по пять раз»).

GPT says «готово» without looking more often than Claude. Hermes fires `pre_verify`
when the agent edited files this turn and is about to finish; returning
{"action":"continue","message":...} sends it back for one more pass. We send it
back once (attempt 0) with the exact files to re-open; the second time it passes.
Memory/notes edits and questions back to the user are not deliveries — no gate.
Any error -> print nothing, the turn finishes as usual (never block the agent).
"""
import json, os, re, sys, time

# own memory/notes, skills, the team board and second-brain notes are bookkeeping, not the delivery (09.11)
# 13.11: the course's shared brain is /root/ai-shared-brain (tasks/facts/calendar) and the strategist keeps its
# numbers in materials/point-a.md — both are notes, not deliveries. Missing them sent a strategist back for a
# second pass on EVERY turn: two answers in Telegram and double the ChatGPT limit (student, 12–13.11).
OWN = re.compile(r"/\.hermes/|/memor(y|ies)/|/\.claude/|/skills/|/second-brain/|/ai-shared-brain/|"
                 r"/materials/point-a\.md$|/knowledge/|team-tasks\.md$")
QUESTION = re.compile(r"\?\s*$")
DONE = re.compile(r"готов|сделал|исправил|обновил|загрузил|добавил|поменял|заменил|записал|создал|"
                  r"сохранил|подготовил|написал|собрал|смонтировал|оформил|перенёс|перенес|настроил|"
                  r"держи|отправил|вот (файл|архив|сайт|документ|ролик|пост)", re.I)
LOG = os.path.expanduser("~/.hermes/logs/verify-gate.log")
FINAL_HIDDEN = ("Всё верно — дай итоговый ответ владельцу заново ЦЕЛИКОМ: сам результат полностью (весь текст поста, "
                "письма, плана, оффера или что просили), как будто предыдущего ответа не было — владелец его не увидит. "
                "Строку «Проверка: …» (что открыл и увидел) пиши одну, в самом конце. Не пиши «готово», если не проверил.")
FINAL_SHOWN = ("Твой ответ выше владелец УЖЕ получил. Всё верно — ответь ОДНОЙ строкой «Проверка: …» (что открыл и "
               "увидел), результат не повторяй. Нашёл и исправил ошибку — пришли только исправленное и строку «Проверка: …».")


def draft_already_shown(payload):
    """22.11: with display.interim_assistant_messages on, Hermes delivers the draft answer to the owner before
    this check — asking the agent to repeat it «целиком» made every finished task arrive twice (Зюзин, Лаптев)."""
    try:
        home = os.environ.get("HERMES_HOME") or ""
        prof = payload.get("profile") or ""
        if prof and prof != "default" and not home.rstrip("/").endswith("/profiles/" + prof):
            home = os.path.expanduser(f"~/.hermes/profiles/{prof}")
        text = open(os.path.join(home or os.path.expanduser("~/.hermes"), "config.yaml"), encoding="utf-8").read()
        # 22.11: no yaml import — the gateway runs hooks with its own Python, which may lack PyYAML (Дима Син:
        # the import failed silently and the agent was again told to repeat the whole answer)
        return re.search(r"(?m)^\s+interim_assistant_messages:\s*(true|yes|on)\b", text, re.I) is not None
    except Exception:
        return False


def main():
    try:
        payload = json.load(sys.stdin)
        extra = payload.get("extra", {})
    except Exception:
        return
    if int(extra.get("attempt") or 0) > 0:
        return
    final = (extra.get("final_response") or "").strip()
    paths = [p for p in extra.get("changed_paths") or [] if not OWN.search(p)]
    if not paths or not final or QUESTION.search(final) or not DONE.search(final):
        return
    # 22.11 (Лаптев, пошаговая настройка меток): every step re-saved a notes file, the gate fired on every step
    # and each step reached the owner twice. A short step-reply within 10 min of the last check is not sent back.
    # 22.11 (Лаптев «не надо столько сообщений», Дима Син): with the draft already delivered, a short step-reply
    # («Записала: …») came back as a second message «Проверил: …» — noise for a two-line answer. Short shown
    # replies are not sent back at all.
    if len(final) < 400 and draft_already_shown(payload):
        return
    state = os.path.expanduser(f"~/.hermes/logs/verify-gate-last-{payload.get('profile') or 'default'}")
    try:
        if len(final) < 600 and time.time() - os.path.getmtime(state) < 600:
            return
    except OSError:
        pass
    try:
        open(state, "w").close()
    except OSError:
        pass
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%F %T ") + f"sent back to check: {paths[:5]}\n")
    except Exception:
        pass
    listed = "\n".join(f"- {p}" for p in paths[:10])
    print(json.dumps({"action": "continue", "message": (
        "СТОП, перед тем как сдать работу — проверь её сам. Ты изменил:\n" + listed + "\n"
        "1) Открой каждый файл и прочитай: там именно то, что просили, без ошибок и заглушек.\n"
        "2) Картинку/PDF/видео — посмотри сам результат, а не код, который его делал.\n"
        "3) Сайт или ссылку — открой и убедись, что изменение видно.\n"
        "Нашёл ошибку — исправь и проверь снова.\n"
        + (FINAL_SHOWN if draft_already_shown(payload) else FINAL_HIDDEN)
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
