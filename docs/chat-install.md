# Installing ClearJev via chat (Codex CLI chatbot)

> No terminal `curl` needed. Open the Codex CLI (`codex` command in your
> terminal) and paste the prompt below as-is. The AI will walk through the
> installation — you only need to grant approvals, then trust the hook and
> open a new session at the end (only you can do that).
>
> Prerequisites: Codex CLI + `python3` on the machine. A Jev API key is nice
> to have (https://console.typesafe.ai/keys), but the install works without
> it (heuristic fallback mode).

## Copy-paste prompt

```text
Install the ClearJev skill and hook on my machine:

1. Clone the https://github.com/huncijr/ClearJev repo into a temp folder
   (a shallow clone is enough: git clone --depth 1).
2. Run plugins/clearjev-router/scripts/install.sh from the clone.
   It copies a self-contained runtime into ~/.codex/clearjev-runtime,
   installs the discoverable `clearjev` skill into ~/.codex/skills/clearjev
   + ~/.agents/skills/clearjev, registers the UserPromptSubmit hook in
   ~/.codex/hooks.json (merge with backup, keep my existing hooks), installs
   the `clearjev` command into ~/.local/bin, and adds /prompts:clearjev-*
   aliases under ~/.codex/prompts. Do not write system-wide anywhere
   outside ~/.local/bin.
3. If the script asks for TYPESAFE_API_KEY, leave it empty (Enter) — I will
   provide the key manually later.
4. At the end, run:
   python3 ~/.codex/clearjev-runtime/scripts/jev_route.py status
   and show me the full output.
5. Tell me my next two manual steps (Codex restart + hook trust in /hooks +
   new session), but do not attempt them for me.

If any step needs permission (shell, network), ask for approval, do not
bypass it. If install.sh cannot run on this system, tell me, and perform
its steps manually one by one with the same effect.
```

## Manual steps after the prompt (yours)

1. **API key** (if you skipped it — terminal preferred so the key stays out
   of chat history):
   ```bash
   clearjev key set 'your_key_here'
   ```
   or in chat: `$clearjev key set 'your_key_here'` (the skill warns once
   that chat history retains the key).
2. **Verify**: `clearjev status` (if `command not found`:
   `export PATH="$HOME/.local/bin:$PATH"`), then `clearjev check`.
3. **Restart Codex** (CLI: quit + `codex` again; App: a new chat is not
   enough, restart the App too on first install).
4. **Hook trust**: in the CLI, `/hooks` → `ClearJev routing` / `jev_route.py`
   (`UserPromptSubmit`) → approve. Without trust, Codex silently skips the
   hook.
5. Open a **new session**, then a test prompt:
   `Implement Stripe subscriptions with monthly/yearly plans, webhooks and access control.`
   Expected: a `ClearJev routing` status + routing block
   (`Recommended model: gpt-5.6-sol · ...`).

## Controlling it from chat (after install)

- Automatic: type nothing special, every prompt gets a routing recommendation.
- `$clearjev` + plain language — the skill acts immediately, in any language:
  `$clearjev kapcsold ki`, `$clearjev add hozzá a gpt-6-sol modellt`,
  `$clearjev mi a státusz`. A bare `$clearjev` only returns a numbered
  fallback menu.
- `/prompts:clearjev`, `/prompts:clearjev-on`, `/prompts:clearjev-off`,
  `/prompts:clearjev-add`, `/prompts:clearjev-remove`, `/prompts:clearjev-key`
  — deprecated-but-working CLI/IDE aliases for the same actions.
- `@ClearJev ...` — refused in the Codex App (skill is CLI-only), and the
  hook itself stays silent there too: no routing, no usage spent. CLI-only
  product; in the App use Codex natively.
- `noroute: ...` — one prompt without routing.
- `reroute: ...` — correct a recommendation conversationally (hook stays
  silent for that message by design).
- Real model switching in the running session is always native `/model`.
  `clearjev run '<prompt>'` (shell or chat) opens a new CLI session with
  Jev's recommended model and reasoning effort.

## If it does not work (check in order)

1. Is it there? `ls ~/.codex/clearjev-runtime/scripts/jev_route.py`
   and `ls ~/.codex/skills/clearjev/SKILL.md`
2. What does `clearjev status` say?
3. Is the hook trusted in `/hooks`? (Most common cause.)
4. Did the test run in a new session?
5. No other skill named `clearjev`?
6. `clearjev models list` — is any model enabled for your catalog?

## Uninstall (fully reversible)

```bash
~/.codex/clearjev-runtime/scripts/uninstall.sh            # keeps key+state
~/.codex/clearjev-runtime/scripts/uninstall.sh --purge   # also deletes key+state
```

This removes the runtime, skill, CLI, prompt aliases, and only the
ClearJev-owned hook entries. Manage hook trust entries in `/hooks`.
