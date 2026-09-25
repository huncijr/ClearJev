# Hub listings — where to publish ClearJev (no verification needed)

All four targets below accept community plugins without ID verification or
company registration. The official OpenAI universal Plugin Directory is NOT
listed here on purpose: it requires Apps Management rights plus a verified
developer/business identity (see `docs/hub-submission.md` if that path opens
up later).

## 0. Your own repo is already a hub (done, zero action)

Any Codex CLI user can install straight from GitHub, no accounts:

```bash
codex plugin marketplace add huncijr/ClearJev
```

then install `clearjev-router` from `/plugins`. This works because the repo
ships a valid `.agents/plugins/marketplace.json` plus a valid
`.codex-plugin/plugin.json` (both validated by `tests/test_router.py`).

## 1. awesome-codex-plugins (hashgraph-online) — PR package

- Registry: https://hol.org/registry/plugins (156+ plugins)
- Repo: https://github.com/hashgraph-online/awesome-codex-plugins
- How: fork → add the entry below to `plugins.json` (keep alphabetical
  order: after the "ClearJev"... check neighbors starting with "Cl") →
  open PR → automated scanner validates → maintainer merges → appears on
  hol.org within minutes.

Exact entry to add (copy-paste):

```json
{
  "name": "ClearJev",
  "url": "https://github.com/huncijr/ClearJev",
  "owner": "huncijr",
  "repo": "ClearJev",
  "description": "Automatic pre-prompt routing for Codex CLI: Jev (TypeSafe System One) judges every prompt and switches the session to the chosen model plus reasoning effort, with $clearjev chat control and a circuit breaker for bad API keys.",
  "category": "Development & Workflow",
  "source": "awesome-codex-plugins",
  "install_url": "https://raw.githubusercontent.com/huncijr/ClearJev/HEAD/plugins/clearjev-router/.codex-plugin/plugin.json"
}
```

Pre-flight (already verified in this repo):
- `install_url` returns the manifest (contains `name`, `version`,
  `skills`, `hooks`, `interface`).
- Referenced `./skills` and `./hooks/hooks.json` exist under
  `plugins/clearjev-router/`.

## 2. codex-marketplace.com — submit page package

- Site: https://www.codex-marketplace.com (400+ artifacts, community-rated)
- How: open the Submit Plugin page while signed in (GitHub sign-in only),
  enter the repository URL below. Automated review validates the manifest;
  ambiguous cases go to manual review. Nothing to install server-side.

Submit this:

- Repository URL: `https://github.com/huncijr/ClearJev`
- Plugin path in repo: `plugins/clearjev-router`
- One-command install for the listing:
  `npx codex-marketplace add huncijr/ClearJev --plugin`

If the form asks for a direct manifest URL, use the same `install_url` as
in section 1.

## 3. awesome-codex-cli (RoggeOhta) — README line package

- Repo: https://github.com/RoggeOhta/awesome-codex-cli (274 stars)
- How: fork → add one line under the Plugins section → open PR (or comment
  on openai/codex discussion #16329).

Exact line to add:

```md
- [ClearJev](https://github.com/huncijr/ClearJev) - Automatic Jev-powered pre-prompt model routing for Codex CLI with same-thread switching, `$clearjev` chat control, and API-key circuit breaker.
```

## After acceptance

- Users install with one command (section 0); the shell installer adds the
  runtime, CLI, hook, skill, and `/prompts:` aliases.
- Keep `version` in `.codex-plugin/plugin.json` bumped per release so hubs
  and users see updates.
- Never commit secrets; the TypeSafe key always stays on the user's machine
  (`~/.codex/clearjev/credentials.json`, owner-only).
