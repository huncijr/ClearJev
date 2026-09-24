# CODEX.md — how Codex App and Codex CLI use the Jev layer

This file is for Codex (App + CLI). It describes the ClearJev pre-prompt
routing layer. Follow it on every task.

## 1. The layer runs before you do

A `UserPromptSubmit` hook (`scripts/jev_route.py`) already judged the user
prompt with **Jev** (TypeSafe System One model `jev-latest`) and injected a
routing block as developer context:

```
[ClearJev routing · jev] intent=... · complexity=NN (band)
Model: ... · Reasoning: ... · Planning: ... · Validation: ... · Repo: ...
Why: ...
```

If the block says `heuristic fallback`, no `TYPESAFE_API_KEY` was available —
treat the decision as a rough hint, not a confident judgment.

## 2. Obey the routing block

- Use the routed model family, reasoning effort, planning depth and validation
  level. They were composed in code from typed Jev answers, not guessed.
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
  corrected intent — do not re-run the hook.
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

## 6. Never do this

- Never invent model capabilities; profiles live in
  `assets/router-config.yaml` / `references/models.md`.
- Never bypass the routing block silently; if it looks wrong, say why and
  what you use instead.
- Never block or break the session because of routing — the hook is
  advisory and fail-open by design.
