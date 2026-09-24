# Models — GPT-6 capability profiles (explicit config)

These profiles are **hand-maintained configuration**, not model output.
Tune them from benchmark results (`task type × model × success/cost`).
Canonical values live in `assets/router-config.yaml`; this file explains them.

| model | strong at | weak at | use when |
|---|---|---|---|
| GPT-6 Luna | explanation, speed, cheap Q&A | planning, architecture, big refactors | explain, question, documentation, trivial edits |
| GPT-6 Terra | balanced small features | deep reasoning, repo-wide design | single-component features, light refactors, tests |
| GPT-6 Sol | coding, debugging, refactoring, tool use | — (costly for trivial) | multi-file features, debugging, migrations, security impl |
| GPT-6 Astra | reasoning, planning, architecture, context | speed, cost | system design, multi-tenancy, critical decisions |

Rules:

- No universal ranking. Every decision is `score(model, task)` for *this* task.
- A complex request may legitimately use several models in one run
  (e.g. Astra plans, Sol implements, Luna documents).
- If Codex exposes different real model slugs than `gpt-6-*`, map them here
  without touching the router logic.
