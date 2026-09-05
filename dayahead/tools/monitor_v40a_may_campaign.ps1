param([string]$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,[switch]$Once)
. (Join-Path $PSScriptRoot 'monitor_v39e_may_campaign.ps1') -Repo $Repo -LibraryOnly
$root=Join-Path $Repo 'dayahead\artifacts\v40b_v40a_may_launch'
$failures=@{}; $details=@{}; $master=$null
try { $Host.UI.RawUI.WindowTitle='V40A May 2025 Campaign Monitor' } catch {}
do {
    $warning=''
    try { $master=Get-Content -LiteralPath (Join-Path $root 'V40A_MAY_PROGRESS.json') -Raw -ErrorAction Stop | ConvertFrom-Json }
    catch { $warning='Progress source unavailable; retaining last snapshot.' }
    if ($null -ne $master) {
        foreach ($day in @(@($master.running_days)+@($master.completed_days)+@($master.failed_days)|Sort-Object -Unique)) {
            if ($day -notmatch '^2025-05-(0[1-9]|[12][0-9]|3[01])$') {continue}
            try {
                $detail=Get-Content -LiteralPath (Join-Path $root "status\$day.json") -Raw -ErrorAction Stop | ConvertFrom-Json
                $stage=[string]$detail.current_stage
                $sd=$detail.solver_detail
                if ($stage -eq 'M1_ROUTE_PQ' -and $sd) {
                    $parts=@($stage)
                    if ($sd.mess_index) {$parts+=('MESS{0}' -f $sd.mess_index)}
                    if ($sd.event) {$parts+=[string]$sd.event}
                    if ($sd.search_level) {$parts+=[string]$sd.search_level}
                    $detail.current_stage=$parts -join ' / '
                }
                elseif ($sd.OpenDSS_slot) {$detail.current_stage=('{0} / {1}/96' -f $stage,$sd.OpenDSS_slot)}
                $details[$day]=$detail
            } catch {$warning="Status source unavailable for $day; retaining last snapshot."}
        }
        $live=Get-CampaignLiveness $master
        $view=Get-MonitorView $master $details $failures $live
        foreach ($row in $view.Rows) {
            if ($row.Status -ne 'RUNNING') {continue}
            $detail=$details[$row.Date]
            if ($null -eq $detail) {continue}
            $process=Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $detail.worker_pid) -ErrorAction SilentlyContinue
            $age=([DateTime]::UtcNow-([datetime]$detail.heartbeat_timestamp_utc).ToUniversalTime()).TotalSeconds
            $workerAlive=$null -ne $process -and $process.CommandLine -like '*run_v40b_campaign.py*' -and $process.CommandLine -like "*$($row.Date)*"
            if ($workerAlive) {
                try {$workerAlive=[math]::Abs((([datetime]$process.CreationDate).ToUniversalTime()-([datetime]$detail.worker_creation_time_utc).ToUniversalTime()).TotalSeconds) -le 2}
                catch {$workerAlive=$false}
            }
            if (-not $workerAlive) {$row.Status='DEAD';$view.Running--;if ($view.Status -eq 'RUNNING') {$view.Status='DEAD'}}
            elseif ($age -gt 45) {$row.Status='STALE';$view.Running--;if ($view.Status -eq 'RUNNING') {$view.Status='STALE'}}
        }
        if (-not $Once) {Clear-Host}
        Get-MonitorFrame $view 120 $warning | ForEach-Object {Write-Host $_}
    } else {if (-not $Once) {Clear-Host};Write-Host 'MAY 2025 CAMPAIGN MONITOR';Write-Host 'Prelaunch gates in progress. Campaign has not started.'}
    if (-not $Once) {Start-Sleep -Seconds 10}
} while (-not $Once)
