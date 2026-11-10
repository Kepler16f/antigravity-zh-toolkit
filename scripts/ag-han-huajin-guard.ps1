$ErrorActionPreference = 'SilentlyContinue'
# Antigravity localization guard.
#
# An official IDE update replaces resources\app.asar (which carries the injected
# translation engine + dictionary), so the UI falls back to English.
# This detects that by comparing the asar SHA256 against the hash recorded after
# the last successful localization, and re-applies the patch.
#
#   IDE not running  -> patch right now (~30s)
#   IDE running      -> never kill it (unsaved work!); arm the exit-watcher,
#                       which patches within seconds after the user closes the IDE
#
# The scheduled task calls this every 5 minutes; the IDE launcher also calls it
# before starting the app.
#
# IMPORTANT: keep this file pure ASCII. Windows PowerShell 5.1 reads .ps1 as ANSI
# (GBK) unless it has a BOM, so any non-ASCII char here breaks parsing.

$here   = $PSScriptRoot
$asar   = Join-Path $env:LOCALAPPDATA 'Programs\antigravity\resources\app.asar'
$state  = Join-Path $here 'state.json'
$toolDirFile = Join-Path $here 'tool-path.txt'
$log    = Join-Path $here 'guard.log'
$outF   = Join-Path $here 'localize.out.txt'
$errF   = Join-Path $here 'localize.err.txt'
$watcher = Join-Path $here 'ag-han-huajin-watcher.ps1'

function Say($m) {
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $m" | Out-File -FilePath $log -Append -Encoding utf8
}

if (-not (Test-Path $asar)) { exit 0 }
if (-not (Test-Path $toolDirFile)) { exit 0 }
$toolDir = (Get-Content $toolDirFile -Raw).Trim()
$tool    = Join-Path $toolDir 'localize.py'
if (-not (Test-Path $tool)) { Say "localize.py not found under $toolDir"; exit 0 }

# locate python (prefer PATH, else pyenv builds)
$python = $null
$cmd = Get-Command python -ErrorAction SilentlyContinue
if ($cmd) { $python = $cmd.Source }
if (-not $python) {
  $pv = Get-ChildItem (Join-Path $env:USERPROFILE '.pyenv\pyenv-win\versions') -Recurse -Filter 'python.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($pv) { $python = $pv.FullName }
}
if (-not $python) { Say 'python not found, skip'; exit 0 }

$hash = (Get-FileHash $asar -Algorithm SHA256).Hash
if (Test-Path $state) {
  try {
    $st = Get-Content $state -Raw | ConvertFrom-Json
    if ($st.hash -eq $hash) { exit 0 }        # still our localized build
    Say 'app.asar changed (official update overwrote the patch), will re-localize'
  } catch { }
}

# IDE running: do NOT kill it. Arm the exit-watcher instead.
if (Get-Process Antigravity -ErrorAction SilentlyContinue) {
  Say 'IDE is running; arming exit-watcher instead'
  if (Test-Path $watcher) {
    Start-Process -FilePath 'powershell' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$watcher) -WindowStyle Hidden
  }
  exit 0
}

Say 'localizing...'
$p = Start-Process -FilePath $python -ArgumentList @($tool, 'apply', '--yes') -NoNewWindow -Wait -PassThru -RedirectStandardOutput $outF -RedirectStandardError $errF
if ($p -and $p.ExitCode -eq 0) {
  $new = (Get-FileHash $asar -Algorithm SHA256).Hash
  @{ hash = $new; at = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content $state -Encoding utf8
  Say "localized ok, new hash $new"
} else {
  $code = if ($p) { $p.ExitCode } else { 'n/a' }
  Say "localize failed (exit $code), see $errF"
}
exit 0
