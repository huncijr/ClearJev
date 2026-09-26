# ClearJev

[![Codex marketplace](https://img.shields.io/badge/Codex-marketplace-blue)](https://github.com/huncijr/ClearJev)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

> Install in one command (Codex CLI):
> ```bash
> codex plugin marketplace add huncijr/ClearJev
> ```
> then install `clearjev-router` from `/plugins`. No accounts, no verification.

> **Trademark note:** ClearJev is an independent open-source project built on
> the TypeSafe Jev API. It is not affiliated with, endorsed by, or sponsored
> by TypeSafe AI, Inc. "Jev" and "TypeSafe" are trademarks of TypeSafe AI,
> Inc. The "Jev" in ClearJev refers to this technical dependency (API calls
> made with the user's own key), not a partnership. Users must provide their
> own API key.

Advisory pre-prompt routing layer for Codex, built on the **TypeSafe Jev API**
(System One judgments) — with real same-thread model switching.

Every prompt is judged **before** it reaches the model: Jev returns typed
`Choice` / `Score` / `Noul` answers (intent, demands, risk), code composes a
decision, and the hook switches the session to the chosen model through the
local Codex app-server before answering. A short block (recommended model,
switch confirmation, reasoning, planning, validation + reasons) is injected
as developer context. Then execution continues normally.

Scope truth, read first: the switch targets **subsequent turns on the same
thread** and is confirmed before the answer — the block says `Switched this
session to <model>` only then. A turn that is already generating cannot be
re-targeted mid-stream. If the switch fails, the block says `Switch failed
(<reason>)` and the session continues with its previous model. Anything
else is a bug in these docs.

## Install

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.sh | sh
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.ps1 | iex
```

The installer is idempotent: re-running it detects the installed version
and stops with `ClearJev is already downloaded` (routing state preserved);
use `install.sh --force` (or `-Force` on Windows) to reinstall.

The installer copies a self-contained runtime to
`~/.codex/clearjev-runtime`, installs the `clearjev` skill, registers the
hook in `~/.codex/hooks.json` (merged, with backup), installs the `clearjev`
command, and adds `/prompts:clearjev-*` aliases.

**API key** (https://console.typesafe.ai/keys): asked once, stored
owner-only in `~/.codex/clearjev/credentials.json`. No key = labeled
heuristic fallback; with a key = Jev judgments. After 3 straight Jev
failures the hook pauses Jev calls (`Jev paused ... run 'clearjev check'`);
a new key or passing check resumes them. With Jev on, prompt text + basic
repo metadata goes to TypeSafe (disclosed by the installer).

Then restart Codex (CLI or App), review the hook once in `/hooks`, and just
write prompts.

## Three ways to use it

### 1. Codex CLI chat

```
$clearjev turn off routing
$clearjev add the gpt-6-sol model
$clearjev what is the status
```

Explicit commands work too (and are the safest form in scripts):

```
$clearjev status
$clearjev off
$clearjev on
$clearjev models list
$clearjev models available
$clearjev models add gpt-6-astra --reasoning all
$clearjev models add gpt-5.6-luna --reasoning low,medium,high
$clearjev models reasoning gpt-5.6-luna remove ultra
$clearjev models remove gpt-5.5
$clearjev key status
$clearjev key set '<paste-key-here>'
$clearjev run 'Implement Stripe subscriptions with webhooks'
```

A bare `$clearjev` returns a numbered on/off/status/key/models/run menu.

## Once it is ON, just write prompts

When routing is ON you never type `$clearjev` again — every prompt is
routed automatically. Example session:

```
$clearjev on
ClearJev routing ON

> Build a JavaScript dashboard with charts, user auth, and a REST API backend.
Switched this session to gpt-5.6-sol (high). ...

> What is the weather in New York today?
Switched this session to gpt-5.6-luna (low). ...
```

The dashboard task goes to Sol (multi-file coding), the weather question
drops to Luna (cheap Q&A) — no manual `/model` switching. Exact model and
effort may vary slightly with live Jev judgments; the fallback path above
is deterministic. To pause: `$clearjev off` or a plain `clearjev off`
message (the hook executes that itself, no shell needed). To check why a
prompt routed somewhere, read the `Why:` line.

Deprecated-but-working CLI/IDE aliases (installed as `~/.codex/prompts/*.md`).
These are the one-Enter on/off switches — one action per command, no menu:

```
/prompts:clearjev
/prompts:clearjev-on
/prompts:clearjev-off
/prompts:clearjev-add
/prompts:clearjev-remove
/prompts:clearjev-key
```

Note: chat setup types the key into chat history. Prefer the terminal
(`clearjev key set '...'`); if you use chat, the skill warns once and never
prints the key back.

### 2. Codex App chat (ClearJev stays off)

Do not install the plugin in the App: the hook detects non-CLI hosts and
stays completely silent there — no Jev calls, no routing blocks, no usage
spent. The **`@ClearJev` skill refuses control actions in the App — it is
CLI-only.** In the App:

- No recommendations, no switching attempts — use the App natively.
- Plain `clearjev on|off|status` messages answer with a short CLI-only
  pointer (no shell needed, no cost).
- Full routing and control live in Codex CLI.

Manual key step for marketplace installs (the marketplace cannot collect
secrets): run `clearjev key set '...'` once in a terminal on the same
machine, or ask the agent to run it. Then open a new chat, approve the hook
when asked, and verify a routing block appears.

### 3. Shell (outside chat)

```bash
clearjev status    # on/off state, auto-switch, key presence, model counts, smoke test
clearjev check     # full verification incl. live Jev ping
clearjev on        # resume routing (persistent, no restart needed)
clearjev off       # pause routing (silent no-op, zero cost)
clearjev autoswitch off  # keep routing advice, never switch the session model
clearjev autoswitch on   # re-enable automatic switching (default)
clearjev key set '<key>' | clearjev key unset | clearjev key status
clearjev models list | clearjev models available
clearjev models add <slug> --reasoning all|low,medium,...
clearjev models remove <slug>
clearjev models reasoning <slug> add|remove <levels>
clearjev run 'your task'            # route, then open Codex with that model
clearjev run --dry-run 'your task'  # show the routing + command only
```

More ways to skip routing:

| Method | Scope | How |
|---|---|---|
| `CLEARJEV_ENABLED=0 <cmd>` | one process | env kill-switch, overrides everything |
| `noroute:` prompt prefix | one prompt | skips routing for that prompt |
| `reroute:` prompt prefix | one prompt | correction handled conversationally, no re-route |
| CLI `/hooks` | hook on/off | Codex-native hook browser |
| App Plugins tab | install/uninstall | Codex-native |

Precedence: `CLEARJEV_ENABLED` env > config file (`~/.codex/clearjev/config.json`) > default ON.

## Model management

`clearjev models available` lists your local Codex catalog — only these
models can ever be recommended. The router is catalog-first: **any** visible
model is routable (curated profiles in `assets/router-config.json`, inferred
otherwise).

- `add` validates the slug and filters reasoning levels to what the model
  supports (`low, medium, high, xhigh, max, ultra` vary by model).
- `remove` only takes a model out of routing, never out of Codex.
- Keep at least one reasoning level per model.

## Real model switching

| Situation | What happens |
|---|---|
| Normal prompt, routing ON | Hook routes with Jev, switches the thread (`thread/settings/update`), waits for confirmation, then the answer comes from the new model |
| Switch confirmed | Block says `Switched this session to <model> (<effort>)` |
| Already the right model | Block says `Already on <model>; no switch needed` |
| Switch rejected/unavailable | Block says `Switch failed (<reason>)` or `Switch unavailable in this host`; session continues with its previous model |
| Desktop App / non-CLI host | The hook stays completely silent there: no Jev calls, no blocks, no usage spent |
| Already-generating turn | Cannot be re-targeted mid-stream; the switch applies from that point on |
| `clearjev autoswitch off` / `off` | No switching; hook stays advisory-only |
| New CLI session with Jev's pick | `clearjev run '<prompt>'` (routes, then `codex --model <slug> -c model_reasoning_effort=<level>`) |

## Remove

```bash
# POSIX: removes runtime, skill, CLI, prompts, hook entries (keeps key+state)
~/.codex/clearjev-runtime/scripts/uninstall.sh
# ...add --purge to also delete the API key and state
```

```powershell
# Windows: same scope; add -Purge for key+state
& ~/.codex/clearjev-runtime/scripts/uninstall.ps1
```

Marketplace installs: uninstall `clearjev-router` from `/plugins` (CLI) or
the Plugins tab (App), then run the matching uninstaller above to remove the
hook entry, runtime, and CLI. Hook trust entries are managed in `/hooks`.

## Codex Hub / marketplace

Repo marketplace: `.agents/plugins/marketplace.json`. Add it in Codex:

```bash
codex plugin marketplace add huncijr/ClearJev
```

then install `clearjev-router` from the `/plugins` browser (CLI) or the
Plugins tab (App). Marketplace installs do not collect the API key and do
not install the shell CLI — complete both manually (see App chat above).
See `CODEX.md` for how Codex App + CLI use the Jev layer.

## Layout

```
plugins/clearjev-router/
  .codex-plugin/plugin.json      # plugin manifest (skills + hooks)
  skills/clearjev/SKILL.md       # CLI chat control skill ($clearjev)
  skills/clearjev/agents/openai.yaml
  prompts/clearjev*.md           # /prompts:clearjev-* chat aliases
  hooks/hooks.json               # UserPromptSubmit -> jev_route.py
  scripts/jev_route.py           # the router: Jev batch call + code composition (stdlib only)
  scripts/clearjev[.cmd]         # CLI wrapper (resolves bundled or installed runtime)
  scripts/install.sh / install.ps1 / uninstall.sh / uninstall.ps1
  assets/router-config.json      # THE config: endpoint, weights, thresholds, model profiles
  references/                    # question definitions, routing rules, model notes
tests/test_router.py             # 65 tests, no network needed
```

## How routing works

`INTENT → CONTEXT → COMPLEXITY → ROUTING → REASONING → PLANNING → EXECUTION → VALIDATION → EVALUATION → ESCALATION`

- Principle: smallest model that reliably solves the task — never strongest-by-default.
- Model, reasoning, planning and validation are independent decisions.
- Low confidence → targeted scan or one clarifying question, never a guess.
- Failures re-route (fresh Jev call with error context), never blind-retry.
- The hook never blocks: any routing error = labeled fallback or silent no-op, session continues.

## Dev

```bash
python3 -m unittest discover -s tests -v
echo '{"prompt":"...","cwd":"."}' | python3 plugins/clearjev-router/scripts/jev_route.py
```

See [`docs/testing.md`](docs/testing.md) for the full matrix: test from Codex
CLI → full uninstall → re-download and retest in the Codex App.
