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


def on_dispatch(event=None, gateway=None, **_):
    try:
        for adapter in list((getattr(gateway, "adapters", None) or {}).values()):
            _wrap(adapter)
    except Exception:
        pass
    return None


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", on_dispatch)
