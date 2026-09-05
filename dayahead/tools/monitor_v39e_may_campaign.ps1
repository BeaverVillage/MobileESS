param(
    [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$LibraryOnly
)

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

if ($LibraryOnly) { return }

$progressPath = Join-Path $Repo 'progress\V39E_OVERNIGHT_PROGRESS.json'
$statusRoot = Join-Path $Repo 'dayahead\artifacts\v39e_full_may_2025\status'
$resultRoot = Join-Path $Repo 'dayahead\artifacts\v39e_full_may_2025\dates'
$dayLogRoot = Join-Path $Repo 'logs\v39e_may_2025'
$failureLatch = @{}
$detailCache = @{}
$masterCache = $null

while ($true) {
    $sourceWarning = ''
    try {
        $masterCache = Get-Content -LiteralPath $progressPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    }
    catch { $sourceWarning = 'Progress source unavailable; retaining last snapshot.' }
    if ($null -ne $masterCache) {
        $readDays = @(@($masterCache.completed_days) + @($masterCache.running_days) +
            @($masterCache.failed_days) + @($failureLatch.Keys) | Where-Object { $_ } | Sort-Object -Unique)
        foreach ($day in $readDays) {
            # Only dates from the authoritative May axis may identify local files.
            if ($day -notmatch '^2025-05-(0[1-9]|[12][0-9]|3[01])$') { continue }
            $path = Join-Path $statusRoot "$day.json"
            if (Test-Path -LiteralPath $path) {
                try { $detailCache[$day] = Get-Content -LiteralPath $path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop }
                catch { $sourceWarning = "Status source unavailable for $day; retaining last snapshot." }
            }
            if (($day -in $masterCache.failed_days -or $detailCache[$day].status -eq 'FAIL') -and
                    -not $detailCache[$day].error_summary -and -not $detailCache[$day].error) {
                $reason = $null
                try {
                    $result = Get-Content -LiteralPath (Join-Path $resultRoot "$day.json") -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
                    $reason = $result.error
                } catch { }
                if (-not $reason) {
                    # Logs are supplementary, only for an already authoritative failure.
                    $logPath = Join-Path $dayLogRoot "$day.log"
                    if (Test-Path -LiteralPath $logPath) {
                        $reason = Get-Content -LiteralPath $logPath -Tail 40 -ErrorAction SilentlyContinue |
                            Where-Object { $_ -match '(^|\s)(\w*Error|\w*Exception):' } | Select-Object -Last 1
                    }
                }
                if ($reason) {
                    if ($null -eq $detailCache[$day]) { $detailCache[$day] = [pscustomobject]@{} }
                    $detailCache[$day] | Add-Member -NotePropertyName error_summary -NotePropertyValue ([string]$reason) -Force
                }
            }
        }
        $liveness = Get-CampaignLiveness $masterCache
        $view = Get-MonitorView $masterCache $detailCache $failureLatch $liveness
        $consoleWidth = 120
        try { $consoleWidth = $Host.UI.RawUI.WindowSize.Width } catch { }
        Clear-Host
        Get-MonitorFrame $view $consoleWidth $sourceWarning | ForEach-Object { Write-Host $_ }
    }
    else {
        Clear-Host
        Write-Host 'MAY 2025 CAMPAIGN MONITOR'
        Write-Host 'Waiting for authoritative progress source...'
    }
    Start-Sleep -Seconds 10
}
