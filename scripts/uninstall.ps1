param([switch]$Purge)
$ErrorActionPreference = "Stop"
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$hooks = Join-Path $codexHome "hooks.json"
if (Test-Path $hooks) {
  $env:CLEARJEV_HOOKS = $hooks
  $script = @'
import json, os
path = os.environ["CLEARJEV_HOOKS"]
with open(path, encoding="utf-8-sig") as f: data = json.load(f)
groups = data.get("hooks", {}).get("UserPromptSubmit", [])
kept = []
for group in groups:
    hooks = [hook for hook in group.get("hooks", [])
             if "clearjev-runtime" not in hook.get("command", "")
             and "clearjev-router/scripts/jev_route.py" not in hook.get("command", "")]
    if hooks:
        copy = dict(group); copy["hooks"] = hooks; kept.append(copy)
if "hooks" in data and "UserPromptSubmit" in data["hooks"]:
    if kept: data["hooks"]["UserPromptSubmit"] = kept
    else: del data["hooks"]["UserPromptSubmit"]
with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2); f.write("\n")
'@
  if (Get-Command py -ErrorAction SilentlyContinue) { $script | & py -3 - } else { $script | & python - }
}
foreach ($path in @(
  (Join-Path $codexHome "clearjev-runtime"),
  (Join-Path $codexHome "skills/clearjev"),
  (Join-Path $HOME ".agents/skills/clearjev"),
  (Join-Path $codexHome "skills/clearjev-router"),
  (Join-Path $HOME ".agents/skills/clearjev-router")
)) { if (Test-Path $path) { Remove-Item -Recurse -Force $path } }
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $HOME ".local/bin/clearjev.cmd")
foreach ($name in @("clearjev", "clearjev-on", "clearjev-off", "clearjev-add", "clearjev-remove", "clearjev-key")) {
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $codexHome "prompts/$name.md")
}
if ($Purge) { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $codexHome "clearjev") }
Write-Host $(if ($Purge) { "ClearJev removed. Key and state purged." } else { "ClearJev removed. Key and state preserved." })
