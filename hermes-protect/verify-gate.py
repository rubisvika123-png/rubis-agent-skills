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

OWN = re.compile(r"/\.hermes/|/memor(y|ies)/|/\.claude/|/skills/")
QUESTION = re.compile(r"\?\s*$")
DONE = re.compile(r"готов|сделал|исправил|обновил|загрузил|добавил|поменял|заменил|записал|создал|"
                  r"сохранил|подготовил|написал|собрал|смонтировал|оформил|перенёс|перенес|настроил|"
                  r"держи|отправил|вот (файл|архив|сайт|документ|ролик|пост)", re.I)
LOG = os.path.expanduser("~/.hermes/logs/verify-gate.log")


def main():
    try:
        extra = json.load(sys.stdin).get("extra", {})
    except Exception:
        return
    if int(extra.get("attempt") or 0) > 0:
        return
    final = (extra.get("final_response") or "").strip()
    paths = [p for p in extra.get("changed_paths") or [] if not OWN.search(p)]
    if not paths or not final or QUESTION.search(final) or not DONE.search(final):
        return
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
        "Нашёл ошибку — исправь и проверь снова. Всё верно — дай итоговый ответ и одной строкой "
        "«Проверил: …» — что именно открыл и увидел. Не пиши «готово», если не проверил."
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
