#!/bin/sh
# Remove only ClearJev-owned files and hook entries. Use --purge for key/state.
set -eu
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

HOOKS="$CODEX_HOME/hooks.json"
if [ -f "$HOOKS" ]; then
  HOOKS="$HOOKS" python3 - <<'PY'
import json, os
path = os.environ["HOOKS"]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
groups = data.get("hooks", {}).get("UserPromptSubmit", [])
kept = []
for group in groups:
    hooks = [hook for hook in group.get("hooks", [])
             if "clearjev-runtime" not in hook.get("command", "")
             and "clearjev-router/scripts/jev_route.py" not in hook.get("command", "")]
    if hooks:
        copy = dict(group)
        copy["hooks"] = hooks
        kept.append(copy)
if "hooks" in data and "UserPromptSubmit" in data["hooks"]:
    if kept:
        data["hooks"]["UserPromptSubmit"] = kept
    else:
        del data["hooks"]["UserPromptSubmit"]
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
fi

rm -rf "$CODEX_HOME/clearjev-runtime" "$CODEX_HOME/skills/clearjev" \
  "$HOME/.agents/skills/clearjev"
rm -f "$HOME/.local/bin/clearjev"
for name in clearjev clearjev-on clearjev-off clearjev-add clearjev-remove clearjev-key; do
  rm -f "$CODEX_HOME/prompts/$name.md"
done
if [ "$PURGE" -eq 1 ]; then rm -rf "$CODEX_HOME/clearjev"; fi
echo "ClearJev removed.$([ "$PURGE" -eq 1 ] && printf ' Key and state purged.')"
