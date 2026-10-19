import v44_recovery_r045
import v44_week2_restart_r045a as entry
from v44_recovery_r045 import operations as op
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive
from v44.checkpoints import checked,ledger_state
from v44.config import axis
from pathlib import Path
from collections import Counter
import json,urllib.request

with op.bindings(),entry.install():
    permit=op.authority();state=read(op.STATE);status=read(op.CAMPAIGN/'CAMPAIGN_STATUS.json')
    assert state['phase']=='MAIN_PREPARE_SERIAL' and alive(state['lease'])
    assert len(status['workers'])==1 and status['workers'][0]['day']=='2025-05-08' and status['workers'][0]['arm']=='B3'
    for p in permit['plan']:
        r=read(p['original_request']);r.update(case_root=p['case_root'],lease=state['lease'],R045_authorization=record(op.PERMIT),
            sequence_mode='MAIN' if op.seq.key(p) in op.seq.MAIN else 'BASELINE_FULL',sequence_authorization=record(op.seq.AUTH))
        if not p['reuse_prepared']:
            r['sources']=list({x['path']:x for x in r['sources']+op.sources()+[record(op.PERMIT)]}.values());r['source_sha']=digest(r['sources'])
        assert r['axis']==axis(p['day']);op.request_authority(r)
    target=next(j for j in state['jobs'] if op.seq.key(j)==('2025-05-08','B3'));root=Path(target['case_root'])
    stage=root/'A2';r=read(stage/'RESULT.json');checked(stage/'COMPLETED_STAGE_CHECKPOINT.json',read(stage/'request.json'),'COMPLETED')
    assert r['PASS'] and r['FULL_feasible'] and r['independent_Global_LB_validated'] and r['status']=='A2_STRICT_PASS'
    assert r['UB']==r['LB'] and r['certified_gap']==0
    ledger=ledger_state(stage/'NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    admission=read(root/'R044_RECOVERY_ADMISSION.json');assert admission['inherited_A2_Native_seconds']==12.59800386428833
    assert admission['M1_reoptimized'] is False and admission['Native_clock_reset'] is False
    old=read(op.repair.PERMIT);m1=next(x for x in old['evidence'] if x['path'].endswith('M1\\RESULT.json') or x['path'].endswith('M1/RESULT.json'))
    verify([m1]);assert not (root/'M1').exists()
    with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=30) as response:monitor=json.load(response)
    value=dict(PASS=True,UTC=now(),all_28_restart_request_authorities_validated=True,date_and_axis_checks_PASS=True,
        current_phase=state['phase'],state_counts=dict(Counter(j['status'] for j in state['jobs'])),
        live_worker=status['workers'][0],A2_status=r['status'],A2_UB=r['UB'],A2_LB=r['LB'],A2_gap=r['certified_gap'],
        A2_total_Native_seconds=ledger['measured'],A2_inherited_Native_seconds=12.59800386428833,
        A2_new_Native_seconds=ledger['measured']-12.59800386428833,completed_M1_unchanged=m1,
        A2_result=record(stage/'RESULT.json'),A2_checkpoint=record(stage/'COMPLETED_STAGE_CHECKPOINT.json'),
        continuous_repair=record(stage/'OUTPUT/EXACT_CONTINUOUS_REPAIR_CERTIFICATE.json'),
        current_case_stage=read(root/'progress.json')['stage'],official_Actual_Fresh_PASS_claimed=False,
        monitor=dict(status=monitor.get('status'),state=monitor.get('state'),day=monitor.get('day'),arm=monitor.get('arm'),
            Actual_paused_by_user=monitor.get('Actual_paused_by_user'),case_loading_rows=len(monitor.get('case_line_loading',{}).get('rows',[])) if isinstance(monitor.get('case_line_loading'),dict) else None))
    atomic(op.OPS/'R045_LIVE_RESUMPTION_VERIFIED.json',value);print(json.dumps(value,ensure_ascii=False,indent=2))
