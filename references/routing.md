# Routing — weights, thresholds, escalation (code logic, not prompts)

## On/off precedence (checked first, before any Jev call)

1. `CLEARJEV_ENABLED` env (`0/false/no/off` = paused; `1/true/yes/on` = forced on).
2. State file: `$CLEARJEV_CONFIG` > `$CLEARJEV_STATE` > `~/.codex/clearjev/config.json`
   (`{"enabled": false}` = paused; managed by `clearjev on/off`).
3. Default: ON. Prompt prefixes `noroute:` and `reroute:` skip routing for one prompt.
Paused = silent no-op (exit 0, empty stdout, no Jev call, zero cost).

## Complexity 0–100 (composite scoring, in code)

```
norm(score_answer_0to3) = score / 3
complexity =
    30 * norm(coding_demand)
  + 25 * norm(reasoning_demand)
  + 15 * norm(repo_demand)
  + 20 * norm(risk)
  + 10 * noul(ambiguous)
```

Bands: 0–20 trivial · 20–40 simple · 40–60 moderate · 60–75 complex · 75–90 very complex · 90–100 critical.

## Confidence gates

- `intent.confidence < 0.60` → do not act on intent; ask one clarifying question or do a targeted scan first.
- `complexity` (mean Score confidence) `< 0.50` → treat complexity as one band higher (safe side).
- High-stakes action (security/migration/prod data) with confidence `< 0.85` → confirm with user before edits.
- Noul near 0.5 = uncertain, not "medium". Escalate, do not average it away.

## Model score (in code, per task)

```
score(model, task) =
    capabilityFit(model, demands)   # dot product vs profiles in router-config.json
  + explanationBonus                  # explain/question/documentation -> cheapest strong explainer
  - 8 * costClass                   # cheap tasks raise this penalty
  + policyBonus                     # e.g. debug -> Sol-family, security floor -> reasoning>=8
```

Smallest model that reliably solves the task wins, chosen only from models
that are enabled and present in the user's Codex model catalog. Policies from
`assets/router-config.json` are hard floors (security, architecture), never suggestions.

## Reasoning / planning / validation mapping

Reasoning uses only values the Codex model catalog supports
(`low, medium, high, xhigh, max, ultra`), filtered per model:

| complexity | reasoning | planning | validation |
|---|---|---|---|
| 0–30 | low | none | none/basic |
| 30–60 | medium | light/standard | basic/tests |
| 60–80 | high | deep | deep |
| 80–95 | xhigh | deep/multi_phase | deep/full_regression |
| 95–100 | max | multi_phase | full_regression |

`security_sensitive >= 0.7` forces reasoning ≥ high regardless of band.

## Escalation (re-route, not retry)

Triggers (observed in code): 2+ failed attempts, test failures after a fix,
diff far larger than `change_size` predicted, new cross-module dependencies,
confidence drop on re-judgment. Action: fresh Jev call with updated state
(error output included) → next-best capability fit, usually one cost class up.
Never retry more than twice with the same model+plan.

## Multi-model tasks

`planning == multi_phase`: split into phases (analyze → plan → implement →
test → validate) across separate Codex sessions. Cheap phases (docs, simple
UI) may use Luna-class models inside a Sol-led workflow. A plugin or hook
cannot change the model of an already-running session; switch it natively
with `/model` or start the next phase with `clearjev run '<prompt>'`.
