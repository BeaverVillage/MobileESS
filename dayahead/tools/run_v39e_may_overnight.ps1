param(
    [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$NoMonitor,
    [switch]$PreflightOnly,
    [switch]$DiagnosticOverrideAuthorized
)

$monitor = Join-Path $Repo "dayahead\tools\monitor_v39e_may_campaign.ps1"
if (-not $NoMonitor) {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$monitor`"",
        "-Repo", "`"$Repo`""
    )
}

Set-Location -LiteralPath $Repo
$env:PYTHONPATH = $Repo
$arguments = @("-m", "dayahead.tools.run_v39e_may_overnight", "--repo", $Repo)
if ($PreflightOnly) { $arguments += "--preflight-only" }
if ($DiagnosticOverrideAuthorized) { $arguments += "--diagnostic-override-authorized" }
python @arguments
exit $LASTEXITCODE
