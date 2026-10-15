"""Serial, process-isolated 233 MB/job R2 first-event and first16 replay."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import threading
from time import perf_counter

import numpy as np
import psutil

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,record
from v42_integration.isolated_unknown import prepare_source,prepare_packet,RAW,no_native
from v42_integration.current_ac_admission import CausalObservations
from v42_integration.rc02_prefix_cache import memory_gate
from v42_integration.rc02_voltage_audit import write_new
from v42_integration.research_presite_literature_actual import run_literature_variant,SCOPE
from v42_integration.research_presite_transfer_literature import validate_literature_spec
from v42_integration.policy import digest

RC=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
CASE='R2_PER_JOB_233MB_B0.25_T0'
DEFAULT=RC/'RC03/ACTUAL_LITERATURE01'
CONTRACT=RC/'RC03/LITERATURE_TRANSFER/CONTRACTS01'/CASE/'RESEARCH_CONTRACT.json'


def material():
    old=read(RC/'RC01/AIDC/REPLAY02/EXECUTED_SOURCE.json')['files']
    paths=('v42_integration/research_presite_actual.py','v42_integration/research_presite_contract.py',
        'v42_integration/rc02_prefix_cache.py','tools/run_v42_research_presite_actual.py',
        'v42_integration/research_presite_literature_actual.py',
        'v42_integration/research_presite_transfer_literature.py','tools/run_v42_literature_presite_actual.py')
    files=old+[record(ROOT/p) for p in paths]
    if any(record(r['path'])!=r for r in files):raise ValueError('LITERATURE_ACTUAL_EXECUTED_SOURCE_DRIFT')
    return old,files


def worker(args):
    root=args.output;case=root/CASE;target=case/('FIRST_EVENT' if args.slots==3 else '')/args.variant
    memory_gate();old,files=material();executed=read(root/'EXECUTED_SOURCE.json')
    if executed['files']!=files:raise ValueError('LITERATURE_WORKER_MATERIAL_SOURCE_DRIFT')
    process=psutil.Process();samples=[];stop=threading.Event();began=perf_counter()
    def monitor():
        while not stop.is_set():
            m=process.memory_info();samples.append(dict(at_seconds=perf_counter(),rss=m.rss,private=getattr(m,'private',None)))
            stop.wait(1)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        with no_native() as attempts:
            source=prepare_packet(prepare_source());begin=source['arguments']['begin']
            source['observations']=CausalObservations.load(RAW,begin=begin,end=begin+16*900)
            packet=read(CONTRACT);spec=packet['spec'];validate_literature_spec(spec)
            common=dict(schema='RC03_SHARED_INITIAL_AND_DATA_ENVIRONMENT_V1',scope=SCOPE,
                historical_PR223_source=source['audit'],Known_commands_sha=digest(source['commands']),
                new_D0_planning_handoff=False,source_strict_result_preserved=True,
                observed_source_bundle_sha=source['observations'].sha,observed_sources=source['observations'].sources,
                MESS_plan_sha=source['mess']['plan_sha'],Original_C1_SHA=source['arguments']['power_model'].authority_sha,
                research_spec=spec,research_science_sha=digest(spec),research_contract_source=record(CONTRACT),
                assumptions_are_source_facts=False,C0_environment_equals_C1=True,C0_only_pending_presite_action_disabled=True,
                Source_metadata_QoS_hard_windows_changed=False,Source7=old,code_files=files,
                Gate_contract='SLOTTED_SETTLED_ORIGINAL_PR223_V1',Native_calls=0,
                candidate_guard_order='COMPATIBILITY_GPU_RACK_DATA_QOS_CURRENT_AC_SENSITIVITY',
                payload_MB_per_job=233,payload_scales_with_GPU=False,legacy_80GB_per_GPU_proxy_used=False,
                original_reference_fixed_MESS_diagnostic_not_D0_joint=True,
                current_AC_asof_and_offline_Fresh_are_different_scopes=True)
            common['release_case_sha']=digest(common);source['release_case_sha']=common['release_case_sha']
            if (case/'COMMON_RUN_INPUTS.json').exists():
                if read(case/'COMMON_RUN_INPUTS.json')!=common:raise ValueError('LITERATURE_WORKER_COMMON_INPUT_DRIFT')
            else:
                write_new(case/'COMMON_RUN_INPUTS.json',common);write_new(case/'EXECUTED_SOURCE.json',executed)
            print('LITERATURE_WORKER_BEGIN',args.variant,args.slots,flush=True)
            result=run_literature_variant(source,args.variant,target,spec=spec,proof_records=files,slots=args.slots)
            if args.slots==3 and result['Unknown_submitted_UIDs']==0:raise ValueError('FIRST_UNKNOWN_NOT_OBSERVED')
            if any(record(r['path'])!=r for r in files):raise ValueError('LITERATURE_MATERIAL_CHANGED_DURING_EXECUTION')
            print('LITERATURE_WORKER_END',args.variant,args.slots,result['Unknown_started_UIDs'],result['PreSite_changed_UIDs'],flush=True)
    finally:
        stop.set();thread.join(timeout=2);m=process.memory_info()
        write_new(root/f'WORKER_{args.variant}_{args.slots}_RESOURCE.json',dict(pid=process.pid,
            wall_seconds=perf_counter()-began,OS_peak_RSS_bytes=getattr(m,'peak_wset',None),
            OS_peak_pagefile_bytes=getattr(m,'peak_pagefile',None),samples=samples,Native_calls=0,
            no_external_worker_interrupted=True,independent_process_releases_all_unreachable_controller_ledgers=True))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--worker',action='store_true');p.add_argument('--variant',choices=('C0','C1'))
    p.add_argument('--slots',type=int,choices=(3,16));args=p.parse_args()
    if args.worker:return worker(args)
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'EXECUTED_SOURCE.json').exists():raise FileExistsError('LITERATURE_ATTEMPT_MUST_NOT_OVERWRITE')
    old,files=material();benchmark=RC/'RC02/VOLTAGE/PREFIX_CACHE_BENCH01/BENCHMARK_RESULT.json'
    if read(benchmark)['status']!='PASS_SAME_INPUT_PHYSICAL_SVR_AND_QUEUE_EQUIVALENCE':
        raise ValueError('ORIGINAL_PREFIX_CACHE_EQUIVALENCE_REQUIRED')
    executed=dict(scope=SCOPE,files=files,Native_calls=0,process_isolation_only=True,
        original_engines_clocks_SVR_and_physical_guards_preserved=True,prefix_benchmark=record(benchmark))
    write_new(args.output/'EXECUTED_SOURCE.json',executed)
    for r in files:
        dest=args.output/'SOURCE'/Path(r['path']).relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(r['path'],dest)
    case=args.output/CASE;case.mkdir(parents=True,exist_ok=False);began=perf_counter()
    for slots in (3,16):
        for variant in ('C0','C1'):
            memory_gate()
            subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker','--output',str(args.output),
                '--variant',variant,'--slots',str(slots)],check=True,cwd=ROOT)
        if slots==3:
            write_new(case/'FIRST_EVENT_GATE.json',dict(status='EXECUTED_LEGITIMATE_QUEUE_OR_START',
                variants={v:read(case/'FIRST_EVENT'/v/'ACTUAL_RESULT.json') for v in ('C0','C1')},
                zero_START_is_not_a_gate_failure=True,Native_calls=0))
    variants={v:read(case/v/'ACTUAL_RESULT.json') for v in ('C0','C1')}
    arrays={}
    for label in variants:
        with np.load(case/label/'ACTUAL_GPU_PQ.npz',allow_pickle=False) as z:arrays[label]={k:z[k].copy() for k in z.files}
    if any(record(r['path'])!=r for r in files):raise ValueError('LITERATURE_SOURCE_CHANGED_AFTER_WORKERS')
    result=dict(status='COMPARISON_COMPLETE',scope=SCOPE,variants=variants,Native_calls=0,new_D0_full_chain=False,
        identical_exogenous_initial_Known_and_fixed_MESS=True,official_Fresh_status='NOT_RUN',
        same_Actual_PQ_arrays=all(np.array_equal(arrays['C0'][k],arrays['C1'][k]) for k in arrays['C0']),
        wall_seconds=perf_counter()-began,independent_serial_processes=4)
    write_new(case/'COMPARISON_COMPLETE.json',result);write_new(args.output/'ALL_RESEARCH_COMPARISONS_COMPLETE.json',result)


if __name__=='__main__':main()
