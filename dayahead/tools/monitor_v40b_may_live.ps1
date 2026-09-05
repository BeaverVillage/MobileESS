param(
    [string]$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$Once,
    [switch]$LibraryOnly
)
# Read-only presentation companion; the sealed campaign sources remain intact.
$liveLibraryOnly=$LibraryOnly
. (Join-Path $PSScriptRoot 'monitor_v39e_may_campaign.ps1') -Repo $Repo -LibraryOnly

function Get-V40BLiveDetail {
    param($Detail, $Baseline)
    $view=$Detail.PSObject.Copy()
    $stage=[string]$Detail.current_stage
    $sd=$Detail.solver_detail
    $useBaseline=$false
    if ($Detail.status -eq 'RUNNING' -and $Detail.case -in @('B0','B1','B2') -and $null -ne $Baseline) {
        try {
            $useBaseline=$Baseline.date -eq $Detail.day -and $Baseline.case -eq $Detail.case -and
                ([datetime]$Baseline.last_update).ToUniversalTime() -ge ([datetime]$Detail.worker_creation_time_utc).ToUniversalTime()
        } catch { $useBaseline=$false }
    }
    if ($useBaseline) {
        $parts=@([string]$Baseline.current_stage)
        if ($Baseline.beam_parent_total) {$parts+=('P{0}/{1}' -f $Baseline.beam_parent_index,$Baseline.beam_parent_total)}
        if ($Baseline.full_milp_status -eq 'RUNNING') {
            if ($Baseline.seed_total) {$parts+=('full MILP {0}/{1}' -f ([int]$Baseline.seed_done+1),$Baseline.seed_total)}
            else {$parts+='full MILP running'}
        }
        elseif ($null -ne $Baseline.candidate_done -and $Baseline.candidate_total) {
            if ($Baseline.search_level) {$parts+=[string]$Baseline.search_level}
            $parts+=('cand {0}/{1}' -f $Baseline.candidate_done,$Baseline.candidate_total)
        }
        elseif ($Baseline.full_milp_status) {$parts+=[string]$Baseline.full_milp_status}
        elseif ($null -ne $Baseline.fresh_slots_done -and $Baseline.fresh_slots_total) {
            $parts+=('AC {0}/{1}' -f $Baseline.fresh_slots_done,$Baseline.fresh_slots_total)
        }
        $view.current_stage=$parts -join ' / '
    }
    elseif ($stage -eq 'M1_ROUTE_PQ' -and $sd) {
        $parts=@($stage)
        if ($sd.mess_index) {$parts+=('MESS{0}' -f $sd.mess_index)}
        if ($sd.event) {$parts+=[string]$sd.event}
        if ($sd.search_level) {$parts+=[string]$sd.search_level}
        $view.current_stage=$parts -join ' / '
    }
    elseif ($sd.OpenDSS_slot) {$view.current_stage=('{0} / {1}/96' -f $stage,$sd.OpenDSS_slot)}
    return $view
}

if ($liveLibraryOnly) {return}
$root=Join-Path $Repo 'dayahead\artifacts\v40b_v40a_may_launch'
$failures=@{}; $details=@{}; $master=$null
try {$Host.UI.RawUI.WindowTitle='V40A May 2025 Campaign Monitor - Live B2'} catch {}
do {
    $warning=''
    try {$master=Get-Content -LiteralPath (Join-Path $root 'V40A_MAY_PROGRESS.json') -Raw -ErrorAction Stop | ConvertFrom-Json}
    catch {$warning='Progress source unavailable; retaining last snapshot.'}
    if ($null -ne $master) {
        foreach ($day in @(@($master.running_days)+@($master.completed_days)+@($master.failed_days)|Sort-Object -Unique)) {
            if ($day -notmatch '^2025-05-(0[1-9]|[12][0-9]|3[01])$') {continue}
            try {
                $detail=Get-Content -LiteralPath (Join-Path $root "status\$day.json") -Raw -ErrorAction Stop | ConvertFrom-Json
                $baseline=$null
                if ($detail.status -eq 'RUNNING' -and $detail.case -in @('B0','B1','B2')) {
                    try {$baseline=Get-Content -LiteralPath (Join-Path $root "baseline_status\$day.json") -Raw -ErrorAction Stop | ConvertFrom-Json}
                    catch {$warning="Baseline detail unavailable for $day."}
                }
                $detail=Get-V40BLiveDetail $detail $baseline
                # Preserve the original monitor's failure latch across this display restart.
                $archive=Join-Path $root "repairs\02_windows_baseline_path\failed_attempts\$day\$day.json"
                if ($detail.status -ne 'PASS' -and -not $failures.ContainsKey($day) -and (Test-Path -LiteralPath $archive)) {
                    $old=Get-Content -LiteralPath $archive -Raw -ErrorAction Stop | ConvertFrom-Json
                    if ($old.day -eq $day -and $old.status -eq 'FAIL') {$failures[$day]=Get-MonitorDayRow $day 'FAIL' $old ([string]$old.error)}
                }
                if ($failures.ContainsKey($day) -and $detail.status -eq 'RUNNING') {
                    $detail.current_stage='RETRY / '+$detail.current_stage
                }
                $details[$day]=$detail
            } catch {$warning="Status source unavailable for $day; retaining last snapshot."}
        }
        $live=Get-CampaignLiveness $master
        $view=Get-MonitorView $master $details $failures $live
        foreach ($row in $view.Rows) {
            $detail=$details[$row.Date]
            if ($null -eq $detail -or $detail.status -ne 'RUNNING') {continue}
            $process=Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $detail.worker_pid) -ErrorAction SilentlyContinue
            $age=([DateTime]::UtcNow-([datetime]$detail.heartbeat_timestamp_utc).ToUniversalTime()).TotalSeconds
            $alive=$null -ne $process -and $process.CommandLine -like '*run_v40b_campaign.py*' -and $process.CommandLine -like "*$($row.Date)*"
            if ($alive) {
                try {$alive=[math]::Abs((([datetime]$process.CreationDate).ToUniversalTime()-([datetime]$detail.worker_creation_time_utc).ToUniversalTime()).TotalSeconds) -le 2}
                catch {$alive=$false}
            }
            if (-not $alive -or $age -gt 45) {
                $state=if (-not $alive) {'DEAD'} else {'STALE'}
                if ($row.Status -eq 'RUNNING') {$row.Status=$state}
                else {$row.Substage=$state+' / '+$row.Substage}
                if ($view.Running -gt 0) {$view.Running--}
                if ($view.Status -eq 'RUNNING') {$view.Status=$state}
            }
        }
        if (-not $Once) {Clear-Host}
        Get-MonitorFrame $view 120 $warning | ForEach-Object {Write-Host $_}
        Write-Host 'PROGRESS = completed major units; B2 details update within 2/10. P = beam parent.'
        if ($failures.Count) {Write-Host 'RETRY = active recovery; the prior FAIL stays visible until that day passes.'}
    }
    else {if (-not $Once) {Clear-Host};Write-Host 'MAY 2025 CAMPAIGN MONITOR';Write-Host 'Waiting for campaign progress.'}
    if (-not $Once) {Start-Sleep -Seconds 10}
} while (-not $Once)
