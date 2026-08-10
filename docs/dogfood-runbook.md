# Dogfood loop: repo → live instance

A maintainer runbook for updating a live Hermes instance to the latest merged
`main` of this plugin.

This plugin is self-contained: the plugin directory **is** the artifact. There
is deliberately **no `install.py`** — the installer is `hermes plugins install`
(a git clone under `~/.hermes/plugins/gateway-enrich/`) plus
`hermes plugins enable`. Updates are a git pull, not a re-install.

## 1. Update procedure

1. **Pre-flight.** Confirm the PR is merged to `main`. Then confirm the
   installed clone is clean:

   ```sh
   git -C ~/.hermes/plugins/gateway-enrich status --short
   ```

   A dirty installed clone means someone hand-patched live. Inspect the diff,
   upstream it via a PR, or discard it — never leave it.

2. **Pull.** Update the installed clone to merged `main`:

   ```sh
   hermes plugins update gateway-enrich
   ```

   (Equivalent to `git -C ~/.hermes/plugins/gateway-enrich pull --rebase origin main`.)

3. **Restart the gateway.**

   ```sh
   hermes gateway restart
   ```

   This **must** be run from a shell **outside** the gateway's own process
   tree. Agent sessions running *inside* the gateway cannot restart it: the
   command is blocked by design, because `SIGTERM` would propagate to the
   calling process. If you are an agent operating inside the gateway, hand
   this single command to the operator.

4. **Enable state survives restarts** — it lives in the instance config list,
   not the process. Re-enabling after an update is unnecessary. The
   `--allow-tool-override` grant is **not** required: the plugin ships no
   tools, only a `pre_gateway_dispatch` hook.

## 2. Verification — four layers, in order, all must pass

1. **Identity.** Every installed file is byte-identical to the working clone
   at merged `main`:

   ```sh
   diff -r --brief ~/.hermes/plugins/gateway-enrich/ <working-clone>/ \
     --exclude='.git' --exclude='__pycache__' --exclude='*.pyc'
   ```

   Replace `<working-clone>` with your checkout path. The check compares the
   whole tree recursively, so any added, missing, or stale file shows up;
   `Only in` lines or `differ` lines mean live drift — investigate, do not
   leave it. The excludes keep version-control and Python bytecode artifacts
   out of the comparison.

2. **Compile.**

   ```sh
   python3 -m py_compile ~/.hermes/plugins/gateway-enrich/__init__.py
   ```

3. **Discovery.**

   ```sh
   hermes plugins list --plain
   ```

   Expect a row: `enabled  git  1.0.0  gateway-enrich` (version per
   `plugin.yaml`).

4. **Live behavior smoke.** In a test Discord thread and a non-thread
   channel:

   - Post one message in a **test thread** → the agent-visible text begins
     with `[thread: <thread name>]`.
   - Post in a **non-thread channel** → no stamp.
   - Post a **`/`-prefixed command** inside a thread → the command still
     executes (the stamp must never bury the slash).

   A message dispatch that crashes or drops is a **fail-open violation** —
   the plugin must never break dispatch.

## 3. Sandbox pre-merge validation

Run both before opening an update PR:

1. **Repo test suite** (stdlib only):

   ```sh
   python3 tests/fake_event_test.py
   ```

2. **Disposable-home install test:**

   ```sh
   HERMES_HOME=/tmp/<scratch> hermes plugins install <repo-url> --enable
   HERMES_HOME=/tmp/<scratch> hermes plugins list
   ```

   Use a `file://` URL to the local checkout for branch testing —
   `hermes plugins update` only pulls the default branch.

## 4. Pitfalls

- **In-process restart is blocked.** `hermes gateway restart` run from inside
  the gateway process tree is refused by design. Use an outside shell, or
  hand the command to the operator.
- **A dirty installed clone is drift, not state.** Investigate, upstream, or
  discard — never treat it as intended.
- **`hermes plugins update` only pulls the default branch.** For pre-merge
  branch testing, install into a sandbox home via a `file://` URL instead.
- **Never hand-edit the installed clone.** Upstream changes via PR, or
  discard the local edit. Live edits are drift.
