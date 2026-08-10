"""gateway-enrich — stamp inbound Discord thread messages with a thread-name line.

WHAT IT DOES
  This Hermes Agent plugin registers the ``pre_gateway_dispatch`` hook. The
  gateway fires that hook once per inbound message, *before* auth/dispatch,
  and passes the live ``MessageEvent``. For messages whose source is a Discord
  thread (``platform == discord`` and ``chat_type == thread``) the callback
  rewrites the message text to prepend a single stamp line::

      [thread: <bare-thread-name>]
      <original text>

  Non-thread messages, non-Discord platforms, and slash-command texts are left
  untouched. The rewrite is returned as ``{"action": "rewrite", "text": ...}``
  and the gateway applies it via ``dataclasses.replace(event, text=new_text)``
  before command parsing continues.

HOOK CONTRACT
  - ``register(ctx)`` calls ``ctx.register_hook("pre_gateway_dispatch", _cb)``.
  - ``_cb(event=None, gateway=None, session_store=None, **kwargs)`` is invoked
    synchronously inside the gateway process (stdlib only, no asyncio).
  - Return ``{"action": "rewrite", "text": str}`` to replace text;
    ``None`` to let dispatch proceed normally. ``{"action": "skip"}`` is
    FORBIDDEN by this plugin — we never drop a message.

DESIGN RULES
  - **Fail-open.** Every step is wrapped in try/except; any exception returns
    ``None`` so dispatch is never broken by this plugin.
  - **Event-derived name.** The bare thread name is read from the event
    itself (``raw_message.channel.name`` when the channel looks like a real
    thread, else a substring of ``source.chat_name``). No Discord REST lookup,
    no cache, no TTL — the name already rides on the event.
  - **No network.** Only the Python standard library is imported; no network
    client modules of any kind and no environment reads.
  - **Commands never stamped.** Because the gateway re-parses text after the
    rewrite and ``event.is_command()`` checks ``text.lstrip().startswith("/")``,
    stamping a command would break ``/new`` / ``/reset`` in threads. Any text
    whose stripped form starts with ``/`` is passed through unchanged.
  - **Only Discord threads.** Platform and chat_type are gated first; every
    other message shape is a fast ``None``.
  - **Sanitized name.** C0, DEL, and C1 control characters in the
    platform-provided thread name are collapsed to single spaces so a crafted
    name can't break out of the stamp line; ``]`` is preserved deliberately —
    the vector was the newline, and the stamp is human-readable, not
    machine-parsed.

Python 3.11 compatible.
"""

import re

__version__ = "1.0.0"


def register(ctx):
    """Register the pre_gateway_dispatch hook with the Hermes plugin context."""
    ctx.register_hook("pre_gateway_dispatch", _pre_gateway_dispatch)


def _pre_gateway_dispatch(event=None, gateway=None, session_store=None, **kwargs):
    """Rewrite inbound Discord thread messages to prepend a thread-name stamp.

    Returns a rewrite dict for Discord thread messages, or ``None`` for
    everything else / on any error (fail-open).
    """
    try:
        # No event → nothing to do.
        if event is None:
            return None

        source = getattr(event, "source", None)
        text = getattr(event, "text", None)
        # Need a source and non-empty text to even consider stamping.
        if source is None or not text:
            return None

        # Platform gate: only Discord.
        platform = getattr(source, "platform", None)
        if getattr(platform, "value", None) != "discord":
            return None

        # Thread gate: only thread chat_type.
        if getattr(source, "chat_type", None) != "thread":
            return None

        # Command guard: never stamp slash-command text — the gateway re-parses
        # text after the rewrite and a leading "/" would be buried under the
        # stamp line, breaking /new /reset etc. in threads.
        if text.lstrip().startswith("/"):
            return None

        name = _resolve_thread_name(event, source)
        name = _sanitize_name(name)
        if not name:
            return None

        return {"action": "rewrite", "text": f"[thread: {name}]\n{text}"}
    except Exception:
        # Fail-open: never break dispatch.
        return None


def _resolve_thread_name(event, source):
    """Resolve the bare thread name from the event, preferring the channel.

    Order:
      1. ``raw_message.channel.name`` — trusted only when the channel looks
         like a real thread (has ``parent_id``) or its id matches
         ``source.thread_id``.
      2. Fallback: substring of ``source.chat_name`` after the last ``" / "``,
         with a leading ``#`` stripped.
    Returns the name string, or ``None`` if nothing usable was found.
    """
    # 1. Try the raw message channel.
    raw = getattr(event, "raw_message", None)
    channel = getattr(raw, "channel", None) if raw is not None else None
    name = getattr(channel, "name", None) if channel is not None else None

    if name:
        looks_like_thread = hasattr(channel, "parent_id") or (
            str(getattr(channel, "id", "")) == str(getattr(source, "thread_id", ""))
        )
        if looks_like_thread:
            return name

    # 2. Fallback: derive from the formatted chat_name.
    chat_name = getattr(source, "chat_name", None)
    if chat_name:
        # chat_name looks like "Guild / #parent / Thread Name" (or variants).
        # The bare thread name is the substring after the last " / ".
        if " / " in chat_name:
            tail = chat_name.rsplit(" / ", 1)[-1].strip()
        else:
            tail = chat_name.strip()
        # Strip a leading "#" (slash-command / parent-channel prefix).
        if tail.startswith("#"):
            tail = tail[1:]
        if tail:
            return tail

    return None


def _sanitize_name(name):
    """Collapse C0, DEL, and C1 control chars in a thread name to single spaces.

    A platform-provided thread name containing control characters (notably
    newlines) could break out of the single ``[thread: <name>]`` stamp line
    and inject name-controlled text into the message body. This collapses any
    run of C0, DEL, and C1 control characters (``\\x00``-``\\x1f``,
    ``\\x7f``, and ``\\x80``-``\\x9f``, which includes ``\\r`` and ``\\n``)
    to a single space, then strips leading/trailing whitespace.

    Returns the sanitized string, or ``None`` if the result is empty/blank
    (so the caller's fail-open ``if not name`` path engages).
    """
    if not name:
        return None
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]+", " ", name).strip()
    return cleaned if cleaned else None
