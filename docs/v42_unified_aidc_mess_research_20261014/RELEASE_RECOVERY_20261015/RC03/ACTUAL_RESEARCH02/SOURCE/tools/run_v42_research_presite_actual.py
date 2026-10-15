"""Execute RC03 first observed Unknown and 16-slot R1/R2 C0/C1; Native0."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import argparse
import json
import shutil
import sys
import threading

import numpy as np
import psutil

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.isolated_unknown import prepare_source,prepare_packet,RAW,no_native
from v42_integration.current_ac_admission import CausalObservations
from v42_integration.research_presite_actual import run_research_variant,SCOPE
from v42_integration.rc02_prefix_cache import memory_gate
from v42_integration.rc02_voltage_audit import write_new
from v42_integration.actual_validation import read,record
from v42_integration.unified_contract import digest

RC=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
DEFAULT=RC/'RC03/ACTUAL_RESEARCH02'
CASES=('R1_SHARED_READY','R2_P1_B0.25_T900')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT)
    parser.add_argument('--case',choices=CASES,action='append')
    args=parser.parse_args();output=args.output
    output.mkdir(parents=True,exist_ok=True)
    if (output/'EXECUTED_SOURCE.json').exists():raise FileExistsError('RC03_EXECUTED_ATTEMPT_IMMUTABLE')
    benchmark=read(RC/'RC02/VOLTAGE/PREFIX_CACHE_BENCH01/BENCHMARK_RESULT.json')
    if benchmark['status']!='PASS_SAME_INPUT_PHYSICAL_SVR_AND_QUEUE_EQUIVALENCE':
        raise ValueError('RC03_PREFIX_CACHE_MUST_BE_VALIDATED_BEFORE_ADOPTION')
    benchmark_source=read(RC/'RC02/VOLTAGE/PREFIX_CACHE_BENCH01/EXECUTED_BENCHMARK_SOURCE.json')
    for receipt in benchmark_source['material']:
        if any(record(receipt['path'])[k]!=receipt[k] for k in ('sha256','bytes')):
            raise ValueError('RC03_VALIDATED_CACHE_SOURCE_CHANGED')
    old=read(RC/'RC01/AIDC/REPLAY02/EXECUTED_SOURCE.json')['files']
    code=old+[record(ROOT/path) for path in ('v42_integration/research_presite_actual.py',
        'v42_integration/research_presite_contract.py','v42_integration/rc02_prefix_cache.py',
        'tools/run_v42_research_presite_actual.py')]
    if len({str(Path(r['path']).resolve()) for r in code})!=len(code):raise ValueError('RC03_DUPLICATE_MATERIAL_SOURCE')
    for receipt in code:
        if record(receipt['path'])!=receipt:raise ValueError('RC03_MATERIAL_SOURCE_CHANGED')
    executed=dict(scope=SCOPE,files=code,Native_calls=0,prefix_benchmark=record(
        RC/'RC02/VOLTAGE/PREFIX_CACHE_BENCH01/BENCHMARK_RESULT.json'))
    write_new(output/'EXECUTED_SOURCE.json',executed)
    for receipt in code:
        source=Path(receipt['path']);dest=output/'SOURCE'/source.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    process=psutil.Process();stop=threading.Event();samples=[]
    def monitor():
        while not stop.is_set():
            m=process.memory_info();samples.append(dict(time_seconds=perf_counter(),rss=m.rss,
                private=getattr(m,'private',None),peak_rss=getattr(m,'peak_wset',None),
                peak_pagefile=getattr(m,'peak_pagefile',None)))
            stop.wait(1)
    thread=threading.Thread(target=monitor,daemon=True);thread.start();began=perf_counter()
    results={}
    try:
        memory_gate()
        with no_native() as attempts:
            source=prepare_packet(prepare_source());begin=source['arguments']['begin']
            source['observations']=CausalObservations.load(RAW,begin=begin,end=begin+16*900)
            for case in args.case or CASES:
                folder=output/case;folder.mkdir(parents=True,exist_ok=False)
                contract_path=RC/'RC03/PRESITE_CONTRACTS02'/case/'RESEARCH_CONTRACT.json'
                contract=read(contract_path);spec=contract['spec']
                current=dict(source)
                common=dict(schema='RC03_SHARED_INITIAL_AND_DATA_ENVIRONMENT_V1',scope=SCOPE,
                    historical_PR223_source=source['audit'],Known_commands_sha=digest(source['commands']),
                    new_D0_planning_handoff=False,source_strict_result_preserved=True,
                    observed_source_bundle_sha=source['observations'].sha,observed_sources=source['observations'].sources,
                    MESS_plan_sha=source['mess']['plan_sha'],Original_C1_SHA=source['arguments']['power_model'].authority_sha,
                    research_spec=spec,research_science_sha=digest(spec),research_contract_source=record(contract_path),
                    assumptions_are_source_facts=False,C0_environment_equals_C1=True,
                    C0_only_pending_presite_action_disabled=True,Source_metadata_QoS_hard_windows_changed=False,
                    Source7=old,code_files=code,prefix_cache_benchmark=executed['prefix_benchmark'],
                    Gate_contract='SLOTTED_SETTLED_ORIGINAL_PR223_V1',
                    diagnostic_substep_status='PRIOR_FAIL_PRESERVED_NOT_OFFICIAL_VETO',
                    current_AC_asof_and_offline_Fresh_are_different_scopes=True)
                common['release_case_sha']=digest(common);current['release_case_sha']=common['release_case_sha']
                write_new(folder/'COMMON_RUN_INPUTS.json',common);write_new(folder/'EXECUTED_SOURCE.json',executed)
                first={}
                for label in ('C0','C1'):
                    print('RC03_FIRST_EVENT_BEGIN',case,label,flush=True)
                    first[label]=run_research_variant(current,label,folder/'FIRST_EVENT'/label,spec=spec,proof_records=code,slots=3)
                    if first[label]['Unknown_submitted_UIDs']<=0:raise ValueError('RC03_FIRST_OBSERVED_UNKNOWN_MISSING')
                write_new(folder/'FIRST_EVENT_GATE.json',dict(status='EXECUTED_LEGITIMATE_QUEUE_OR_START',variants=first,
                    zero_START_is_not_a_gate_failure=True,Native_calls=0))
                variants={}
                for label in ('C0','C1'):
                    print('RC03_FULL16_BEGIN',case,label,flush=True)
                    variants[label]=run_research_variant(current,label,folder/label,spec=spec,proof_records=code,slots=16)
                    print('RC03_FULL16_END',case,label,variants[label]['Unknown_started_UIDs'],
                        variants[label]['PreSite_changed_UIDs'],variants[label]['controller_max_seconds'],flush=True)
                arrays={}
                for label in variants:
                    with np.load(folder/label/'ACTUAL_GPU_PQ.npz',allow_pickle=False) as z:
                        arrays[label]={k:z[k].copy() for k in z.files}
                results[case]=dict(status='COMPARISON_COMPLETE',scope=SCOPE,case_sha=common['release_case_sha'],
                    research_science_sha=digest(spec),variants=variants,
                    new_D0_full_chain=False,official_Fresh_status='NOT_RUN',Native_calls=0,
                    identical_exogenous_initial_Known_and_fixed_MESS=True,
                    same_Actual_PQ_arrays=all(np.array_equal(arrays['C0'][k],arrays['C1'][k]) for k in arrays['C0']))
                write_new(folder/'COMPARISON_COMPLETE.json',results[case])
        for receipt in code:
            if record(receipt['path'])!=receipt:raise ValueError('RC03_MATERIAL_SOURCE_CHANGED_DURING_REPLAY')
        write_new(output/'ALL_RESEARCH_COMPARISONS_COMPLETE.json',dict(results=results,Native_calls=0,blocked_native_attempts=attempts,
            total_wall_seconds=perf_counter()-began,Source7_byte_immutable=True,official_Fresh_status='NOT_RUN',
            Source_strict_R1_R2_are_separate_cases=True))
    finally:
        stop.set();thread.join(timeout=2)
        m=process.memory_info()
        write_new(output/'RUNNER_RESOURCE_RECEIPT.json',dict(pid=process.pid,total_wall_seconds=perf_counter()-began,
            OS_peak_RSS_bytes=getattr(m,'peak_wset',None),OS_peak_pagefile_bytes=getattr(m,'peak_pagefile',None),
            sampled_private_peak_bytes=max((r['private'] for r in samples if r['private'] is not None),default=None),
            sampled_private_peak_is_lower_bound=True,sampling_interval_seconds=1,samples=samples,
            no_external_process_interrupted=True,Native_calls=0))


if __name__=='__main__':main()
