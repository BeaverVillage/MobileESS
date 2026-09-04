param(
    [string]$ProjectRoot,
    [string]$StatusRoot,
    [int]$ExpectedCount = 31,
    [int]$RefreshSeconds = 10,
    [switch]$Once,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
if (-not $StatusRoot) {
    $StatusRoot = Join-Path $ProjectRoot 'dayahead\artifacts\v37_may_locked_final\status'
}
$artifactRoot = Join-Path $ProjectRoot 'dayahead\artifacts\v37_may_locked_final'
$lockPath = Join-Path $artifactRoot 'V37_MONITOR.lock.json'
$summaryPath = Join-Path $artifactRoot 'V37_MAY_FINAL_REVIEW.md'
$meetingPath = Join-Path $artifactRoot 'V37_MAY_MEETING_TABLE.csv'
[Console]::Title = 'MobileESS V37 May Final Monitor'
New-Item -ItemType Directory -Force -Path $StatusRoot | Out-Null

function Test-LivePid([int]$ProcessId) {
    if ($ProcessId -le 0) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Write-AtomicJson([string]$Path, [object]$Value) {
    $temporary = "$Path.$PID.tmp"
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

$ownsLock = $false
if (-not $Once) {
    if (Test-Path -LiteralPath $lockPath) {
        try { $prior = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json } catch { $prior = $null }
        if ($null -ne $prior -and (Test-LivePid ([int]$prior.pid))) {
            Write-Host "MONITOR_ALREADY_RUNNING pid=$($prior.pid)"
            exit 0
        }
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
    Write-AtomicJson $lockPath ([ordered]@{ artifact_id='V37_MONITOR_LOCK_V1'; pid=$PID; started_at=(Get-Date).ToUniversalTime().ToString('o') })
    $ownsLock = $true
}

function Get-MonitorView {
    $rows = @()
    Get-ChildItem -LiteralPath $StatusRoot -Filter '2025-05-*.json' -File -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
        try {
            $value = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            if ($value.date -match '^2025-05-\d\d$') { $rows += $value }
        } catch {
            # Atomic writers make this exceptional; a transient invalid file is ignored.
        }
    }
    $passed = @($rows | Where-Object { $_.status -eq 'PASS' }).Count
    $failed = @($rows | Where-Object { $_.status -eq 'FAIL' }).Count
    $active = @($rows | Where-Object { $_.status -eq 'RUNNING' } | Sort-Object date)
    $pending = @($rows | Where-Object { $_.status -eq 'PENDING' } | Sort-Object date)
    $lastFail = @($rows | Where-Object { $_.status -eq 'FAIL' } | Sort-Object last_update -Descending | Select-Object -First 1)
    [ordered]@{
        PASS = $passed
        FAIL = $failed
        ACTIVE = $active.Count
        REMAIN = [Math]::Max(0, $ExpectedCount - $passed - $failed)
        active_dates = @($active)
        next_pending = if ($pending.Count) { $pending[0].date } else { $null }
        last_fail = if ($lastFail.Count) { [ordered]@{ date=$lastFail[0].date; error_summary=$lastFail[0].error_summary } } else { $null }
        complete = (($passed + $failed) -ge $ExpectedCount -and $active.Count -eq 0)
    }
}

function Write-ActiveDetail([object]$row) {
    $done = if ($null -ne $row.major_units_done) { [int]$row.major_units_done } else { [int]$row.completed_units }
    $total = if ($null -ne $row.major_units_total) { [int]$row.major_units_total } else { [int]$row.total_units }
    $stage = if ($row.stage) { [string]$row.stage } else { [string]$row.current_stage }
    Write-Host (" {0} RUN {1,2}/{2}  {3}" -f $row.date,$done,$total,$stage)
    if ($stage -match '_RESTORATION$') {
        $round = if ($null -ne $row.restoration_round) { [int]$row.restoration_round } else { 0 }
        $roundMax = if ($null -ne $row.restoration_round_max) { [int]$row.restoration_round_max } else { 5 }
        $newCuts = if ($null -ne $row.restoration_new_cuts) { [int]$row.restoration_new_cuts } else { 0 }
        $totalCuts = if ($null -ne $row.restoration_total_cuts) { [int]$row.restoration_total_cuts } else { 0 }
        if ($null -ne $row.fresh_slots_done) {
            Write-Host ("   round {0}/{1} | cuts +{2} / total {3} | Fresh {4}/{5}" -f $round,$roundMax,$newCuts,$totalCuts,$row.fresh_slots_done,$row.fresh_slots_total)
        } else {
            Write-Host ("   round {0}/{1} | cuts +{2} / total {3} | {4}" -f $round,$roundMax,$newCuts,$totalCuts,$row.full_milp_status)
        }
        return
    }
    if ($null -ne $row.fresh_slots_done) {
        Write-Host ("   Fresh {0}/{1}" -f $row.fresh_slots_done,$row.fresh_slots_total)
        return
    }
    if ($null -ne $row.seed_total) {
        $parent = if ($null -ne $row.beam_parent_index) { "parent $($row.beam_parent_index)/$($row.beam_parent_total) | " } else { '' }
        Write-Host ("   {0}{1} | seed {2}/{3} | {4}" -f $parent,$row.search_level,$row.seed_done,$row.seed_total,$row.full_milp_status)
        return
    }
    if ($null -ne $row.candidate_total) {
        $parent = if ($null -ne $row.beam_parent_index) { "parent $($row.beam_parent_index)/$($row.beam_parent_total) | " } else { '' }
        $newPart = if ($null -ne $row.candidate_new_total) { " | new $($row.candidate_new_done)/$($row.candidate_new_total)" } else { '' }
        Write-Host ("   {0}{1} | cand {2}/{3}{4}" -f $parent,$row.search_level,$row.candidate_done,$row.candidate_total,$newPart)
        return
    }
    if ($row.full_milp_status) {
        Write-Host ("   {0}" -f $row.full_milp_status)
    } else {
        Write-Host '   running'
    }
}

try {
    do {
        $view = Get-MonitorView
        if ($Json) {
            $view | ConvertTo-Json -Depth 6 -Compress
        } else {
            if (-not $Once) { Clear-Host }
            Write-Host '=========================================================='
            if ($view.complete) {
                Write-Host ' V37 MAY LOCKED FINAL - COMPLETE'
            } else {
                Write-Host " V37 MAY LOCKED FINAL | 4 DAYS PARALLEL | REFRESH ${RefreshSeconds}s"
            }
            Write-Host (" PASS  {0}   FAIL  {1}   ACTIVE  {2}   REMAIN  {3}" -f $view.PASS,$view.FAIL,$view.ACTIVE,$view.REMAIN)
            Write-Host '=========================================================='
            foreach ($row in $view.active_dates) {
                Write-ActiveDetail $row
            }
            if ($null -ne $view.last_fail) {
                Write-Host (" LAST FAIL: {0} {1}" -f $view.last_fail.date,$view.last_fail.error_summary)
            }
            Write-Host ''
            Write-Host (" Updated: {0}" -f (Get-Date -Format 'HH:mm:ss'))
            if ($view.complete) {
                Write-Host ''
                Write-Host " Summary: $summaryPath"
                Write-Host " Meeting: $meetingPath"
            }
            Write-Host '=========================================================='
        }
        if (-not $Once) { Start-Sleep -Seconds $RefreshSeconds }
    } while (-not $Once)
} finally {
    if ($ownsLock -and (Test-Path -LiteralPath $lockPath)) {
        try {
            $current = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
            if ([int]$current.pid -eq $PID) { Remove-Item -LiteralPath $lockPath -Force }
        } catch { }
    }
}
