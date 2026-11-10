$ErrorActionPreference = 'SilentlyContinue'
# Remove what this toolkit added. The upstream localization tool is untouched.
$here = $PSScriptRoot

$taskName = 'Antigravity Localization Guard'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  Write-Host "Removed task: $taskName"
}

$launcher = 'C:\ABP\launch.cmd'
if (Test-Path $launcher) {
  $txt = Get-Content $launcher -Raw
  if ($txt -match 'ag-han-huajin-guard') {
    $lines = $txt -split "`r?`n"
    $out = @()
    $skip = 0
    foreach ($l in $lines) {
      if ($skip -gt 0) { $skip--; continue }
      if ($l -match 'ag-han-huajin-guard') { $skip = 2; continue }   # the if(...) block: 2 lines
      $out += $l
    }
    Set-Content -Path $launcher -Value ($out -join "`r`n") -Encoding ASCII
    Write-Host "Unhooked: $launcher"
  }
}

foreach ($f in @('state.json', 'tool-path.txt', 'watcher.lock', 'guard.log', 'localize.out.txt', 'localize.err.txt')) {
  $p = Join-Path $here $f
  if (Test-Path $p) { Remove-Item $p -Force; Write-Host "Removed: $f" }
}

Write-Host ''
Write-Host 'The extra dictionary entries are still in the tool zh_data.json.'
Write-Host 'Restore the original with:  copy zh_data.json.bak-install zh_data.json'
