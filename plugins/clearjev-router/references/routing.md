# Routing — weights, thresholds, escalation (code logic, not prompts)

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
    capabilityFit(model, demands)   # dot product vs profiles in router-config.yaml
  + contextFit(model, repo_demand)
  - 8 * costClass                   # simple_tasks policy raises this penalty
  + policyBonus                     # e.g. documentation -> Luna, debug -> Sol, security floor -> Sol+
```

Smallest model that reliably solves the task wins. Policies from
`assets/router-config.yaml` are hard floors (security, architecture), never suggestions.

## Reasoning / planning / validation mapping

| complexity | reasoning | planning | validation |
|---|---|---|---|
| 0–20 | low | none | none/basic |
| 20–40 | low/medium | light | basic |
| 40–60 | medium | standard | tests |
| 60–75 | high | deep | deep |
| 75–100 | high/very_high | deep/multi_phase | deep/full_regression |

`security_sensitive >= 0.7` forces reasoning ≥ high regardless of band.

## Escalation (re-route, not retry)

Triggers (observed in code): 2+ failed attempts, test failures after a fix,
diff far larger than `change_size` predicted, new cross-module dependencies,
confidence drop on re-judgment. Action: fresh Jev call with updated state
(error output included) → next-best capability fit, usually one cost class up.
Never retry more than twice with the same model+plan.

## Multi-phase tasks

`planning == multi_phase`: split into phases (analyze → plan → implement →
test → validate); each phase gets its own routing decision. Cheap phases
(docs, simple UI) may use Luna/Terra inside a Sol-led workflow.
