# ClearJev installer for Windows PowerShell 5.1+.
# Download-first: fetch the script, inspect it, then run it. Never pipe a
# download straight into the shell.
#   Invoke-WebRequest -OutFile $env:TEMP\clearjev-install.ps1 https://raw.githubusercontent.com/huncijr/ClearJev/main/scripts/install.ps1
#   notepad $env:TEMP\clearjev-install.ps1
#   powershell -ExecutionPolicy Bypass -File $env:TEMP\clearjev-install.ps1
# Idempotent: re-running without -Force detects the installed version and
# stops with "already downloaded". Routing state (on/off) is never reset.
param([switch]$Force)
$ErrorActionPreference = "Stop"
$Repo = "huncijr/ClearJev"

$Src = $null
foreach ($candidate in @(".", "plugins/clearjev-router", $env:PLUGIN_SRC)) {
  if ($candidate -and (Test-Path (Join-Path $candidate ".codex-plugin/plugin.json"))) {
    $Src = (Resolve-Path $candidate).Path
    break
  }
}
if (-not $Src) {
  $tmp = Join-Path $env:TEMP ("clearjev-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  Write-Host "Downloading ClearJev..."
  $zip = Join-Path $tmp "repo.zip"
  Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/heads/main.zip" -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $tmp
  $Src = Join-Path $tmp "ClearJev-main"
}

$usePy = $null -ne (Get-Command py -ErrorAction SilentlyContinue)
if (-not $usePy -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3 is required"
}
function Invoke-Python([string[]]$Arguments) {
  if ($script:usePy) { & py -3 @Arguments } else { & python @Arguments }
  if ($LASTEXITCODE -ne 0) { throw "Python command failed ($LASTEXITCODE)" }
}

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$runtime = Join-Path $codexHome "clearjev-runtime"
$manifest = Get-Content (Join-Path $Src ".codex-plugin/plugin.json") -Raw | ConvertFrom-Json
$srcVersion = $manifest.version
$installedVersionPath = Join-Path $runtime "VERSION"
if (-not $Force -and (Test-Path $installedVersionPath) -and (Test-Path (Join-Path $runtime "scripts/jev_route.py"))) {
  $installedVersion = (Get-Content $installedVersionPath -Raw).Trim()
  if ($installedVersion -eq $srcVersion) {
    Write-Host "ClearJev is already downloaded (v$installedVersion at $runtime)."
    Write-Host "Re-running without -Force changes nothing (routing state preserved)."
    Write-Host "Use -Force to reinstall, or run 'clearjev status' to verify."
    exit 0
  }
  Write-Host "Installed v$installedVersion found, source is v$srcVersion — upgrading."
}
$skill1 = Join-Path $codexHome "skills/clearjev"
$skill2 = Join-Path $HOME ".agents/skills/clearjev"
$prompts = Join-Path $codexHome "prompts"
$binDir = Join-Path $HOME ".local/bin"
foreach ($dir in @($codexHome, $prompts, $binDir)) {
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
}
if (Test-Path $runtime) { Remove-Item -Recurse -Force $runtime }
Copy-Item -Recurse $Src $runtime
Set-Content -NoNewline $installedVersionPath $srcVersion
Write-Host "runtime -> $runtime (v$srcVersion)"
foreach ($dest in @($skill1, $skill2)) {
  $parent = Split-Path $dest
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  Copy-Item -Recurse (Join-Path $runtime "skills/clearjev") $dest
  Write-Host "skill -> $dest"
}
Copy-Item -Force (Join-Path $runtime "scripts/clearjev.cmd") (Join-Path $binDir "clearjev.cmd")
Copy-Item -Force (Join-Path $runtime "prompts/*.md") $prompts
Write-Host "chat prompts -> $prompts"
$installedCli = Join-Path $binDir "clearjev.cmd"
try {
  $null = & $installedCli status 2>$null
  if ($LASTEXITCODE -eq 0) { Write-Host "cli self-check: OK ($installedCli status)" }
  else { Write-Warning "$installedCli status failed — check PATH and reinstall." }
+} catch { Write-Warning "$installedCli status failed — check PATH and reinstall." }
# Legacy cleanup (v0.1 layout): wrong-depth skill dir.
foreach ($legacy in @((Join-Path $codexHome "skills/clearjev-router"), (Join-Path $HOME ".agents/skills/clearjev-router"))) {
+  if (Test-Path $legacy) { Remove-Item -Recurse -Force $legacy }
+}

$hookScript = Join-Path $runtime "scripts/jev_route.py"
$env:CLEARJEV_HOOK_CMD = if ($usePy) { "py -3 `"$hookScript`"" } else { "python `"$hookScript`"" }
$env:CLEARJEV_CODEX_HOME = $codexHome
$mergeHooks = @'
import json, os, shutil
home = os.environ["CLEARJEV_CODEX_HOME"]
path = os.path.join(home, "hooks.json")
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise SystemExit("existing hooks.json is invalid; not modified: " + str(exc))
    shutil.copy2(path, path + ".clearjev.bak")
else:
    data = {}
groups = data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
entry = {"type": "command", "command": os.environ["CLEARJEV_HOOK_CMD"],
         "timeout": 12, "statusMessage": "ClearJev routing",
         "additionalContextLimit": 2000}
found = False
for group in groups:
    for hook in group.get("hooks", []):
        command = hook.get("command", "")
        if "clearjev-runtime" in command or "clearjev-router/scripts/jev_route.py" in command:
            hook.clear(); hook.update(entry); found = True
if not found:
    groups.append({"hooks": [entry]})
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2); f.write("\n")
print("hook -> " + path)
'@
if ($usePy) { $mergeHooks | & py -3 - } else { $mergeHooks | & python - }
if ($LASTEXITCODE -ne 0) { throw "Could not merge hooks.json" }

if (-not $env:TYPESAFE_API_KEY) {
  Write-Host ""
  Write-Host "ClearJev sends prompt text and limited repository metadata to TypeSafe when Jev is enabled."
  Write-Host "Get a key at https://console.typesafe.ai/keys, or leave this empty for heuristic fallback."
  $secure = Read-Host "TYPESAFE_API_KEY" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { $env:TYPESAFE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
if ($env:TYPESAFE_API_KEY) {
  Invoke-Python @($hookScript, "key", "import-env")
} else {
  Write-Host "No key saved; heuristic fallback remains available."
}
Invoke-Python @($hookScript, "status")
Write-Host ""
Write-Host "Installed and active by default (routing ON unless you turned it off"
Write-Host "before — that state is preserved). Pause anytime: clearjev off."
Write-Host "Restart Codex, trust ClearJev in /hooks, then open a new chat."
Write-Host 'Chat: use $clearjev with on/off/status/models/key actions.'
Write-Host "Shell: $binDir\clearjev.cmd status"
