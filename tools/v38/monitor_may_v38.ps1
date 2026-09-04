param(
    [string]$ProjectRoot,
    [int]$ExpectedCount = 31,
    [int]$RefreshSeconds = 10,
    [switch]$Once,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
$artifactRoot = Join-Path $ProjectRoot 'dayahead\artifacts\v38_aidc_spatiotemporal_wan'
$statusRoot = Join-Path $artifactRoot 'status'
$lockPath = Join-Path $artifactRoot 'V38_MONITOR.lock.json'
$readyPath = Join-Path $artifactRoot 'V38_READY_STATE.json'
$fingerprintPath = Join-Path $artifactRoot 'V38_IMPLEMENTATION_FINGERPRINT.json'
[Console]::Title = 'MobileESS V38 May Final Monitor'
New-Item -ItemType Directory -Force -Path $statusRoot | Out-Null

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
    Write-AtomicJson $lockPath ([ordered]@{
        artifact_id='V38_MONITOR_LOCK_V1'; pid=$PID
        title='MobileESS V38 May Final Monitor'; refresh_seconds=$RefreshSeconds
        started_at=(Get-Date).ToUniversalTime().ToString('o')
    })
    $ownsLock = $true
}

function Get-View {
    $rows = @()
    Get-ChildItem -LiteralPath $statusRoot -Filter '2025-05-*.json' -File -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
        try { $rows += (Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json) } catch { }
    }
    $active = @($rows | Where-Object { $_.status -eq 'RUNNING' } | Sort-Object date | Select-Object -First 4)
    $passed = @($rows | Where-Object { $_.status -eq 'PASS' }).Count
    $failed = @($rows | Where-Object { $_.status -eq 'FAIL' }).Count
    $ready = if (Test-Path -LiteralPath $readyPath) { Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json } else { $null }
    $fp = if (Test-Path -LiteralPath $fingerprintPath) { Get-Content -LiteralPath $fingerprintPath -Raw | ConvertFrom-Json } else { $null }
    [ordered]@{
        title='MobileESS V38 May Final Monitor'; refresh_seconds=$RefreshSeconds
        fingerprint=if($null -ne $fp){$fp.root_sha256}else{$null}
        V38_READY=if($null -ne $ready){$ready.V38_READY}else{'UNKNOWN'}
        blocker=if($null -ne $ready){$ready.blocker}else{$null}
        PASS=$passed; FAIL=$failed; ACTIVE=$active.Count
        REMAIN=[Math]::Max(0,$ExpectedCount-$passed-$failed)
        active_dates=$active
        updated_at=(Get-Date).ToUniversalTime().ToString('o')
    }
}

function Write-Active([object]$row) {
    Write-Host (" {0} RUN {1,2}/14  {2}" -f $row.date,$row.major_units_done,$row.stage)
    if ($row.stage -eq 'B1_AIDC_SPATIOTEMPORAL_PLANNING') {
        Write-Host ("   AIDC Spatial/WAN | pending cohorts {0}/{1} | migrations {2}/{3}" -f $row.pending_cohorts_done,$row.pending_cohorts_total,$row.migration_candidates_done,$row.migration_candidates_total)
        Write-Host ("   WAN transfers active {0} | fixed path {1} | bottleneck {2}" -f $row.WAN_transfers_active,$row.fixed_path_id,$row.WAN_bottleneck_link)
        Write-Host ("   checkpoint {0}/{1} GB | READY {2} | peak WAN {3} | Rack {4}/{5} | site power {6}/96" -f $row.checkpoint_GB_transferred,$row.checkpoint_GB_total,$row.READY_state,$row.peak_WAN_utilization,$row.rack_oracle_round,$row.rack_oracle_round_max,$row.site_power_slots_done)
    } elseif ($row.stage -match 'RESTORATION') {
        Write-Host ("   RESTORATION {0}/5 | cuts +{1} total {2} | P/Q {3} | Fresh {4}/96" -f $row.restoration_round,$row.restoration_new_cuts,$row.restoration_total_cuts,$row.full_milp_status,$row.fresh_slots_done)
    } elseif ($null -ne $row.candidate_total) {
        Write-Host ("   parent {0}/2 | {1} {2}/{3} | seed {4}/2 | {5}" -f $row.beam_parent_index,$row.search_level,$row.candidate_done,$row.candidate_total,$row.seed_done,$row.full_milp_status)
    }
}

try {
    do {
        $view = Get-View
        if ($Json) { $view | ConvertTo-Json -Depth 8 -Compress }
        else {
            if (-not $Once) { Clear-Host }
            Write-Host '============================================================'
            Write-Host ' V38 FINAL MAY CAMPAIGN'
            Write-Host (" fingerprint {0}" -f $view.fingerprint)
            Write-Host (" PASS {0}  FAIL {1}  ACTIVE {2}  REMAIN {3}" -f $view.PASS,$view.FAIL,$view.ACTIVE,$view.REMAIN)
            if ($view.V38_READY -ne 'YES') { Write-Host (" NOT READY: {0}" -f $view.blocker) }
            Write-Host '============================================================'
            foreach($row in $view.active_dates){ Write-Active $row }
            Write-Host (" Updated: {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
            Write-Host '============================================================'
        }
        if (-not $Once) { Start-Sleep -Seconds $RefreshSeconds }
    } while (-not $Once)
} finally {
    if ($ownsLock -and (Test-Path -LiteralPath $lockPath)) {
        try { $current=Get-Content -LiteralPath $lockPath -Raw|ConvertFrom-Json; if([int]$current.pid -eq $PID){Remove-Item -LiteralPath $lockPath -Force} } catch { }
    }
}
