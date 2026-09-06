$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'dayahead\tools\monitor_v40b_may_live.ps1') -Repo $repo -LibraryOnly
$master=[pscustomobject]@{completed_days=@(1..24);failed_days=@();paused_days=@('2025-05-21');last_update='test'}
$details=@{'2025-05-21'=[pscustomobject]@{case='B3';current_stage='B2_REPAIRED_WAITING_B3';completed_units=3;total_units=10}}
$view=Get-V40BPausedView $master $details
if ($view.Status -ne 'PAUSED_BY_USER' -or $view.Running -ne 0 -or $view.Completed -ne 24 -or $view.Failed -ne 0) {throw 'Wrong paused campaign state'}
if ($view.Rows[0].Status -ne 'PAUSED' -or $view.Orchestrator -ne 'STOPPED_BY_USER') {throw 'Pause displayed as crashed worker'}
if ((Get-MonitorFrame $view 120 | Out-String) -match 'FAILURE DETECTED|DEAD|STALE') {throw 'Intentional pause raised failure banner'}
Write-Output 'PASS: paused campaign, completed-day count, queued repaired B2, no false crash.'
