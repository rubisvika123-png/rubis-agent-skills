"""busy-ack-ru — owner writes while the agent is busy -> one short Russian «принял» (Vika 05.11.2026).

Quiet mode turns Hermes' own busy ack off (it is English, with emoji and iteration
counters), so a student who writes «ну что там?» mid-task hears nothing for minutes and
thinks the agent died. This plugin wraps each adapter's busy-session handler: the original
handling (steer / queue / interrupt) runs unchanged, then one Russian line is sent, at most
once per COOLDOWN per session. Wrapping happens lazily on the first normal message
(pre_gateway_dispatch is the only hook that hands us the gateway). Never raises.
"""
import logging, time

log = logging.getLogger("busy-ack-ru")

TEXT = "Принял. Доделываю текущую задачу, твоё сообщение учту по ходу."
COOLDOWN = 120
_last = {}


def _wrap(adapter):
    orig = getattr(adapter, "_busy_session_handler", None)
    if orig is None or getattr(orig, "_busy_ack_ru", False) or not hasattr(adapter, "send"):
        return

    async def wrapped(event, session_key):
        result = await orig(event, session_key)
        try:
            now = time.time()
            if now - _last.get(session_key, 0) >= COOLDOWN:
                _last[session_key] = now
                src = getattr(event, "source", None)
                meta = {"thread_id": src.thread_id} if getattr(src, "thread_id", None) else None
                await adapter.send(src.chat_id, TEXT, metadata=meta)
                log.info("busy-ack-ru: ack sent for %s", session_key)
        except Exception:
            pass
        return result

    wrapped._busy_ack_ru = True
    adapter._busy_session_handler = wrapped
    log.info("busy-ack-ru: wrapped busy handler of %s", type(adapter).__name__)


# 22.11 (Ольга Мирай: «что с лимитами?» → «Your request was not processed…»): Hermes' own failure notices are
# hard-coded English. The owner does not read English — send the same meaning in Russian.
RU_NOTICES = {
    "Your request was not processed. Send it again if you still want me to carry it out.":
        "Не получилось ответить: чаще всего это значит, что закончился лимит ChatGPT или пропала связь. "
        "Напишите это сообщение ещё раз чуть позже.",
    "This turn did not complete. Some actions may already have run; verify their effects before resending.":
        "Задача прервалась на середине. Часть действий могла уже выполниться — напишите «что успел сделать?», "
        "я проверю и доделаю.",
    "An automated delivery was interrupted and was not run again. Some actions may already have run; verify their effects.":
        "Задача по расписанию прервалась и не перезапускалась. Часть действий могла уже выполниться.",
}


def ru_text(text):
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    for en, ru in RU_NOTICES.items():
        if stripped.startswith(en):
            return ru + stripped[len(en):]
    return text


def _wrap_send(adapter):
    orig = getattr(adapter, "send", None)
    if orig is None or getattr(orig, "_ru_notices", False):
        return

    async def send(chat_id, content=None, *args, **kwargs):
        try:
            content = ru_text(content)
        except Exception:
            pass
        return await orig(chat_id, content, *args, **kwargs)

    send._ru_notices = True
    adapter.send = send


def on_dispatch(event=None, gateway=None, **_):
    try:
        for adapter in list((getattr(gateway, "adapters", None) or {}).values()):
            _wrap(adapter)
            _wrap_send(adapter)
        # 17.11: one gateway can serve several profiles; their adapters are kept per profile
        for by_platform in list((getattr(gateway, "_profile_adapters", None) or {}).values()):
            for adapter in list((by_platform or {}).values()):
                _wrap(adapter)
                _wrap_send(adapter)
    except Exception:
        pass
    return None


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", on_dispatch)
