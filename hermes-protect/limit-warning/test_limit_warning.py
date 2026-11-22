import importlib.util, os
spec = importlib.util.spec_from_file_location("lw", os.path.join(os.path.dirname(__file__), "limit_warning.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert m.format_moscow_reset("2026-11-25 07:59 MSK") == "25 ноября в 07:59 по Москве"
assert m.format_moscow_reset("2026-11-25 15:13 CET") == "25 ноября в 17:13 по Москве"
assert m.format_moscow_reset("2026-11-25 12:00 UTC") == "25 ноября в 15:00 по Москве"
print("OK limit_warning")
