"""busy-ack-ru: when the owner writes while the agent is busy, they get one short
Russian «принял» instead of silence (Vika 05.11.2026); the original busy handling runs."""
import asyncio, importlib.util, os, types

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("ba", os.path.join(HERE, "__init__.py"))
ba = importlib.util.module_from_spec(spec); spec.loader.exec_module(ba)

sent, orig_calls = [], []

class Adapter:
    async def send(self, chat_id, content, reply_to=None, metadata=None):
        sent.append((chat_id, content))
    def set_busy_session_handler(self, h):
        self._busy_session_handler = h

async def orig(event, key):
    orig_calls.append(key); return True

ad = Adapter(); ad.set_busy_session_handler(orig)
gw = types.SimpleNamespace(adapters={"telegram": ad})
ev = types.SimpleNamespace(source=types.SimpleNamespace(chat_id="42", thread_id=None))

# first normal message: plugin wraps the busy handler, dispatch untouched
assert ba.on_dispatch(event=ev, gateway=gw) is None
assert ad._busy_session_handler is not orig
# wrapping twice must not double-wrap
w = ad._busy_session_handler; ba.on_dispatch(event=ev, gateway=gw); assert ad._busy_session_handler is w

async def run():
    assert await ad._busy_session_handler(ev, "k1") is True     # original result kept
    await ad._busy_session_handler(ev, "k1")                     # within cooldown -> no 2nd ack
asyncio.run(run())
assert orig_calls == ["k1", "k1"], orig_calls
assert len(sent) == 1 and sent[0][0] == "42" and "Принял" in sent[0][1], sent

# handler set later by the gateway (reconnect) gets wrapped again on next dispatch
ad.set_busy_session_handler(orig); ba.on_dispatch(event=ev, gateway=gw)
assert ad._busy_session_handler is not orig

# no gateway / odd adapters never break dispatch
assert ba.on_dispatch(event=ev, gateway=None) is None
assert ba.on_dispatch(event=ev, gateway=types.SimpleNamespace(adapters={"x": object()})) is None
print("OK: busy-ack-ru tests passed")
