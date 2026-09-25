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
| T1 | `Explain dependency injection in TypeScript.` | intent=explain, `gpt-5.6-luna`, low, light |
| T2 | `Add a dark mode toggle to the settings page.` | intent=implement, cheap model (`gpt-5.6-luna`/`gpt-5.5`), light |
| T3 | `Implement Stripe subscriptions with monthly/yearly plans, webhooks, subscription state sync and access control.` | intent=implement, `gpt-5.6-sol`, high, deep |
| T4 | `Redesign the backend to support 10x traffic without breaking customer data.` | intent=architect, `gpt-6-astra`, multi_phase |
| T5 | `Find why websocket connections randomly disconnect in production.` | intent=debug, `gpt-5.6-sol`, high |

With an API key the model/reasoning may differ slightly (Jev judgments beat
heuristics) — what matters is that a routing block appears, names a model
from your catalog, and is sane. The block is advisory developer context: it
recommends, it never switches the session model by itself.

## Round 1 — test from Codex CLI

1. Install (pick one method; try a different one in Round 3):
   - Installer (pipe): `curl -fsSL https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.sh | sh`
     (key prompt reads from `/dev/tty` with echo off, safe when piped).
   - Installer (download-first, safest on any shell): `curl -fsSL -o
     /tmp/clearjev-install.sh <same URL above>` then `sh
     /tmp/clearjev-install.sh`.
   - Chat: open `codex`, paste the prompt from `docs/chat-install.md`.
   - The installer stores the key in `~/.codex/clearjev/credentials.json`
     (owner-only), never in shell profiles. `grep TYPESAFE_API_KEY
     ~/.bashrc` must show nothing ClearJev-related.
2. `clearjev status` → expect `routing: ON`, model counts, and a fallback
   smoke line. `clearjev check` → `OK` with key, `CHECK FAILED`
   (fallback note) without.
3. Restart the CLI, trust the hook in `/hooks`
   (`ClearJev routing` / `jev_route.py`, `UserPromptSubmit`), open a **new
   session**.
4. Send T1–T5 (one per message). Each answer must come from the routed
   model: the block says `Switched this session to <model>` (or `Already on
   <model>`), and the session header shows that model. With a key the block
   header says `· jev`; without, `· heuristic fallback · <reason>`. A
   `Switch failed (<reason>)` line means the session kept its previous
   model — that is an honest, valid outcome, not a silent miss.
5. Exercise the switch — all from chat, no terminal needed. Plain language
   works; explicit commands are shown in parentheses:
   - `$clearjev off` (`kapcsold ki a routingot`) → next prompt: **no** routing status.
   - `$clearjev on` → next prompt: routing block is back.
   - `$clearjev status` → state, key presence, model counts.
   - `$clearjev models list` / `$clearjev models available`.
   - `$clearjev models remove gpt-5.5` → T2 routes elsewhere;
     `$clearjev models add gpt-5.5 --reasoning all` restores it.
   - `$clearjev models reasoning gpt-5.6-luna remove ultra` (already absent
     → expect a clear outcome, never a silent no-op).
   - `$clearjev key status` → set/missing without printing the key.
   - `noroute: T2 text...` → that one prompt skips routing.
   - `reroute: this is actually a refactor` → hook stays silent, the agent
     continues with the corrected intent.
   - `clearjev autoswitch off` (shell or `$clearjev autoswitch off`) →
     next routed prompt keeps the session model with no `Switched` line;
     `autoswitch on` restores switching.
   - `/prompts:clearjev-off` then `/prompts:clearjev-on` → same as the
     `$clearjev` equivalents.
6. Real model switching:
   - In-session: `/model` picker changes model + reasoning for next turns.
   - New pre-routed session: `clearjev run --dry-run 'T3 text...'` shows
     the exact `codex --model ...` command; without `--dry-run` it launches it.

## Round 2 — full uninstall

Reverse the install completely, then prove nothing fires anymore:

```bash
~/.codex/clearjev-runtime/scripts/uninstall.sh --purge
```

Verify: new session → send T3 → **no** `ClearJev routing` status, and
`clearjev` is `command not found`. Without `--purge`, key and routing state
are preserved for reinstall.

## Round 3 — re-download and retest in the Codex App

1. Reinstall using a **different** method than Round 1 (e.g. chat prompt if
   Round 1 was the installer, or `codex plugin marketplace add
   huncijr/ClearJev` + install from the Plugins tab).
2. Marketplace installs need manual completion on the same machine (the
   marketplace cannot collect secrets or install the shell CLI): run the
   shell installer once to get the runtime + `clearjev` CLI, save the key
   with `clearjev key set '...'` (or `$clearjev key set '...'` in chat);
   then restart the App, approve the hook, open a **new chat**.
3. Send T1–T5 again, compare routing blocks with Round 1 (same intents,
   same model families expected).
4. In-chat control check: `@ClearJev off` → next prompt has no routing
   block; `@ClearJev on` restores it. `@ClearJev models list` shows
   catalog-filtered profiles.

## Methods to exercise the skill (agent-testing toolbox)

Seven methods, cheapest first. Use 1–2 during development, all of them
before a release:

1. **Direct hook call (no Codex at all)** — fastest iteration:
   `echo '{"prompt":"...","cwd":"."}' | python3
   plugins/clearjev-router/scripts/jev_route.py`
2. **Unit tests** — `python3 -m unittest discover -s tests -v` (44 tests,
   no network, hermetic state/catalog/credentials via temp dirs).
3. **`clearjev status` / `clearjev check`** — on/off state, key presence,
   model counts, live Jev ping + fallback smoke test.
4. **Automatic hook path** — just write normal prompts in a Codex session;
   the `UserPromptSubmit` hook fires before every prompt.
5. **Explicit skill invocation** — type `$clearjev` (CLI) or `@ClearJev`
   (App) in chat to exercise on/off/models/key/run (separates install
   problems from trigger problems).
6. **`codex exec` (non-interactive, scriptable)** — repeatable agent runs
   without the TUI, e.g.:
   `codex exec --skip-git-repo-check "Explain dependency injection in
   TypeScript."` — good for running T1–T5 unattended and diffing outputs.
7. **Install-method coverage** — verify each distribution path at least
   once: `install.sh` / `install.ps1`, chat prompt (`docs/chat-install.md`),
   marketplace (`codex plugin marketplace add huncijr/ClearJev`).

## What counts as PASS

- Routing block appears for T1–T5 in both CLI and App, intents correct,
  models from the local catalog.
- `off` silences it (zero Jev calls), `on` restores it, `noroute:` and
  `reroute:` each skip once.
- `models add` rejects unknown slugs and unsupported reasoning levels;
  `remove` only affects routing; at least one reasoning level always remains.
- `--check` is `OK` with a valid key and honestly reports fallback without one.
- Uninstall leaves no trace: no status line, no block, no `clearjev` binary
  (key+state gone only with `--purge`/`-Purge`).
- Unit suite stays 44/44 green after any change.
