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
   It copies the skill into ~/.codex/skills + ~/.agents/skills,
   registers the UserPromptSubmit hook in ~/.codex/hooks.json (merge, keep
   my existing hooks), enables the skills+hooks features in
   ~/.codex/config.toml, and installs the `clearjev` command into
   ~/.local/bin. Do not write system-wide anywhere outside ~/.local/bin.
3. If the script asks for TYPESAFE_API_KEY, leave it empty (Enter) — I will
   provide the key manually later.
4. At the end, run:
   python3 ~/.codex/skills/clearjev-router/scripts/jev_route.py --check
   and show me the full output.
5. Tell me my next two manual steps (Codex restart + hook trust in /hooks +
   new session), but do not attempt them for me.

If any step needs permission (shell, network), ask for approval, do not
bypass it. If install.sh cannot run on this system, tell me, and perform
its steps manually one by one with the same effect.
```

## Manual steps after the prompt (yours)

1. **API key** (if you skipped it):
   ```bash
   export TYPESAFE_API_KEY="your_key_here"
   ```
2. **Verify**: `clearjev status` (if `command not found`:
   `export PATH="$HOME/.local/bin:$PATH"`), then `clearjev check`.
3. **Restart Codex** (CLI: quit + `codex` again; App: a new chat is not
   enough, restart the App too on first install).
4. **Hook trust**: in the CLI, `/hooks` → `ClearJev routing` / `jev_route.py`
   (`UserPromptSubmit`) → approve. Without trust, Codex silently skips the
   hook.
5. Open a **new session**, then a test prompt:
   `Implement Stripe subscriptions with monthly/yearly plans, webhooks and access control.`
   Expected: a `ClearJev routing` status + routing block (`Model: gpt-6-sol · ...`).

## Controlling it from chat (after install)

- Automatic: type nothing special, every prompt gets routed.
- `$clearjev-router` — explicit skill invocation.
- `noroute: ...` — one prompt without routing.
- `reroute: ...` — correct a wrong decision.
- You can also ask the agent in words: "Turn off ClearJev routing"
  (the agent then runs `clearjev off` in a shell — needs shell rights;
  if it refuses, use the terminal: `clearjev off` / `on`).

## If it does not work (check in order)

1. Is it there? `ls ~/.codex/skills/clearjev-router/SKILL.md`
2. What does `clearjev status` say?
3. Is the hook trusted in `/hooks`? (Most common cause.)
4. Did the test run in a new session?
5. No other skill named `clearjev-router`?

## Uninstall (fully reversible)

```bash
clearjev off
rm -rf ~/.codex/skills/clearjev-router ~/.agents/skills/clearjev-router
rm -f ~/.local/bin/clearjev
```

then remove the `jev_route.py` entry from the `UserPromptSubmit` list in
`~/.codex/hooks.json` (or disable it in `/hooks`).
