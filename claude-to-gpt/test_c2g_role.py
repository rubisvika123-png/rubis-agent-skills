"""22.11: techspec in a personally-named profile must get deep thinking (Ольга's «nikita» got medium)."""
import importlib.util, os, tempfile
spec = importlib.util.spec_from_file_location("c2g", os.path.join(os.path.dirname(__file__), "claude-to-gpt.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
    a = os.path.join(d, "ai-victoriarubis"); os.makedirs(a)
    open(os.path.join(a, "CLAUDE.md"), "w").write("# Никита — техспец Ольги\n\n## Кто я\n")
    assert m.effort_for(a, "nikita") == "high"
    assert m.model_for(a, "nikita") == m.TECH_MODEL
    b = os.path.join(d, "helper"); os.makedirs(b)
    open(os.path.join(b, "CLAUDE.md"), "w").write("# Аня — помощник\n\n## Кто я\n")
    assert m.effort_for(b, "anya") == "medium"
print("OK role")
