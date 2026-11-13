#!/usr/bin/env python3
"""verify-gate: notes are not deliveries (13.11.2026). Run: python3 hermes-protect/test_verify_gate.py"""
import json, os, subprocess, sys, tempfile

GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify-gate.py")


def run(paths, final="Записал, вот план на неделю.", attempt=0):
    env = {**os.environ, "HOME": tempfile.mkdtemp()}
    os.makedirs(os.path.join(env["HOME"], ".hermes", "logs"))
    data = json.dumps({"extra": {"attempt": attempt, "changed_paths": paths, "final_response": final}})
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
