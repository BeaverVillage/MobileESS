"""Reuse the existing production PowerShell; data/labels only, no new monitor."""
from pathlib import Path
import json,hashlib,difflib
OUT=Path(__file__).absolute().parent
source=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\tools')
target=OUT/'monitoring';target.mkdir(exist_ok=True)
name='monitor_v41r1_may_live.ps1';original=(source/name).read_text(encoding='utf-8-sig');s=original
s=s.replace('/124','/12').replace('/31일','/3일').replace(')/124',')/12').replace('V41R4  5월 캠페인','IEEE123 3-day Actual Q-first/minimal-P')
s=s.replace("$lines.Add('  B1 / A1 각각 F&O 루프 30분 · 후보·랭킹·계산·풀이 포함 · B1은 날짜별 B0에서 시작')","$lines.Add('  Planning/Fresh 동결 · Actual만 재실행 · solver 4 threads')")
s=s.replace("$lines.Add('  B3: B1 재사용(A0) → M1 → A1 → MF → Fresh → Actual · MF는 고정 경로 P/Q·SoC 조정')","$lines.Add('  Q-first → 최소 P 보정 → 인과적 에너지 회복 · 경로/AIDC 고정')")
s=s.replace("$lines.Add('  무개선 조기 종료 없음 · 30분 종료 후 최선해 반환 · 일회성 준비·계수 생성 제외')","$lines.Add('  날짜 2025-05-01 / 05-02 / 05-12 · 새 Actual namespace')")
anchor="        $displayCap=if($progress.day_workers){[int]$progress.day_workers}else{4}"
assert s.count(anchor)==1
s=s.replace(anchor,anchor+"\n        $tm=$progress.telemetry\n        if($tm){$lines.Add(('  PID {0} | CPU {1:N1}s | RAM {2:N2} GiB | {3} {4} | {5} | elapsed {6:N1}min' -f $tm.pid,$tm.CPU_seconds,$tm.RSS_GiB,$tm.day,$tm.policy,$tm.process_state,($tm.elapsed_seconds/60)));$lines.Add(('  log: '+(Get-MonitorText $tm.log_tail 140)))}")
(target/name).write_text(s,encoding='utf-8-sig')
(target/'monitor_v39e_may_campaign.ps1').write_bytes((source/'monitor_v39e_may_campaign.ps1').read_bytes())
(target/'TEMPLATE_ADAPTATION.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=str(source/name),tofile=str(target/name))),encoding='utf-8')
import runpy
runpy.run_path(str(OUT/'upgrade_actual_monitor.py'),run_name='__main__')

if (OUT/'ACTIVE_SCOPE.json').exists():
 scope=json.loads((OUT/'ACTIVE_SCOPE.json').read_text(encoding='utf-8'))
 if scope['scope']=='EXISTING_3DAY_BOTH_ROUNDS':
  s=s.replace('IEEE123 May 31-day Actual · 1Round + 2Round','IEEE123 3-day Actual · 1Round + 2Round').replace('/155','/15').replace('/31일','/3일')
  s=s.replace('IEEE123 5월 전체 Actual · 1Round / 2Round','IEEE123 3-day / 4 threads · 1Round / 2Round')
  s=s.replace('2025-05-01 ~ 05-31 · 155 distinct replays / 248 round-policy rows','2025-05-01 / 05-02 / 05-12 · 15 distinct replays / 24 round-policy rows')
  s=s.replace('MONTHLY_CAMPAIGN_STATUS.json','THREE_DAY_ROUND_CAMPAIGN_STATUS.json')
  (target/name).write_text(s,encoding='utf-8-sig')
  (target/'TEMPLATE_ADAPTATION.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=str(source/name),tofile=str(target/name))),encoding='utf-8')
(target/'SOURCE.json').write_text(json.dumps(dict(source=str(source/name),source_SHA256=hashlib.sha256((source/name).read_bytes()).hexdigest(),retained='Existing refresh loop, process liveness, stage/day/policy tables, hotkeys, QuickEdit protection and heartbeat; adapted only namespace schema, scope labels, current telemetry display'),indent=2),encoding='utf-8')

# The user extended the campaign to the entire month and both B3 rounds.
s=s.replace('IEEE123 3-day Actual Q-first/minimal-P','IEEE123 May 31-day Actual · 1Round + 2Round').replace('/12','/155').replace('/3일','/31일')
s=s.replace('날짜 2025-05-01 / 05-02 / 05-12 · 새 Actual namespace','2025-05-01 ~ 05-31 · 155 distinct replays / 248 round-policy rows')
s=s.replace('공통 최대 4 워커 · DA/Fresh + Actual','Actual 1 worker × 4 threads').replace('공통 최대 {0} 워커 · DA/Fresh + Actual','Actual {0} worker × 4 threads')
s=s.replace("$Host.UI.RawUI.WindowTitle='V41R4 5월 실행 현황 · alpha 1.15 · Codex 독립 실행'","$Host.UI.RawUI.WindowTitle='IEEE123 5월 전체 Actual · 1Round / 2Round'")
s=s.replace("$_.status -eq 'COMPLETE'}).Count -eq 4","$_.status -eq 'COMPLETE'}).Count -eq 5")
s=s.replace("foreach($policy in @('B0','B1','B2','B3'))","foreach($policy in @('B0','B1','B2','B3_1R','B3_2R'))")
s=s.replace("$accept=Join-Path $out ($chosen+'\\'+$policy+'_ACCEPTANCE.json')","$accept=Join-Path $out ($chosen+'\\'+$policy+'_ACCEPTANCE.json')\n                if($policy -eq 'B3_2R' -and -not (Test-Path -LiteralPath $accept)){$accept=Join-Path $out ($chosen+'\\B3_ACCEPTANCE.json')}")
s=s.replace("$lines.Add(('  Day-Ahead/Fresh 완료 {0}/155 · 배정 순서는 아래 자원 운영 모드에 따름' -f $daComplete))","$lines.Add('  Day-Ahead/Fresh: 기존 최종 authority 동결 · Planning 재실행 없음')")
anchor="        $units=@($state.units.PSObject.Properties | ForEach-Object {$_.Value})"
extra="""
        $monthlyPath=Join-Path (Split-Path $Repo -Parent) 'MONTHLY_CAMPAIGN_STATUS.json'
        if(Test-Path -LiteralPath $monthlyPath){
            $monthly=Read-LiveJson $monthlyPath
            $oldUnits=$units
            $units=@($monthly.units.PSObject.Properties | ForEach-Object {$_.Value})
            if($monthly.status -eq 'ADOPTING_INITIAL_QUEUE'){
                foreach($u in $oldUnits){
                    $label=if($u.policy -eq 'B3'){'B3_2R'}else{$u.policy}
                    $target=$units | Where-Object {$_.day -eq $u.day -and $_.policy -eq $label} | Select-Object -First 1
                    if($target -and $u.status -eq 'RUNNING'){$target.status=$u.status;$target.phase=$u.phase;$target.worker_pid=$u.worker_pid}
                }
            }
        }
"""
assert s.count(anchor)==1;s=s.replace(anchor,anchor+extra)
anchor="        $progress=Read-LiveJson (Join-Path $runtime 'campaign_progress.json')"
replacement=anchor+"""
        $monthNow=Read-LiveJson (Join-Path (Split-Path $Repo -Parent) 'MONTHLY_CAMPAIGN_STATUS.json')
        if($monthNow.scope -eq 'FULL MAY 2025; THREE CONCURRENT DAYS; FOUR THREADS EACH'){
            $progress=$monthNow
            $state=[pscustomobject]@{units=$monthNow.units}
        }
"""
assert s.count(anchor)==1;s=s.replace(anchor,replacement)
s=s.replace('Actual {0} worker × 4 threads','동시 {0} dates × 4 threads/date (총 12 threads)')
s=s.replace('Actual 1 worker × 4 threads','동시 3 dates × 4 threads/date (총 12 threads)')
s=s.replace("$dayPct=100.0*(@($dayUnits | Where-Object {$_.status -eq 'COMPLETE'}).Count)/4","$dayPct=100.0*(@($dayUnits | Where-Object {$_.status -eq 'COMPLETE'}).Count)/5")
(target/name).write_text(s,encoding='utf-8-sig')
(target/'TEMPLATE_ADAPTATION.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=str(source/name),tofile=str(target/name))),encoding='utf-8')
