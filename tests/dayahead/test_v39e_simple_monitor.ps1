$ErrorActionPreference = 'Stop'
$testRepo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $testRepo 'dayahead\tools\monitor_v39e_may_campaign.ps1') -Repo $testRepo -LibraryOnly

$script:assertions = 0
function Assert-Monitor {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:assertions++
}
function New-Master {
    param($Completed = @(), $Running = @(), $Failed = @())
    [pscustomobject]@{ completed_days = @($Completed); running_days = @($Running); failed_days = @($Failed)
        last_update = '2026-09-05T04:35:00+00:00'; latest_failure = $null; exact_current_blocker = $null }
}
$latch = @{}
$details = @{
    '2025-05-01' = [pscustomobject]@{ status = 'PASS'; pass = $true; completed_units = 14; total_units = 14 }
    '2025-05-06' = [pscustomobject]@{ status = 'RUNNING'; case = 'B3'; current_stage = 'B3_RESTORATION'; full_milp_status = 'P_Q_FULL_MILP_RUNNING'; completed_units = 13; total_units = 14 }
}
$master = New-Master @('2025-05-01') @('2025-05-06')
$view = Get-MonitorView $master $details $latch
Assert-Monitor ($view.Completed -eq 1 -and $view.Total -eq 31 -and $view.Running -eq 1 -and $view.Status -eq 'RUNNING') 'Summary incorrect'
Assert-Monitor ($view.Rows.Count -eq 1 -and $view.Rows[0].Date -eq '2025-05-06') 'Completed PASS date was not hidden'
Assert-Monitor ($view.Rows[0].Stage -eq 'B3' -and $view.Rows[0].Substage -eq 'RESTORATION / P_Q_FULL_MILP_RUNNING') 'Current authority stage not preserved'
Assert-Monitor ($view.Rows[0].Progress -eq '13/14') 'Invented progress percentage'

$details['2025-05-06'] = [pscustomobject]@{ status = 'RUNNING'; case = 'B3'; current_stage = 'B3_FRESH' }
$view = Get-MonitorView $master $details $latch
Assert-Monitor ($view.Rows[0].Substage -eq 'FRESH' -and $view.Rows[0].Progress -eq 'RUNNING') 'Past PASS stage persisted / fake progress'
$details['2025-05-06'] = [pscustomobject]@{ status = 'FAIL'; fail = $true; case = 'B3'; current_stage = 'B3_FRESH'; error_summary = 'Voltage gate failed' }
$view = Get-MonitorView $master $details $latch
Assert-Monitor ($view.Status -eq 'FAIL' -and $view.Failed -eq 1 -and $view.Rows[0].Result -eq 'FAIL') 'Failure not immediately latched'
$frame = @(Get-MonitorFrame $view)
Assert-Monitor ($frame[2] -eq '!!! FAILURE DETECTED !!!' -and ($frame -join "`n") -match 'Voltage gate failed') 'Failure banner or reason missing'
$details['2025-05-06'] = [pscustomobject]@{ status = 'RUNNING'; case = 'B3'; current_stage = 'B3_RESTORATION' }
$view = Get-MonitorView $master $details $latch
Assert-Monitor ($view.Rows[0].Substage -eq 'RESTORATION' -and $view.Failures[0].Substage -eq 'FRESH') 'Current repair stage and unresolved failure must remain distinct'
$view = Get-MonitorView (New-Master @('2025-05-01') @()) $details $latch
Assert-Monitor ($view.Failed -eq 1 -and $view.Rows[0].Substage -eq 'FRESH') 'Unresolved failure disappeared or lost failing stage'
$details['2025-05-06'] = [pscustomobject]@{ status = 'PASS'; pass = $true }
$view = Get-MonitorView (New-Master @('2025-05-01','2025-05-06') @()) $details $latch
Assert-Monitor ($view.Failed -eq 0 -and $view.Rows.Count -eq 0 -and $view.Completed -eq 2) 'Repaired PASS not cleared/hidden'

$view = Get-MonitorView (New-Master @(1..31 | ForEach-Object { '2025-05-{0:00}' -f $_ }) @()) @{} @{}
Assert-Monitor ($view.Status -eq 'PASS' -and $view.Completed -eq 31 -and $view.Percent -eq 100 -and $view.Rows.Count -eq 0) 'Whole-month terminal PASS incorrect'
$view = Get-MonitorView (New-Master @() @('2025-05-06')) @{} @{}
Assert-Monitor ($view.Rows[0].Stage -eq '-' -and $view.Rows[0].Substage -eq '-' -and $view.Rows[0].Progress -eq 'RUNNING') 'Missing fields produced invented stage/progress'

$four = @('2025-05-06','2025-05-07','2025-05-08','2025-05-09')
$view = Get-MonitorView (New-Master @('2025-05-01','2025-05-02','2025-05-03','2025-05-04','2025-05-05') $four) @{} @{}
$frame = @(Get-MonitorFrame $view 120)
Assert-Monitor ($frame.Count -le 30 -and @($frame | Where-Object { $_.Length -ge 120 }).Count -eq 0) 'Four-worker display exceeds 120 x 30 console'
Assert-Monitor (($frame -join "`n") -notmatch '2025-05-01|SHA|CPU|traceback') 'Hidden historical/technical output leaked into default UI'
$script = Get-Content -LiteralPath (Join-Path $testRepo 'dayahead\tools\monitor_v39e_may_campaign.ps1') -Raw
Assert-Monitor ($script -notmatch '(?im)^\s*(Start-Process|Stop-Process|Set-Content|Add-Content|Out-File|Remove-Item|python|gurobi)\b') 'Monitor execution must be read-only'
Assert-Monitor ($script -match 'Start-Sleep -Seconds 10') 'Refresh cadence changed'
Write-Output "PASS: $script:assertions monitor-only assertions; zero campaign/solver calls."
$frame
