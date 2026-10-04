param([string]$Root, [switch]$LibraryOnly, [switch]$Once, [switch]$Json)
# Port of PR25 V39E readonly monitor functions and PID/creation/command liveness.
# Presentation only: read existing authorities; never start/stop campaign work.
function Get-MonitorText {
    param($Value, [int]$Width = 120)
    $text = ([string]$Value -replace '\s+', ' ').Trim()
    if (-not $text) { return '-' }
    if ($text.Length -gt $Width) { return $text.Substring(0, $Width - 3) + '...' }
    return $text
}

function Get-MonitorDayRow {
    param([string]$Day, [string]$State, $Detail, [string]$Reason)
    $stage = Get-MonitorText $Detail.case
    $substage = [string]$Detail.current_stage
    if (-not $substage) { $substage = [string]$Detail.stage }
    if ($stage -ne '-' -and $substage.StartsWith($stage + '_')) {
        $substage = $substage.Substring($stage.Length + 1)
    }
    if ($Detail.full_milp_status) { $substage += ' / ' + $Detail.full_milp_status }
    elseif ($Detail.search_level) { $substage += ' / ' + $Detail.search_level }
    $progress = $State
    if ($null -ne $Detail.completed_units -and $null -ne $Detail.total_units -and $Detail.total_units -gt 0) {
        $progress = '{0}/{1}' -f $Detail.completed_units, $Detail.total_units
    }
    [pscustomobject]@{
        Date = $Day; Status = $State; Stage = $stage
        Substage = (Get-MonitorText $substage); Progress = $progress
        Result = $(if ($State -eq 'FAIL') { 'FAIL' } else { '-' })
        Reason = (Get-MonitorText $Reason)
    }
}

function Get-CampaignLiveness {
    param(
        $Master,
        [datetime]$NowUtc = ([DateTime]::UtcNow),
        [int]$FreshSeconds = 45,
        $ProcessInfo = $null
    )
    $heartbeat = [string]$Master.heartbeat_timestamp_utc
    if (-not $heartbeat) { $heartbeat = [string]$Master.last_update }
    $age = [double]::PositiveInfinity
    try { $age = [math]::Max(0, ($NowUtc.ToUniversalTime() - ([datetime]$heartbeat).ToUniversalTime()).TotalSeconds) }
    catch { }
    $pidValue = 0
    try { $pidValue = [int]$Master.orchestrator_pid } catch { }
    if ($pidValue -le 0) {
        return [pscustomobject]@{ State = 'DEAD'; Orchestrator = 'DEAD'; HeartbeatAgeSeconds = $age; IdentityMatches = $false }
    }
    if ($null -eq $ProcessInfo) {
        try { $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $pidValue" -ErrorAction Stop }
        catch { $ProcessInfo = $null }
    }
    if ($null -eq $ProcessInfo) {
        return [pscustomobject]@{ State = 'DEAD'; Orchestrator = 'DEAD'; HeartbeatAgeSeconds = $age; IdentityMatches = $false }
    }
    $identity = $true
    try {
        $expectedCreation = ([datetime]([string]$Master.orchestrator_creation_time_utc)).ToUniversalTime()
        $actualCreation = ([datetime]$ProcessInfo.CreationDate).ToUniversalTime()
        $identity = [math]::Abs(($expectedCreation - $actualCreation).TotalSeconds) -le 2
    } catch { $identity = $false }
    $tokens = @($Master.orchestrator_command_match_tokens | Where-Object { $_ })
    if ($tokens.Count -eq 0) { $identity = $false }
    $command = [string]$ProcessInfo.CommandLine
    foreach ($token in $tokens) {
        if ($command.IndexOf([string]$token, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { $identity = $false }
    }
    if (-not $identity) {
        return [pscustomobject]@{ State = 'DEAD'; Orchestrator = 'DEAD'; HeartbeatAgeSeconds = $age; IdentityMatches = $false }
    }
    if ($age -gt $FreshSeconds) {
        return [pscustomobject]@{ State = 'STALE'; Orchestrator = 'ALIVE'; HeartbeatAgeSeconds = $age; IdentityMatches = $true }
    }
    return [pscustomobject]@{ State = 'RUNNING'; Orchestrator = 'ALIVE'; HeartbeatAgeSeconds = $age; IdentityMatches = $true }
}

function Get-MonitorView {
    param($Master, [hashtable]$Details, [hashtable]$Failures, $Liveness = $null)
    $completed = @($Master.completed_days | Where-Object { $_ })
    $running = @($Master.running_days | Where-Object { $_ })
    $failed = @($Master.failed_days | Where-Object { $_ })
    $days = @(@($completed) + @($running) + @($failed) + @($Failures.Keys) | Sort-Object -Unique)
    $passed = @{}
    foreach ($day in $days) {
        $detail = $Details[$day]
        $isFailure = $day -in $failed -or $detail.status -eq 'FAIL' -or $detail.fail -eq $true
        if ($isFailure) {
            $reason = [string]$detail.error_summary
            if (-not $reason) { $reason = [string]$detail.error }
            if (-not $reason -and $day -eq $Master.latest_failure) { $reason = [string]$Master.exact_current_blocker }
            if (-not $reason -and $Failures.ContainsKey($day)) { $reason = $Failures[$day].Reason }
            # Preserve the failing stage while a subsequent repair is RUNNING.
            if (-not $Failures.ContainsKey($day) -or $detail.status -eq 'FAIL' -or $detail.fail -eq $true) {
                $Failures[$day] = Get-MonitorDayRow $day 'FAIL' $detail $reason
            }
        }
        elseif ($detail.status -eq 'PASS' -or $detail.pass -eq $true -or
                ($day -in $completed -and $day -notin $running -and -not $Failures.ContainsKey($day))) {
            $Failures.Remove($day)
            $passed[$day] = $true
        }
    }
    $rows = @()
    foreach ($day in @(@($running) + @($Failures.Keys) | Sort-Object -Unique)) {
        if ($Failures.ContainsKey($day)) {
            if ($day -in $running -and $Details[$day].status -eq 'RUNNING') {
                $rows += Get-MonitorDayRow $day 'FAIL' $Details[$day] $Failures[$day].Reason
            }
            else { $rows += $Failures[$day] }
        }
        elseif (-not $passed.ContainsKey($day)) {
            $state = 'RUNNING'
            if ($null -ne $Liveness -and $Liveness.State -in @('DEAD', 'STALE')) { $state = $Liveness.State }
            if ($Details[$day].status -eq 'PENDING') { $state = 'PENDING' }
            $rows += Get-MonitorDayRow $day $state $Details[$day] ''
        }
    }
    $status = 'RUNNING'
    if ($Failures.Count -gt 0) { $status = 'FAIL' }
    elseif ($passed.Count -eq 31 -and $rows.Count -eq 0) { $status = 'PASS' }
    elseif ($null -ne $Liveness -and $Liveness.State -in @('DEAD', 'STALE')) { $status = $Liveness.State }
    $runningCount = @($running | Where-Object { -not $passed.ContainsKey($_) }).Count
    if ($null -ne $Liveness -and $Liveness.State -ne 'RUNNING') { $runningCount = 0 }
    [pscustomobject]@{
        Completed = $passed.Count; Total = 31
        Percent = [math]::Round(100.0 * $passed.Count / 31, 1)
        Running = $runningCount
        Failed = $Failures.Count; Status = $status
        Rows = @($rows); Failures = @($Failures.Values | Sort-Object Date)
        LastUpdate = $Master.last_update
        Orchestrator = $(if ($null -eq $Liveness) { 'UNKNOWN' } else { $Liveness.Orchestrator })
        HeartbeatAgeSeconds = $(if ($null -eq $Liveness) { $null } else { $Liveness.HeartbeatAgeSeconds })
    }
}

function Get-MonitorFrame {
    param($View, [int]$Width = 120, [string]$SourceWarning = '')
    # Keep the ordinary four-worker display within a 120 x 30 console.
    $width = [math]::Max(70, $Width - 1)
    $subWidth = [math]::Max(14, $width - 55)
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add(('=' * [math]::Min(76, $width)))
    $lines.Add(' MAY 2025 CAMPAIGN MONITOR')
    if ($View.Failed -gt 0) { $lines.Add('!!! FAILURE DETECTED !!!') }
    if ($SourceWarning) { $lines.Add((Get-MonitorText "SOURCE WARNING: $SourceWarning" $width)) }
    $lines.Add(('Progress : {0} / {1} days ({2}%)' -f $View.Completed, $View.Total, $View.Percent))
    $lines.Add(('Running  : {0}' -f $View.Running))
    $lines.Add(('Failed   : {0}' -f $View.Failed))
    $lines.Add(('Status   : {0}' -f $View.Status))
    $lines.Add(('Orchestrator : {0}' -f $View.Orchestrator))
    $heartbeatText = if ($null -eq $View.HeartbeatAgeSeconds) { '-' } elseif ([double]::IsPositiveInfinity($View.HeartbeatAgeSeconds)) { 'STALE' } elseif ($View.Status -in @('DEAD', 'STALE')) { 'STALE ({0:N0} s)' -f $View.HeartbeatAgeSeconds } else { '{0:N0} s ago' -f $View.HeartbeatAgeSeconds }
    $lines.Add(('Heartbeat    : {0}' -f $heartbeatText))
    $lines.Add('')
    $lines.Add('ACTIVE / FAILED DATES')
    $format = '{0,-10} {1,-7} {2,-10} {3,-' + $subWidth + '} {4,-8} {5}'
    $lines.Add(($format -f 'DATE', 'STATUS', 'STAGE', 'SUB-STAGE', 'PROGRESS', 'RESULT'))
    if ($View.Rows.Count -eq 0) { $lines.Add('None') }
    foreach ($row in $View.Rows) {
        $lines.Add(($format -f $row.Date, $row.Status, (Get-MonitorText $row.Stage 10),
            (Get-MonitorText $row.Substage $subWidth), $row.Progress, $row.Result))
    }
    $lines.Add('')
    $lines.Add('FAILURES')
    if ($View.Failures.Count -eq 0) { $lines.Add('None') }
    foreach ($failure in $View.Failures) {
        $lines.Add((Get-MonitorText ('{0} | {1} / {2} | {3}' -f $failure.Date,
            $failure.Stage, $failure.Substage, $failure.Reason) $width))
    }
    $lines.Add('')
    $lines.Add(('Last update: {0}' -f $View.LastUpdate))
    $lines.Add('Refresh: 10s | Ctrl+C: close monitor only')
    $lines.Add(('=' * [math]::Min(76, $width)))
    return $lines.ToArray()
}

function Read-AtomicSnapshot {
    param([string]$Path, $Previous)
    try { return Get-Content -LiteralPath $Path -Encoding UTF8 -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop }
    catch { return $Previous }
}

function Get-B1Frame {
    param($Live,$Heartbeat,$Resource,[hashtable]$Failures)
    $process = $Heartbeat.process
    $master = [pscustomobject]@{
        heartbeat_timestamp_utc=$Heartbeat.timestamp_UTC; last_update=$Live.timestamp_UTC
        orchestrator_pid=$process.PID
        orchestrator_creation_time_utc=([DateTimeOffset]::FromUnixTimeMilliseconds([long]($process.creation_time*1000))).UtcDateTime.ToString('o')
        orchestrator_command_match_tokens=@('v42_b1_production','--root',$Root)
        completed_days=@($Live.day_rows | Where-Object status -eq 'PASS' | ForEach-Object day)
        running_days=@($Live.day_rows | Where-Object { $_.status -ne 'PASS' -and $_.status -ne 'NOT_RUN' -and $_.status -ne 'FAIL' } | ForEach-Object day)
        failed_days=@($Live.day_rows | Where-Object status -eq 'FAIL' | ForEach-Object day)
    }
    $details=@{}
    foreach($row in $Live.day_rows) {
        $details[$row.day]=[pscustomobject]@{status=$row.status;case='B1';current_stage=$row.stage;error_summary=$row.reason}
    }
    $liveness=Get-CampaignLiveness $master
    $view=Get-MonitorView $master $details $Failures $liveness
    $state=if ($liveness.State -in @('DEAD','STALE')) {$liveness.State} else {$Live.state}
    [pscustomobject]@{State=$state; Liveness=$liveness; View=$view; Live=$Live; Resource=$Resource; Readonly=$true; Root=$Root}
}

if ($LibraryOnly) { return }
if (-not $Root) { throw 'Run root required' }
$Host.UI.RawUI.WindowTitle='Mobile ESS V42 May B1 Production Monitor'
$live=$null; $heartbeat=$null; $resource=$null; $failures=@{}
do {
    $live=Read-AtomicSnapshot (Join-Path $Root 'B1_LIVE_STATUS.json') $live
    $heartbeat=Read-AtomicSnapshot (Join-Path $Root 'B1_HEARTBEAT.json') $heartbeat
    $resource=Read-AtomicSnapshot (Join-Path $Root 'B1_RESOURCE_LIVE.json') $resource
    if ($live.process -and $heartbeat.process) {
        $frame=Get-B1Frame $live $heartbeat $resource $failures
        if ($Json) { $frame | ConvertTo-Json -Depth 20 }
        else {
            if (-not $Once) { Clear-Host }
            Write-Host 'Mobile ESS V42 May B1 Production Monitor'
            Write-Host ("Run: {0} | State: {1} | Coordinator: {2} | heartbeat age: {3:N1}s" -f $live.run_id,$frame.State,$frame.Liveness.Orchestrator,$frame.Liveness.HeartbeatAgeSeconds)
            Write-Host ("B1: {0}/31 PASS | stages: {1}/155 | day-worker=1 | Threads=1 | A1 total TimeLimit=1800s" -f $live.PASS_days,$live.stage_PASS)
            Write-Host ("RAM available: {0:N2} GiB | commit: {1:N2}% | tree RSS: {2:N2} GiB | A1 RSS: {3:N2} GiB" -f $resource.available_GiB,$resource.commit_percent,$resource.B1_tree_RSS_GiB,$resource.A1_solver_RSS_GiB)
            Write-Host ("CPU: {0}% | pagefile: {1:N2} GiB | pages input/sec: {2} | foreign heavy: {3}" -f $resource.CPU_percent,$resource.pagefile_used_GiB,$resource.pages_input_per_sec,(@($resource.foreign_heavy).Count))
            Write-Host 'B2=0 B3=0 M1=0 M2=0 | MESS OFF | reoptimization=0 | P/Q repair=0'
            Write-Host ''
            Write-Host 'ACTIVE / FAILED DATES (completed PASS dates omitted)'
            if ($frame.View.Rows.Count) { $frame.View.Rows | Format-Table Date,Status,Stage,Substage,Progress,Reason -AutoSize | Out-Host }
            else { Write-Host 'None' }
            if ($live.active.stage -eq 'A1' -and $live.progress) {
                $p=$live.progress
                $metrics=foreach($key in @('phase','solver_status','elapsed','incumbent','BestBd','gap','node_count')) {
                    $v=$p.$key; if($null -eq $v) {$v='N/A'}; "$key=$v"
                }
                Write-Host ($metrics -join ' | ')
            } else { Write-Host 'A1 objective/incumbent/BestBd/gap/nodes: N/A' }
            if ($live.active.stage -eq 'FRESH_AC' -and $null -ne $live.progress.OpenDSS_slot) {
                Write-Host ("Fresh OpenDSS: {0}/96" -f $live.progress.OpenDSS_slot)
            } else { Write-Host 'Fresh OpenDSS progress: N/A' }
            Write-Host 'Atomic status reads | Refresh 1s | Ctrl+C closes only this monitor'
        }
    } elseif ($Once) { throw 'Live status/heartbeat not ready' }
    else { Write-Host 'Waiting for atomic B1 status/heartbeat...' }
    if (-not $Once) { Start-Sleep -Seconds 1 }
} while (-not $Once)
