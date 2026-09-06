$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'dayahead\tools\monitor_v40b_may_live.ps1') -Repo $repo -LibraryOnly
$detail=[pscustomobject]@{
    day='2025-05-19';case='B2';status='RUNNING';current_stage='M1_ROUTE_PQ'
    completed_units=2;total_units=10;worker_creation_time_utc='2026-09-05T16:00:00Z';solver_detail=$null
    heartbeat_timestamp_utc='2026-09-05T16:05:00Z';error=$null
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
if ((Get-V40BLiveDetail $detail $baseline).current_stage -notmatch 'MESS02') {throw 'Failure lost its same-attempt detailed stage'}
$baseline.current_stage='B2_RESTORATION';$baseline.full_milp_status=$null
$baseline.candidate_done=$null;$baseline.candidate_total=$null;$baseline.beam_parent_total=$null
$baseline | Add-Member restoration_round 5
$baseline | Add-Member restoration_round_max 5
$baseline | Add-Member fresh_slots_done 96
$baseline | Add-Member fresh_slots_total 96
$detail.error="RuntimeError('V37_R3_FAIL_CLOSED_MAX_RESTORATION_ROUNDS:2025-05-19:B2')"
$failed=Get-V40BLiveDetail $detail $baseline
if ($failed.current_stage -ne 'B2_AC_RESTORE / 5/5 / Fresh 96/96 / FAIL') {throw 'Terminal restoration location missing'}
if ($failed.display_progress -ne 'R5/5') {throw 'Restoration misrepresented as outer 2/10'}
if ($failed.status -ne 'FAIL' -or $detail.current_stage -ne 'M1_ROUTE_PQ') {throw 'Presentation mutated terminal status or source'}
if ($failed.error_summary -notmatch 'route search completed') {throw 'Failure explanation missing'}
$baseline.last_update='2026-09-05T16:06:00Z'
if ((Get-V40BLiveDetail $detail $baseline).current_stage -match '5/5') {throw 'Post-failure baseline leaked into prior attempt'}
$baseline.last_update='2026-09-05T15:59:00Z'
if ((Get-V40BLiveDetail $detail $baseline).current_stage -match '5/5') {throw 'Pre-worker baseline leaked into failure'}
$detail.error='FileNotFoundError: checkpoint';$missing=Get-V40BLiveDetail $detail $null
if ($missing.current_stage -ne 'M1_ROUTE_PQ' -or $missing.display_progress -ne '-') {throw 'Unrelated failure mislabeled as restoration'}
$baseline.last_update='2026-09-05T16:04:00Z';$detail.case='B3'
if ((Get-V40BLiveDetail $detail $baseline).current_stage -match 'AC_RESTORE') {throw 'B2 baseline contaminated B3'}
$detail.case='B2';$detail.error=$null
$detail.status='RUNNING'
$master=[pscustomobject]@{completed_days=@();running_days=@('2025-05-19');failed_days=@();last_update='test'}
$live=[pscustomobject]@{State='RUNNING';Orchestrator='ALIVE';HeartbeatAgeSeconds=1}
$latch=@{'2025-05-19'=(Get-MonitorDayRow '2025-05-19' 'FAIL' $detail 'original path error')}
$details=@{'2025-05-19'=$rendered}
$view=Get-MonitorView $master $details $latch $live
if ($view.Failed -ne 1 -or $view.Rows[0].Substage -notmatch 'cand 184/201') {throw 'Recovery hid failure or live progress'}
Set-V40BDisplayProgress $view $details
if ($view.Rows[0].Progress -ne '184/201') {throw 'Candidate progress still shows outer units'}
if (@(Get-MonitorFrame $view 120 | Where-Object {$_.Length -gt 120}).Count) {throw 'Monitor row overflow'}
$details['2025-05-19'].status='PASS'
$view=Get-MonitorView $master $details $latch $live
if ($view.Failed -ne 0) {throw 'Certified PASS did not clear failure'}
Write-Output 'PASS: live candidate/seed display, source isolation, stale retry rejection, failure latch, layout.'
