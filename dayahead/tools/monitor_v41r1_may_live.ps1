param([string]$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,[switch]$Once,[Alias('Detail')][switch]$ShowDetail,[string]$Day='2025-05-01')
. (Join-Path $PSScriptRoot 'monitor_v39e_may_campaign.ps1') -Repo $Repo -LibraryOnly
$runtime=Join-Path $Repo 'frozen_artifacts\v41r4_may\loop_wall_v4'
$out=Join-Path $runtime 'audit'
$showDetails=[bool]$ShowDetail
$selectedDay=[Math]::Max(1,[Math]::Min(31,[int]$Day.Substring(8,2)))
$quit=$false
# A monitor must never wait for a key-down after observing a key-up or mouse
# event. Peek and drain this console's hotkey-only queue without a ReadKey call.
if(-not ('V41MonitorConsoleInput' -as [type])){
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class V41MonitorConsoleInput {
    [StructLayout(LayoutKind.Explicit, CharSet=CharSet.Unicode, Size=20)]
    public struct InputRecord {
        [FieldOffset(0)] public ushort EventType;
        [FieldOffset(4)] public int KeyDown;
        [FieldOffset(10)] public ushort VirtualKeyCode;
    }
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int n);
    [DllImport("kernel32.dll")] static extern bool GetConsoleMode(IntPtr h, out uint mode);
    [DllImport("kernel32.dll")] static extern bool SetConsoleMode(IntPtr h, uint mode);
    [DllImport("kernel32.dll", EntryPoint="PeekConsoleInputW")]
    static extern bool PeekConsoleInput(IntPtr h, [Out] InputRecord[] records, uint length, out uint count);
    [DllImport("kernel32.dll")] static extern bool FlushConsoleInputBuffer(IntPtr h);
    static IntPtr input;
    static uint originalMode;
    static bool configured;
    public static int HotkeysHandled;
    public static bool Configure() {
        input=GetStdHandle(-10);
        if(!GetConsoleMode(input,out originalMode)) return false;
        // ENABLE_EXTENDED_FLAGS is required to disable this window's QuickEdit.
        configured=SetConsoleMode(input,(originalMode | 0x80u) & ~0x40u);
        return configured;
    }
    public static int PollHotkey() {
        var records=new InputRecord[128];uint count;
        if(!PeekConsoleInput(input,records,(uint)records.Length,out count) || count==0) return 0;
        // This dashboard accepts only shortcuts, never a text-input line.
        // Both operations return immediately; no filtering read can block it.
        FlushConsoleInputBuffer(input);
        for(int i=0;i<count;i++) {
            if(records[i].EventType!=1 || records[i].KeyDown==0) continue;
            int key=records[i].VirtualKeyCode;
            if(key==0x44 || key==0x4f || key==0x51 || key==0x52 || key==37 || key==39) {
                HotkeysHandled++;return key;
            }
        }
        return 0;
    }
    public static void Restore() { if(configured) SetConsoleMode(input,originalMode); }
}
'@
}
$monitorInputConfigured=if(-not $Once){[V41MonitorConsoleInput]::Configure()}else{$false}
$refreshClock=[Diagnostics.Stopwatch]::StartNew()
$refreshSequence=0
function Read-LiveJson([string]$Path) {
    $reader=$null
    $share=[System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,$share)
    try {
        $reader=New-Object System.IO.StreamReader($stream);$text=$reader.ReadToEnd()
        try{return ($text | ConvertFrom-Json -ErrorAction Stop)}
        catch{return ($text | ConvertFrom-Json -AsHashtable -ErrorAction Stop)}
    }
    finally {if($reader){$reader.Dispose()}else{$stream.Dispose()}}
}
function Get-B3MonitorPhase([string]$Folder) {
    # Stage receipts take precedence over an A1 live file retained after A1.
    if(Test-Path -LiteralPath (Join-Path $Folder 'FROZEN_JOINT_DECISION.json')){return 'FRESH'}
    $stages=Join-Path $Folder 'optimization\stages'
    if(Test-Path -LiteralPath (Join-Path $stages 'MF_OUTPUT.json')){return 'MF_COMPLETE'}
    if(Test-Path -LiteralPath (Join-Path $stages 'MF_INPUT_CERTIFICATE.json')){return 'MF'}
    if(Test-Path -LiteralPath (Join-Path $stages 'A1_INPUT.json')){return 'A1'}
    if(Test-Path -LiteralPath (Join-Path $stages 'M1_INPUT.json')){return 'M1'}
    return 'A0'
}
function Get-PhaseStatus([string]$Path) {
    # Phase result payloads can be several MB. Read the root status header only;
    # a nested result's status must never be mistaken for the phase status.
    $share=[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,$share)
    $reader=New-Object IO.StreamReader($stream)
    try{
        $buffer=New-Object char[] 512;$count=$reader.Read($buffer,0,512)
        $header=New-Object string($buffer,0,$count)
        if($header -match '^\s*\{\s*"status"\s*:\s*"([^"]+)"'){return $Matches[1]}
    }finally{$reader.Dispose()}
    return (Read-LiveJson $Path).status
}
try {
    $Host.UI.RawUI.WindowTitle='V41R4 5월 실행 현황 · alpha 1.15 · Codex 독립 실행'
    if(-not $Once){
        $size=$Host.UI.RawUI.BufferSize;$size.Width=150;$size.Height=2000;$Host.UI.RawUI.BufferSize=$size
        $window=$Host.UI.RawUI.WindowSize;$window.Width=145;$window.Height=38;$Host.UI.RawUI.WindowSize=$window
    }
} catch {}
try {
do {
    $refreshDeadline=$refreshClock.ElapsedMilliseconds+5000
    $refreshSequence++
    $lines=New-Object 'System.Collections.Generic.List[string]'
    $lines.Add('  V41R4  5월 캠페인                         공통 최대 4 워커 · DA/Fresh + Actual')
    $lines.Add('')
    try {
        $state=Read-LiveJson (Join-Path $runtime 'campaign_state.json')
        $progress=Read-LiveJson (Join-Path $runtime 'campaign_progress.json')
        $actualAuthority=$null;$actualRoot=$null
        $authorityPath=Join-Path $out 'ACTUAL_EXECUTION_METHOD_CURRENT.json'
        if(Test-Path -LiteralPath $authorityPath){
            $actualAuthority=Read-LiveJson $authorityPath
            $actualRoot=[string]$actualAuthority.namespace
            $progress=Read-LiveJson $actualAuthority.dispatcher_state
        }
        $displayCap=if($progress.day_workers){[int]$progress.day_workers}else{4}
        $lines[0]=('  V41R4  5월 캠페인                         공통 최대 {0} 워커 · DA/Fresh + Actual' -f $displayCap)
        $units=@($state.units.PSObject.Properties | ForEach-Object {$_.Value})
        $reuseIndex=$null;$reusePath=Join-Path $out 'REUSED_RESULTS_INDEX.json'
        if(Test-Path -LiteralPath $reusePath){$reuseIndex=Read-LiveJson $reusePath}
        # Display completed receipts and current worker liveness even when
        # the supervisor heartbeat is stale. This never changes run state.
        foreach($unit in $units){
            $unitRoot=Join-Path $runtime ($unit.day+'\'+$unit.policy)
            if($actualRoot){
                # Historical Actual receipts cannot complete or hide a V2 worker.
                $newFolder=Join-Path $actualRoot ('replays\'+$unit.day+'\'+$unit.policy)
                $newReceipt=Join-Path $newFolder 'CANDIDATE_RECEIPT.json'
                $unit.status='WAITING';$unit.phase='queued';$unit.worker_pid=$null
                $daReceipt=Join-Path $out ($unit.day+'\PHASE_'+$unit.policy+'_DA.json')
                if((Test-Path -LiteralPath $daReceipt) -and (Get-PhaseStatus $daReceipt) -eq 'PASS'){$unit.status='DA_COMPLETE';$unit.phase='Robust V2 Actual 대기'}
                if(Test-Path -LiteralPath $newReceipt){
                    $nr=Read-LiveJson $newReceipt
                    if($nr.status -eq 'COMPLETE' -and $nr.method_SHA -eq $actualAuthority.method_SHA){$unit.status='COMPLETE';$unit.phase='Robust V2 Actual 완료'}
                }
                $running=$progress.active | Where-Object {$_.day -eq $unit.day -and ($_.policy -eq $unit.policy -or ($unit.policy -eq 'B0' -and $_.phase -in @('electrical','domain')))} | Select-Object -First 1
                if($running){
                    $unit.worker_pid=$running.worker_pid
                    $unit.status=if(Get-Process -Id $unit.worker_pid -ErrorAction SilentlyContinue){'RUNNING'}else{'INTERRUPTED'}
                    $unit.phase=switch -Regex ([string]$running.phase){
                        '_ETA95_QSAFE_AC$' {'actual_v2';break}
                        '_DA$' {'dayahead';break}
                        '^electrical$' {'ELECTRICAL_GENERATION';break}
                        '^domain$' {'DOMAIN_PREPARATION';break}
                        default {[string]$running.phase}
                    }
                    $unit | Add-Member -NotePropertyName active_record -NotePropertyValue $running -Force
                }
                elseif($unit.status -ne 'COMPLETE'){
                    $problem=$progress.errors | Where-Object {$_.day -eq $unit.day -and $_.phase.StartsWith($unit.policy)} | Select-Object -Last 1
                    if($problem){$unit.status='FAILED';$unit | Add-Member -NotePropertyName error -NotePropertyValue $problem.error -Force}
                }
                continue
            }
            $phaseReceipt=Join-Path $out ($unit.day+'\PHASE_'+$unit.policy+'_AC.json')
            $phaseValue=$null
            if(Test-Path -LiteralPath $phaseReceipt){$phaseValue=Read-LiveJson $phaseReceipt}
            $actualReceipt=Join-Path $unitRoot 'actual\ACTUAL_RECEIPT.json'
            $actualDone=(Test-Path -LiteralPath $actualReceipt) -and ((Read-LiveJson $actualReceipt).status -eq 'COMPLETE')
            if(($phaseValue -and $phaseValue.status -eq 'PASS') -or $actualDone){$unit.status='COMPLETE';$unit.phase='complete';$unit.worker_pid=$null}
            elseif($phaseValue -and $phaseValue.status -eq 'FAIL_CLOSED'){
                $unit.status='FAILED'
                $reason=[string]$phaseValue.error
                $seedPath=Join-Path $unitRoot 'dayahead\policy_seed\POLICY_FEASIBLE_SEED_AUDIT.json'
                if(Test-Path -LiteralPath $seedPath){
                    $seed=Read-LiveJson $seedPath
                    if($seed.electrical.status -eq 'FAIL'){
                        $g=$seed.electrical
                        $reason='전기 한계: Vmax {0:N6} pu · 변압기 전류 {1:N2}% · kVA {2:N2}%' -f $g.Vmax,(100*$g.maximum_transformer_phase_current),(100*$g.maximum_transformer_kVA)
                    }
                }
                $unit | Add-Member -NotePropertyName error -NotePropertyValue $reason -Force
            }elseif($unit.status -eq 'RUNNING'){
                if(-not (Get-Process -Id $unit.worker_pid -ErrorAction SilentlyContinue)){$unit.status='INTERRUPTED';$unit.phase='완료 증거 없음'}
                elseif(Test-Path -LiteralPath (Join-Path $unitRoot 'actual\ACTUAL_BOUNDARY_RECEIPT.json')){$unit.phase='actual'}
            }
        }
        foreach($unit in $units){
            if($unit.status -eq 'WAITING'){
                $daPhase=Join-Path $out ($unit.day+'\PHASE_'+$unit.policy+'_DA.json')
                if((Test-Path -LiteralPath $daPhase) -and (Get-PhaseStatus $daPhase) -eq 'PASS'){$unit.status='DA_COMPLETE';$unit.phase='Day-Ahead 재사용 완료'}
            }
        }
        $days=@($units | Group-Object day)
        $complete=@($days | Where-Object {@($_.Group | Where-Object {$_.status -eq 'COMPLETE'}).Count -eq 4}).Count
        $fails=@($days | Where-Object {@($_.Group | Where-Object {$_.status -eq 'FAILED'}).Count -gt 0}).Count
        $percent=100.0*(@($units | Where-Object {$_.status -eq 'COMPLETE'}).Count)/124
        $done=@($units | Where-Object {$_.status -eq 'COMPLETE'}).Count
        $filled=[Math]::Min(24,[int][Math]::Floor($percent*24/100))
        $bar=('■'*$filled)+('·'*(24-$filled))
        $lines.Add(('  [{0}] {1,5:N1}%     {2}/124 정책 완료 · {3}/31일 완료 · FAIL {4}일' -f $bar,$percent,$done,$complete,$fails))
        $alive=$null -ne (Get-Process -Id $progress.supervisor_pid -ErrorAction SilentlyContinue)
        $age=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()-[double]$progress.updated_at
        $liveness=if($alive -and $age -lt 30){'정상'}elseif($progress.status -eq 'COMPLETE'){'완료'}elseif($alive){'상태 갱신 지연 · 워커와 완료 파일 직접 확인'}else{'supervisor 종료 · 완료 파일 직접 확인'}
        $lines.Add(('  상태 {0} · 연결 {1} · 갱신 {2:N0}초 전' -f $progress.status,$liveness,$age))
        $lines.Add('  α_BG 1.15 고정 · AIDC 780 GPU · MESS 4 × 300 kW / 400 kVA / 1200 kWh')
        $lines.Add('  B1 / A1 각각 F&O 루프 30분 · 후보·랭킹·계산·풀이 포함 · B1은 날짜별 B0에서 시작')
        $lines.Add('  B3: B1 재사용(A0) → M1 → A1 → MF → Fresh → Actual · MF는 고정 경로 P/Q·SoC 조정')
        $lines.Add('  무개선 조기 종료 없음 · 30분 종료 후 최선해 반환 · 일회성 준비·계수 생성 제외')
        $daComplete=@($units | Where-Object {$dp=Join-Path $out ($_.day+'\PHASE_'+$_.policy+'_DA.json');(Test-Path -LiteralPath $dp) -and (Get-PhaseStatus $dp) -eq 'PASS'}).Count
        $lines.Add(('  Day-Ahead/Fresh 완료 {0}/124 · 배정 순서는 아래 자원 운영 모드에 따름' -f $daComplete))
        if($actualRoot){$lines.Add(('  Actual: Robust V2 · η=0.95 · P 고정 / Q-only · 새 버전 완료 {0}/124 · 과거 Actual 별도 보존' -f $done))}
        if($actualRoot){
            $splitPath=Join-Path $actualRoot 'TEMPORARY_RESOURCE_POLICY.json'
            if(Test-Path -LiteralPath $splitPath){
                $split=Read-LiveJson $splitPath
                if($split.status -eq 'ACTIVE'){
                    $nd=@($progress.active | Where-Object {$_.kind -eq 'DA_FRESH'}).Count
                    $na=@($progress.active | Where-Object {$_.kind -in @('ACTUAL_ONLY','DIAGNOSTIC_ONLY')}).Count
                    $lines.Add(('  임시 DA/Fresh {0} + Actual {1}: 현재 {2} + {3} · 밀린 Actual 완료 후 정상 4워커 복귀' -f $split.MAX_DA_FRESH_WORKERS,$split.MAX_ACTUAL_WORKERS,$nd,$na))
                }
            }
            if($progress.resource_mode -eq 'NORMAL_4'){$lines.Add('  정상 4워커 · 날짜/정책별 DA/Fresh → 해당 Actual · 전역 Actual 우선 배정 없음')}
            $holdPath=Join-Path $actualRoot 'ACTUAL_DISPATCH_HOLD.json'
            if((Test-Path -LiteralPath $holdPath) -and (Read-LiveJson $holdPath).status -eq 'HOLD'){$lines.Add('  본 Actual 배정 보류 · May12 경량 검색 + 선택 Q 96개 검증 후 재개')}
        }
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
        foreach($auditWorker in @($progress.active | Where-Object {$_.kind -eq 'DIAGNOSTIC_ONLY'})){
            $auditPolicy=if($auditWorker.phase -match 'FINAL_96_GATE_(B[0-3])_'){$Matches[1]}elseif($auditWorker.phase -eq 'LIGHTWEIGHT_SEARCH_SELECTED_Q_GATE'){'B3'}else{'감사'}
            $active+=@([pscustomobject]@{day=$auditWorker.day;policy=$auditPolicy;phase='actual_equivalence_audit';worker_pid=$auditWorker.worker_pid;active_record=$auditWorker})
        }
        $lines.Add('워커   날짜       정책   현재 단계          일 진행률   세부 진행')
        $lines.Add('--------------------------------------------------------------------------------------------')
        for($i=0;$i -lt [Math]::Max($displayCap,$active.Count);$i++) {
            if($i -ge $active.Count){$lines.Add(('{0}      대기' -f ($i+1)));continue}
            $u=$active[$i];$stage=[string]$u.phase;$detail='진행 중';$fo=$null;$b3Phase=$null
            $dayUnits=@($units | Where-Object {$_.day -eq $u.day})
            $dayPct=100.0*(@($dayUnits | Where-Object {$_.status -eq 'COMPLETE'}).Count)/4
            if($stage -eq 'CAUSAL_ML'){$stage='Q90 입력 준비';$detail='인과적 학습 / 예측 저장 / 재읽기 검증'}
            elseif($stage -eq 'MEMORY_CHECK'){$stage='동시 메모리 검사';$detail='전체 크기 모델 / 4개 워커 동시 실행'}
            elseif($stage -eq 'ELECTRICAL_GENERATION'){
                $stage='전기계수 생성';$detail='OpenDSS 계수 생성 / 검증'
                $electricalRoot=Join-Path $runtime ('e\'+$u.day.Replace('-',''))
                $voltage=0;$current=0
                $vp=Join-Path $electricalRoot 'PROGRESS_voltage.json';$cp=Join-Path $electricalRoot 'PROGRESS_current.json'
                if(Test-Path -LiteralPath $vp){$voltage=(Read-LiveJson $vp).SolveSnap_calls}
                if(Test-Path -LiteralPath $cp){$current=(Read-LiveJson $cp).SolveSnap_calls;$voltage=11617}
                $detail=('{0:N1}% · 전압 {1:N0} / 전류 {2:N0} solve' -f (100*($voltage+$current)/23234),$voltage,$current)
            }
            elseif($stage -eq 'DOMAIN_PREPARATION'){$stage='후보 준비';$detail='기존 공간·시간·migration 도메인 / SHA 봉인'}
            elseif($stage -eq 'CERTIFIED_REUSE'){$stage='검증 결과 재사용';$detail='May-04 계수·B0·최종 B1 / 중복 실행 없음'}
            elseif($stage -eq 'actual_equivalence_audit'){
                $stage=if($u.active_record.phase -eq 'LIGHTWEIGHT_SEARCH_SELECTED_Q_GATE'){'Actual 경량 검증'}else{'Actual 동등성 감사'};$detail=[string]$u.active_record.phase
                $auditDir=Split-Path -Parent $u.active_record.diagnostic_result
                $auditProgress=Join-Path $auditDir 'PROGRESS.json'
                if($u.active_record.phase -eq 'EXACT_FULL_SEARCH_AUDIT'){$auditProgress=Join-Path $auditDir 'FULL_SEARCH_PROGRESS.json'}
                if(Test-Path -LiteralPath $auditProgress){
                    $ap=Read-LiveJson $auditProgress
                    $detail=if($null -ne $ap.slots_complete){'{0} · {1}/96 슬롯 완료 · 슬롯 {2} / 후보 {3}' -f $(if($ap.phase){$ap.phase}else{$ap.mode}),$ap.slots_complete,$ap.slot,$ap.trial}else{'{0} · Q 후보 {1}' -f $ap.mode,$ap.trials}
                }
            }
            elseif($stage -eq 'actual_v2'){
                $stage='Actual Robust V2'
                $af=Join-Path $actualRoot ('replays\'+$u.day+'\'+$u.policy)
                $elapsed=[Math]::Max(0,([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()-[double]$u.active_record.started_at)/60)
                if($u.policy -in @('B0','B1')){$detail='공통 binding 회귀 검증 / Exact OpenDSS'}
                else{
                    $qp=Join-Path $af 'ETA95_QSAFE_ACTUAL\PROGRESS.json'
                    if(Test-Path -LiteralPath $qp){
                        $q=Read-LiveJson $qp
                        $detail=if($q.slots_complete -lt 96){'QSAFE 슬롯 {0} 평가 · {0}/96 완료 · Q개입 {1} · 미해결 {2}' -f $q.slots_complete,$q.interventions,$q.infeasible}else{'96/96 완료 · 연속 재생 / P·SoC 동일성 감사'}
                    }elseif(Test-Path -LiteralPath (Join-Path $af 'ETA95_QSAFE_ACTUAL')){$detail='QSAFE 슬롯 0 평가 · 0/96 완료 / robust Q 탐색'}
                    elseif(Test-Path -LiteralPath (Join-Path $af 'ETA95_ACTUAL')){$detail='ETA95 기준 궤적 / Exact OpenDSS 재생'}
                    else{$detail='η=0.95 입력 / 동결 결정 SHA 검증'}
                }
                $detail+=(' · {0:N1}분' -f $elapsed)
            }
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
                    $stage='M1';$detail='MESS 경로 / 전력 최적화'
                    $m1=Join-Path $folder 'M1\M1_PROGRESS.json'
                    if(Test-Path -LiteralPath $m1){try{$v=(Read-LiveJson $m1).detail;$detail=Get-MonitorText ($v | ConvertTo-Json -Compress) 48}catch{}}
                    if($u.policy -eq 'B3'){
                        $b3Phase=Get-B3MonitorPhase $folder
                        switch($b3Phase){
                            'A0' {$stage='A0 재사용';$detail='최종 B1 결정 검증 / M1 준비'}
                            'A1' {$stage='A1 준비';$detail='M1 고정 / B1과 동일 AIDC 탐색 준비'}
                            'MF' {$stage='MF';$detail='A1·M1 경로 고정 / P·Q·SoC 최적화'}
                            'MF_COMPLETE' {
                                $stage='MF 완료';$detail='고정 경로 최종 결과 검증 / 결정 저장'
                                $candidate=Read-LiveJson (Join-Path $folder 'optimization\stages\MF_CANDIDATE_OUTPUT.json')
                                if($candidate.info.solver.termination -eq 'SHARED_BUDGET_RETAINED_VERIFIED_M1'){$detail='예산 부족 / 검증된 M1 전력 유지'}
                            }
                            'FRESH' {$stage='Fresh';$detail='고정 결정 OpenDSS 검증'}
                        }
                    }
                }else{$detail='기준 스케줄 평가'}
                if(-not (Test-Path -LiteralPath (Join-Path $folder 'FROZEN_JOINT_DECISION.json')) -and ($u.policy -ne 'B3' -or $b3Phase -eq 'A1')){
                    $foStage=if($u.policy -eq 'B3'){'A1'}else{'A0'}
                    $foFile=Join-Path $folder ($foStage+'\F_AND_O_LIVE.json')
                    if(Test-Path -LiteralPath $foFile){
                        $fo=Read-LiveJson $foFile;$stage='F&O '+$foStage
                        $priority=@{'PRIMARY_MIN_RHO'='P1';'rho_max'='P1';'V41_SECONDARY_MIN_MEAN_H4_SHORTFALL'='P2';'V41_mean_H4_shortfall_GPUh'='P2';'SECONDARY_MIN_MIGRATIONS'='P3';'TERTIARY_COMPLETE_REFERENCE_DEVIATION'='P4';'complete_segment_site_symmetric_GPU_slots'='P4';'QUATERNARY_STABLE_TIE'='P5';'deterministic_tie'='P5'}
                        if($priority[[string]$fo.stage]){$stage=if($u.policy -eq 'B3'){'A1 F&O '+$priority[[string]$fo.stage]}else{'F&O '+$priority[[string]$fo.stage]}}
                        if($fo.search_loop_started_at_unix -and -not $fo.search_loop_stopped){
                            $fo.budget_used_seconds=[Math]::Min(1800,[Math]::Max([double]$fo.budget_used_seconds,([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.-[double]$fo.search_loop_started_at_unix)))
                            $fo.remaining_seconds=1800-$fo.budget_used_seconds
                        }
                        $detail=('{0}회 · 루프 {1:N1}/30분 · P1 {2:N5} · P2 {3:N1}' -f $fo.iteration,($fo.budget_used_seconds/60),$fo.incumbent[0],$fo.incumbent[1])
                    }
                }
            }
            $lines.Add(('{0}      {1}      {2}    {3,-18} {4,5:N0}%      {5}' -f ($i+1),$u.day.Substring(5),$u.policy,$stage,$dayPct,(Get-MonitorText ($stage+' · '+$detail) 90)))
            if($showDetails -and $fo -and $fo.compute_control_version){
                $reason=if($fo.termination_reason){$fo.termination_reason}else{'SEARCHING'}
                $lines.Add(('       Sweep {0} {1} / 단계 {2:N1}분 / 전체 {3:N1}분 / 남음 {4:N1}분' -f $fo.STAGE_SWEEP_ID,$fo.sweep_mode,($fo.stage_runtime_seconds/60),($fo.budget_used_seconds/60),($fo.remaining_seconds/60)))
                if($null -ne $fo.elapsed_component_wall_seconds){$lines.Add(('       F&O 루프 {0:N1}분 / 준비 포함 경과 {1:N1}분 · 루프 안의 검증·저장도 예산 포함' -f ($fo.budget_used_seconds/60),($fo.elapsed_component_wall_seconds/60)))}
                $lines.Add(('       탐색군 {0:N0}% / 단계 후보 {1:N1}% / 전체 후보 {2:N1}% / 개선 {3}' -f (100*$fo.stage_family_coverage_fraction),(100*$fo.STAGE_COVERAGE_FRACTION),(100*$fo.coverage_fraction),$fo.material_improvements))
                $lines.Add(('       incumbent [{0}] / {1}' -f (($fo.incumbent | ForEach-Object {'{0:G8}' -f $_}) -join ', '),$reason))
            }
        }
        foreach($u in @($units | Where-Object {$_.status -eq 'FAILED'} | Sort-Object day,policy)){
            $lines.Add(('FAIL   {0}  {1}  {2}' -f $u.day,$u.policy,(Get-MonitorText $u.error 112)))
        }
        if($true){
            $chosen='2025-05-{0:D2}' -f $selectedDay
            $lines.Add('')
            $lines.Add(('  상세 {0}  [← / → 날짜 변경]    F&O는 전역 최적 인증을 주장하지 않습니다.' -f $chosen))
            $lines.Add('  정책  상태          P1(계획)     P2(GPUh)    Fresh     Actual     Actual Vmax / ρmax')
            foreach($policy in @('B0','B1','B2','B3')){
                $unit=$units | Where-Object {$_.day -eq $chosen -and $_.policy -eq $policy} | Select-Object -First 1
                $folder=Join-Path $runtime ($chosen+'\'+$policy)
                $objective=Join-Path $folder 'dayahead\optimization\OBJECTIVE_LEDGER.json'
                $p1='-';$p2='-';$fg='-';$ag='-';$voltageText='-'
                if(Test-Path -LiteralPath $objective){$v=(Read-LiveJson $objective).OBJECTIVE_VECTOR;$p1='{0:N6}' -f $v[0];$p2='{0:N2}' -f $v[1]}
                $daProof=Join-Path $out ($chosen+'\PHASE_'+$policy+'_DA.json')
                if((Test-Path -LiteralPath $daProof) -and (Get-PhaseStatus $daProof) -eq 'PASS'){$fg='PASS'}
                $accept=Join-Path $out ($chosen+'\'+$policy+'_ACCEPTANCE.json')
                if(-not $actualRoot -and (Test-Path -LiteralPath $accept)){
                    $a=Read-LiveJson $accept
                    if($a.classification -eq 'REUSED_CERTIFIED_RESULT_NO_REPLAY'){$fg=$a.evidence.Fresh;$ag=$a.evidence.Actual;$s=$a.evidence.actual}
                    else{$fg=$a.Fresh;$ag=if($a.Actual_physical_outcome -eq 'WITH_VIOLATIONS'){'위반 있음'}else{'유효 재생'};$s=$a.Actual_summary}
                    if($s){$voltageText='{0:N6} / {1:N6}' -f $s.Vmax_pu,$s.rho_max_AC}
                }
                $retainedRow=$reuseIndex.rows | Where-Object {$_.day -eq $chosen -and $_.policy -eq $policy} | Select-Object -First 1
                $displayStatus=$unit.status
                if($retainedRow -and $unit.status -eq 'DA_COMPLETE'){$displayStatus='재사용 DA'}
                if(-not $actualRoot -and $retainedRow -and $retainedRow.stages.AC -and $ag -eq '-'){
                    $rg=$retainedRow.stages.AC
                    $ag=if($rg.grid.physical_outcome -eq 'WITH_VIOLATIONS'){'기존 위반'}else{'기존 결과'}
                    $voltageText='{0:N6} / {1:N6}' -f $rg.Vmax,$rg.rho_max
                }
                if($actualRoot){
                    $af=Join-Path $actualRoot ('replays\'+$chosen+'\'+$policy)
                    $receipt=Join-Path $af 'CANDIDATE_RECEIPT.json'
                    $ag=if($unit.status -eq 'RUNNING' -and $unit.phase -eq 'actual_v2'){'V2 실행 중'}elseif($unit.status -eq 'FAILED'){'실행 오류'}else{'V2 대기'}
                    if(Test-Path -LiteralPath $receipt){
                        $nr=Read-LiveJson $receipt
                        if($nr.status -eq 'COMPLETE' -and $nr.method_SHA -eq $actualAuthority.method_SHA){
                            $completed=Read-LiveJson (Join-Path $af 'COMPLETE.json')
                            $s=if($policy -in @('B0','B1')){$completed.summary}else{$completed.ETA95_QSAFE_ACTUAL}
                            $ag=if($completed.ROBUST_Q_ONLY_UNRESOLVED_slots -gt 0){'UNRESOLVED'}elseif($s.physical_violation){'위반 있음'}else{'V2 PASS'}
                            $voltageText='{0:N6} / {1:N6}' -f $s.Vmax_pu,$s.rho_max_AC
                        }
                    }
                    elseif($unit.phase -eq 'actual_v2'){
                        $qp=Join-Path $af 'ETA95_QSAFE_ACTUAL\PROGRESS.json'
                        if(Test-Path -LiteralPath $qp){$q=Read-LiveJson $qp;$voltageText='{0}/96 완료 · 최종값 감사 대기' -f $q.slots_complete}
                    }
                }
                $lines.Add(('  {0,-5} {1,-12} {2,11} {3,12}    {4,-8}  {5,-8}  {6}' -f $policy,$displayStatus,$p1,$p2,$fg,$ag,$voltageText))
                $detailPath=Join-Path $out ($chosen+'\'+$policy+'_DAYAHEAD_SUMMARY.json')
                if($showDetails -and (Test-Path -LiteralPath $detailPath)){
                    $ds=Read-LiveJson $detailPath
                    $lines.Add(('        P3/P4/P5 [{0}] · 시간 {1} / 공간 {2} / checkpoint {3} · MESS 운행 {4}' -f (($ds.OBJECTIVE_VECTOR[2..4]) -join ', '),@($ds.temporal_shifts).Count,@($ds.spatial_relocations).Count,@($ds.checkpoint_migrations).Count,$ds.MESS.movement_count))
                }
            }
            $resultFolder=if($actualRoot){Join-Path $actualRoot ('replays\'+$chosen)}else{Join-Path $runtime $chosen}
            $lines.Add(('  [O] 날짜 Actual 결과 폴더: {0}' -f $resultFolder))
        }
    } catch {
        $lines.Add(('  상태를 읽지 못했습니다: {0}' -f (Get-MonitorText $_.Exception.Message 110)))
        $lines.Add('  실행 결과를 0 또는 PASS로 추정하지 않습니다. 다음 갱신에서 다시 읽습니다.')
    }
    $lines.Add('')
    $lines.Add(('  {0}  ·  [D] {1}  [←/→] 상세 날짜  [O] 결과 폴더  [Q] 화면 닫기' -f (Get-Date -Format 'HH:mm:ss'),$(if($showDetails){'간단히'}else{'상세 보기'})))
    $lines.Add('  5초마다 갱신 · 이 화면 또는 Codex를 닫아도 캠페인은 계속 실행됩니다.')
    $frame=$lines -join [Environment]::NewLine
    if(-not $Once){Clear-Host}
    foreach($line in $lines){
        $color=if($line -match 'FAIL_CLOSED|^FAIL|확인 필요|읽지 못'){ 'Red' }elseif($line -match 'V41R4|상세 2025|\[D\]'){'Cyan'}elseif($line -match '위반 있음'){'Yellow'}else{'Gray'}
        Write-Host $line -ForegroundColor $color
    }
    [System.IO.File]::WriteAllText((Join-Path $out 'MONITOR_LAST_FRAME.txt'),$frame)
    $refreshProof=[ordered]@{pid=$PID;sequence=$refreshSequence;rendered_at_utc=[DateTime]::UtcNow.ToString('o');elapsed_ms=$refreshClock.ElapsedMilliseconds;refresh_interval_ms=5000;blocking_keyboard_reads=0;quick_edit_disabled=$monitorInputConfigured;hotkeys_handled=[V41MonitorConsoleInput]::HotkeysHandled}
    [System.IO.File]::WriteAllText((Join-Path $out 'MONITOR_REFRESH_HEARTBEAT.json'),($refreshProof | ConvertTo-Json -Compress))
    if(-not $Once){
        while($refreshClock.ElapsedMilliseconds -lt $refreshDeadline){
            $key=[V41MonitorConsoleInput]::PollHotkey()
            if($key -eq 0x44){$showDetails=-not $showDetails}
            elseif($key -eq 39){$selectedDay=1+($selectedDay%31);$showDetails=$true}
            elseif($key -eq 37){$selectedDay=1+(($selectedDay+29)%31);$showDetails=$true}
            elseif($key -eq 0x4f){$folder=if($actualRoot){Join-Path $actualRoot ('replays\2025-05-{0:D2}' -f $selectedDay)}else{Join-Path $runtime ('2025-05-{0:D2}' -f $selectedDay)};if(Test-Path -LiteralPath $folder){Invoke-Item -LiteralPath $folder}}
            elseif($key -eq 0x52){$reuseFolder=Join-Path $runtime 'reused_results';if(Test-Path -LiteralPath $reuseFolder){Invoke-Item -LiteralPath $reuseFolder}}
            elseif($key -eq 0x51){$quit=$true}
            if($key -ne 0){break}
            $remaining=$refreshDeadline-$refreshClock.ElapsedMilliseconds
            if($remaining -gt 0){Start-Sleep -Milliseconds ([int][Math]::Min(100,$remaining))}
        }
    }
} while(-not $Once -and -not $quit)
} finally {
    [V41MonitorConsoleInput]::Restore()
}
