# Testing ClearJev — full matrix

Covers: testing from Codex CLI, full uninstall, re-download + retest in the
Codex App, and every method available to exercise the skill.

Prerequisites: Codex CLI (`codex --version`), `python3`. A Jev API key
(https://console.typesafe.ai/keys) is optional — without it you test the
labeled heuristic fallback; with it you test the real Jev path.

## Canonical test prompts

Use the same prompts every round so results are comparable:

| # | Prompt | Expected routing (fallback) |
|---|---|---|
| T1 | `Explain dependency injection in TypeScript.` | intent=explain, `gpt-6-luna`, low/medium, light |
| T2 | `Add a dark mode toggle to the settings page.` | intent=implement, `gpt-6-luna`, light |
| T3 | `Implement Stripe subscriptions with monthly/yearly plans, webhooks, subscription state sync and access control.` | intent=implement, `gpt-6-sol`, high, deep |
| T4 | `Redesign the backend to support 10x traffic without breaking customer data.` | intent=architect, `gpt-6-astra`, multi_phase |
| T5 | `Find why websocket connections randomly disconnect in production.` | intent=debug, `gpt-6-sol`, high |

With an API key the model/reasoning may differ slightly (Jev judgments beat
heuristics) — what matters is that a routing block appears and is sane.

## Round 1 — test from Codex CLI

1. Install (pick one method; try a different one in Round 3):
   - Installer: `curl -fsSL https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.sh | sh`
   - Chat: open `codex`, paste the prompt from `docs/chat-install.md`.
2. `clearjev status` → expect `routing: ON`. `clearjev check` → `OK` with
   key, `CHECK FAILED` (fallback note) without.
3. Restart the CLI, trust the hook in `/hooks`
   (`ClearJev routing` / `jev_route.py`, `UserPromptSubmit`), open a **new
   session**.
4. Send T1–T5 (one per message). Each answer must be preceded by the
   `ClearJev routing` status and a 3-line routing block. With a key the
   block header says `· jev`; without, `· heuristic fallback`.
5. Exercise the switch (stays in the CLI, no restart needed):
   - `clearjev off` (in a terminal) → next prompt: **no** routing status.
   - `clearjev on` → next prompt: routing block is back.
   - `noroute: T2 text...` → that one prompt skips routing.
   - Reply `reroute: this is actually a refactor` to a routed answer and
     confirm the agent continues with the corrected intent.

## Round 2 — full uninstall

Reverse the install completely, then prove nothing fires anymore:

```bash
clearjev off
rm -rf ~/.codex/skills/clearjev-router ~/.agents/skills/clearjev-router
rm -f ~/.local/bin/clearjev
```

Then remove the hook entry: open `/hooks` in the CLI and disable/remove the
`jev_route.py` entry (or delete the `UserPromptSubmit` block containing it
from `~/.codex/hooks.json` by hand).

Verify: new session → send T3 → **no** `ClearJev routing` status, and
`clearjev` is `command not found`. (`config.toml` feature lines may stay;
they are harmless.)

## Round 3 — re-download and retest in the Codex App

1. Reinstall using a **different** method than Round 1 (e.g. chat prompt if
   Round 1 was the installer, or `codex plugin marketplace add
   huncijr/ClearJev` + install from the Plugins tab).
2. Restart the App, approve the hook when asked, open a **new chat**.
3. Send T1–T5 again, compare routing blocks with Round 1 (same intents,
   same model families expected).
4. In-chat control check: type `noroute:` + T2 (skips once), then ask the
   agent in words: "Turn off ClearJev routing" (it should run `clearjev
   off` via shell — needs shell approval; if refused, that itself is a
   valid finding, fall back to the terminal).

## Methods to exercise the skill (agent-testing toolbox)

Seven methods, cheapest first. Use 1–2 during development, all of them
before a release:

1. **Direct hook call (no Codex at all)** — fastest iteration:
   `echo '{"prompt":"...","cwd":"."}' | python3
   plugins/clearjev-router/scripts/jev_route.py`
2. **Unit tests** — `python3 -m unittest discover -s tests -v` (15 tests,
   no network, hermetic on/off state via temp dirs).
3. **`clearjev status` / `clearjev check`** — on/off state, key presence,
   live Jev ping + fallback smoke test.
4. **Automatic hook path** — just write normal prompts in a Codex session;
   the `UserPromptSubmit` hook fires before every prompt.
5. **Explicit skill invocation** — type `$clearjev-router` in chat to force
   the skill (separates install problems from trigger problems).
6. **`codex exec` (non-interactive, scriptable)** — repeatable agent runs
   without the TUI, e.g.:
   `codex exec --skip-git-repo-check "Explain dependency injection in
   TypeScript."` — good for running T1–T5 unattended and diffing outputs.
7. **Install-method coverage** — verify each distribution path at least
   once: `install.sh` / `install.ps1`, chat prompt (`docs/chat-install.md`),
   marketplace (`codex plugin marketplace add huncijr/ClearJev`).

## What counts as PASS

- Routing block appears for T1–T5 in both CLI and App, intents correct.
- `off` silences it (zero Jev calls), `on` restores it, `noroute:` skips once.
- `--check` is `OK` with a valid key and honestly reports fallback without one.
- Uninstall leaves no trace: no status line, no block, no `clearjev` binary.
- Unit suite stays 15/15 green after any change.
