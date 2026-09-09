"""Isolated renderer regression. No solver, worker or scientific output mutation."""
import json, os, subprocess, time, hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
fixture=HERE/'fixture';run=fixture/'frozen_artifacts/v41r4_may/loop_wall_v4';actual=fixture/'actual_v2'
shell='C:/Users/kjw39/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'
script=ROOT/'dayahead/tools/monitor_v41r1_may_live.ps1'
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding='utf-8')
units={}
for n in range(1,32):
    d=f'2025-05-{n:02}'
    for p in ('B0','B1','B2','B3'):
        units[d+'|'+p]=dict(day=d,policy=p,status='COMPLETE',phase='complete',worker_pid=None)
        save(run/d/p/'actual/ACTUAL_RECEIPT.json',dict(status='COMPLETE'))
save(run/'campaign_state.json',dict(units=units))
active=[]
for d,p,phase in [('2025-05-01','B2','B2_ETA95_QSAFE_AC'),('2025-05-02','B3','B3_ETA95_QSAFE_AC'),('2025-05-22','B3','B3_DA'),('2025-05-23','B2','B2_DA')]:
    active.append(dict(day=d,policy=p,phase=phase,worker_pid=os.getpid(),started_at=time.time()-120))
state=dict(status='RUNNING',supervisor_pid=os.getpid(),updated_at=time.time(),active=active,errors=[])
save(run/'campaign_progress.json',state);save(actual/'DISPATCHER_STATE.json',state)
save(run/'audit/ACTUAL_EXECUTION_METHOD_CURRENT.json',dict(namespace=str(actual),dispatcher_state=str(actual/'DISPATCHER_STATE.json'),method_SHA='new-sha'))
save(actual/'replays/2025-05-01/B2/ETA95_QSAFE_ACTUAL/PROGRESS.json',dict(slots_complete=6,interventions=1,infeasible=0))
(actual/'replays/2025-05-02/B3/ETA95_QSAFE_ACTUAL').mkdir(parents=True,exist_ok=True)
save(actual/'replays/2025-05-02/B2/CANDIDATE_RECEIPT.json',dict(status='COMPLETE',method_SHA='new-sha'))
save(actual/'replays/2025-05-02/B2/COMPLETE.json',dict(ETA95_QSAFE_ACTUAL=dict(Vmax_pu=1.041234,rho_max_AC=.512345,physical_violation=False),ROBUST_Q_ONLY_UNRESOLVED_slots=0))
save(run/'audit/2025-05-02/B2_ACCEPTANCE.json',dict(Actual_physical_outcome='WITH_VIOLATIONS',Actual_summary=dict(Vmax_pu=1.09,rho_max_AC=.999999)))
save(run/'2025-05-22/B3/dayahead/optimization/stages/A1_INPUT.json',{})
save(run/'2025-05-22/B3/dayahead/A1/F_AND_O_LIVE.json',dict(stage='PRIMARY_MIN_RHO',iteration=3,budget_used_seconds=600,incumbent=[.7,100,0,0,1]))
frames=[]
for day in ('2025-05-02','2025-05-01'):
    proc=subprocess.run([shell,'-NoLogo','-NoProfile','-File',str(script),'-Repo',str(fixture),'-Once','-Day',day],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    assert proc.returncode==0,proc.stderr.decode(errors='replace')
    frame=(run/'audit/MONITOR_LAST_FRAME.txt').read_text(encoding='utf-8');frames.append(frame)
    assert '상태를 읽지 못했습니다' not in frame,frame
    assert '1/124 정책 완료' in frame and 'A1 F&O P1' in frame
    assert '05-23      B2    M1' in frame and '6/96 완료' in frame
    assert 'QSAFE 슬롯 0 평가' in frame and '3      대기' not in frame and '4      대기' not in frame
    assert '1.090000' not in frame
assert '1.041234 / 0.512345' in frames[0] and 'V2 PASS' in frames[0]
assert 'V2 실행 중' in frames[1] and '최종값 감사 대기' in frames[1]
save(HERE/'MONITOR_REGRESSION.json',dict(status='PASS',checks=['historical completion cannot hide V2 workers','new Actual metrics only','pending V2 never shows historical metrics','A1 and M1 phase normalization','running Actual date policy slot displayed','pre-first-slot search displayed','V2-only completion count'],optimizer_calls=0,scientific_outputs_changed=0,monitor_sha256=hashlib.sha256(script.read_bytes()).hexdigest()))
print('V2_MONITOR_REGRESSION_PASS')
