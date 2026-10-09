from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import psutil
from v42_b2_start_recovery_v13 import coordinator as co, monitor as previous
from v42_campaign_monitor import monitor as display
from v42_may_campaign_native90.a_routing import rebound
from v42_pr134_b1.common import read, same_process
from v42_may_campaign_native90.common import exclusive_lock


def optional(path):
    return read(path) if Path(path).is_file() else {}


def view(root):
    root=Path(root);value=previous.view(root)
    gate=optional(root/'B2_BUILD_FULL_VALIDATION_V13.json')
    status=optional(root/'CAMPAIGN_STATUS.json')
    active=gate.get('active') or {}
    heartbeat=optional(Path(active['result']).parent/'HEARTBEAT.json') if active else {}
    progress=optional(Path(active['result']).parent/'progress.json') if active else {}
    rows=[]
    for day in ('2025-05-01','2025-05-23'):
        for mode in ('BASELINE','OPTIMIZED'):
            entry=gate.get('builds',{}).get(day+'/'+mode)
            running=active.get('day')==day and active.get('mode')==mode
            summary=(entry or {}).get('summary',{})
            rows.append(dict(day=day,mode=mode,status='PASS' if entry else 'RUNNING' if running else 'PENDING',
                seconds=summary.get('total_preparation_seconds'),fingerprint=summary.get('fingerprint'),
                original_transport_PASS=(summary.get('original_transport_verification') or {}).get('PASS'),
                inherited_reference=bool((entry or {}).get('inherited_original_reference'))))
    elapsed=max(0.,datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(active['started_UTC']).timestamp()) if active else None
    resource={}
    if active and same_process(active.get('process',{})):
        try:
            p=psutil.Process(active['process']['PID']);cpu=p.cpu_times()
            resource=dict(RSS_GB=p.memory_info().rss/2**30,CPU_seconds=cpu.user+cpu.system)
        except psutil.Error:pass
    value['B2_validation_detail']=dict(status=gate.get('status'),PASS=gate.get('PASS'),error=gate.get('error'),
        completed=sum(r['status']=='PASS' for r in rows),total=4,rows=rows,comparisons=gate.get('comparisons',{}),
        active=dict(day=active.get('day'),mode=active.get('mode'),PID=active.get('process',{}).get('PID'),
            alive=same_process(active.get('process',{})),phase=progress.get('phase',heartbeat.get('phase')),
            elapsed_seconds=elapsed,heartbeat_UTC=heartbeat.get('UTC'),resource=resource),
        inherited_verification=status.get('inherited_result_verification'),Native_calls=0)
    pending=[r['day'] for r in co.read(root/'CHECKPOINT_V13.json')['dates'].values() if r['arm']=='B2' and r['status']=='PENDING']
    value['workers']=[w for w in value['workers'] if w['arm']=='B2']
    for slot in value['worker_slots']:
        if not slot.get('day'):
            index=slot['worker_slot']-1
            slot.update(day=pending[index] if index<len(pending) else None,display_waiting=True,
                phase='FULL_MODEL_VALIDATION_WAIT' if not gate.get('PASS') else 'DISPATCH_WAIT',
                target_gap=.03,Native_Runtime_seconds=0,Native_calls=0,native_remaining_seconds=5400,
                wall_seconds=0,resource={},progress={},global_gap_display=dict(reason='B2 유효 해·독립 하한 대기'))
    value.update(display_version='B2_DETAIL_MONITOR_V14',read_only=True,current_phase='B2')
    return value


def run(root):
    with exclusive_lock(Path(root)/'MONITOR_GAP_V8.lock'):
        proxy=SimpleNamespace(runtime_path=co.runtime_path,load_manifest=co.load_manifest)
        return rebound(display.run,dict(display.run.__globals__,original=proxy,view=view,__file__=__file__))(root)
