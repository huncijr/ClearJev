# ClearJev agent install guide (Codex Hub)

> Read this file when the user asks you to download, install, or set up the
> ClearJev agent skill from Codex Hub (or the ClearJev repo/marketplace).
> Follow it step by step. Ask for approval before running shell or network
> commands, and never bypass approvals.

## 1. What you are installing

ClearJev is automatic pre-prompt routing for Codex: a `UserPromptSubmit`
hook judges every prompt with the TypeSafe Jev API and switches the thread
to the chosen model and reasoning effort through the local Codex app-server.
A `clearjev` chat skill (`$clearjev` in Codex CLI) controls
on/off, API key, models, and reasoning levels. The skill is CLI-only and
refuses on other hosts; in the App the hook stays advisory and plain
`clearjev on|off|status` messages still work hook-side.

## 2. Install from Codex Hub (marketplace)

```bash
codex plugin marketplace add huncijr/ClearJev
```

Then install the `clearjev-router` plugin from the `/plugins` browser (CLI)
or the Plugins tab (App). A marketplace install alone is NOT complete:
it does not install the shell CLI, the self-contained runtime, or the
`/prompts:` aliases, and it cannot collect the API key. Continue with
step 3.

## 3. Complete the installation (required)

Run the shell installer on the same machine. POSIX:

```bash
curl -fsSL https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.ps1 | iex
```

The installer copies a self-contained runtime to
`~/.codex/clearjev-runtime`, installs the discoverable `clearjev` skill,
registers the hook in `~/.codex/hooks.json` (merged with backup), installs
the `clearjev` command into `~/.local/bin`, and adds `/prompts:clearjev-*`
aliases. It ends with a `cli self-check: OK` line — if you see a WARNING
instead, stop and report it.

Offline alternative (no pipe): shallow-clone
`https://github.com/huncijr/ClearJev`, then run
`plugins/clearjev-router/scripts/install.sh` from the clone.

## 4. API key

Get a key at https://console.typesafe.ai/keys. Preferred (keeps the key out
of chat history), in a private terminal:

```bash
clearjev key set 'THE_KEY'
```

Only if the user explicitly asks for chat setup: `$clearjev key set '...'`
(CLI only), warn once that chat history retains the key,
and never print the key back. Without a key the layer works in labeled
heuristic-fallback mode.

## 5. Manual steps that only the user can do

Tell the user, do not attempt them:

1. Restart Codex (CLI: quit + start; App: restart the App on first install).
2. Trust the hook in `/hooks` (`ClearJev routing` / `jev_route.py`).
3. Open a new session/chat.

## 6. Verify

```bash
clearjev status
clearjev check
```

`check` must print `OK` with a valid key (live Jev ping). Then send a test
prompt, e.g. `Explain dependency injection in TypeScript.` Expect a
`ClearJev routing` status and a block ending in
`Switched this session to gpt-5.6-luna (low)` — and the session model must
actually change. A `Switch failed (<reason>)` line is an honest, valid
outcome: the session kept its previous model.

Chat control checks: `$clearjev off` (next prompt: no routing block),
`$clearjev on` (block returns), `$clearjev models list`. Where the agent
sandbox blocks shell commands (Desktop App bubblewrap), use the no-shell
path instead: type `clearjev off`, `clearjev on`, or `clearjev status` as a
plain message — the hook executes it itself.

## 7. CLI vs App differences

- CLI: automatic switching works through the local app-server daemon.
- Desktop App: do not install or enable the plugin there. The hook
  detects non-CLI hosts and stays completely silent — no Jev calls, no
  routing blocks, no usage spent. Plain `clearjev on|off|status` messages
  answer with a short CLI-only pointer. `clearjev run '<prompt>'` (CLI)
  remains the guaranteed pre-routed path.

## 8. If it does not work (check in order)

1. Runtime present? `ls ~/.codex/clearjev-runtime/scripts/jev_route.py`
2. Skill present? `ls ~/.codex/skills/clearjev/SKILL.md`
3. `clearjev status` output (routing, auto-switch, key, models)?
4. Hook trusted in `/hooks`?
5. Test run in a new session/chat?
6. Exact `Switch failed (...)` reason, if any?
