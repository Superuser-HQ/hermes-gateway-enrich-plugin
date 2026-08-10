# gateway-enrich

A Hermes Agent plugin that stamps inbound **Discord thread** messages with a
`[thread: <name>]` line via the `pre_gateway_dispatch` hook, so the agent sees
the thread name directly in the message text — no channel-info lookup required.

This is useful for research ingestion workflows that resolve their subject from
a Discord thread name: with the name already in the text, those workflows can
read it with zero tool calls.

## What it does

For every inbound message, the Hermes gateway fires `pre_gateway_dispatch`
*before* auth/dispatch. This plugin's callback:

- Passes through non-Discord messages, non-thread messages, and slash-command
  texts (`/new`, `/reset`, …) **unchanged**.
- For Discord thread messages, rewrites the text to:

  ```
  [thread: <bare-thread-name>]
  <original text>
  ```

The bare thread name is read from the event itself (`raw_message.channel.name`
when available, else derived from `source.chat_name`). No network, no
credentials, no Discord REST calls, no cache.

## Install

From the public repo:

```sh
hermes plugins install Superuser-HQ/hermes-gateway-enrich-plugin
hermes plugins enable gateway-enrich
```

Reloading the gateway picks it up — no separate restart of long-running
sessions is required; the hook is registered on plugin load.

## Example

A message arriving in a Discord thread named `demo-research-thread` with body
`summarize the latest arxiv papers on diffusion` is rewritten to:

```
[thread: demo-research-thread]
summarize the latest arxiv papers on diffusion
```

The agent then sees both the stamp and the original text. Non-thread messages
and commands are unaffected.

## Design notes

- **Name read from the event.** The thread name already rides on the inbound
  `MessageEvent` (on `raw_message.channel.name`, with a fallback to a substring
  of `source.chat_name`). The plugin does zero network I/O.
- **No network / no cache.** Stdlib only. No `urllib`, `requests`, `aiohttp`,
  `httpx`, or `socket`. No environment variables, no config reads.
- **Fail-open.** Every step is wrapped in try/except; any exception returns
  `None` so dispatch never breaks because of this plugin.
- **Commands never stamped.** Because the gateway re-parses text after the
  rewrite, stamping a `/`-prefixed command would break text commands in
  threads. Command-like texts are passed through untouched.
- **Only Discord threads.** Platform (`discord`) and `chat_type` (`thread`)
  are gated first; everything else is a fast pass-through.

## License

MIT — see [LICENSE](LICENSE).
