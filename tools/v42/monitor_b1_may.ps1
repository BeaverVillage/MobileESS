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

function Get-B1OutputFolder {
    param($Live,$Checkpoint,[string]$Stage)
    $day=[string]$Live.active.day
    if (-not $day -or -not $Checkpoint.stages -or $Checkpoint.run_id -ne $Live.run_id) { return $null }
    $row=$Checkpoint.stages.PSObject.Properties["$day/$Stage"].Value
    if ($row.status -eq 'PASS') {
        $receipt=Read-AtomicSnapshot $row.receipt $null
        $id=$receipt.identity
        if ($receipt.mode -ne 'B1_PRODUCTION' -or -not $receipt.PASS) { return $null }
        $folder=[string]$receipt.folder
    } elseif ($row.status -eq 'RUNNING' -and $Stage -eq $Live.active.stage -and
              $row.worker.PID -eq $Live.active.worker.PID -and $row.worker.PID) {
        $request=Read-AtomicSnapshot $row.request $null
        $id=$request.identity; $folder=[string]$request.output
        if ($request.mode -ne 'B1_PRODUCTION') { return $null }
    } else { return $null }
    if ($id.arm -ne 'B1' -or $id.day -ne $day -or $id.stage -ne $Stage -or $id.run_id -ne $Live.run_id -or -not $folder) { return $null }
    $full=[IO.Path]::GetFullPath($folder)
    $prefix=[IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'
    if (-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { return $null }
    return $full
}

function Get-B1Metrics {
    param($Live,$Solve,$Audit,$Fresh)
    $rho=$null; $source=$null; $gap=$null
    $p=$Live.progress
    $stage=[string]$Live.active.stage
    if ($stage -in @('FRESH_AC','VALIDATION_FREEZE') -and $null -ne $Fresh.summary.rho_max_AC) {
        $rho=$Fresh.summary.rho_max_AC; $source='Fresh AC'
    } elseif ($stage -eq 'A1' -and $Live.state -eq 'RUNNING' -and
              $p.phase -eq 'rho' -and $p.solver_status -eq 'OPTIMIZING' -and $null -ne $p.incumbent) {
        $rho=$p.incumbent; $source='Planning'
    } elseif ($stage -in @('A1','PLANNING_FREEZE','ACTUAL','FRESH_AC','VALIDATION_FREEZE')) {
        if ($null -ne $Audit.P1_rho) { $rho=$Audit.P1_rho; $source='Planning' }
        else {
            $primary=@($Solve.passes | Where-Object component -eq 'rho' | Select-Object -Last 1)
            if ($primary.Count -and $null -ne $primary[0].objective) { $rho=$primary[0].objective; $source='Planning' }
        }
    }
    if ($stage -eq 'A1' -and $Live.state -eq 'RUNNING' -and $p.solver_status -eq 'OPTIMIZING') {
        $gap=$p.gap
    }
    # Preserve zero, reject NaN/Inf and sentinel values; never relabel a P2
    # intervention objective as line loading or fabricate a missing incumbent.
    if ($null -ne $rho -and (-not [double]::IsNaN([double]$rho)) -and
        (-not [double]::IsInfinity([double]$rho)) -and [double]$rho -ge 0 -and [double]$rho -lt 1e90) {
        $loadingText=('{0:N2}% ({1})' -f (100*[double]$rho),$source)
    } else { $rho=$null; $loadingText='-- (해 대기)' }
    if ($null -ne $gap -and (-not [double]::IsNaN([double]$gap)) -and
        (-not [double]::IsInfinity([double]$gap)) -and [double]$gap -ge 0 -and [double]$gap -lt 1e90) {
        $gapText=('{0:N2}%' -f (100*[double]$gap))
    } else { $gap=$null; $gapText='--' }
    [pscustomobject]@{Loading=$rho;Source=$source;Gap=$gap;LoadingText=$loadingText;GapText=$gapText}
}

function Get-CompactB1Lines {
    param($Frame,$Metrics)
    $live=$Frame.Live; $resource=$Frame.Resource
    $labels=@{RUNNING='실행 중';WAIT_RESOURCE='자원 대기';FAIL='실패';COMPLETE='완료';DEAD='연결 끊김';STALE='갱신 지연';INFRASTRUCTURE_FAILURE='실행 오류';INTERRUPTING_RESOURCE_GUARD='자원 보호 중'}
    $state=$labels[[string]$Frame.State]; if (-not $state) { $state=$Frame.State }
    $stage=[string]$live.active.stage; $phase=[string]$live.progress.phase
    $phaseLabels=@{MODEL_BUILD='모델 생성';SOURCE_VERIFICATION='입력 확인';rho='선로부하율 최적화';migration_count='이동 횟수 최소화';shift_magnitude='시간 변경 최소화';prestart_relocation='배치 변경 최소화'}
    $detail=$phaseLabels[$phase]
    $current=if ($live.active.day) { "$($live.active.day)  /  $stage" } else { '--' }
    if ($detail -and $stage -eq 'A1') { $current+=" · $detail" }
    if ($stage -eq 'FRESH_AC' -and $null -ne $live.progress.OpenDSS_slot) { $current+=" · $($live.progress.OpenDSS_slot)/96" }
    $lines=[Collections.Generic.List[string]]::new()
    $lines.Add('Mobile ESS | May 2025 · B1')
    $lines.Add(('상태  {0}     완료  {1}/31     실패  {2}' -f $state,$live.PASS_days,$Frame.View.Failed))
    $lines.Add(('현재  {0}' -f $current))
    $lines.Add('')
    $lines.Add(('최대 선로 부하율  {0}     Gap  {1}' -f $Metrics.LoadingText,$Metrics.GapText))
    $lines.Add('')
    $lines.Add(('RAM 여유  {0:N2} GiB     Commit  {1:N1}%' -f $resource.available_GiB,$resource.commit_percent))
    if ($Frame.State -eq 'WAIT_RESOURCE') {
        $reason=if (@($resource.foreign_heavy).Count) { '다른 대규모 계산 실행 중' }
            elseif ($resource.available_GiB -lt 1) { '가용 메모리 부족' }
            elseif ($resource.commit_percent -ge 95) { 'Commit 한도 대기' }
            elseif ($resource.catastrophic_sustained_paging) { '지속적인 페이징' }
            else { '자원 확인 중' }
        $lines.Add("대기 이유  $reason · 안전해지면 자동 재개")
    }
    foreach ($failure in $Frame.View.Failures) {
        $lines.Add((Get-MonitorText ("실패  $($failure.Date) · $($failure.Substage) · $($failure.Reason)") 110))
    }
    if ($Frame.Liveness.State -in @('DEAD','STALE')) { $lines.Add('상태 갱신이 멈췄습니다.') }
    return $lines.ToArray()
}

if ($LibraryOnly) { return }
if (-not $Root) { throw 'Run root required' }
$Root=(Resolve-Path -LiteralPath $Root).Path
$Host.UI.RawUI.WindowTitle='Mobile ESS V42 May B1 Production Monitor'
$live=$null; $heartbeat=$null; $resource=$null; $failures=@{}
do {
    $live=Read-AtomicSnapshot (Join-Path $Root 'B1_LIVE_STATUS.json') $live
    $heartbeat=Read-AtomicSnapshot (Join-Path $Root 'B1_HEARTBEAT.json') $heartbeat
    $resource=Read-AtomicSnapshot (Join-Path $Root 'B1_RESOURCE_LIVE.json') $resource
    if ($live.process -and $heartbeat.process) {
        $frame=Get-B1Frame $live $heartbeat $resource $failures
        $checkpoint=Read-AtomicSnapshot (Join-Path $Root 'CHECKPOINT.json') $null
        $a1=Get-B1OutputFolder $live $checkpoint 'A1'
        $freshFolder=Get-B1OutputFolder $live $checkpoint 'FRESH_AC'
        $solve=$null; $audit=$null; $fresh=$null
        if ($a1) {
            $solve=Read-AtomicSnapshot (Join-Path $a1 'A1_SOLVE_RESULT.json') $null
            $audit=Read-AtomicSnapshot (Join-Path $a1 'A1_PHYSICAL_AUDIT.json') $null
        }
        if ($freshFolder) { $fresh=Read-AtomicSnapshot (Join-Path $freshFolder 'FRESH_RESULT.json') $null }
        $metrics=Get-B1Metrics $live $solve $audit $fresh
        if ($Json) { [pscustomobject]@{Frame=$frame;Metrics=$metrics} | ConvertTo-Json -Depth 20 }
        else {
            if (-not $Once) { Clear-Host }
            $lines=Get-CompactB1Lines $frame $metrics
            $color=if ($frame.State -eq 'FAIL') {'Red'} elseif ($frame.State -eq 'WAIT_RESOURCE') {'Yellow'} else {'Cyan'}
            for ($i=0;$i -lt $lines.Count;$i++) {
                if ($i -eq 1) { Write-Host $lines[$i] -ForegroundColor $color }
                else { Write-Host $lines[$i] }
            }
        }
    } elseif ($Once) { throw 'Live status/heartbeat not ready' }
    else { Write-Host 'B1 상태를 기다리는 중...' }
    if (-not $Once) { Start-Sleep -Seconds 1 }
} while (-not $Once)
