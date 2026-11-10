import importlib.util, os, tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))


def load(facts_dir, lines):
    os.environ["FACTS_DIR"] = facts_dir
    spec = importlib.util.spec_from_file_location("fi", os.path.join(HERE, "__init__.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    m.HERE = facts_dir
    with open(os.path.join(facts_dir, "facts.txt"), "w") as f:
        f.write("\n".join(lines))
    return m


def test_all():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "prices.md"), "w").write("Флагман 70 000 ₽")
    open(os.path.join(d, "reminders.tsv"), "w").write(
        "2026-11-01T10:00+00:00\tпрошлое\n2026-11-12T10:00+00:00\tбудущее\nмусор\n")
    board = os.path.join(d, "team-tasks.md")
    open(board, "w").write("\n".join(f"строка {i}" for i in range(100)))
    m = load(d, ["prices.md", "reminders.tsv", f"{board}|tail=3", "missing.md", "# comment", "tz=7"])
    ctx = m.build_context(datetime(2026, 11, 10, 13, 0, tzinfo=timezone.utc))
    assert "10.11.2026 20:00, вторник" in ctx, ctx[:200]
    assert "70 000" in ctx
    assert "будущее" in ctx and "прошлое" not in ctx and "мусор" not in ctx
    assert "строка 99" in ctx and "строка 96" not in ctx  # tail=3
    assert "ДОСКА ЗАДАЧ" in ctx
    assert "missing" not in ctx and "comment" not in ctx
    assert m.on_pre_llm_call()["context"].startswith("СВЕЖИЕ ФАКТЫ")
    m2 = load(d, ["prices.md"])
    assert "10.11.2026 16:00, вторник" in m2.build_context(datetime(2026, 11, 10, 13, 0, tzinfo=timezone.utc))  # default MSK
    print("ALL PASS")


if __name__ == "__main__":
    test_all()
