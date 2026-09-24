---
name: clearjev-router
description: Route Codex tasks to the right GPT-6 model, reasoning effort, planning and validation via Jev judgments. Use when the user asks to implement, debug, refactor, architect, review, migrate, test, explain or research code.
---

# ClearJev Router

Pre-prompt routing layer for Codex. Jev (TypeSafe System One) judges the prompt **before** execution; code composes the routing decision.

## When to use

Any coding task: implement, debug, refactor, architect, review, research, test, migration, security, documentation, explanation. The `UserPromptSubmit` hook runs automatically — you do not need to invoke this skill manually.

## How it works

1. Hook sends `state = {prompt.text, repo_meta, git_status}` + 11 typed questions (1 batch) to Jev (`jev-latest`).
2. Code composes answers: complexity 0–100, confidence gate, capability-fit model score minus cost penalty.
3. Hook returns `additionalContext` (3–6 lines): model, reasoning, planning, validation + reasons.
4. On low confidence, uncertain intent, or Jev failure: targeted repo scan or one clarifying question — never guess. No API key = labeled heuristic fallback, still fail-open.

## Files (load lazily, never all at once)

- `scripts/jev_route.py` — run it, do not reimplement routing by hand.
- `references/jev-questions.md` — the exact Choice/Score/Noul definitions.
- `references/routing.md` — weights, thresholds, escalation rules.
- `references/models.md` — GPT-6 Astra/Sol/Terra/Luna capability profiles (explicit config).
- `assets/router-config.yaml` — single place for questions, thresholds, weights.

## Rules

- Code owns the workflow; Jev only returns typed judgments, never free-text plans.
- Never invent model capabilities — read them from `assets/router-config.yaml`.
- Never block the session on routing failure; exit 0 with empty output.
- Keep `additionalContext` under ~6 lines; details stay in references.
- On/off: `clearjev off/on/status`, `CLEARJEV_ENABLED=0` for one process,
  `noroute:` prompt prefix to skip once. Paused = silent no-op; say nothing.
