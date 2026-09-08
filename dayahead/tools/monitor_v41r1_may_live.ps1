param([string]$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,[switch]$Once)
. (Join-Path $PSScriptRoot 'monitor_v39e_may_campaign.ps1') -Repo $Repo -LibraryOnly
$runtime=Join-Path $Repo 'frozen_artifacts\v41r1_migration'
$out=Join-Path $Repo 'dayahead\artifacts\v41r1_pending_running_migration'
function Read-LiveJson([string]$Path) {
    $reader=$null
    $share=[System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,$share)
    try {$reader=New-Object System.IO.StreamReader($stream);return ($reader.ReadToEnd() | ConvertFrom-Json)}
    finally {if($reader){$reader.Dispose()}else{$stream.Dispose()}}
}
try {$Host.UI.RawUI.WindowTitle='V41R1 5월 실행 현황'} catch {}
do {
    $lines=New-Object 'System.Collections.Generic.List[string]'
    $lines.Add('                         5월 전체 실행 현황')
    $lines.Add('')
    try {
        $state=Read-LiveJson (Join-Path $runtime 'campaign_state.json')
        $progress=Read-LiveJson (Join-Path $runtime 'campaign_progress.json')
        $units=@($state.units.PSObject.Properties | ForEach-Object {$_.Value})
        $days=@($units | Group-Object day)
        $complete=@($days | Where-Object {@($_.Group | Where-Object {$_.status -eq 'COMPLETE'}).Count -eq 4}).Count
        $fails=@($days | Where-Object {@($_.Group | Where-Object {$_.status -eq 'FAILED'}).Count -gt 0}).Count
        $percent=100.0*(@($units | Where-Object {$_.status -eq 'COMPLETE'}).Count)/124
        $lines.Add(('전체  {0} / 31일 완료          진행률  {1:N1}%          FAIL  {2}일' -f $complete,$percent,$fails))
        $lines.Add(('상태  {0}' -f $progress.status))
        $lines.Add('')
        $active=@($units | Where-Object {$_.status -match 'RUNNING'} | Sort-Object day,policy)
        $prepFile=Join-Path $runtime 'BASELINE_PREPARATION_PROGRESS.json'
        if($progress.status -like 'PAUSED*' -and (Test-Path -LiteralPath $prepFile)){
            $prep=Read-LiveJson $prepFile
            $prepRows=@($prep.days.PSObject.Properties)
            $ready=@($prepRows | Where-Object {$_.Value.status -eq 'PASS'}).Count
            $lines.Add(('재개 준비: Q90 입력 검증 {0}/31일 ({1:N1}%)' -f $ready,(100.0*$ready/31)))
            $active=@($prepRows | Where-Object {$_.Value.status -eq 'RUNNING'} | ForEach-Object {
                [pscustomobject]@{day=$_.Name;policy='공통';phase='CAUSAL_ML';worker_pid=$_.Value.pid}
            })
            $electricalFile=Join-Path $runtime 'COEFFICIENT_PREPARATION_PROGRESS.json'
            if(Test-Path -LiteralPath $electricalFile){
                $electrical=Read-LiveJson $electricalFile
                $electricalRows=@($electrical.days.PSObject.Properties)
                $electricReady=@($electricalRows | Where-Object {$_.Value.status -eq 'PASS'}).Count
                $electricFail=@($electricalRows | Where-Object {$_.Value.status -eq 'FAIL'}).Count
                $lines.Add(('전기계수 검증: {0}/31일 ({1:N1}%) · FAIL {2}일' -f $electricReady,(100.0*$electricReady/31),$electricFail))
                if($prep.status -eq 'PASS'){
                    $active=@($electricalRows | Where-Object {$_.Value.status -eq 'RUNNING'} | ForEach-Object {
                        [pscustomobject]@{day=$_.Name;policy='공통';phase='ELECTRICAL_GENERATION';worker_pid=$_.Value.pid}
                    })
                }
                $stressFile=Join-Path $out 'FOUR_WORKER_STRESS_CURRENT.json'
                if($electrical.status -eq 'PASS' -and (Test-Path -LiteralPath $stressFile)){
                    $stress=Read-LiveJson $stressFile
                    $heartbeatFile=Join-Path $stress.folder 'heartbeat.json'
                    if((Test-Path -LiteralPath $heartbeatFile) -and -not (Test-Path -LiteralPath (Join-Path $stress.folder 'RESULT.json'))){
                        $memory=Read-LiveJson $heartbeatFile
                        $active=@($memory.workers | ForEach-Object {
                            [pscustomobject]@{day='2025-05-01';policy='검사';phase='MEMORY_CHECK';worker_pid=$_.pid}
                        })
                    }
                }
            }
        }
        $acceptanceFile=Join-Path $runtime 'F_AND_O_ACCEPTANCE_PROGRESS.json'
        if($progress.status -like 'PAUSED*' -and (Test-Path -LiteralPath $acceptanceFile)){
            $acceptance=Read-LiveJson $acceptanceFile
            if($acceptance.status -eq 'RUNNING' -and (Get-Process -Id $acceptance.pid -ErrorAction SilentlyContinue)){
                $acceptedUnit=Join-Path $acceptance.folder '2025-05-04\B1'
                $acceptedPhase=if(Test-Path -LiteralPath (Join-Path $acceptedUnit 'actual\ACTUAL_BOUNDARY_RECEIPT.json')){'actual'}else{'dayahead'}
                $active=@([pscustomobject]@{day='2025-05-04';policy='B1';phase=$acceptedPhase;worker_pid=$acceptance.pid;output_folder=(Join-Path $acceptedUnit 'dayahead')})
                if(Test-Path -LiteralPath (Join-Path $runtime 'USER_FULL_MAY_HOLD.json')){$lines.Add('May-04 B1 수락 검증: 완료 후 종료 / 5월 전체 실행 보류')}else{$lines.Add('May-04 B1 수락 검증: 완료 후 월간 4개 워커 재개')}
            }
        }
        $lines.Add('워커   날짜       정책   현재 단계          일 진행률   세부 진행')
        $lines.Add('--------------------------------------------------------------------------------------------')
        for($i=0;$i -lt 4;$i++) {
            if($i -ge $active.Count){$lines.Add(('{0}      대기' -f ($i+1)));continue}
            $u=$active[$i];$stage=[string]$u.phase;$detail='진행 중';$fo=$null
            $dayUnits=@($units | Where-Object {$_.day -eq $u.day})
            $dayPct=100.0*(@($dayUnits | Where-Object {$_.status -eq 'COMPLETE'}).Count)/4
            if($stage -eq 'CAUSAL_ML'){$stage='Q90 입력 준비';$detail='인과적 학습 / 예측 저장 / 재읽기 검증'}
            elseif($stage -eq 'MEMORY_CHECK'){$stage='동시 메모리 검사';$detail='전체 크기 모델 / 4개 워커 동시 실행'}
            elseif($stage -eq 'ELECTRICAL_GENERATION'){$stage='계통 입력 생성';$detail='OpenDSS 계수 생성 / 검증'}
            elseif($stage -eq 'actual'){$stage='Actual';$detail='고정 결정 재생 / OpenDSS 평가'}
            elseif($stage -eq 'dayahead'){
                $stage='Day-Ahead'
                $folder=Join-Path $runtime ($u.day+'\'+$u.policy+'\dayahead')
                if($u.PSObject.Properties.Name -contains 'output_folder'){$folder=$u.output_folder}
                if(Test-Path -LiteralPath (Join-Path $folder 'FROZEN_JOINT_DECISION.json')){$stage='Fresh';$detail='고정 결정 OpenDSS 검증'}
                elseif($u.policy -eq 'B1'){
                    $detail='모델 구성 / P1 초기화'
                    $file=Join-Path $folder 'A0\SOLVER_STAGES.json'
                    if(Test-Path -LiteralPath $file){
                        try{
                            $last=(Read-LiveJson $file).stages | Select-Object -Last 1
                            $names=@{'PRIMARY_MIN_RHO'='P1 계통 부하';'V41_SECONDARY_MIN_MEAN_H4_SHORTFALL'='P2 예비 용량';'SECONDARY_MIN_MIGRATIONS'='P3 이동 횟수';'TERTIARY_COMPLETE_REFERENCE_DEVIATION'='P4 기준 편차';'QUATERNARY_STABLE_TIE'='P5 결정 확정'}
                            $detail=$names[[string]$last.stage];if(-not $detail){$detail=[string]$last.stage}
                            if($last.OPTIMAL){$detail+=' 완료 / 다음 단계'}
                            elseif($null -ne $last.incumbent -and $null -ne $last.bound -and [math]::Abs([double]$last.incumbent) -gt 1e-12){$gap=100*[math]::Abs(([double]$last.incumbent-[double]$last.bound)/[double]$last.incumbent);$detail+=(' / gap {0:N2}%' -f $gap)}
                            elseif($null -eq $last.bound){$detail+=' / 전역 인증 없음'}
                        }catch{}
                    }
                }elseif($u.policy -in @('B2','B3')){
                    $detail='MESS 경로 / 전력 최적화'
                    $m1=Join-Path $folder 'M1\M1_PROGRESS.json'
                    if(Test-Path -LiteralPath $m1){try{$v=(Read-LiveJson $m1).detail;$detail=Get-MonitorText ($v | ConvertTo-Json -Compress) 48}catch{}}
                }else{$detail='기준 스케줄 평가'}
                if(-not (Test-Path -LiteralPath (Join-Path $folder 'FROZEN_JOINT_DECISION.json'))){
                    $foStage=if($u.policy -eq 'B3'){'A1'}else{'A0'}
                    $foFile=Join-Path $folder ($foStage+'\F_AND_O_LIVE.json')
                    if(Test-Path -LiteralPath $foFile){
                        $fo=Read-LiveJson $foFile;$stage='F&O '+$foStage
                        $priority=@{'PRIMARY_MIN_RHO'='P1';'rho_max'='P1';'V41_SECONDARY_MIN_MEAN_H4_SHORTFALL'='P2';'V41_mean_H4_shortfall_GPUh'='P2';'SECONDARY_MIN_MIGRATIONS'='P3';'TERTIARY_COMPLETE_REFERENCE_DEVIATION'='P4';'complete_segment_site_symmetric_GPU_slots'='P4';'QUATERNARY_STABLE_TIE'='P5';'deterministic_tie'='P5'}
                        if($priority[[string]$fo.stage]){$stage='F&O '+$priority[[string]$fo.stage]}
                        $detail=('{0}회 / 예산 {1:N1}/30분 / 후보 {2:N1}% / 전역 인증 없음' -f $fo.iteration,($fo.budget_used_seconds/60),(100*$fo.coverage_fraction))
                    }
                }
            }
            $lines.Add(('{0}      {1}      {2}    {3,-18} {4,5:N0}%      {5}' -f ($i+1),$u.day.Substring(5),$u.policy,$stage,$dayPct,(Get-MonitorText $detail 52)))
            if($fo -and $fo.compute_control_version){
                $reason=if($fo.termination_reason){$fo.termination_reason}else{'SEARCHING'}
                $lines.Add(('       Sweep {0} {1} / 단계 {2:N1}분 / 전체 {3:N1}분 / 남음 {4:N1}분' -f $fo.STAGE_SWEEP_ID,$fo.sweep_mode,($fo.stage_runtime_seconds/60),($fo.budget_used_seconds/60),($fo.remaining_seconds/60)))
                $lines.Add(('       탐색군 {0:N0}% / 단계 후보 {1:N1}% / 전체 후보 {2:N1}% / 개선 {3}' -f (100*$fo.stage_family_coverage_fraction),(100*$fo.STAGE_COVERAGE_FRACTION),(100*$fo.coverage_fraction),$fo.material_improvements))
                $lines.Add(('       incumbent [{0}] / {1}' -f (($fo.incumbent | ForEach-Object {'{0:G8}' -f $_}) -join ', '),$reason))
            }
        }
        foreach($u in @($units | Where-Object {$_.status -eq 'FAILED'} | Sort-Object day,policy)){
            $lines.Add(('FAIL   {0}  {1}  {2}  {3}' -f $u.day,$u.policy,$u.phase,(Get-MonitorText $u.error 65)))
        }
    } catch {
        $lines.Add('전체  0 / 31일 완료          진행률  0.0%          FAIL  0일')
        $lines.Add('상태  독립 실행 프로세스 시작 준비 중')
        $lines.Add('')
        for($i=1;$i -le 4;$i++){$lines.Add(('워커 {0}    실행 대기' -f $i))}
    }
    $lines.Add('')
    $lines.Add(('갱신 {0}  ·  5초마다 갱신  ·  창을 닫아도 실행은 계속됩니다' -f (Get-Date -Format 'HH:mm:ss')))
    $frame=$lines -join [Environment]::NewLine
    if(-not $Once){Clear-Host};Write-Host $frame
    [System.IO.File]::WriteAllText((Join-Path $out 'MONITOR_LAST_FRAME.txt'),$frame)
    if(-not $Once){Start-Sleep -Seconds 5}
} while(-not $Once)
