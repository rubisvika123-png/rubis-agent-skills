import importlib.util, os, tempfile, sys
spec = importlib.util.spec_from_file_location("c2g", os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-to-gpt.py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as root:
    a, b = os.path.join(root, "a"), os.path.join(root, "b")
    calls = []
    fake = lambda cmd, **k: calls.append(cmd)
    assert m.install_limit_warning("a", a, "Europe/Moscow", run=fake) is True
    code = open(os.path.join(a, "scripts/limit_warning.py")).read()
    assert a in code and "__PDIR__" not in code
    assert calls and "--no-agent" in calls[0] and "limit_warning.py" in calls[0]
    assert m.install_limit_warning("b", b, "Europe/Moscow", run=fake) is False  # one warner per account
    assert len(calls) == 1
print("OK limit")
