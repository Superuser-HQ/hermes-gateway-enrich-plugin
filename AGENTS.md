# AGENTS.md — contributor notes for gateway-enrich

## Repo posture

This is a **public** repo containing **generic** plugin content only. There is
nothing organization-specific in here: no internal project names, no internal
identifiers, no secrets, no references to internal infrastructure.

**Hard rule:** if this plugin ever grows organization-internal features
(internal-only consumers, internal naming conventions, internal integrations),
the repo **must be flipped private before that work continues**. Do not push
internal-only content to a public repo, even temporarily.

## Fail-open is a hard rule

The `pre_gateway_dispatch` callback must **never** break message dispatch. The
entire callback body is wrapped in try/except and returns `None` on any
exception. Preserve this. Do not narrow the try/except to "known" cases — new
failure modes must continue to fail open.

Likewise, the plugin must **never** return `{"action": "skip"}`. We rewrite or
we pass through; we never drop a message.

## Do not touch Hermes core

This plugin runs *inside* the gateway process and interacts with it only via
the documented `pre_gateway_dispatch` hook contract. Do not patch, monkey-patch,
or otherwise reach into Hermes internals from here. If the hook contract is
insufficient, raise it upstream rather than working around it in this plugin.

## No network, no credentials

The plugin imports only the Python standard library and performs no network I/O.
The thread name is read from the event itself. Do not add `urllib`, `requests`,
`aiohttp`, `httpx`, `socket`, or any HTTP client. Do not read secrets, env
vars, or config files. Do not add a cache or TTL — none is needed.

## Leak gate

Before any push, scan the entire repo (excluding `.git/`) for internal
references: internal project or vault codenames, internal agent-orchestration
terminology, issue-tracker ticket IDs (e.g. `ABC-123` style), secret-reference
URIs, internal chat-platform guild/channel/thread IDs, internal host paths.
The scan **must return zero hits**.

The exact banned-pattern list is maintained outside this repo (it itself
contains internal names, so it must never be committed here). If you are
unsure whether a string counts as internal, ask the maintainer team before
pushing. The org name `Superuser-HQ` is allowed (author, LICENSE, install
command) — it hosts the repo and is not a leak.

## Commands never stamped

The gateway re-parses text after applying a rewrite, and `event.is_command()`
checks `text.lstrip().startswith("/")`. Stamping a `/`-prefixed command would
bury the slash under the stamp line and break `/new` / `/reset` in threads.
The command guard is mandatory.
