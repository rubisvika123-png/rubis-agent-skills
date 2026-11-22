"""22.11: the Claude-era owner dialogue is exported as one clean, greppable, oldest-first file."""
import importlib.util, json, os, re, tempfile
spec = importlib.util.spec_from_file_location("c2g", os.path.join(os.path.dirname(__file__), "claude-to-gpt.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as home:
    agent = os.path.join(home, "ai-x"); os.makedirs(agent)
    enc = re.sub(r"[^A-Za-z0-9]", "-", agent)
    d = os.path.join(home, ".claude/projects", enc + "-dashi-plugin-claude-code-plugin"); os.makedirs(d)
    rows = [
        {"type": "user", "timestamp": "2026-11-02T10:00:00Z", "message": {"content": '<channel source="telegram">Залей сайт на Тильду</channel>'}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "curl tilda"}},
            {"type": "tool_use", "name": "mcp__dashi-channel__reply", "input": {"text": "Залил на Тильду, проект 123"}}]}},
        {"type": "user", "timestamp": "2026-11-01T09:00:00Z", "message": {"content": '<channel source="telegram">Привет token=abc123secret</channel>'}},
    ]
    open(os.path.join(d, "a.jsonl"), "w").write("\n".join(json.dumps(r) for r in rows))
    out = os.path.join(agent, "state", m.DIALOG_NAME)
    assert m.export_claude_dialog(agent, home, out) == 2
    text = open(out).read()
    assert text.index("2026-11-01") < text.index("2026-11-02")  # oldest first
    assert "Залил на Тильду, проект 123" in text and "$ curl tilda" in text
    assert "abc123secret" not in text
    block = m.history_block(agent, home)
    assert out in block and "grep -n -i" in block
print("OK dialog")
