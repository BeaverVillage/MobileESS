$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'dayahead\tools\monitor_v39e_may_campaign.ps1') -Repo $repo -LibraryOnly

$script:assertions = 0
function Assert-V39L {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:assertions++
}

$now = [DateTime]::UtcNow
$created = $now.AddMinutes(-1)
$master = [pscustomobject]@{
    orchestrator_pid = 12345
    orchestrator_creation_time_utc = $created.ToString('o')
    orchestrator_command_match_tokens = @('run_v39l_detached_may.py', '--scheduled-resume')
    heartbeat_timestamp_utc = $now.AddSeconds(-7).ToString('o')
    last_update = $now.AddSeconds(-7).ToString('o')
    completed_days = @('2025-05-01')
    running_days = @('2025-05-13')
    failed_days = @()
}
$process = [pscustomobject]@{
    ProcessId = 12345
    CreationDate = $created
    CommandLine = 'python run_v39l_detached_may.py --scheduled-resume'
}
$running = Get-CampaignLiveness $master $now 45 $process
Assert-V39L ($running.State -eq 'RUNNING' -and $running.IdentityMatches) 'Fresh matching process was not RUNNING'

$master.heartbeat_timestamp_utc = $now.AddSeconds(-46).ToString('o')
$stale = Get-CampaignLiveness $master $now 45 $process
Assert-V39L ($stale.State -eq 'STALE' -and $stale.Orchestrator -eq 'ALIVE') 'Old heartbeat was not STALE'

$deadMaster = $master.PSObject.Copy()
$deadMaster.orchestrator_pid = 2147483000
$dead = Get-CampaignLiveness $deadMaster $now 45
Assert-V39L ($dead.State -eq 'DEAD' -and $dead.Orchestrator -eq 'DEAD') 'Dead PID was not DEAD'

$wrongCreation = $process.PSObject.Copy()
$wrongCreation.CreationDate = $created.AddMinutes(-5)
$reusedPid = Get-CampaignLiveness $master $now 45 $wrongCreation
Assert-V39L ($reusedPid.State -eq 'DEAD' -and -not $reusedPid.IdentityMatches) 'Reused PID passed creation-time check'

$details = @{ '2025-05-13' = [pscustomobject]@{ status = 'RUNNING'; case = 'B3'; current_stage = 'B3_MESS04'; completed_units = 12; total_units = 14 } }
$view = Get-MonitorView $master $details @{} $stale
Assert-V39L ($view.Status -eq 'STALE' -and $view.Running -eq 0 -and $view.Rows[0].Status -eq 'STALE') 'Stale JSON still displayed RUNNING'
$view = Get-MonitorView $deadMaster $details @{} $dead
Assert-V39L ($view.Status -eq 'DEAD' -and $view.Running -eq 0 -and $view.Rows[0].Status -eq 'DEAD') 'Dead JSON still displayed RUNNING'
$deadFrame = @(Get-MonitorFrame $view)
Assert-V39L (($deadFrame -join "`n") -match 'Heartbeat\s+: STALE \(') 'Dead display did not label stale heartbeat'

$passMaster = $master.PSObject.Copy()
$passMaster.completed_days = @(1..31 | ForEach-Object { '2025-05-{0:00}' -f $_ })
$passMaster.running_days = @()
$passView = Get-MonitorView $passMaster @{} @{} $dead
Assert-V39L ($passView.Status -eq 'PASS') 'Terminal PASS state was lost'

$failMaster = $master.PSObject.Copy()
$failMaster.failed_days = @('2025-05-13')
$failDetails = @{ '2025-05-13' = [pscustomobject]@{ status = 'FAIL'; fail = $true; error = 'test failure' } }
$failView = Get-MonitorView $failMaster $failDetails @{} $running
Assert-V39L ($failView.Status -eq 'FAIL') 'FAIL state was lost'

Write-Output "PASS: $script:assertions V39L liveness assertions; RUNNING/STALE/DEAD/FAIL/PASS verified."
