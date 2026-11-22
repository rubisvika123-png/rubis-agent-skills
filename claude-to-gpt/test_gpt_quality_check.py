import importlib.util, os
spec = importlib.util.spec_from_file_location("q", os.path.join(os.path.dirname(__file__), "gpt-quality-check.py"))
q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
E = lambda ts, ask, said=("ok",), did=(): {"ts": ts, "who": "Владелец", "ask": ask, "said": list(said), "did": list(did)}
eps = [E("1", "Сколько роликов осталось в очереди на неделю?"),
       E("2", "Почему ты опять не то сделал, переделай"),          # next-message correction of #1? no: it corrects #1
       E("3", "Напиши пост про запуск интенсива на 14 дней"),
       E("4", "Удали старые бэкапы со всего сервера", did=["$ rm -rf /root/old"]),
       E("5", "Какая погода будет у нас на выходных в Москве?", said=())]
got = [e["ts"] for e in q.pick(eps, 5)]
assert "1" not in got  # owner corrected it in the next message
assert "4" not in got  # changed the server
assert "5" not in got  # no Claude answer
assert got[0] == "3"   # newest first
class R: stdout = "ответ"; stderr = ""
seen = {}
def fake(cmd, **k): seen["cmd"] = cmd; return R()
assert q.ask_gpt("joe", "привет", run=fake) == "ответ"
assert seen["cmd"][-2:] == ["-t", "file"] and "Ничего не меняй" in seen["cmd"][5]
print("OK quality-check")
assert q.final_answer("trace\n☤ Hermes\nДима, ноль.\n──────\nВозобновить") == "Дима, ноль."
import tempfile
with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "state")); f = os.path.join(d, "state", "claude-dialog.md")
    open(f, "w").write("# x\n\n## 2026-11-10 10:00\nстарое\n\n## 2026-11-17 08:03\nответ про карту\n")
    with q.HiddenFuture(d, "2026-11-17T08:03:00Z"):
        t = open(f).read(); assert "старое" in t and "про карту" not in t
    assert "про карту" in open(f).read()
print("OK quality-check hide")
