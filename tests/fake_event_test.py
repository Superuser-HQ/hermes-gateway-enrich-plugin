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

    # (i) Thread name with control chars (newline injection attempt).
    #     channel.name = 'injected]\nfake-instruction' → newline collapsed to
    #     one space, ']' preserved. Stamp line must be a single line.
    chan_i = types.SimpleNamespace(
        name="injected]\nfake-instruction", parent_id="p1", id="t1"
    )
    ev_i = make_event(text="hello world", raw_channel=chan_i)
    out_i = cb(event=ev_i)
    expected_i = "[thread: injected] fake-instruction]\nhello world"
    check(
        "(i) control-char thread name collapsed, ] preserved",
        out_i == {"action": "rewrite", "text": expected_i},
    )
    # Stamp line (first line) must be a single line — no embedded newline.
    if out_i is not None:
        stamp_line_i = out_i["text"].split("\n", 1)[0]
    else:
        stamp_line_i = ""
    check(
        "(i) stamp line is a single line",
        "\n" not in stamp_line_i and "\r" not in stamp_line_i,
    )

    # (j) channel.name all control chars, chat_name empty → fail-open None.
    chan_j = types.SimpleNamespace(name="\n\r", parent_id="p2", id="t2")
    ev_j = make_event(text="hi", chat_name="", raw_channel=chan_j)
    out_j = cb(event=ev_j)
    check("(j) blank-after-sanitize fails open to None", out_j is None)

    # (k) DEL and C1 control chars in thread name are collapsed/stripped.
    #     channel.name = 'bad\x7fname\x9b' → DEL collapses to a space between
    #     words; trailing CSI char collapses then strips.
    chan_k = types.SimpleNamespace(name="bad\x7fname\x9b", parent_id="p3", id="t3")
    ev_k = make_event(text="hello world", raw_channel=chan_k)
    out_k = cb(event=ev_k)
    expected_k = "[thread: bad name]\nhello world"
    check(
        "(k) DEL+C1 thread name collapsed to spaces",
        out_k == {"action": "rewrite", "text": expected_k},
    )
    # Stamp line (first line) must contain no control chars at all.
    if out_k is not None:
        stamp_line_k = out_k["text"].split("\n", 1)[0]
    else:
        stamp_line_k = ""
    check(
        "(k) stamp line has no C0/DEL/C1 control chars",
        all(ord(c) >= 0x20 and not 0x7f <= ord(c) <= 0x9f for c in stamp_line_k),
    )

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
