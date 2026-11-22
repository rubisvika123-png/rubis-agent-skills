#!/usr/bin/env python3
"""Replay real owner requests that the Claude agent handled well against the moved GPT agent (22.11, Vika:
«агенты на GPT тупые» — the move check only asked «did it answer», never «is it as good»).

Runs ON the student's server, next to claude-to-gpt.py:
    python3 gpt-quality-check.py <profile> <agent_dir> [N] [--out FILE]
Picks N recent owner requests whose Claude answer the owner did not correct, that need no changes on the
server (Claude only read files or just answered), and asks the GPT agent the same in a separate one-shot
conversation with read-only tools and an explicit «change nothing, send nothing». Writes pairs side by side
for a human (Denis) to judge. Each run spends the owner's ChatGPT limit — keep N small (3-5).
"""
import argparse, importlib.util, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("c2g", os.path.join(HERE, "claude-to-gpt.py"))
c2g = importlib.util.module_from_spec(spec); spec.loader.exec_module(c2g)

WRITE = re.compile(r"^(Edit|Write) |^\$ .*(\brm\b|>\s*\S|\bmv\b|\bsend\b|curl .*-X ?POST|systemctl (re)?start|crontab|git push)")
CORRECTED = re.compile(r"(?i)(не то|не так|опять|снова|^нет\b|неправ|ошиб|почему ты|туп|бля|хуй|переделай|исправь)")
GUARD = ("ЭТО ПРОВЕРКА КАЧЕСТВА, а не живая задача. Ничего не меняй на сервере, не записывай файлы, не отправляй "
         "сообщений и ничего не публикуй. Файлы можно только читать. Ответь владельцу ровно так, как ответил бы "
         "в Telegram; если для ответа нужно что-то сделать — сделай всё, что можно только чтением, а остальное опиши "
         "одной строкой «сделал бы: …».\n\nСообщение владельца:\n")


def pick(episodes, n, min_len=25, want=None, any_source=False):
    """Newest owner requests with a Claude answer, no server changes, and no correction in the next message.
    any_source: also tasks handed over by another agent (our Liza gets most work from Denis)."""
    owner = [e for e in sorted(episodes, key=lambda e: e["ts"]) if any_source or e["who"] == "Владелец"]
    good = []
    for i, e in enumerate(owner):
        nxt = owner[i + 1]["ask"] if i + 1 < len(owner) else ""
        ask = e["ask"].strip()
        if not e["said"] or not (min_len <= len(ask) <= 700) or CORRECTED.search(nxt[:200]):
            continue
        if want and not re.search(want, ask, re.I):
            continue
        if any(WRITE.search(d) for d in e["did"]):
            continue
        good.append(e)
    seen, out = set(), []
    for e in reversed(good):  # newest first, no near-duplicates
        key = re.sub(r"\W+", " ", e["ask"].lower())[:60]
        if key in seen:
            continue
        seen.add(key); out.append(e)
        if len(out) == n:
            break
    return out


def ask_gpt(profile, text, timeout=600, run=subprocess.run):
    try:
        r = run(["hermes", "-p", profile, "chat", "-q", GUARD + text, "--oneshot", "-t", "file"],
                capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() or (r.stderr or "").strip()[-800:]
    except (OSError, subprocess.SubprocessError) as e:
        return f"[ошибка запуска: {e}]"


def final_answer(out):
    """The one-shot CLI prints its tool trace too; keep only the reply after the «☤ Hermes» header."""
    if "☤ Hermes" not in out:
        return out
    body = out.split("☤ Hermes", 1)[1]
    return body.split("────", 1)[0].strip() if "────" in body else body.strip()


class HiddenFuture:
    """22.11: the first run copied Claude's old answers from claude-dialog.md — it tested search, not thinking.
    For the run, the dialogue file ends before the earliest replayed request; the full file is put back after."""

    def __init__(self, agent_dir, before_ts):
        self.path = os.path.join(agent_dir, "state", c2g.DIALOG_NAME)
        self.before = before_ts[:16].replace("T", " ")
        self.backup = self.path + ".full-during-quality-check"

    def __enter__(self):
        if os.path.isfile(self.path):
            os.replace(self.path, self.backup)
            keep, cut = [], False
            for line in open(self.backup, encoding="utf-8"):
                if line.startswith("## ") and line[3:19] >= self.before:
                    cut = True
                if not cut:
                    keep.append(line)
            with open(self.path, "w", encoding="utf-8") as f:
                f.writelines(keep)
        return self

    def __exit__(self, *exc):
        if os.path.isfile(self.backup):
            os.replace(self.backup, self.path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile"); ap.add_argument("agent_dir"); ap.add_argument("n", nargs="?", type=int, default=3)
    ap.add_argument("--out", default=None); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--min", type=int, default=25, help="shortest request, chars (short ones depend on chat context)")
    ap.add_argument("--any-source", action="store_true")
    ap.add_argument("--want", default=None, help="regex the request must match, e.g. 'напиши|пост|сценари'")
    a = ap.parse_args()
    eps = pick(c2g._claude_episodes(a.agent_dir, os.path.expanduser("~")), a.n, a.min, a.want, a.any_source)
    if not eps:
        sys.exit("нет подходящих просьб в истории Claude")
    out = a.out or os.path.join(os.path.expanduser("~"), f".hermes/profiles/{a.profile}/quality-check.md")
    parts = [f"# Проверка качества {a.profile}: {len(eps)} настоящих просьб владельца\n"]
    with HiddenFuture(a.agent_dir, min(e["ts"] for e in eps)):
        answers = ["(--dry)" if a.dry else final_answer(ask_gpt(a.profile, e["ask"])) for e in eps]
    for i, (e, gpt) in enumerate(zip(eps, answers), 1):
        parts.append(c2g._redact(f"\n## {i}. {e['ts'][:16]}\nВладелец: {e['ask']}\n\n### Claude ответил\n{e['said'][-1][:2500]}"
                                 f"\n\n### GPT ответил\n{gpt[:2500]}\n"))
        print(f"{i}/{len(eps)} готово", flush=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(out)


if __name__ == "__main__":
    main()
