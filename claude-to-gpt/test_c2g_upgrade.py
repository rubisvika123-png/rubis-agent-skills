"""22.11: --upgrade-all refreshes converter-owned rules in place and keeps everything else."""
import importlib.util, os, tempfile
spec = importlib.util.spec_from_file_location("c2g", os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-to-gpt.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rules = "## Правило А\nновое А\n\n## Правило Б\nновое Б\n"
old = ("# Гриша — техспец\nрол\n\n## Владелец просил (НЕ НАРУШАТЬ)\nне трогать\n\n## Правило А\nстарое А\n\n"
       "## Моя работа до переезда на GPT (не начинаю с чистого листа)\nстарая история\n\n" + m.MEM_BEGIN + "\nпамять\n" + m.MEM_END + "\n")
new = m.upgrade_soul(old, rules=rules, hist="## Моя работа до переезда на GPT (не начинаю с чистого листа)\nновая история")
assert "новое А" in new and "старое А" not in new
assert "не трогать" in new and new.startswith("# Гриша")
assert "новое Б" in new and new.index("новое Б") < new.index("новая история") < new.index(m.MEM_BEGIN) and "память" in new
assert "старая история" not in new
assert m.upgrade_soul(new, rules=rules, hist="## Моя работа до переезда на GPT (не начинаю с чистого листа)\nновая история") == new  # idempotent
with tempfile.TemporaryDirectory() as home:
    a = os.path.join(home, "ai-x"); os.makedirs(a)
    p = os.path.join(home, ".hermes/profiles/grisha"); os.makedirs(p)
    open(os.path.join(p, "SOUL.md"), "w").write(f"## Моя папка\\nМоя рабочая папка — {a}. Пути из этого файла\\n")
    open(os.path.join(p, "SOUL.md"), "w").write(f"## Моя папка\nМоя рабочая папка — {a}. Пути из этого файла\n")
    assert m.moved_profiles(home) == [(a, "grisha")]
print("OK upgrade")
