#!/bin/sh
# ClearJev installer for macOS and Linux.
# Download-first: fetch the script, inspect it, then run it. Never pipe a
# download straight into a shell.
#   curl -fsSL -o /tmp/clearjev-install.sh https://raw.githubusercontent.com/huncijr/ClearJev/main/scripts/install.sh
#   less /tmp/clearjev-install.sh
#   sh /tmp/clearjev-install.sh [--force]
# Idempotent: re-running without --force detects the installed version and
# stops with "already downloaded". Routing state (on/off) is never reset.
set -eu

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

REPO="huncijr/ClearJev"
SRC=""
TMP=""
cleanup() { [ -n "$TMP" ] && [ -d "$TMP" ] && rm -rf "$TMP"; return 0; }
trap cleanup EXIT

if [ -f ".codex-plugin/plugin.json" ]; then
  SRC="."
elif [ -f "plugins/clearjev-router/.codex-plugin/plugin.json" ]; then
  SRC="plugins/clearjev-router"
elif [ -n "${PLUGIN_SRC:-}" ] && [ -f "$PLUGIN_SRC/.codex-plugin/plugin.json" ]; then
  SRC="$PLUGIN_SRC"
else
  command -v curl >/dev/null || { echo "error: curl is required" >&2; exit 1; }
  TMP="$(mktemp -d)"
  echo "Downloading ClearJev..."
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP"
  SRC="$TMP/ClearJev-main"
fi

command -v python3 >/dev/null || { echo "error: python3 is required" >&2; exit 1; }
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
RUNTIME="$CODEX_HOME/clearjev-runtime"

SRC_VERSION="$(python3 -c "import json;print(json.load(open('$SRC/.codex-plugin/plugin.json'))['version'])")"
if [ "$FORCE" -eq 0 ] && [ -f "$RUNTIME/VERSION" ] && [ -f "$RUNTIME/scripts/jev_route.py" ]; then
  INSTALLED_VERSION="$(cat "$RUNTIME/VERSION")"
  if [ "$INSTALLED_VERSION" = "$SRC_VERSION" ]; then
    echo "ClearJev is already downloaded (v$INSTALLED_VERSION at $RUNTIME)."
    echo "Re-running without --force changes nothing (routing state preserved)."
    echo "Use '$0 --force' to reinstall, or 'clearjev status' to verify."
    python3 "$RUNTIME/scripts/jev_route.py" status || true
    exit 0
  fi
  echo "Installed v$INSTALLED_VERSION found, source is v$SRC_VERSION — upgrading."
fi
SKILL1="$CODEX_HOME/skills/clearjev"
SKILL2="$HOME/.agents/skills/clearjev"
PROMPTS="$CODEX_HOME/prompts"
BIN="$HOME/.local/bin"

mkdir -p "$CODEX_HOME" "$BIN" "$PROMPTS"
rm -rf "$RUNTIME"
cp -R "$SRC" "$RUNTIME"
printf '%s\n' "$SRC_VERSION" > "$RUNTIME/VERSION"
echo "runtime -> $RUNTIME (v$SRC_VERSION)"

for dest in "$SKILL1" "$SKILL2"; do
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -R "$RUNTIME/skills/clearjev" "$dest"
  echo "skill -> $dest"
done
# Legacy cleanup (v0.1 layout): wrong-depth skill dir + old shims.
rm -rf "$CODEX_HOME/skills/clearjev-router" "$HOME/.agents/skills/clearjev-router"
rm -f "$BIN/clearjev.cmd"

cp -f "$RUNTIME/scripts/clearjev" "$BIN/clearjev"
chmod +x "$BIN/clearjev"
for prompt in "$RUNTIME"/prompts/*.md; do cp -f "$prompt" "$PROMPTS/$(basename "$prompt")"; done
echo "chat prompts -> $PROMPTS"
# Self-check: the installed wrapper must reach a working router.
if "$BIN/clearjev" status >/dev/null 2>&1; then
  echo "cli self-check: OK ($BIN/clearjev status)"
else
  echo "WARNING: $BIN/clearjev status failed — check PATH and reinstall." >&2
fi

HOOK_CMD="python3 \"$RUNTIME/scripts/jev_route.py\""
HOOK_CMD="$HOOK_CMD" CODEX_HOME="$CODEX_HOME" python3 - <<'PY'
import json, os, shutil
codex_home = os.environ["CODEX_HOME"]
path = os.path.join(codex_home, "hooks.json")
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise SystemExit("error: existing hooks.json is invalid; not modified: " + str(exc))
    shutil.copy2(path, path + ".clearjev.bak")
else:
    data = {}
hooks = data.setdefault("hooks", {})
groups = hooks.setdefault("UserPromptSubmit", [])
entry = {"type": "command", "command": os.environ["HOOK_CMD"], "timeout": 12,
         "statusMessage": "ClearJev routing", "additionalContextLimit": 2000}
found = False
for group in groups:
    for hook in group.get("hooks", []):
        command = hook.get("command", "")
        if "clearjev-runtime" in command or "clearjev-router/scripts/jev_route.py" in command:
            hook.clear()
            hook.update(entry)
            found = True
if not found:
    groups.append({"hooks": [entry]})
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print("hook -> " + path)
PY

# Prompt for the key only when a real terminal answers (readable AND
# openable — `[ -r /dev/tty ]` alone is true even with no controlling
# terminal, which broke non-interactive installs). The probe runs in a
# subshell so a failed open can never trip `set -eu` in the parent.
can_prompt=0
if [ -z "${TYPESAFE_API_KEY:-}" ]; then
  if ( : </dev/tty ) 2>/dev/null; then can_prompt=1; fi
fi
if [ "$can_prompt" -eq 1 ]; then
  echo ""
  echo "ClearJev sends prompt text and limited repository metadata to TypeSafe when Jev is enabled."
  echo "Get a key at https://console.typesafe.ai/keys, or press Enter for local heuristic fallback."
  printf "Paste your API key: "
  stty -echo </dev/tty 2>/dev/null || true
  read -r TYPESAFE_API_KEY </dev/tty || TYPESAFE_API_KEY=""
  stty echo </dev/tty 2>/dev/null || true
  echo ""
fi
if [ -n "${TYPESAFE_API_KEY:-}" ]; then
  export TYPESAFE_API_KEY
  python3 "$RUNTIME/scripts/jev_route.py" key import-env
else
  echo "No key saved; heuristic fallback remains available."
fi

echo ""
python3 "$RUNTIME/scripts/jev_route.py" status
echo ""
echo "Installed and active by default (routing ON unless you turned it off"
echo "before — that state is preserved). Pause anytime: clearjev off."
echo "Restart Codex, trust ClearJev in /hooks, then open a new chat."
echo "Chat: use \$clearjev with on/off/status/models/key actions."
echo "Deprecated aliases: /prompts:clearjev, /prompts:clearjev-on, /prompts:clearjev-off."
echo "Shell: $BIN/clearjev status"
