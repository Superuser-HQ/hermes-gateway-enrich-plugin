#!/usr/bin/env python3
"""Standalone stdlib test for the gateway-enrich plugin.

Runnable as: python3 tests/fake_event_test.py
Prints PASS/FAIL lines and exits nonzero on any failure.
Uses duck-typed fakes (types.SimpleNamespace) — no Hermes imports needed.
"""
import importlib.util
import os
import sys
import types

# Load the plugin's __init__.py directly as the "gateway_enrich" module,
# since the containing directory name has hyphens and is not importable.
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INIT_PATH = os.path.join(_PLUGIN_DIR, "__init__.py")
_spec = importlib.util.spec_from_file_location("gateway_enrich", _INIT_PATH)
gateway_enrich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gateway_enrich)


class FakePlatform:
    """Enum-like with a .value attribute, mirroring source.platform."""

    def __init__(self, value):
        self.value = value


def make_event(platform="discord", chat_type="thread", text="hello world",
               chat_name=None, thread_id=None, raw_channel=None):
    """Build a duck-typed MessageEvent fake."""
    source = types.SimpleNamespace(
        platform=FakePlatform(platform),
        chat_type=chat_type,
        chat_name=chat_name,
        thread_id=thread_id,
        user_id="u1",
    )
    raw_message = None
    if raw_channel is not None:
        raw_message = types.SimpleNamespace(channel=raw_channel)
    return types.SimpleNamespace(
        source=source,
        text=text,
        raw_message=raw_message,
    )


class FakeCtx:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, cb):
        self.hooks[name] = cb


results = []


def check(label, cond):
    results.append((label, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + label)


def main():
    # Verify register() wires the hook.
    ctx = FakeCtx()
    gateway_enrich.register(ctx)
    cb = ctx.hooks.get("pre_gateway_dispatch")
    check("register wires pre_gateway_dispatch", cb is not None)

    # (a) Discord thread event with a real channel name.
    chan_a = types.SimpleNamespace(name="demo-research-thread", parent_id="123", id="456")
    ev_a = make_event(text="hello world", raw_channel=chan_a)
    out_a = cb(event=ev_a)
    check(
        "(a) thread event rewrites with bare channel name",
        out_a == {"action": "rewrite", "text": "[thread: demo-research-thread]\nhello world"},
    )

    # (b) Non-thread (group) → None.
    ev_b = make_event(chat_type="group", text="hi")
    out_b = cb(event=ev_b)
    check("(b) non-thread passes through", out_b is None)

    # (c) Thread with command text "/new" → None.
    ev_c = make_event(text="/new", raw_channel=chan_a)
    out_c = cb(event=ev_c)
    check("(c) command text not stamped", out_c is None)

    # (d) No raw_message; derive from chat_name.
    ev_d = make_event(
        text="hello",
        chat_name="My Guild / #parent / fallback-thread-name",
    )
    out_d = cb(event=ev_d)
    check(
        "(d) fallback chat_name derives bare name",
        out_d == {"action": "rewrite", "text": "[thread: fallback-thread-name]\nhello"},
    )

    # (e) Telegram thread → None (platform gate).
    ev_e = make_event(platform="telegram", chat_type="thread", text="hi", raw_channel=chan_a)
    out_e = cb(event=ev_e)
    check("(e) non-discord platform passes through", out_e is None)

    # (f) raw_message present but channel.name empty; fallback to chat_name.
    chan_f = types.SimpleNamespace(name="", parent_id="1", id="2")
    ev_f = make_event(
        text="hi",
        chat_name="Guild / ForumName / forum thread",
        raw_channel=chan_f,
    )
    out_f = cb(event=ev_f)
    check(
        "(f) empty channel.name falls back to chat_name tail",
        out_f == {"action": "rewrite", "text": "[thread: forum thread]\nhi"},
    )

    # (g) event=None → None, no crash.
    out_g = cb(event=None)
    check("(g) event=None does not crash", out_g is None)

    # (h) Static check: __init__.py source contains none of the network libs.
    init_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "__init__.py",
    )
    with open(init_path, "r", encoding="utf-8") as fh:
        src = fh.read()
    forbidden = ["urllib", "requests", "aiohttp", "httpx", "socket"]
    hits = [w for w in forbidden if w in src]
    check("(h) no network imports in __init__.py (" + ",".join(forbidden) + ")", not hits)

    # Summary.
    failed = [r for r in results if not r[1]]
    print()
    print("PASSED: %d / %d" % (len(results) - len(failed), len(results)))
    if failed:
        print("FAILURES:")
        for label, _ in failed:
            print("  - " + label)
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
