param(
    [switch]$NoMonitor,
    [switch]$ValidateOnly,
    [string]$ReadinessPathOverride = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$artifactRoot = Join-Path $projectRoot 'dayahead\artifacts\v37_may_locked_final'
$statusRoot = Join-Path $artifactRoot 'status'
$logRoot = Join-Path $projectRoot 'logs\v37_may_locked_final'
$campaignLock = Join-Path $artifactRoot 'V37_CAMPAIGN.lock.json'
$monitorScript = Join-Path $PSScriptRoot 'monitor_may.ps1'
$readinessPath = if ($ReadinessPathOverride) {
    (Resolve-Path -LiteralPath $ReadinessPathOverride).Path
} else {
    Join-Path $projectRoot 'dayahead\artifacts\v37_r4_may_campaign_repair\V37_R4_MAY_31DAY_PRODUCTION_PREFLIGHT.json'
}
$monitorLock = Join-Path $artifactRoot 'V37_MONITOR.lock.json'
$launchState = Join-Path $artifactRoot 'V37_MAY_LAUNCH_STATE.json'
New-Item -ItemType Directory -Force -Path $statusRoot,$logRoot | Out-Null

function Test-LivePid([int]$ProcessId) {
    if ($ProcessId -le 0) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Write-AtomicJson([string]$Path, [object]$Value) {
    $temporary = "$Path.$PID.tmp"
    $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
        } finally {
            $hasher.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Stop-Preflight([string]$Reason) {
    Write-Host 'MAY_CAMPAIGN_PREFLIGHT_FAIL'
    throw $Reason
}

if (-not (Test-Path -LiteralPath $readinessPath)) {
    Stop-Preflight "READINESS_MANIFEST_MISSING: $readinessPath"
}
$ready = Get-Content -LiteralPath $readinessPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($ready.MAY_CAMPAIGN_LAUNCH_READY -ne 'YES' -or $ready.MAY_STARTED -ne 'NO') {
    Stop-Preflight 'MAY_CAMPAIGN_NOT_READY'
}
if (
    [int]$ready.expected_dates -ne 31 -or
    [int]$ready.ready_dates -ne 31 -or
    [int]$ready.not_ready_dates -ne 0 -or
    [int]$ready.missing_dates -ne 0
) {
    Stop-Preflight 'MAY_DATE_MANIFEST_NOT_31_OF_31'
}
$dateRows = @($ready.dates)
if ($dateRows.Count -ne 31 -or @($dateRows | Where-Object { $_.status -ne 'READY' }).Count -ne 0) {
    Stop-Preflight 'MAY_DATE_ROWS_NOT_31_READY'
}
$expectedDateAxis = 1..31 | ForEach-Object { '2025-05-{0:D2}' -f $_ }
$actualDateAxis = @($dateRows | ForEach-Object { [string]$_.operating_day })
if ((Compare-Object -ReferenceObject $expectedDateAxis -DifferenceObject $actualDateAxis).Count -ne 0) {
    Stop-Preflight 'MAY_DATE_AXIS_MISMATCH'
}
if ($null -eq $ready.launch_fingerprints -or @($ready.launch_fingerprints).Count -eq 0) {
    Stop-Preflight 'MAY_LAUNCH_FINGERPRINTS_MISSING'
}
foreach ($authority in $ready.launch_fingerprints) {
    $rawPath = [string]$authority.path
    $candidate = if ([System.IO.Path]::IsPathRooted($rawPath)) {
        $rawPath
    } else {
        Join-Path $projectRoot $rawPath
    }
    if (-not (Test-Path -LiteralPath $candidate)) {
        Stop-Preflight "AUTHORITY_MISSING: $candidate"
    }
    $actual = Get-Sha256 $candidate
    if ($actual -ne ([string]$authority.sha256).ToLowerInvariant()) {
        Stop-Preflight "AUTHORITY_SHA_MISMATCH: $candidate"
    }
}
$branch = (& git -C $projectRoot branch --show-current).Trim()
if ($branch -ne [string]$ready.branch) { Stop-Preflight "WRONG_BRANCH: $branch" }

$alreadyRunning = $false
if (Test-Path -LiteralPath $campaignLock) {
    try { $prior = Get-Content -LiteralPath $campaignLock -Raw | ConvertFrom-Json } catch { $prior = $null }
    if ($null -ne $prior -and (Test-LivePid ([int]$prior.pid))) {
        $alreadyRunning = $true
    } else {
        Remove-Item -LiteralPath $campaignLock -Force -ErrorAction SilentlyContinue
    }
}

if (Test-Path -LiteralPath $monitorLock) {
    try { $priorMonitor = Get-Content -LiteralPath $monitorLock -Raw | ConvertFrom-Json } catch { $priorMonitor = $null }
    if ($null -eq $priorMonitor -or -not (Test-LivePid ([int]$priorMonitor.pid))) {
        Remove-Item -LiteralPath $monitorLock -Force -ErrorAction SilentlyContinue
    }
}
$monitorRunning = $false
if (Test-Path -LiteralPath $monitorLock) {
    try { $priorMonitor = Get-Content -LiteralPath $monitorLock -Raw | ConvertFrom-Json } catch { $priorMonitor = $null }
    $monitorRunning = $null -ne $priorMonitor -and (Test-LivePid ([int]$priorMonitor.pid))
}
if (-not $NoMonitor -and -not $monitorRunning -and -not $ValidateOnly) {
    Start-Process powershell.exe -WindowStyle Normal -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $monitorScript,
        '-ProjectRoot', $projectRoot, '-RefreshSeconds', '10'
    ) | Out-Null
}

if ($alreadyRunning) {
    Write-Host 'CAMPAIGN_ALREADY_RUNNING'
    exit 0
}

if ($ValidateOnly) {
    Write-Host 'MAY_LAUNCHER_VALIDATION_PASS'
    exit 0
}

Write-Host 'campaign started'
Write-Host "worktree: $projectRoot"
Write-Host 'date count: 31'
Write-Host 'parallel dates = 4'
Write-Host 'workers/date = 4'
Write-Host ("monitor launched: {0}" -f (-not $NoMonitor))
Write-Host "artifact root: $artifactRoot"
Write-Host "log root: $logRoot"

$campaignProcess = Start-Process python.exe -WindowStyle Hidden -WorkingDirectory $projectRoot -PassThru `
    -ArgumentList @('-m','dayahead.tools.run_v37_may','--campaign') `
    -RedirectStandardOutput (Join-Path $logRoot 'campaign.stdout.log') `
    -RedirectStandardError (Join-Path $logRoot 'campaign.stderr.log')
Write-AtomicJson $launchState ([ordered]@{
    artifact_id='V37_MAY_LAUNCH_STATE_V1'
    MAY_STARTED='YES'
    launcher_pid=$PID
    campaign_pid=$campaignProcess.Id
    launched_at=(Get-Date).ToUniversalTime().ToString('o')
    readiness_sha256=(Get-Sha256 $readinessPath)
})
for ($attempt = 0; $attempt -lt 50; $attempt++) {
    if (Test-Path -LiteralPath $campaignLock) { break }
    if ($campaignProcess.HasExited) { throw "CAMPAIGN_PROCESS_EXITED: $($campaignProcess.ExitCode)" }
    Start-Sleep -Milliseconds 200
}
Write-Host "campaign pid: $($campaignProcess.Id)"
Write-Host 'CAMPAIGN_LAUNCHED'
exit 0
