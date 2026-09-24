#!/bin/sh
# ClearJev one-command installer — macOS / Linux.
#   curl -fsSL https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.sh | sh
# What it does:
#   1. Gets the plugin (local repo if present, else downloads the tarball).
#   2. Copies the skill to $CODEX_HOME/skills + $HOME/.agents/skills.
#   3. Registers the UserPromptSubmit hook in ~/.codex/hooks.json (merged, never overwritten).
#   4. Enables skills+hooks in ~/.codex/config.toml.
#   5. Asks for TYPESAFE_API_KEY (https://console.typesafe.ai/keys).
set -eu

REPO="huncijr/ClearJev"
SRC=""
TMP=""

cleanup() { [ -n "$TMP" ] && [ -d "$TMP" ] && rm -rf "$TMP"; }
trap cleanup EXIT

# 1. Locate or download the plugin source.
if [ -f "plugins/clearjev-router/.codex-plugin/plugin.json" ]; then
  SRC="plugins/clearjev-router"
elif [ -n "${PLUGIN_SRC:-}" ] && [ -f "$PLUGIN_SRC/.codex-plugin/plugin.json" ]; then
  SRC="$PLUGIN_SRC"
else
  command -v curl >/dev/null || { echo "error: curl is required" >&2; exit 1; }
  TMP="$(mktemp -d)"
  echo "Downloading ClearJev..."
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP"
  SRC="$TMP/ClearJev-main/plugins/clearjev-router"
fi

command -v python3 >/dev/null || { echo "error: python3 is required" >&2; exit 1; }

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SKILL1="$CODEX_HOME/skills/clearjev-router"
SKILL2="$HOME/.agents/skills/clearjev-router"

# 2. Install the skill in both discovery roots (harmless duplicates).
for dest in "$SKILL1" "$SKILL2"; do
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -R "$SRC" "$dest"
  echo "skill -> $dest"
done
HOOK_CMD="python3 \"$SKILL1/scripts/jev_route.py\""

# 3+4. Merge hook + features via python3 (safe JSON/TOML handling).
HOOK_CMD="$HOOK_CMD" CODEX_HOME="$CODEX_HOME" python3 - <<'EOF'
import json, os
home = os.path.expanduser("~")
codex_home = os.environ.get("CODEX_HOME", os.path.join(home, ".codex"))
hook_cmd = os.environ["HOOK_CMD"]
os.makedirs(codex_home, exist_ok=True)

# hooks.json merge
hp = os.path.join(codex_home, "hooks.json")
try:
    with open(hp) as f:
        data = json.load(f)
except (OSError, ValueError):
    data = {}
hooks = data.setdefault("hooks", {})
groups = hooks.setdefault("UserPromptSubmit", [])
entry = {"type": "command", "command": hook_cmd, "timeout": 12,
         "statusMessage": "ClearJev routing", "additionalContextLimit": 2000}
holder = None
for g in groups:
    for h in g.get("hooks", []):
        if "jev_route.py" in h.get("command", ""):
            h.update(entry)
            holder = True
if not holder:
    groups.append({"hooks": [entry]})
with open(hp, "w") as f:
    json.dump(data, f, indent=2)
print("hooks -> " + hp)

# config.toml features
cp = os.path.join(codex_home, "config.toml")
text = ""
try:
    with open(cp) as f:
        text = f.read()
except OSError:
    text = ""
need = []
if "skills" not in text:
    need.append("skills = true")
if "hooks" not in text and "codex_hooks" not in text:
    need.append("hooks = true")
if need:
    if "[features]" not in text:
        text = text.rstrip() + "\n\n[features]\n" if text.strip() else "[features]\n"
    text = text.rstrip() + "\n" + "\n".join(need) + "\n"
    with open(cp, "w") as f:
        f.write(text)
    print("config -> " + cp)
else:
    print("config already enables skills+hooks")
EOF

# 5. `clearjev` CLI on PATH (on/off/status without touching config files).
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
cp -f "$SKILL1/scripts/clearjev" "$BIN/clearjev"
chmod +x "$BIN/clearjev"
echo "cli -> $BIN/clearjev"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "NOTE: add to PATH (e.g. export PATH=\"\$HOME/.local/bin:\$PATH\") to use 'clearjev on|off|status'." ;;
esac

# 6. API key.
if [ -z "${TYPESAFE_API_KEY:-}" ]; then
  echo ""
  echo "Get a Jev API key at https://console.typesafe.ai/keys"
  printf "Paste TYPESAFE_API_KEY (Enter to skip, heuristic fallback will be used): "
  read -r TYPESAFE_API_KEY || TYPESAFE_API_KEY=""
  export TYPESAFE_API_KEY
fi
if [ -n "${TYPESAFE_API_KEY:-}" ]; then
  RC="$HOME/.bashrc"
  [ -n "${ZSH_VERSION:-}" ] && RC="$HOME/.zshrc"
  [ -f "$HOME/.zshrc" ] && RC="$HOME/.zshrc"
  if ! grep -qs "TYPESAFE_API_KEY" "$RC" 2>/dev/null; then
    printf '\nexport TYPESAFE_API_KEY="%s"\n' "$TYPESAFE_API_KEY" >> "$RC"
    echo "key saved to $RC"
  fi
else
  echo "No key set — continuing with heuristic fallback."
fi

echo ""
python3 "$SKILL1/scripts/jev_route.py" --check || true
echo ""
echo "Done. Restart Codex (CLI/App), review the hook once in /hooks, then just write prompts."
echo "The Jev layer routes every prompt automatically before execution."
echo "Pause anytime: clearjev off | resume: clearjev on | status: clearjev status"
