# CODEX.md — how Codex App and Codex CLI use the Jev layer

This file is for Codex (App + CLI). It describes the ClearJev advisory
pre-prompt routing layer. Follow it on every task.

> Scope truth: the hook below only **recommends** a model and reasoning
> effort. It cannot change the model of the session that is already running.
> Never claim an automatic switch happened.

## 1. The layer runs before you do

A `UserPromptSubmit` hook (`scripts/jev_route.py`) already judged the user
prompt with **Jev** (TypeSafe System One model `jev-latest`) and injected a
routing block as developer context:

```
[ClearJev routing · jev] intent=... · complexity=NN (band)
Recommended model: ... · Current model: ... · Reasoning: ... · Planning: ... · Validation: ... · Repo: ...
Why: ...
```

If the block says `heuristic fallback`, Jev was unavailable — the header
names the exact reason (`API key missing`, `API key rejected`, `Jev
temporarily unavailable`, `Jev network timeout`, `Jev response error`).
Treat fallback output as a rough hint, not a confident judgment.

## 2. Obey the routing block (advisory)

- Treat `Recommended model` + `Reasoning` as the routing advice for this
  task. They were composed in code from typed Jev answers, not guessed.
- The **Current model** line names the model of this session. If it differs
  from the recommendation, say so in one short line and either continue with
  the current model or ask the user to switch natively with `/model`
  (same session, next turns). `clearjev run '<prompt>'` starts a new,
  pre-routed CLI session instead.
- `Repo:` tells you how much context to load: `unnecessary` (prompt only) →
  `targeted` (1–3 files) → `broad` (subsystem) → `deep` (progressive scan,
  stop as soon as sufficient). Never dump the whole repo by default.
- `Validation:` tells you how to finish: `none/basic` → eyeball the diff;
  `tests` → run/add tests; `deep` → edge cases; `full_regression` → full suite.

## 3. Uncertainty protocol

- If the block flags uncertainty (`reroute:` hint, low confidence, or
  `intent=unknown`): do a targeted scan or ask ONE clarifying question before
  editing. Never start random code modification.
- If the user replies `reroute: <correction>`, accept it and continue with the
  corrected intent — the hook stays silent for that message by design.
- Debugging tasks: inspect → hypothesize → gather evidence → reproduce →
  diagnose → fix → regression test. No jump-to-fix.

## 4. Escalation

If you hit 2+ failed attempts, test failures after a fix, an unexpectedly
large diff, or new cross-module dependencies: stop retrying with the same
plan. State what changed (error output, new evidence) and continue with a
stronger approach (deeper reasoning, broader context, next model up).

## 5. Cost awareness

Use the smallest model that reliably solves the task. Simple explanation,
rename, or single-file edit must not trigger heavy reasoning or deep scans.

## 6. Paused routing

If no routing block was injected, routing is paused (`clearjev off`,
`CLEARJEV_ENABLED=0`, or a `noroute:`/`reroute:` prompt) — work normally and
do not ask about it. The user re-enables it with `clearjev on` (shell) or
`$clearjev on` / `@ClearJev on` (chat).

## 7. Managing ClearJev from chat

The `clearjev` skill exposes: `on`, `off`, `status`, `key set/unset/status`,
`models list/available/add/remove/reasoning`, `run`. Run exactly one command
per request and report its output. Never print an API key back into chat.

## 8. Never do this

- Never invent model capabilities; profiles live in
  `assets/router-config.json` / `references/models.md`.
- Never claim the hook switched the active session model.
- Never bypass the routing block silently; if it looks wrong, say why and
  what you use instead.
- Never block or break the session because of routing — the hook is
  advisory and fail-open by design.
