$ErrorActionPreference = 'SilentlyContinue'
# Exit-watcher: waits for Antigravity to close, then re-localizes.
# Armed by ag-han-huajin-guard.ps1 when an official update overwrote the patch
# while the IDE was still running (we never kill a running IDE - unsaved work).
# Single instance via a marker file (2h TTL).
# Keep this file pure ASCII (PowerShell 5.1 reads .ps1 as ANSI).

$here   = $PSScriptRoot
$marker = Join-Path $here 'watcher.lock'
$log    = Join-Path $here 'guard.log'
$state  = Join-Path $here 'state.json'
$toolDirFile = Join-Path $here 'tool-path.txt'
$outF   = Join-Path $here 'localize.out.txt'
$errF   = Join-Path $here 'localize.err.txt'

function Say($m) {
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [watcher] $m" | Out-File -FilePath $log -Append -Encoding utf8
}

# single instance
if (Test-Path $marker) {
  $age = (Get-Date) - (Get-Item $marker).LastWriteTime
  if ($age.TotalHours -lt 2) { exit 0 }
}
Set-Content -Path $marker -Value (Get-Date -Format o)

try {
  Say 'armed; waiting for Antigravity to exit (max 12h)'
  $deadline = (Get-Date).AddHours(12)
  while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process Antigravity -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 3
  }
  if (Get-Process Antigravity -ErrorAction SilentlyContinue) { Say 'IDE still running at deadline; giving up'; return }
  Start-Sleep -Seconds 3
  if (Get-Process Antigravity -ErrorAction SilentlyContinue) { Say 'IDE reappeared quickly; giving up'; return }

  $toolDir = (Get-Content $toolDirFile -Raw).Trim()
  $tool    = Join-Path $toolDir 'localize.py'
  if (-not (Test-Path $tool)) { Say 'localize.py not found'; return }

  $python = $null
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { $python = $cmd.Source }
  if (-not $python) {
    $pv = Get-ChildItem (Join-Path $env:USERPROFILE '.pyenv\pyenv-win\versions') -Recurse -Filter 'python.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pv) { $python = $pv.FullName }
  }
  if (-not $python) { Say 'python not found'; return }

  Say 'IDE closed; re-localizing now'
  $p = Start-Process -FilePath $python -ArgumentList @($tool, 'apply', '--yes') -NoNewWindow -Wait -PassThru -RedirectStandardOutput $outF -RedirectStandardError $errF
  if ($p -and $p.ExitCode -eq 0) {
    $asar = Join-Path $env:LOCALAPPDATA 'Programs\antigravity\resources\app.asar'
    if (Test-Path $asar) {
      $new = (Get-FileHash $asar -Algorithm SHA256).Hash
      @{ hash = $new; at = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content $state -Encoding utf8
      Say "localized ok after IDE exit, new hash $new"
    }
  } else {
    $code = if ($p) { $p.ExitCode } else { 'n/a' }
    Say "localize failed (exit $code), see $errF"
  }
} finally {
  Remove-Item $marker -ErrorAction SilentlyContinue
}
exit 0
