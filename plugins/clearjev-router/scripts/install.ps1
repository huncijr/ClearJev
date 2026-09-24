# ClearJev one-command installer — Windows (PowerShell).
#   irm https://raw.githubusercontent.com/huncijr/ClearJev/main/plugins/clearjev-router/scripts/install.ps1 | iex
$ErrorActionPreference = "Stop"
$Repo = "huncijr/ClearJev"

# 1. Locate or download the plugin source.
$Src = $null
foreach ($cand in @("plugins/clearjev-router", $env:PLUGIN_SRC)) {
  if ($cand -and (Test-Path (Join-Path $cand ".codex-plugin/plugin.json"))) { $Src = $cand; break }
}
if (-not $Src) {
  $tmp = Join-Path $env:TEMP ("clearjev-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  Write-Host "Downloading ClearJev..."
  $zip = Join-Path $tmp "repo.zip"
  Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/heads/main.zip" -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $tmp
  $Src = Join-Path $tmp "ClearJev-main/plugins/clearjev-router"
}

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$skill1 = Join-Path $codexHome "skills/clearjev-router"
$skill2 = Join-Path $HOME ".agents/skills/clearjev-router"

# 2. Install the skill in both discovery roots.
foreach ($dest in @($skill1, $skill2)) {
  $parent = Split-Path $dest
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  Copy-Item -Recurse -Path $Src -Destination $dest
  Write-Host "skill -> $dest"
}
$hookScript = Join-Path $skill1 "scripts/jev_route.py"

# Python launcher: prefer py, fall back to python.
$py = "py -3"
try { & py -3 --version 2>$null | Out-Null } catch { $py = "python" }
try { & $py.Split(" ")[0] --version 2>$null | Out-Null }
catch { Write-Error "Python 3 is required (install from python.org)"; exit 1 }

# 3. Merge hook into hooks.json.
if (-not (Test-Path $codexHome)) { New-Item -ItemType Directory -Path $codexHome | Out-Null }
$hooksPath = Join-Path $codexHome "hooks.json"
$data = @{ hooks = @{} }
if (Test-Path $hooksPath) {
  try { $data = Get-Content $hooksPath -Raw | ConvertFrom-Json -AsHashtable } catch { $data = @{ hooks = @{} } }
}
if (-not $data.hooks) { $data.hooks = @{} }
$entry = @{ type = "command"; command = "$py `"$hookScript`""; timeout = 12;
            statusMessage = "ClearJev routing"; additionalContextLimit = 2000 }
$groups = $data.hooks["UserPromptSubmit"]
if (-not $groups) { $groups = @(); $data.hooks["UserPromptSubmit"] = $groups }
$found = $false
foreach ($g in $groups) {
  foreach ($h in $g.hooks) {
    if ($h.command -like "*jev_route.py*") { foreach ($k in $entry.Keys) { $h[$k] = $entry[$k] }; $found = $true }
  }
}
if (-not $found) { $data.hooks["UserPromptSubmit"] += @{ hooks = @($entry) } }
$data | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 $hooksPath
Write-Host "hooks -> $hooksPath"

# 4. Enable features in config.toml.
$cfgPath = Join-Path $codexHome "config.toml"
$text = ""
if (Test-Path $cfgPath) { $text = Get-Content $cfgPath -Raw }
$need = @()
if ($text -notmatch "skills") { $need += "skills = true" }
if (($text -notmatch "hooks") -and ($text -notmatch "codex_hooks")) { $need += "hooks = true" }
if ($need.Count -gt 0) {
  if ($text -notmatch "\[features\]") { $text = $text.Trim() + "`n`n[features]`n" }
  $text = $text.TrimEnd() + "`n" + ($need -join "`n") + "`n"
  Set-Content -Encoding utf8 $cfgPath $text
  Write-Host "config -> $cfgPath"
} else { Write-Host "config already enables skills+hooks" }

# 5. `clearjev` CLI on PATH.
$binDir = Join-Path $HOME ".local/bin"
if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir | Out-Null }
Copy-Item -Force (Join-Path $skill1 "scripts/clearjev.cmd") (Join-Path $binDir "clearjev.cmd")
Write-Host "cli -> $binDir\clearjev.cmd"
if (($env:PATH -split ";") -notcontains $binDir) {
  Write-Host "NOTE: add $binDir to your user PATH to use 'clearjev on|off|status'."
}

# 6. API key.
if (-not $env:TYPESAFE_API_KEY) {
  Write-Host ""
  Write-Host "Get a Jev API key at https://console.typesafe.ai/keys"
  $key = Read-Host "Paste TYPESAFE_API_KEY (Enter to skip, heuristic fallback will be used)"
  if ($key) {
    [Environment]::SetEnvironmentVariable("TYPESAFE_API_KEY", $key, "User")
    $env:TYPESAFE_API_KEY = $key
    Write-Host "key saved to user environment"
  } else { Write-Host "No key set — continuing with heuristic fallback." }
}

Write-Host ""
& $py.Split(" ")[0] $hookScript --check
Write-Host ""
Write-Host "Done. Restart Codex (CLI/App), review the hook once in /hooks, then just write prompts."
Write-Host "Pause anytime: clearjev off | resume: clearjev on | status: clearjev status"
