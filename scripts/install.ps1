param(
  [string]$ToolDir = '',
  [switch]$SkipTask,
  [switch]$SkipLauncherHook
)
$ErrorActionPreference = 'Stop'
# One-shot installer for the Antigravity Chinese enhancement toolkit.
#   1) merge the extra dictionary entries into the upstream tool's zh_data.json
#   2) record the tool dir so the guard scripts can find localize.py
#   3) register a scheduled task that runs the guard every 5 minutes
#   4) hook the guard into C:\ABP\launch.cmd (if present) so the IDE always
#      starts Chinese
# Run:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1

$here = $PSScriptRoot
$patchFile = Join-Path $here '..\patches\zh_data.extra.json'
$toolDirFile = Join-Path $here 'tool-path.txt'

function Say($m) { Write-Host $m }

# ---------- 1) locate the upstream localization tool ----------
if (-not $ToolDir) {
  $cands = @()
  foreach ($root in @("$env:USERPROFILE", "$env:LOCALAPPDATA", "$env:USERPROFILE\Downloads", "$env:USERPROFILE\Desktop", 'C:\')) {
    $cands += Get-ChildItem $root -Recurse -Depth 3 -Filter 'localize.py' -File -ErrorAction SilentlyContinue |
              Where-Object { $_.DirectoryName -match 'ngk|hangua|HanHua|Hanzhua' } | Select-Object -ExpandProperty DirectoryName
  }
  $cands = $cands | Sort-Object -Unique
  if ($cands.Count -eq 1) { $ToolDir = $cands[0] }
  else {
    Say "Could not uniquely locate the localization tool (found $($cands.Count))."
    $cands | ForEach-Object { Say "   $_" }
    Say "Re-run with:  -ToolDir '<path to the tool folder>'"
    exit 1
  }
}
$tool = Join-Path $ToolDir 'localize.py'
if (-not (Test-Path $tool)) { Say "localize.py not found in $ToolDir"; exit 1 }
Say "Tool dir : $ToolDir"

# ---------- 2) merge the extra dictionary entries ----------
# NOTE: done in Python on purpose - PowerShell's ConvertFrom-Json treats
# dictionary keys case-insensitively and would choke on pairs like
# "ran commands" / "Ran commands" (the JS engine IS case-sensitive).
$dataFile = Join-Path $ToolDir 'zh_data.json'
if (-not (Test-Path $dataFile)) { Say "zh_data.json not found in $ToolDir"; exit 1 }

$python = $null
$cmd = Get-Command python -ErrorAction SilentlyContinue
if ($cmd) { $python = $cmd.Source }
if (-not $python) {
  $pv = Get-ChildItem (Join-Path $env:USERPROFILE '.pyenv\pyenv-win\versions') -Recurse -Filter 'python.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($pv) { $python = $pv.FullName }
}
if (-not $python) { Say 'python not found (required by the localization tool anyway)'; exit 1 }

& $python (Join-Path $here 'merge_dict.py') $ToolDir $patchFile
if ($LASTEXITCODE -ne 0) { Say 'dictionary merge failed'; exit 1 }

# Keep user-named content (conversation / project names) out of the translator.
# An upstream upgrade replaces engine.js, so this must run on every install.
# Non-fatal: localization still works without it, just with the user-content bug.
& $python (Join-Path $here 'patch_engine.py') $ToolDir
if ($LASTEXITCODE -ne 0) { Say 'WARNING: engine patch skipped (upstream engine.js layout changed?)' }

Set-Content -Path $toolDirFile -Value $ToolDir -Encoding UTF8

# ---------- 3) scheduled task ----------
if (-not $SkipTask) {
  $taskName = 'Antigravity Localization Guard'
  $action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$here\ag-han-huajin-guard.ps1`""
  try {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
      Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    $st = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
    $act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$here\ag-han-huajin-guard.ps1`""
    Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $st -Description 'Re-applies the Antigravity Chinese localization after an official update' -Force | Out-Null
    Say "Task     : $taskName (every 5 min)"
  } catch {
    Say "Task     : could not register ($($_.Exception.Message))"
    Say "           run ag-han-huajin-guard.ps1 manually, or add it to your own task."
  }
}

# ---------- 4) hook the launcher ----------
if (-not $SkipLauncherHook) {
  $launcher = 'C:\ABP\launch.cmd'
  if (Test-Path $launcher) {
    $txt = Get-Content $launcher -Raw
    if ($txt -notmatch 'ag-han-huajin-guard') {
      $hook = @"
REM Localization guard: re-apply the Chinese patch after an official update.
if exist "$here\ag-han-huajin-guard.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$here\ag-han-huajin-guard.ps1"
)
"@
      # insert before the line that starts the IDE
      $lines = $txt -split "`r?`n"
      $idx = ($lines | Select-String -Pattern '^\s*start\s+""?\s*%APP%|^\s*start\s+""\s+"%APP%"' | Select-Object -First 1).LineNumber
      if (-not $idx) { $idx = ($lines | Select-String -Pattern 'start\s+.*%APP%' | Select-Object -First 1).LineNumber }
      if ($idx) {
        $before = $lines[0..($idx - 2)]
        $after = $lines[($idx - 1)..($lines.Length - 1)]
        Set-Content -Path $launcher -Value (($before + ($hook -split "`r?`n") + $after) -join "`r`n") -Encoding ASCII
        Say "Launcher : hooked $launcher"
      } else {
        Say "Launcher : $launcher found, but could not locate the start line - add the guard call manually."
      }
    } else {
      Say "Launcher : already hooked"
    }
  } else {
    Say "Launcher : C:\ABP\launch.cmd not found (skip). Call ag-han-huajin-guard.ps1 before starting the IDE."
  }
}

Say ''
Say 'Done. Now re-apply the localization once so the new entries take effect:'
Say "  cd `"$ToolDir`""
Say '  python localize.py apply --yes'
