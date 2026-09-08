"""Render the existing monitor against isolated stage receipts; no solver runs."""
from fast_prepare import *
from v41r4_search_runtime import MAY_RUN,MAY_OUT
import os,time,subprocess
from dayahead.paper_analysis.storage import write_json


def main():
    fixture=ROOT/'frozen_artifacts/mf_ui_test'
    runtime=fixture/'frozen_artifacts/v41r4_may/search_time_v3'
    out=runtime/'audit';out.mkdir(parents=True,exist_ok=True)
    cases=[('2025-05-01','A1'),('2025-05-02','MF'),('2025-05-03','MF_COMPLETE'),('2025-05-04','FRESH')]
    units={}
    for day,phase in cases:
        units[day+'|B3']=dict(day=day,policy='B3',status='RUNNING',phase='dayahead',worker_pid=os.getpid())
        folder=runtime/day/'B3/dayahead';stages=folder/'optimization/stages'
        write_json(stages/'A1_INPUT.json',{})
        write_json(folder/'A1/F_AND_O_LIVE.json',dict(stage='PRIMARY_MIN_RHO',iteration=3,
            budget_used_seconds=600,incumbent=[.7,100.,0.,0.,1.]))
        if phase in ('MF','MF_COMPLETE','FRESH'):write_json(stages/'MF_INPUT_CERTIFICATE.json',{})
        if phase=='MF_COMPLETE':
            write_json(stages/'MF_OUTPUT.json',{})
            write_json(stages/'MF_CANDIDATE_OUTPUT.json',dict(info=dict(solver=dict(termination='SHARED_BUDGET_RETAINED_VERIFIED_M1'))))
        if phase=='FRESH':write_json(folder/'FROZEN_JOINT_DECISION.json',{})
    write_json(runtime/'campaign_state.json',dict(units=units))
    write_json(runtime/'campaign_progress.json',dict(status='RUNNING',supervisor_pid=os.getpid(),updated_at=time.time()))
    shell=Path('C:/Users/kjw39/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe')
    script=ROOT/'dayahead/tools/monitor_v41r1_may_live.ps1'
    r=subprocess.run([str(shell),'-NoLogo','-NoProfile','-File',str(script),'-Repo',str(fixture),'-Once'],
        capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    assert r.returncode==0,(r.returncode,r.stderr)
    frame=(out/'MONITOR_LAST_FRAME.txt').read_text(encoding='utf-8')
    assert '상태를 읽지 못했습니다' not in frame,frame
    lines={day:next(line for line in frame.splitlines() if day[5:] in line and 'B3' in line) for day,_ in cases}
    assert 'A1 F&O P1' in lines['2025-05-01']
    assert 'MF' in lines['2025-05-02'] and 'F&O' not in lines['2025-05-02']
    assert 'MF 완료' in lines['2025-05-03'] and '예산 부족' in lines['2025-05-03'] and 'F&O' not in lines['2025-05-03']
    assert 'Fresh' in lines['2025-05-04'] and 'F&O' not in lines['2025-05-04']
    assert 'B1 재사용(A0) → M1 → A1 → MF → Fresh → Actual' in frame
    write_json(MAY_OUT/'regression/MF_MONITOR_REGRESSION.json',dict(status='PASS',cases=lines,
        stale_A1_cannot_hide_MF=True,budget_fallback_explicit=True,complete_chain_visible=True,
        test_frame=record(out/'MONITOR_LAST_FRAME.txt'),monitor=record(script),campaign_writes=0,optimizer_calls=0))
    print('MF_MONITOR_FOUR_STAGE_RENDER_PASS')

if __name__=='__main__':main()
