"""media-check — третья ступень «проверки перед готово» для агентов на GPT (Vika 05.11.2026).

The pre_verify gate only sees files the agent edited with write_file/patch. Videos,
PDFs, images and archives are built by programs (ffmpeg, python, zip) via terminal /
execute_code, so the engine never counts them as changed. This plugin watches those
tool calls: when the command names a fresh media file that now exists, the tool
result the model reads gets an extra line telling it to look at the result itself
(frames of the video, pages of the PDF) before answering. Once per file per session.
No extra model calls — the agent just can't skip the look.
"""
import os, re, time

MEDIA = {
    "video": ("mp4", "mov", "webm", "mkv", "avi"),
    "pdf": ("pdf",),
    "image": ("png", "jpg", "jpeg", "webp", "gif"),
    "doc": ("docx", "pptx", "xlsx"),
    "archive": ("zip",),
}
EXT = {e: kind for kind, exts in MEDIA.items() for e in exts}
PATH = re.compile(r"""(?:^|[\s'"=(,])((?:/|\./|~/)?[\w./~-]+\.(%s))\b""" % "|".join(EXT), re.I)
HOW = {
    "video": "вытащи 3–4 кадра (начало, середина, конец) и посмотри их; проверь длительность и что звук есть",
    "pdf": "открой и посмотри страницы (картинкой), а не только код, который его делал",
    "image": "открой картинку и посмотри её сам",
    "doc": "открой файл и прочитай, что внутри",
    "archive": "посмотри список файлов внутри архива",
}
FRESH_SEC = 600
_seen = {}


def _fresh_files(text, cwd):
    out = []
    for m in PATH.finditer(text or ""):
        p = os.path.expanduser(m.group(1))
        if not os.path.isabs(p):
            p = os.path.join(cwd, p)
        try:
            if os.path.isfile(p) and time.time() - os.path.getmtime(p) < FRESH_SEC and p not in out:
                out.append(p)
        except OSError:
            pass
    return out


def transform(tool_name="", args=None, result="", status="", session_id="", **_):
    if tool_name not in ("terminal", "execute_code") or status not in ("ok", "", None):
        return None
    args = args or {}
    text = str(args.get("command") or args.get("code") or "")
    files = _fresh_files(text, str(args.get("workdir") or args.get("cwd") or os.getcwd()))
    seen = _seen.setdefault(session_id or "-", set())
    files = [f for f in files if f not in seen]
    if not files:
        return None
    seen.update(files)
    lines = [f"- {f}: {HOW[EXT[f.rsplit('.', 1)[1].lower()]]}" for f in files[:5]]
    note = ("\n\n[ПРОВЕРКА ПЕРЕД «ГОТОВО»] Ты собрал результат программой. Прежде чем отвечать владельцу, "
            "посмотри его сам:\n" + "\n".join(lines) +
            "\nНашёл ошибку — исправь и проверь снова. В ответе одной строкой «Проверил: …».")
    return f"{result if isinstance(result, str) else str(result)}{note}"


def register(ctx):
    ctx.register_hook("transform_tool_result", transform)
