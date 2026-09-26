# ClearJev costs — measuring and cutting Jev spend

TypeSafe bills every Jev call (no server-side prompt caching), so savings
live in the router. This file explains how to see the spend and what the
router does about it.

## See the spend

```bash
clearjev costs
```

Output:

```
ClearJev costs
- jev calls: 128
- jev input tokens: 96400 (~$0.004049)
- saved events (cache/reuse/trivial): 41
- saved input tokens: 30500 (~$0.001281)
  cache: 12
  fallback: 100
  jev: 128
  reuse: 20
  trivial: 9
```

Every routing event appends one line to `~/.codex/clearjev/usage.jsonl`
(`kind`, tokens, cost). Nothing leaves the machine; the ledger is local.

## What saves tokens (all conservative)

1. **Exact-duplicate cache (15 min TTL).** Same prompt + same repo state +
   same candidate models = the stored Jev decision, zero tokens. Logged as
   `cache` with the tokens it would have cost.
2. **Session reuse for stable follow-ups.** The hook remembers the last
   decision per session. A short follow-up (<120 chars) with the same
   heuristic intent and low prior complexity (<40) reuses it — but never
   after a manual `/model` switch, and never for a model that left the
   candidate set. Logged as `reuse`.
3. **Trivial gate.** Short chit-chat with no code signals (`thanks!`,
   `hogy vagy?`) is routed locally with no network call. Logged as
   `trivial`.
4. **Slim state.** At most 12 filenames plus a git change summary (counts,
   not filenames) are sent; the full 40-file list and per-file git status
   are gone.
5. **Stickiness.** The model switches only on significant gain (forced floor, big complexity jump, or high confidence); otherwise the model stays — preserving the Codex prompt cache — while effort still adjusts. `clearjev stickiness off` restores switch-on-any-difference.
6. **Circuit breaker (existing).** After 3 straight Jev failures, calls
   pause with notice until a new key or a passing `clearjev check`.

Anything uncertain still goes to Jev. If routing quality ever looks off,
`clearjev off` (or `noroute:` for one prompt) bypasses everything.

## Acceptance check (big project)

Run the canonical T1–T5 prompts plus repeats and follow-ups, then compare:

```bash
clearjev costs
```

Target: same routing decisions as the uncached baseline, at least 40% fewer
Jev input tokens. Check: duplicates and stable follow-ups must show up as
`cache`/`reuse`, never as new `jev` calls.
