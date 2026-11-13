<#
.SYNOPSIS
  Install / uninstall the "one-click localization" plugin (antigravity-zh-manager).

.DESCRIPTION
  Copies plugin\antigravity-zh-manager into the Antigravity plugin directory
  (~/.gemini/config/plugins/antigravity-zh-manager) and registers it as enabled
  in ~/.gemini/config/config.json.

  The plugin carries no dictionary of its own: it drives the upstream
  "Antigravity YiJianHanHua" tool (localize.py) to apply / restore the patch.
  Run scripts\install.ps1 first so the extra entries are merged and the
  upstream tool is in place.

  IMPORTANT: keep this file pure ASCII. Windows PowerShell 5.1 reads .ps1 as ANSI
  (GBK) unless it has a BOM, so any non-ASCII char here breaks parsing.
#>
param(
  [string]$PluginDir = '',
  [switch]$Uninstall
)

$ErrorActionPreference = 'SilentlyContinue'

function Say($m, $kind = '') {
  if ($kind -eq 'ok')        { Write-Host "  [ok]   $m" }
  elseif ($kind -eq 'warn') { Write-Host "  [warn] $m" }
  elseif ($kind -eq 'err')  { Write-Host "  [err]  $m" }
  else { Write-Host "  $m" }
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
if (-not $PluginDir) { $PluginDir = Join-Path $repo 'plugin\antigravity-zh-manager' }

$home_ = $env:USERPROFILE
$pluginsRoot = Join-Path $home_ '.gemini\config\plugins'
$target = Join-Path $pluginsRoot 'antigravity-zh-manager'
$configFile = Join-Path $home_ '.gemini\config\config.json'

Say 'Antigravity zh toolkit - localization plugin'

# ---------- uninstall ----------
if ($Uninstall) {
  if (Test-Path $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
    Say "removed: $target" 'ok'
  } else {
    Say 'plugin not installed, nothing to remove'
  }
  # Drop the "enabled" registration. The sidecars section is maintained by the
  # host itself - do not touch it.
  if (Test-Path $configFile) {
    try {
      $cfg = Get-Content $configFile -Raw | ConvertFrom-Json
      if ($cfg.plugins -and ($cfg.plugins.PSObject.Properties.Name -contains 'antigravity-zh-manager')) {
        $cfg.plugins.PSObject.Properties.Remove('antigravity-zh-manager')
        $cfg | ConvertTo-Json -Depth 32 | Set-Content $configFile -Encoding UTF8
        Say 'disabled in config.json' 'ok'
      }
    } catch { Say "config.json update failed: $($_.Exception.Message)" 'warn' }
  }
  Say 'done. restart Antigravity to unload the sidecar.'
  exit 0
}

# ---------- install ----------
if (-not (Test-Path $PluginDir)) { Say "plugin source not found: $PluginDir" 'err'; exit 1 }
if (-not (Test-Path $pluginsRoot)) {
  New-Item -ItemType Directory -Path $pluginsRoot -Force | Out-Null
}

if (Test-Path $target) {
  Say "updating existing plugin at $target"
  Remove-Item -LiteralPath $target -Recurse -Force
}
Copy-Item -LiteralPath $PluginDir -Destination $target -Recurse -Force
Say "installed: $target" 'ok'

# config.json: register as enabled (the sidecars section is host-generated)
if (Test-Path $configFile) {
  try {
    $cfg = Get-Content $configFile -Raw | ConvertFrom-Json
    if (-not $cfg.plugins) {
      $cfg | Add-Member -NotePropertyName plugins -NotePropertyValue ([pscustomobject]@{}) -Force
    }
    if (-not ($cfg.plugins.PSObject.Properties.Name -contains 'antigravity-zh-manager')) {
      $cfg.plugins | Add-Member -NotePropertyName 'antigravity-zh-manager' -NotePropertyValue ([pscustomobject]@{ enabled = $true }) -Force
    } else {
      $cfg.plugins.'antigravity-zh-manager' | Add-Member -NotePropertyName enabled -NotePropertyValue $true -Force
    }
    $cfg | ConvertTo-Json -Depth 32 | Set-Content $configFile -Encoding UTF8
    Say 'registered in config.json (plugins.antigravity-zh-manager.enabled = true)' 'ok'
  } catch {
    Say "config.json update failed: $($_.Exception.Message)" 'warn'
    Say 'edit it by hand: add  "plugins": { "antigravity-zh-manager": { "enabled": true } }'
  }
} else {
  Say "config.json not found: $configFile" 'warn'
  Say 'edit it by hand: add  "plugins": { "antigravity-zh-manager": { "enabled": true } }'
}

# ---------- prerequisites ----------
Say ''
Say 'prerequisites'
$found = $null
foreach ($root in @('C:\agh', (Join-Path $home_ 'Desktop'), (Join-Path $home_ 'Downloads'))) {
  if (-not (Test-Path $root)) { continue }
  if (Test-Path (Join-Path $root 'localize.py')) { $found = $root; break }
  Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    if ((-not $found) -and (Test-Path (Join-Path $_.FullName 'localize.py'))) { $found = $_.FullName }
  }
}
if ($found) { Say "upstream tool found: $found" 'ok' }
else { Say 'upstream tool (localize.py) not found - run scripts\install.ps1 first' 'warn' }

Say ''
Say 'done. restart Antigravity, then open the localization panel from the plugin menu.'
