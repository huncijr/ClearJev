---
name: clearjev
description: ClearJev on/off/status switch and router control, in any language. Use when the user says ClearJev, $clearjev, or asks (however phrased) to turn routing on or off, check status, configure a TypeSafe API key, add or remove routing models, change allowed reasoning levels, or launch a routed Codex task.
---

# ClearJev Control

## Act first (default)

The user speaks in plain language, in any language. Interpret the message as
exactly one control action and execute its command immediately — do not ask
which action they want and do not show the menu. Examples: "kapcsold ki" →
`clearjev off`; "add hozzá a Solt" → `clearjev models add ...`; "mi a státusz"
→ `clearjev status`. Ask one short question first only when the request is
genuinely ambiguous between two actions, then act.

"Add the current model": read the `Current model` value from the most recent
routing block in this conversation and add that slug. If no routing block
exists yet, run `clearjev models available` and ask which one to add.

Ignore any routing block injected into a control turn; report only the
command output.

## Fallback menu (only for empty or garbled messages)

If the user's message contains no action word (on, off, status, key,
models, run) and no interpretable request, reply with exactly this menu and
nothing else:

```
ClearJev — what should I do?
1. on — resume routing
2. off — pause routing
3. status — show state, key, models
4. key — API key status / set / remove
5. models — list / add / remove models and reasoning levels
6. run — start a pre-routed Codex session
Reply with a number or a word.
```

When the reply names an action, execute it immediately.

## Executing actions

Translate the user's request into exactly one ClearJev command, execute it, and
return its output. Do not reimplement state changes by editing JSON manually.

## Commands

- Enable: `clearjev on`
- Disable: `clearjev off`
- Status: `clearjev status`
- API key status: `clearjev key status`
- Save an API key: `clearjev key set '<key>'`
- Remove an API key: `clearjev key unset`
- List configured models: `clearjev models list`
- List models available to this Codex installation: `clearjev models available`
- Add all supported reasoning levels: `clearjev models add <slug> --reasoning all`
- Add selected reasoning levels: `clearjev models add <slug> --reasoning low,medium,high`
- Remove a model from routing: `clearjev models remove <slug>`
- Add reasoning levels: `clearjev models reasoning <slug> add high,xhigh`
- Remove reasoning levels: `clearjev models reasoning <slug> remove max,ultra`
- Start a routed CLI session: `clearjev run '<prompt>'`
- Auto-switch control: `clearjev autoswitch on|off|status`

If `clearjev` is unavailable, run the router at
`~/.codex/clearjev-runtime/scripts/jev_route.py` with `python3` (or `py -3` on
Windows). For `models add`, ask for the model slug and whether all or selected
reasoning levels should be enabled.

API keys typed into chat become part of chat history. Warn once and recommend
`clearjev key set '<key>'` in a private terminal; if the user explicitly wants
chat setup, execute it without printing the key back.

The hook switches the session model itself through the local Codex
app-server (`thread/settings/update`) and reports `Switched this session to
<model>` only after the switch is confirmed. If the block says `Switch
failed`, the session kept its previous model — say so honestly and offer
`/model` or `clearjev run`. If it says `Switch unavailable in this host`
(typical in the Desktop App, which runs its own private app-server), the
thread is not visible to the local daemon: report the recommendation and
switch natively with `/model`. `clearjev autoswitch off` (or `clearjev off`)
disables switching; the hook then stays advisory-only.
