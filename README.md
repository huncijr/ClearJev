# ClearJev

> **Trademark note:** ClearJev is an independent open-source project built on
> the TypeSafe Jev API. It is not affiliated with, endorsed by, or sponsored
> by TypeSafe AI, Inc. "Jev" and "TypeSafe" are trademarks of TypeSafe AI,
> Inc. The "Jev" in ClearJev refers to this technical dependency (API calls
> made with the user's own key), not a partnership. Users must provide their
> own API key.

Intelligent pre-prompt routing layer for Codex, built on the **TypeSafe Jev API**
(System One judgments).

Every prompt is judged **before** it reaches the model: Jev returns typed
`Choice` / `Score` / `Noul` answers (intent, demands, risk), code composes the
routing decision, and a 3–6 line block (model, reasoning, planning,
validation + reasons) is injected as developer context. Then execution
continues normally. No manual model picking.

## Install (2 steps)

**1. One command — macOS / Linux / Windows:**

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.ps1 | iex
```

> No-terminal alternative: open the Codex CLI (`codex`) and paste the
> prompt from [`docs/chat-install.md`](docs/chat-install.md) — the AI will
> walk through the installation.

This installs the skill (`$CODEX_HOME/skills` + `~/.agents/skills`), registers
the `UserPromptSubmit` hook in `~/.codex/hooks.json`, and enables
skills+hooks in `~/.codex/config.toml`.

**2. Set your Jev API key** (get one at https://console.typesafe.ai/keys):

```bash
export TYPESAFE_API_KEY="..."
```

Without a key the layer still works (labeled heuristic fallback) — with a key
it uses Jev judgments with confidence gating.

Then restart Codex (CLI or App), review the hook once in `/hooks`, and just
write prompts. Verify anytime with:

```bash
clearjev status   # on/off state, key presence, smoke test
clearjev check    # full verification incl. live Jev ping
```

## On / off

Works in Codex CLI and App, no restart needed (the hook re-reads the flag on
every prompt, paused = silent no-op, zero cost):

```bash
clearjev off      # pause routing
clearjev on       # resume routing
clearjev status   # show state
```

More ways:

| Method | Scope | How |
|---|---|---|
| `clearjev off/on` | persistent, CLI+App | state file (`$PLUGIN_DATA` or `~/.codex/clearjev.json`) |
| `CLEARJEV_ENABLED=0 <cmd>` | one process | env kill-switch, overrides everything |
| `noroute:` prompt prefix | one prompt | start the prompt with `noroute:` to skip routing once |
| CLI `/plugins` → Space | plugin on/off | Codex-native, needs a new session |
| CLI `/hooks` | hook on/off | Codex-native hook browser |
| App Plugins tab | install/uninstall | Codex-native |

Precedence: `CLEARJEV_ENABLED` env > state file > default ON.

## Codex Hub / marketplace

Repo marketplace: `.agents/plugins/marketplace.json`. Add it in Codex:

```bash
codex plugin marketplace add huncijr/ClearJev
```

then install `clearjev-router` from the `/plugins` browser (CLI) or the
Plugins tab (App). See `CODEX.md` for how Codex App + CLI use the Jev layer.

## Layout

```
plugins/clearjev-router/
  .codex-plugin/plugin.json      # plugin manifest (skills + hooks)
  skills/clearjev-router/SKILL.md
  hooks/hooks.json               # UserPromptSubmit -> jev_route.py
  scripts/jev_route.py           # the router: Jev batch call + code composition (stdlib only)
  scripts/clearjev[.cmd]         # on|off|status|check CLI (installed to ~/.local/bin)
  scripts/install.sh / install.ps1
  references/jev-questions.md    # exact Choice/Score/Noul definitions
  references/routing.md          # weights, thresholds, escalation
  references/models.md           # GPT-6 Astra/Sol/Terra/Luna capability profiles
  assets/router-config.yaml      # all tunable constants in one place
tests/test_router.py             # 15 tests, no network needed
```

## How routing works

`INTENT → CONTEXT → COMPLEXITY → ROUTING → REASONING → PLANNING → EXECUTION → VALIDATION → EVALUATION → ESCALATION`

- Principle: smallest model that reliably solves the task — never strongest-by-default.
- Model, reasoning, planning and validation are independent decisions.
- Low confidence → targeted scan or one clarifying question, never a guess.
- Failures re-route (fresh Jev call with error context), never blind-retry.
- The hook never blocks: any routing error = silent no-op, session continues.

## Dev

```bash
python3 -m unittest discover -s tests -v
echo '{"prompt":"...","cwd":"."}' | python3 plugins/clearjev-router/scripts/jev_route.py
```

See [`docs/testing.md`](docs/testing.md) for the full matrix: test from Codex
CLI → full uninstall → re-download and retest in the Codex App.
