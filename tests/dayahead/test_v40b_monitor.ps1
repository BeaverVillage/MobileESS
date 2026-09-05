$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'dayahead\tools\monitor_v39e_may_campaign.ps1') -Repo $repo -LibraryOnly
$master=[pscustomobject]@{completed_days=@('2025-05-01');running_days=@('2025-05-02');failed_days=@();last_update='test'}
$live=[pscustomobject]@{State='RUNNING';Orchestrator='ALIVE';HeartbeatAgeSeconds=3}
$assertions=0
foreach ($stage in @('A0','M1_ROUTE_PQ','A1_FEEDBACK','MF_FIXED_ROUTE_PQ','FRESH','AC_RESTORATION')) {
    $details=@{'2025-05-02'=[pscustomobject]@{status='RUNNING';case='B3';current_stage=$stage;completed_units=5;total_units=10}}
    $view=Get-MonitorView $master $details @{} $live
    $frame=(Get-MonitorFrame $view 120)-join "`n"
    if (-not $frame.Contains($stage)) {throw "Missing B3 stage $stage"};$assertions++
    if ($view.Rows.Count -ne 1 -or $view.Rows[0].Date -ne '2025-05-02') {throw 'Completed PASS row stayed visible'};$assertions++
    foreach ($label in @('Progress :','Running  :','Failed   :','Status   :','Orchestrator :','Heartbeat    :','SUB-STAGE')) {
        if (-not $frame.Contains($label)) {throw "Old monitor layout changed: $label"};$assertions++
    }
}
$monitor=Join-Path $repo 'dayahead\tools\monitor_v40a_may_campaign.ps1'
$tokens=$null;$errors=$null
[System.Management.Automation.Language.Parser]::ParseFile($monitor,[ref]$tokens,[ref]$errors)|Out-Null
if ($errors.Count -gt 0) {throw ($errors|Out-String)}
Write-Output "PASS: $assertions V40A stage/layout assertions; monitor syntax PASS."
