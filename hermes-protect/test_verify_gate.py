#!/usr/bin/env python3
"""verify-gate: notes are not deliveries (13.11.2026). Run: python3 hermes-protect/test_verify_gate.py"""
import json, os, subprocess, sys, tempfile

GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify-gate.py")


def run(paths, final="Записал, вот план на неделю.", attempt=0):
    env = {**os.environ, "HOME": tempfile.mkdtemp()}
    os.makedirs(os.path.join(env["HOME"], ".hermes", "logs"))
    data = json.dumps({"extra": {"attempt": attempt, "changed_paths": paths, "final_response": final}})
    env = {**env, "HOME": tempfile.mkdtemp()}  # 22.11: fresh HOME — the step rate-limit state must not leak between cases
    return subprocess.run([sys.executable, GATE], input=data, capture_output=True, text=True, env=env).stdout.strip()


# notes and the course shared brain never trigger a second pass
for p in ["/root/ai-strategist/materials/point-a.md", "/root/ai-shared-brain/tasks.md",
          "/root/ai-shared-brain/facts.md", "/root/.hermes/profiles/strateg/knowledge/INDEX.md",
          "/root/second-brain/team-tasks.md"]:
    assert run([p]) == "", p
# a real deliverable still gets checked once
out = run(["/root/ai-strategist/materials/point-a.md", "/root/ai-marketing/outbox/post.md"])
assert '"action": "continue"' in out and "post.md" in out and "point-a" not in out, out
# second attempt and questions pass
assert run(["/root/x/post.md"], attempt=1) == ""
assert run(["/root/x/post.md"], final="Какой вариант берём?") == ""
print("PASS verify-gate")

# 22.11: interim messages on → the draft already reached the owner; the gate must not ask to repeat it
with tempfile.TemporaryDirectory() as h:
    p = os.path.join(h, "profiles", "joe"); os.makedirs(p)
    open(os.path.join(p, "config.yaml"), "w").write("display:\n  interim_assistant_messages: true\n")
    inp = json.dumps({"profile": "joe", "extra": {"attempt": 0, "final_response": "Готово, исправил файл.", "changed_paths": ["/root/ai-x/site/index.html"]}})
    out = subprocess.run([sys.executable, GATE], input=inp, capture_output=True, text=True, env={**os.environ, "HERMES_HOME": p, "HOME": h}).stdout
    msg = json.loads(out)["message"]
    assert "УЖЕ получил" in msg and "ЦЕЛИКОМ" not in msg, msg
print("OK verify-gate shown variant")

# 22.11: a second short step-reply within 10 minutes is not sent back (no doubled step messages)
with tempfile.TemporaryDirectory() as home:
    os.makedirs(os.path.join(home, ".hermes", "logs"))
    inp = json.dumps({"profile": "joe", "extra": {"attempt": 0, "final_response": "Готово, сохранил ссылку TikTok.", "changed_paths": ["/root/ai-x/state/links.txt"]}})
    env = {**os.environ, "HOME": home}
    first = subprocess.run([sys.executable, GATE], input=inp, capture_output=True, text=True, env=env).stdout
    second = subprocess.run([sys.executable, GATE], input=inp, capture_output=True, text=True, env=env).stdout
    assert first.strip() and not second.strip(), (first, second)
print("OK verify-gate step rate-limit")
