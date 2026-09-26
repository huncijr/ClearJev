# ClearJev

Automatic routing with Jev from TypeSafe AI: every Codex CLI prompt is
judged before it runs, and the session switches to the right model.

[![Codex marketplace](https://img.shields.io/badge/Codex-marketplace-blue)](https://github.com/huncijr/ClearJev)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

> ClearJev is independent, not affiliated with TypeSafe AI, Inc. You provide
> your own API key.

```
$clearjev on
ClearJev routing ON

> Build a JavaScript dashboard with charts, user auth, and a REST API backend.
Switched this session to gpt-5.6-sol (high). ...

> What is the weather in New York today?
Switched this session to gpt-5.6-luna (low). ...
```

Once it is ON you never type `$clearjev` again — every prompt routes itself.

Jev calls cost input tokens with no server-side caching, so the router
skips what it can prove safe: exact duplicates (15 min), stable follow-ups
in the same session, and trivial chit-chat. `clearjev costs` shows spend
vs. saved. Details: `docs/costs.md`.
No key? It still works with a labeled heuristic fallback.

## Install

```bash
curl -fsSL -o /tmp/clearjev-install.sh https://raw.githubusercontent.com/huncijr/ClearJev/main/scripts/install.sh
sh /tmp/clearjev-install.sh
```

```powershell
Invoke-WebRequest -OutFile $env:TEMP\clearjev-install.ps1 https://raw.githubusercontent.com/huncijr/ClearJev/main/scripts/install.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\clearjev-install.ps1
```

When it asks, paste your API key (https://console.typesafe.ai/keys).
Then restart Codex, open `/hooks`, trust `ClearJev routing` (accept it so
it can run), and open a new session.

## Chat

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

A bare `$clearjev` shows a numbered menu. Plain `clearjev on|off|status`
messages work without shell (the hook runs them itself).

CLI-only: in the Codex App the hook stays silent (no cost) and the skill
refuses — use the App natively. Uninstall:
`~/.codex/clearjev-runtime/scripts/uninstall.sh [--purge]`.
