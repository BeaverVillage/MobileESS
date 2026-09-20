param([switch]$Once,[ValidateRange(1,31)][int]$Day=1)
$ErrorActionPreference='Continue'
$runRoot=Join-Path $PSScriptRoot 'v41r4/frozen_artifacts/v41r4_may/per_mess_900_v1'
$statusPath=Join-Path $runRoot 'audit/MAY_CAMPAIGN_STATUS.json'
$Host.UI.RawUI.WindowTitle='IEEE123 MAY | 15 min per MESS | Independent campaign'
$showDetails=$false; $showLog=$false; $selectedWorker=0
$selectedDay=$Day; $policyDetails=$true
function DurationText($seconds){
    if($null -eq $seconds){return '--:--'}
    $span=[TimeSpan]::FromSeconds([Math]::Max(0,[double]$seconds))
    return ('{0:00}:{1:00}' -f [Math]::Floor($span.TotalMinutes),$span.Seconds)
}
function JsonFile($path){
    try {if(Test-Path -LiteralPath $path){return Get-Content -LiteralPath $path -Raw -Encoding utf8 | ConvertFrom-Json}} catch {}
    return $null
}
function ActualStatus($grid){
    if($null -eq $grid -or $null -eq $grid.violation_counts -or $grid.convergence_count -ne 96){return '확인 필요'}
    foreach($name in @('Vmin','Vmax','rho_max','transformer_current','transformer_kVA')){if($null -eq $grid.$name){return '확인 필요'}}
    $voltageBad=([double]$grid.Vmin*[double]$grid.Vmin -lt (0.95*0.95-1e-8) -or [double]$grid.Vmax*[double]$grid.Vmax -gt (1.05*1.05+1e-8))
    $thermalBad=($grid.violation_counts.line_current -gt 0 -or $grid.violation_counts.transformer_current -gt 0 -or $grid.violation_counts.transformer_kVA -gt 0 -or $grid.rho_max -ge 1 -or $grid.transformer_current -ge 1 -or $grid.transformer_kVA -ge 1)
    if($voltageBad -and $thermalBad){return '전압/부하 위반'}
    if($voltageBad){return '전압 위반'}
    if($thermalBad){return '부하 위반'}
    return 'PASS'
}
function Show-DayComparison($chosen,$campaign){
    Write-Host ''
    Write-Host (' 상세 {0}  [← / → 날짜 변경]' -f $chosen) -ForegroundColor Cyan
    Write-Host ' 정책  상태           P1(계획)      P2(GPUh)    Fresh    Actual       Actual Vmax / 최대선로부하율'
    foreach($policy in @('B0','B1','B2','B3')){
        $da=Join-Path $runRoot ($chosen+'/'+$policy+'/dayahead')
        $audit=Join-Path $runRoot ('audit/'+$chosen)
        $ledger=JsonFile (Join-Path $da 'optimization/OBJECTIVE_LEDGER.json')
        $daReceipt=JsonFile (Join-Path $da 'DAYAHEAD_RECEIPT.json')
        $phase=JsonFile (Join-Path $audit ('PHASE_'+$policy+'_DA.json'))
        $acPhase=JsonFile (Join-Path $audit ('PHASE_'+$policy+'_AC.json'))
        $ac=JsonFile (Join-Path $audit ($policy+'_ACTUAL_SUMMARY.json'))
        $summary=JsonFile (Join-Path $audit ($policy+'_DAYAHEAD_SUMMARY.json'))
        $p1='-';$p2='-';$fresh='대기';$actual='대기';$voltage='-';$state='WAITING'
        if($ledger -and $ledger.OBJECTIVE_VECTOR.Count -ge 2){$p1='{0:N6}' -f $ledger.OBJECTIVE_VECTOR[0];$p2='{0:N2}' -f $ledger.OBJECTIVE_VECTOR[1]}
        if($phase.status -eq 'PASS' -and $daReceipt.status -eq 'COMPLETE'){
            $fresh='PASS';$state=if($policy -eq 'B0' -or ($policy -eq 'B1' -and [int]$chosen.Substring(8,2) -le 8)){'REUSE DA'}else{'DA COMPLETE'}
        }
        if($acPhase.status -eq 'PASS'){
            $actual=ActualStatus $ac.grid;$state=if($state -eq 'REUSE DA'){'REUSE'}else{'COMPLETE'}
            if($null -ne $ac.grid.Vmax -and $null -ne $ac.grid.rho_max){$voltage='{0:N6} / {1:N2}%' -f $ac.grid.Vmax,(100*$ac.grid.rho_max)}
        }
        $running=@($campaign.active | Where-Object {$_.day -eq $chosen -and $_.phase.StartsWith($policy+'_')})
        if($running.Count){
            $state='RUNNING'
            if($running[0].phase.EndsWith('_AC')){$actual='실행 중'}
            elseif(-not $ledger -and $running[0].mess -and $null -ne $running[0].mess.best_certified_objective_at_stop){$p1=('{0:N6}*' -f $running[0].mess.best_certified_objective_at_stop)}
        }
        if($phase.status -eq 'FAIL_CLOSED' -or $acPhase.status -eq 'FAIL_CLOSED'){$state='FAILED'}
        $lineColor=if($state -eq 'FAILED'){'Red'}elseif($state -eq 'RUNNING'){'Yellow'}else{'Gray'}
        Write-Host (' {0,-5} {1,-12} {2,12} {3,13}    {4,-6} {5,-10} {6}' -f $policy,$state,$p1,$p2,$fresh,$actual,$voltage) -ForegroundColor $lineColor
        if($policyDetails -and $summary.OBJECTIVE_VECTOR.Count -ge 5){
            Write-Host ('       P3/P4/P5 [{0}] · 시간 {1} / 공간 {2} / checkpoint {3} · MESS 운행 {4}' -f (($summary.OBJECTIVE_VECTOR[2..4]) -join ', '),@($summary.temporal_shifts).Count,@($summary.spatial_relocations).Count,@($summary.checkpoint_migrations).Count,$summary.MESS.movement_count) -ForegroundColor DarkGray
        }
    }
    Write-Host ' * 탐색 중 최선 인증값(최종 P1 아님). B2/B3는 새 캠페인 결과만 표시합니다.' -ForegroundColor DarkGray
}
while($true){
    $campaign=JsonFile $statusPath
    foreach($worker in @($campaign.active)){
        $policy=$worker.phase.Split('_')[0]
        if($worker.phase.EndsWith('_DA') -and $policy -in @('B2','B3')){
            $livePath=Join-Path $runRoot ($worker.day+'/'+$policy+'/search/PER_MESS_LIVE.json')
            $latest=JsonFile $livePath
            $recoveryPath=Join-Path $runRoot ($worker.day+'/'+$policy+'/search/TECHNICAL_RECOVERY.json')
            if($latest -and (Test-Path -LiteralPath $recoveryPath)){
                $written=([DateTimeOffset](Get-Item -LiteralPath $livePath).LastWriteTimeUtc).ToUnixTimeMilliseconds()/1000.0
                if($written -lt $worker.started_at){
                    $latest=$null
                    $worker | Add-Member -NotePropertyName mess -NotePropertyValue $null -Force
                    $worker | Add-Member -NotePropertyName restoring -NotePropertyValue $true -Force
                }
            }
            if($latest){$worker | Add-Member -NotePropertyName mess -NotePropertyValue $latest -Force}
            if($latest.mess_index -eq 4 -and $latest.stop_reason){
                $da=Join-Path $runRoot ($worker.day+'/'+$policy+'/dayahead')
                foreach($name in @('A1','MF')){
                    $folder=Join-Path $da $name
                    if(Test-Path -LiteralPath $folder){
                        $worker | Add-Member -NotePropertyName component -NotePropertyValue $name -Force
                        $worker | Add-Member -NotePropertyName componentLive -NotePropertyValue (JsonFile (Join-Path $folder 'F_AND_O_LIVE.json')) -Force
                        $worker | Add-Member -NotePropertyName componentLog -NotePropertyValue (Join-Path $folder 'SOLVER.log') -Force
                    }
                }
            }
        }
    }
    if(-not $Once){Clear-Host}
    Write-Host ' IEEE123 MAY  |  900 seconds per MESS  |  4 day workers x 4 Gurobi threads' -ForegroundColor Cyan
    Write-Host ' Codex-independent campaign. Closing this monitor does not stop computation.' -ForegroundColor DarkGray
    if($null -eq $campaign){Write-Host ' Waiting for campaign status...' -ForegroundColor Yellow}
    else{
        $now=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0
        $color=if($campaign.errors.Count){'Red'}elseif($campaign.status -eq 'COMPLETE'){'Green'}else{'Cyan'}
        $doneDays=@($campaign.completed_phases | Group-Object day | Where-Object {$_.Count -eq 7}).Count
        Write-Host (' {0}  |  days {1}/31  |  phases {2}/217  |  campaign {3}  |  refreshed {4:HH:mm:ss}' -f $campaign.status,$doneDays,$campaign.completed_phases.Count,(DurationText ($now-$campaign.started_at)),(Get-Date)) -ForegroundColor $color
        Write-Host ''
        Write-Host ' #  DAY     POLICY / STAGE    MESS   ELAPSED / LIMIT    K      CERT   FULL   BEST P1'
        Write-Host ' --------------------------------------------------------------------------------'
        $workers=@($campaign.active | Sort-Object day)
        for($i=0;$i -lt $workers.Count;$i++){
            $worker=$workers[$i];$mess=$worker.mess
            $stage=$worker.phase;$depth='-';$elapsed=DurationText ($now-$worker.started_at);$limit='--:--';$k='-';$cert='-';$full='-';$best='-'
            if($worker.restoring){$stage=$worker.phase.Replace('_DA',' / restore')}
            if($mess){
                $depth=('{0}/4' -f $mess.mess_index);$limit='15:00';$k=$mess.K_stage
                if(-not $k){$k='PREP'}
                $cert=$mess.certified_candidate_count;$full=if($mess.FULL_entered){'YES'}else{'no'}
                $measured=if($mess.stop_reason){$mess.elapsed_at_stop}else{$now-$mess.started_at}
                $elapsed=DurationText $measured
                if($null -ne $mess.best_certified_objective_at_stop){$best=('{0:F7}' -f $mess.best_certified_objective_at_stop)}
                $stage=$worker.phase.Replace('_DA',' / M1')
                if($mess.mess_index -eq 4 -and $mess.stop_reason){$stage=$worker.phase.Replace('_DA',' / post-M1')}
            }
            $lineColor=if($i -eq $selectedWorker){'White'}else{'Gray'}
            if($mess -and $measured -ge 900){$lineColor='Yellow'}
            if($worker.component){
                $stage=$worker.phase.Replace('_DA',(' / '+$worker.component))
                $depth='done';$k='-';$cert='-';$full='-';$elapsed='--:--';$limit='--:--';$best='-'
                $live=$worker.componentLive
                if($live){
                    $limit=DurationText $live.total_budget_seconds
                    $used=$live.budget_used_seconds
                    if($live.search_loop_started_at_unix -and -not $live.search_loop_stopped){$used=$now-$live.search_loop_started_at_unix}
                    $elapsed=DurationText $used
                    if($live.incumbent.Count){$best='{0:F7}' -f $live.incumbent[0]}
                }
                $lineColor=if($i -eq $selectedWorker){'White'}else{'Gray'}
            }
            Write-Host (' {0}  {1}  {2,-17} {3,-5} {4,7} / {5,-5} {6,-6} {7,5}   {8,-4}   {9}' -f ($i+1),$worker.day.Substring(5),$stage,$depth,$elapsed,$limit,$k,$cert,$full,$best) -ForegroundColor $lineColor
        }
        if(-not $workers.Count){Write-Host ' No active workers.' -ForegroundColor DarkGray}
        Write-Host ''
        Write-Host ' Reuse: B0 Planning/Fresh all May; B1 Planning/Fresh May01-08.' -ForegroundColor DarkGray
        Write-Host ' New: B1 May09-31; B2/B3 all May; missing Actual replays. Yellow = soft overrun.' -ForegroundColor DarkGray
        if($campaign.errors.Count){
            Write-Host ' FAILURE DETAILS' -ForegroundColor Red
            $campaign.errors | ForEach-Object {Write-Host (' {0} {1}: {2}' -f $_.day,$_.phase,$_.error) -ForegroundColor Red}
        }
        Show-DayComparison ('2025-05-{0:D2}' -f $selectedDay) $campaign
        if($workers.Count -and ($showDetails -or $showLog)){
            $selectedWorker=[Math]::Min($selectedWorker,$workers.Count-1)
            $worker=$workers[$selectedWorker];$mess=$worker.mess
            Write-Host (' SELECTED WORKER {0}: {1} {2}  PID {3}' -f ($selectedWorker+1),$worker.day,$worker.phase,$worker.worker_pid) -ForegroundColor Cyan
            if($showDetails -and $worker.component){
                $live=$worker.componentLive
                Write-Host (' Current: {0} | status: {1} | priority: {2} | iteration: {3}' -f $worker.component,$live.status,$live.stage_priority,$live.iteration)
                Write-Host (' Family: {0} | budget used: {1} / {2} | M1 complete' -f $live.current_family,(DurationText $live.budget_used_seconds),(DurationText $live.total_budget_seconds))
            }
            elseif($showDetails -and $mess){
                Write-Host (' Action: {0} | stages: {1}' -f $mess.current_action,($mess.K_stages_entered -join ' -> '))
                Write-Host (' Evaluated: {0} | certified: {1} | stalled: {2} | infeasible: {3}' -f $mess.candidate_evaluations,$mess.certified_candidate_count,$mess.stalled_count,$mess.infeasible_count)
                Write-Host (' Stop: {0} | exhausted: {1} | recorded overrun: {2:F1}s' -f $mess.stop_reason,$mess.budget_exhausted,$mess.soft_budget_overrun_seconds)
                foreach($child in $mess.retained_children){Write-Host (' Retained: {0}  P1={1:F7}  {2}' -f $child.movement,$child.objective,$child.signature.Substring(0,16))}
                $policy=$worker.phase.Split('_')[0]
                foreach($receipt in (Get-ChildItem -LiteralPath (Join-Path $runRoot ($worker.day+'/'+$policy+'/search')) -Filter 'PER_MESS_*_COMPLETE.json' -ErrorAction SilentlyContinue)){
                    $r=JsonFile $receipt.FullName
                    Write-Host (' MESS{0}: {1} | {2} | certified={3} | {4}' -f $r.mess_index,(DurationText $r.elapsed_at_stop),$r.stop_reason,$r.certified_candidate_count,($r.retained_children.movement -join ','))
                }
            }
            if($showLog){
                $policy=$worker.phase.Split('_')[0]
                $messLog=Join-Path $runRoot ($worker.day+'/'+$policy+'/dayahead/M1/BOUNDED_MESS_WORKER.log')
                $logPath=if($mess -and (Test-Path -LiteralPath $messLog)){$messLog}else{$worker.log}
                if($worker.component){$logPath=if(Test-Path -LiteralPath $worker.componentLog){$worker.componentLog}else{$worker.log}}
                Write-Host (' Log: '+$logPath) -ForegroundColor DarkGray
                Get-Content -LiteralPath $logPath -Tail 9 -ErrorAction SilentlyContinue | ForEach-Object {Write-Host (' '+$_)}
            }
        }
    }
    Write-Host ''
    Write-Host ' [←/→] 날짜  [D] 정책 상세  [1/2/3/4] worker 상세  [W] worker 접기  [L] 로그  [O] 결과 폴더  [Q] 닫기' -ForegroundColor Green
    if($Once){break}
    for($tick=0;$tick -lt 15;$tick++){
        if([Console]::KeyAvailable){
            $pressed=[Console]::ReadKey($true)
            if($pressed.Key -eq [ConsoleKey]::RightArrow){$selectedDay=1+($selectedDay%31);break}
            if($pressed.Key -eq [ConsoleKey]::LeftArrow){$selectedDay=1+(($selectedDay+29)%31);break}
            $key=$pressed.KeyChar.ToString().ToUpperInvariant()
            switch($key){
                '1' {$selectedWorker=0;$showDetails=$true}
                '2' {$selectedWorker=1;$showDetails=$true}
                '3' {$selectedWorker=2;$showDetails=$true}
                '4' {$selectedWorker=3;$showDetails=$true}
                'D' {$policyDetails=-not $policyDetails}
                'W' {$showDetails=-not $showDetails}
                'L' {$showLog=-not $showLog}
                'O' {$folder=Join-Path $runRoot ('2025-05-{0:D2}' -f $selectedDay);if(Test-Path -LiteralPath $folder){Invoke-Item -LiteralPath $folder}}
                'Q' {exit}
            }
            break
        }
        Start-Sleep -Milliseconds 200
    }
}
