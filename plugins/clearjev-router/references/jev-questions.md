# Jev questions — exact definitions used by `scripts/jev_route.py`

One batch, same `state`, 11 questions (speculative fan-out: code ignores
answers it does not need on a given path). IDs are for code only; the full
meaning is always in `instructions`.

`state` shape:

```json
{
  "prompt": {"text": "<user prompt>"},
  "repo": {"languages": ["python"], "top_files": ["..."], "git_status": "..."},
  "note": "Classify the developer request in `prompt.text` using `repo` as background only."
}
```

## intent (Choice)

`instructions`: "What is the developer asking the agent to accomplish in `prompt.text`? Classify the primary requested outcome, not the topic words."

| option | what | not_for | examples |
|---|---|---|---|
| explain | Explain a concept, no repo change | Any code modification | "Explain JWT authentication." |
| question | Answer about this repo's code | General concept explanation | "Why does this middleware run twice?" |
| generate | Produce new snippet/file, small scope | Multi-file feature | "Add a loading spinner to this button." |
| implement | Build a feature touching code | Explanation only | "Implement OAuth with Google + GitHub." |
| debug | Find/fix a failure | New feature | "500 on large file uploads." |
| refactor | Restructure without behavior change | New behavior | "Split this 800-line module." |
| architect | Design/decide structure, tradeoffs | Immediate code edit | "Redesign backend for 10x traffic." |
| review | Critique given code/diff | Write new code | "Review this PR for race conditions." |
| research | Survey options, report back | Implement now | "Compare ORM options for Postgres." |
| test | Write/run tests | Fix without tests | "Add regression tests for checkout." |
| migration | Move versions/frameworks/data | Small edit | "Migrate to OAuth2 + refresh rotation." |
| security | Harden/audit/fix vulnerability | Feature work | "Audit session handling for fixation." |
| documentation | Write docs/comments | Code change | "Document the auth middleware." |
| unknown | None of the above fits | — | — |

Always include `unknown` so the model is never forced into a wrong bucket.

## Demand scores (Score, 4 levels each)

- `coding_demand` — "How much code writing does `prompt.text` require?" levels: `No code output.` / `Single snippet or small edit.` / `Multi-file feature or fix.` / `System-wide implementation or migration.`
- `reasoning_demand` — "How much careful reasoning (edge cases, tradeoffs, hidden interactions)?" levels: `Trivial, one obvious step.` / `Some judgment, few steps.` / `Deep reasoning, many interacting parts.` / `Novel design under uncertainty.`
- `planning_demand` — "How much up-front planning/decomposition?" levels: `None, act directly.` / `Light: 1-2 steps in head.` / `Standard: short plan, several files.` / `Deep/multi-phase plan required.`
- `repo_demand` — "How much repository context is needed?" levels: `None, prompt is self-contained.` / `Targeted: 1-3 files.` / `Broad: directory or subsystem.` / `Repository-wide analysis.`
- `risk` — "Cost of getting it wrong?" levels: `Safe: typo, rename, docs.` / `Low: isolated change, easy revert.` / `Medium: auth/data/billing-adjacent or multi-file.` / `High: security, migration, production data.`

## Yes/no gates (Noul)

- `requires_repo` — "Does `prompt.text` need any file from `repo` to answer correctly?" true: `Needs repo files.` / false: `Answerable from prompt alone.`
- `security_sensitive` — "Does `prompt.text` touch auth, sessions, crypto, PII, payments, or access control?" true: `Security-sensitive.` / false: `No security sensitivity.`
- `ambiguous` — "Is `prompt.text` ambiguous about what success looks like?" true: `More than one plausible reading.` / false: `Single clear reading.`

## Speculative (Choice, used only on matching paths)

- `change_size` — "Expected code change size?" `small` / `medium` / `large` / `massive`.
- `validation_need` — "How much validation does this need?" `none` / `basic` / `tests` / `deep` / `full_regression`.
