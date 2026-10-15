"""Table V prepare/serial arm command. No automatic retry or overwrite."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.table_v_run import DEFAULT,prepare,run_arm

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('operation',choices=['prepare','stop','B0','B1','B2','B3'])
    p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--attempt',default=None)
    p.add_argument('--day',default='2025-05-01')
    p.add_argument('--actual-slots',type=int,choices=[16,96],default=96)
    p.add_argument('--launch-plan',type=Path)
    p.add_argument('--launch-gate',type=Path)
    p.add_argument('--carry-forward-native-ledger',type=Path,action='append',default=[])
    p.add_argument('--planning-authorization',type=Path)
    p.add_argument('--k48-authorization',type=Path)
    p.add_argument('--stop-reason',default='EXPLICIT_USER_CAMPAIGN_STOP')
    a=p.parse_args()
    if a.operation=='stop':
        from v42_integration.table_v_control import stop_request
        result=stop_request(a.output,reason=a.stop_reason)
    elif a.operation=='prepare':
        docs=None
        if a.planning_authorization and a.k48_authorization:
            docs={name:json.loads(path.read_text(encoding='utf8')) for name,path in
                  [('PLANNING',a.planning_authorization),('K48',a.k48_authorization)]}
        result=prepare(a.output,day=a.day,carry_forward_native_ledgers=a.carry_forward_native_ledger,authorizations=docs)
    else:
        authority=None
        if a.launch_plan and a.launch_gate:
            authority=dict(plan=json.loads(a.launch_plan.read_text(encoding='utf8')),
                gate=json.loads(a.launch_gate.read_text(encoding='utf8')))
        result=run_arm(a.operation,a.output,attempt=a.attempt,actual_slots=a.actual_slots,launch_authority=authority)
    print('PREPARED' if a.operation=='prepare' else 'STOP_REQUESTED' if a.operation=='stop' else {k:result.get(k) for k in ('arm','status','failed_stage','error','wall_seconds')},flush=True)
