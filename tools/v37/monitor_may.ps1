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
    [ordered]@{
        PASS = $passed
        FAIL = $failed
        ACTIVE = $active.Count
        REMAIN = [Math]::Max(0, $ExpectedCount - $passed - $failed)
        active_dates = @($active | ForEach-Object {
            [ordered]@{ date=$_.date; status=$_.status; completed_units=[int]$_.completed_units; total_units=[int]$_.total_units }
        })
        complete = (($passed + $failed) -ge $ExpectedCount -and $active.Count -eq 0)
    }
}

try {
    do {
        $view = Get-MonitorView
        if ($Json) {
            $view | ConvertTo-Json -Depth 6 -Compress
        } else {
            Clear-Host
            Write-Host '=========================================================='
            if ($view.complete) {
                Write-Host ' V37 MAY LOCKED FINAL - COMPLETE'
            } else {
                Write-Host " V37 MAY LOCKED FINAL | 4 DAYS PARALLEL | REFRESH ${RefreshSeconds}s"
            }
            Write-Host (" PASS  {0}   FAIL  {1}   ACTIVE  {2}   REMAIN  {3}" -f $view.PASS,$view.FAIL,$view.ACTIVE,$view.REMAIN)
            Write-Host '=========================================================='
            foreach ($row in $view.active_dates) {
                Write-Host (" {0}   RUN   {1,2}/{2}" -f $row.date,$row.completed_units,$row.total_units)
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
