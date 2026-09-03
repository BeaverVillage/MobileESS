param([switch]$NoMonitor)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$artifactRoot = Join-Path $projectRoot 'dayahead\artifacts\v37_may_locked_final'
$statusRoot = Join-Path $artifactRoot 'status'
$logRoot = Join-Path $projectRoot 'logs\v37_may_locked_final'
$campaignLock = Join-Path $artifactRoot 'V37_CAMPAIGN.lock.json'
$monitorScript = Join-Path $PSScriptRoot 'monitor_may.ps1'
New-Item -ItemType Directory -Force -Path $statusRoot,$logRoot | Out-Null

function Test-LivePid([int]$ProcessId) {
    if ($ProcessId -le 0) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

$alreadyRunning = $false
if (Test-Path -LiteralPath $campaignLock) {
    try { $prior = Get-Content -LiteralPath $campaignLock -Raw | ConvertFrom-Json } catch { $prior = $null }
    if ($null -ne $prior -and (Test-LivePid ([int]$prior.pid))) {
        $alreadyRunning = $true
    } else {
        Remove-Item -LiteralPath $campaignLock -Force -ErrorAction SilentlyContinue
    }
}

if (-not $NoMonitor) {
    Start-Process powershell.exe -WindowStyle Normal -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $monitorScript,
        '-ProjectRoot', $projectRoot, '-RefreshSeconds', '10'
    ) | Out-Null
}

if ($alreadyRunning) {
    Write-Host 'CAMPAIGN_ALREADY_RUNNING'
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

Push-Location $projectRoot
try {
    & python -m dayahead.tools.run_v37_may --campaign 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot 'campaign.log') -Append
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
