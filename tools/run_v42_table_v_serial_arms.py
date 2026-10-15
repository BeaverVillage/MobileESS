"""Run explicitly requested arms through the common production launch gate."""
import argparse
import gc
import json
from pathlib import Path
import sys
from time import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def run(output,plan,gate,arms):
    from v42_integration.m_engine import _write,file_record
    from v42_integration.table_v_campaign import _launch_gate
    from v42_integration.table_v_control import require_running
    from v42_integration.table_v_memory import memory_sample
    from v42_integration.table_v_run import run_arm,verify_adapters
    if not arms or len(arms)!=len(set(arms)) or any(a not in ('B0','B1','B2','B3') for a in arms):
        raise ValueError('EXPLICIT_UNIQUE_ORIGINAL_ARMS_REQUIRED')
    output=Path(output);report_path=output/'SERIAL_ARM_RUN.json'
    require_running(output);verify_adapters(output);_launch_gate(plan,gate)
    initial=dict(schema='TABLE_V_SERIAL_ARM_RUN_V1',arms=arms,status='RUNNING',results=[],
        started_epoch_seconds=time(),Worker=1,Threads=1,P2_calls=0,R2='HOLD',
        plan=plan,gate=gate,runner_source=file_record(__file__),resource_before=memory_sample())
    with report_path.open('x',encoding='utf8') as stream:json.dump(initial,stream,indent=2)
    report=initial
    try:
        for arm in arms:
            require_running(output)
            # Recheck current release/authority at every safe arm boundary.
            _launch_gate(plan,gate);verify_adapters(output)
            report['active_arm']=arm;_write(report_path,report)
            try:
                outcome=run_arm(arm,output,actual_slots=plan.get('actual_slots',96),
                    launch_authority=dict(plan=plan,gate=gate))
                result=dict(arm=arm,status=outcome['status'],outcome=file_record(output/arm/'ARM_OUTCOME.json'))
            except Exception as error:
                result=dict(arm=arm,status='FAILED_CLOSED',error=type(error).__name__+': '+str(error))
            report['results'].append(result);gc.collect();report['resource_current']=memory_sample()
            _write(report_path,report)
            print(json.dumps(result),flush=True)
        report['status']='COMPLETE_RECORDED_ARM_STATUSES'
    except BaseException as error:
        report['status']='ABORTED_AT_SAFE_ARM_BOUNDARY'
        report['error']=type(error).__name__+': '+str(error)
        raise
    finally:
        report['active_arm']=None;report['finished_epoch_seconds']=time()
        report['resource_after']=memory_sample();_write(report_path,report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--launch-plan',type=Path,required=True)
    parser.add_argument('--launch-gate',type=Path,required=True)
    parser.add_argument('--arms',nargs='+',choices=['B0','B1','B2','B3'],required=True)
    args=parser.parse_args()
    run(args.output,json.loads(args.launch_plan.read_text(encoding='utf8')),
        json.loads(args.launch_gate.read_text(encoding='utf8')),args.arms)
