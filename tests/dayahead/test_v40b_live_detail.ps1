$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'dayahead\tools\monitor_v40b_may_live.ps1') -Repo $repo -LibraryOnly
$detail=[pscustomobject]@{
    day='2025-05-19';case='B2';status='RUNNING';current_stage='M1_ROUTE_PQ'
    completed_units=2;total_units=10;worker_creation_time_utc='2026-09-05T16:00:00Z';solver_detail=$null
}
$baseline=[pscustomobject]@{
    date='2025-05-19';case='B2';current_stage='B2_MESS02';last_update='2026-09-05T16:04:00Z'
    candidate_done=184;candidate_total=201;beam_parent_index=1;beam_parent_total=2
    full_milp_status=$null;seed_done=0;seed_total=2;search_level='K200'
}
$rendered=Get-V40BLiveDetail $detail $baseline
if ($rendered.current_stage -notmatch 'MESS02 / P1/2 / K200 / cand 184/201') {throw 'Missing live baseline progress'}
if ($detail.current_stage -ne 'M1_ROUTE_PQ' -or $rendered.completed_units -ne 2 -or $rendered.total_units -ne 10) {throw 'Presentation changed authoritative units or input'}
$baseline.full_milp_status='RUNNING';$baseline.seed_done=1
if ((Get-V40BLiveDetail $detail $baseline).current_stage -notmatch 'full MILP 2/2') {throw 'Current seed off by one'}
$baseline.last_update='2026-09-05T15:00:00Z'
if ((Get-V40BLiveDetail $detail $baseline).current_stage -ne 'M1_ROUTE_PQ') {throw 'Old worker status leaked into retry'}
$baseline.last_update='2026-09-05T16:04:00Z';$baseline.date='2025-05-18'
if ((Get-V40BLiveDetail $detail $baseline).current_stage -ne 'M1_ROUTE_PQ') {throw 'Wrong date accepted'}
$baseline.date='2025-05-19';$baseline.case='B1'
if ((Get-V40BLiveDetail $detail $baseline).current_stage -ne 'M1_ROUTE_PQ') {throw 'Wrong baseline case accepted'}
$baseline.case='B2';$detail.status='FAIL'
if ((Get-V40BLiveDetail $detail $baseline).current_stage -ne 'M1_ROUTE_PQ') {throw 'Failure stage overwritten'}
$detail.status='RUNNING'
$master=[pscustomobject]@{completed_days=@();running_days=@('2025-05-19');failed_days=@();last_update='test'}
$live=[pscustomobject]@{State='RUNNING';Orchestrator='ALIVE';HeartbeatAgeSeconds=1}
$latch=@{'2025-05-19'=(Get-MonitorDayRow '2025-05-19' 'FAIL' $detail 'original path error')}
$details=@{'2025-05-19'=$rendered}
$view=Get-MonitorView $master $details $latch $live
if ($view.Failed -ne 1 -or $view.Rows[0].Substage -notmatch 'cand 184/201') {throw 'Recovery hid failure or live progress'}
if (@(Get-MonitorFrame $view 120 | Where-Object {$_.Length -gt 120}).Count) {throw 'Monitor row overflow'}
$details['2025-05-19'].status='PASS'
$view=Get-MonitorView $master $details $latch $live
if ($view.Failed -ne 0) {throw 'Certified PASS did not clear failure'}
Write-Output 'PASS: live candidate/seed display, source isolation, stale retry rejection, failure latch, layout.'
