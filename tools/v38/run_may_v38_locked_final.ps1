param(
    [switch]$NoMonitor,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$artifactRoot = Join-Path $projectRoot 'dayahead\artifacts\v38_aidc_spatiotemporal_wan'
$preflightPath = Join-Path $artifactRoot 'V38_MAY_31DAY_INPUT_PREFLIGHT.json'
$loaderPath = Join-Path $artifactRoot 'V38_TRUE_31DAY_PRODUCTION_LOADER_PREFLIGHT.json'
$fingerprintPath = Join-Path $artifactRoot 'V38_IMPLEMENTATION_FINGERPRINT.json'
$freezePath = Join-Path $artifactRoot 'V38_FINAL_SCIENCE_FREEZE.json'
$readyStatePath = Join-Path $artifactRoot 'V38_READY_STATE.json'
$campaignLock = Join-Path $artifactRoot 'V38_CAMPAIGN.lock.json'
$monitorLock = Join-Path $artifactRoot 'V38_MONITOR.lock.json'
$monitorScript = Join-Path $PSScriptRoot 'monitor_may_v38.ps1'
$logRoot = Join-Path $projectRoot 'logs\v38_aidc_spatiotemporal_wan'

function Stop-Preflight([string]$Reason) {
    Write-Host 'V38_MAY_CAMPAIGN_PREFLIGHT_FAIL'
    Write-Host "V38_READY=NO"
    Write-Host "MAY_STARTED=NO"
    throw $Reason
}

function Test-LivePid([int]$ProcessId) {
    if ($ProcessId -le 0) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-AtomicJson([string]$Path, [object]$Value) {
    $temporary = "$Path.$PID.tmp"
    $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

foreach ($required in @($preflightPath,$loaderPath,$fingerprintPath,$readyStatePath)) {
    if (-not (Test-Path -LiteralPath $required)) { Stop-Preflight "V38_REQUIRED_GATE_MISSING:$required" }
}
$preflight = Get-Content -LiteralPath $preflightPath -Raw -Encoding UTF8 | ConvertFrom-Json
$loader = Get-Content -LiteralPath $loaderPath -Raw -Encoding UTF8 | ConvertFrom-Json
$fingerprint = Get-Content -LiteralPath $fingerprintPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ready = Get-Content -LiteralPath $readyStatePath -Raw -Encoding UTF8 | ConvertFrom-Json

if (
    $preflight.status -ne 'PASS' -or
    $preflight.V38_READY -ne 'YES' -or
    [int]$preflight.expected_dates -ne 31 -or
    [int]$preflight.ready_dates -ne 31 -or
    [int]$preflight.not_ready_dates -ne 0 -or
    [int]$preflight.missing_dates -ne 0
) { Stop-Preflight "V38_INPUT_PREFLIGHT_NOT_31_OF_31:$($preflight.blocker)" }
if (
    $loader.status -ne 'PASS' -or
    [int]$loader.ready_dates -ne 31 -or
    [int]$loader.not_ready_dates -ne 0
) { Stop-Preflight 'V38_TRUE_PRODUCTION_LOADER_NOT_31_OF_31' }
if ($fingerprint.status -ne 'PASS' -or $fingerprint.V38_READY -ne 'YES') {
    Stop-Preflight 'V38_FINAL_FINGERPRINT_NOT_READY'
}
if (-not (Test-Path -LiteralPath $freezePath)) { Stop-Preflight 'V38_SCIENCE_FREEZE_MISSING' }
$freeze = Get-Content -LiteralPath $freezePath -Raw -Encoding UTF8 | ConvertFrom-Json
if (
    $ready.V38_SCIENCE_FROZEN -ne 'YES' -or
    $ready.MAY_CAMPAIGN_LAUNCH_READY -ne 'YES' -or
    $ready.MAY_STARTED -ne 'NO' -or
    $freeze.V38_SCIENCE_FROZEN -ne 'YES' -or
    $freeze.implementation_fingerprint_sha256 -ne $fingerprint.root_sha256
) { Stop-Preflight 'V38_FREEZE_OR_LAUNCH_STATE_INVALID' }
$branch = (& git -C $projectRoot branch --show-current).Trim()
$head = (& git -C $projectRoot rev-parse HEAD).Trim()
if ($branch -ne [string]$freeze.branch -or $head -ne [string]$freeze.HEAD) {
    Stop-Preflight 'V38_GIT_STATE_DIFFERS_FROM_SCIENCE_FREEZE'
}

if (Test-Path -LiteralPath $campaignLock) {
    try { $prior = Get-Content -LiteralPath $campaignLock -Raw | ConvertFrom-Json } catch { $prior = $null }
    if ($null -ne $prior -and (Test-LivePid ([int]$prior.pid))) {
        Write-Host "V38_CAMPAIGN_ALREADY_RUNNING pid=$($prior.pid)"
        exit 0
    }
    Remove-Item -LiteralPath $campaignLock -Force -ErrorAction SilentlyContinue
}
if ($ValidateOnly) {
    Write-Host 'V38_MAY_LAUNCHER_VALIDATION_PASS'
    exit 0
}

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$campaign = Start-Process python.exe -WindowStyle Hidden -WorkingDirectory $projectRoot -PassThru `
    -ArgumentList @('-m','dayahead.tools.run_v38_aidc_spatiotemporal','--campaign') `
    -RedirectStandardOutput (Join-Path $logRoot 'campaign.stdout.log') `
    -RedirectStandardError (Join-Path $logRoot 'campaign.stderr.log')
Write-AtomicJson $campaignLock ([ordered]@{
    artifact_id='V38_CAMPAIGN_LOCK_V1'
    pid=$campaign.Id
    started_at=(Get-Date).ToUniversalTime().ToString('o')
    implementation_fingerprint_sha256=$fingerprint.root_sha256
    rolling_parallel_max=4
})
Write-AtomicJson (Join-Path $artifactRoot 'V38_MAY_CAMPAIGN_LAUNCH.json') ([ordered]@{
    artifact_id='V38_MAY_CAMPAIGN_LAUNCH_V1'
    MAY_STARTED='YES'
    supervisor_pid=$campaign.Id
    implementation_fingerprint_sha256=$fingerprint.root_sha256
    launched_at=(Get-Date).ToUniversalTime().ToString('o')
})
if (-not $NoMonitor) {
    $monitorRunning = $false
    if (Test-Path -LiteralPath $monitorLock) {
        try { $priorMonitor = Get-Content -LiteralPath $monitorLock -Raw | ConvertFrom-Json } catch { $priorMonitor = $null }
        $monitorRunning = $null -ne $priorMonitor -and (Test-LivePid ([int]$priorMonitor.pid))
    }
    if (-not $monitorRunning) {
        Start-Process powershell.exe -WindowStyle Normal -ArgumentList @(
            '-NoProfile','-ExecutionPolicy','Bypass','-File',$monitorScript,
            '-ProjectRoot',$projectRoot,'-RefreshSeconds','10'
        ) | Out-Null
    }
}
Write-Host "V38_CAMPAIGN_LAUNCHED pid=$($campaign.Id)"
