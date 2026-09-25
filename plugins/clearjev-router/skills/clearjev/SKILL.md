---
name: clearjev
description: Manage ClearJev routing from chat. Use when the user says ClearJev, asks to turn routing on or off, configure a TypeSafe API key, add or remove routing models, change allowed reasoning levels, inspect status, or launch a routed Codex task.
---

# ClearJev Control

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

If `clearjev` is unavailable, run the router at
`~/.codex/clearjev-runtime/scripts/jev_route.py` with `python3` (or `py -3` on
Windows). Ask which action the user wants when they invoke the skill without an
action. For `models add`, ask for the model slug and whether all or selected
reasoning levels should be enabled.

API keys typed into chat become part of chat history. Warn once and recommend
`clearjev key set '<key>'` in a private terminal; if the user explicitly wants
chat setup, execute it without printing the key back.

The hook can recommend a model but cannot mutate the model of the turn already
being submitted. In an existing Codex session, tell the user to use `/model` for
the native same-session switch. `clearjev run` starts a new, pre-routed CLI
session. Never claim that advisory hook output changed the active model.
