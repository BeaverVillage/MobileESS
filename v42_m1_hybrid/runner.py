"""One pre-registered bounded hybrid pilot; existing results are read-only."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter
import json
import re
import numpy as np
from v42_unified.audit import ROOT,git,write
from v42_unified.storage import sha
from .case import BASE_HEAD,CASE_SHA,REPORTS,RUNTIME,load_case,verify_baseline_files
from .ledger import HybridLedger
from . import blocks,pricing,ub,dw,verify


def protection():
    files=verify_baseline_files()
    for name in ('V42_CONFIG.json','Start-V42.ps1','v42_native/mess.py','v42_bootstrap/m1.py'):
        files[name]=sha(ROOT/name)
    for path in (ROOT/'v42_unified').glob('*.py'):files[path.relative_to(ROOT).as_posix()]=sha(path)
    old=ROOT/'runtime/v42_m1_joint_gap_research'
    for folder in (old/'joint_gap_20261008',old/'joint_gap_20261008_final_strict_admission_view'):
        ledger=json.loads((folder/'NATIVE_RUNTIME_LEDGER.json').read_text())
        if ledger['inflight'] is not None:raise ValueError('PREVIOUS_RUN_NOT_COMPLETED')
        for path in folder.iterdir():
            if path.is_file() and path.suffix in ('.json','.npz','.log'):
                files[path.relative_to(ROOT).as_posix()]=sha(path)
    return files


def check_protection(files):
    # README and attributes may receive only documented research links/byte rules.
    for name,expected in files.items():
        if name in ('README.md','.gitattributes'):continue
        if sha(ROOT/name)!=expected:raise ValueError('HISTORICAL_SOURCE_OR_LEDGER_CHANGED:'+name)
    return dict(PASS=True,protected_files=len(files)-2,historical_ledger_writes=0,
        historical_source_and_proof_writes=0,production_backend_promoted=False)


def plan():
    return dict(case_sha=CASE_SHA,baseline_completed_HEAD=BASE_HEAD,
        global_research_targets={'A1':.005,'A2':.005,'M1':.05,'M2':.05},
        inner_native_MIPGap=.005,scientific_tolerances=1e-8,Threads=1,
        UB={'A':400,'B':400,'C':400},
        first_pricing={'units':4,'MILP_seconds_each':120,'LP_seconds_each':90},
        RMP={'calls':1,'seconds':30},
        optional_RMP_price_LP={'units':4,'seconds_each':60,'condition':'Finite RMP original-row Pi available and pre-call Wall<4800'},
        maximum_requested_Native_seconds=2310,pilot_accounting_ceiling=2700,
        original_stage_Native_ceiling=5400,practical_Wall_ceiling=5400,speed_target_Wall=3600,
        branch_and_price=False,automatic_production_execution=False,
        no_arc_deletion=True,no_SOC_discretization=True,no_memory_limits=True,
        no_historical_budget_reset=True,retry_or_budget_transfer_loop=False,
        May12_numbers_transferred=False,pricing_TIME_LIMIT_not_closure=True,
        RMP_native_objective_not_Global_LB=True,M1_ACCEPTED=False,P2_certificate=None)


def preflight():
    start=perf_counter();protected=protection();case=load_case()
    phase0=verify.phase0(case);decomp=blocks.build_blocks(case)
    independent=verify.verify_decomposition(case,decomp)
    write(REPORTS/'PHASE0_TARGET_AUDIT.json',phase0)
    receipt=dict(PASS=True,case_sha=case.case_sha,plan=plan(),phase0=phase0,
        independent_original_domain_partition=independent,
        original_preservation=check_protection(protected),Native_optimize_calls=0,
        wall_seconds=perf_counter()-start)
    write(REPORTS/'PREFLIGHT_ZERO_NATIVE.json',receipt)
    return receipt


def execute(run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):raise ValueError('SAFE_NEW_RUN_ID_REQUIRED')
    if git('branch','--show-current').decode().strip()!='v42':raise ValueError('V42_BRANCH_REQUIRED')
    if git('rev-parse','HEAD').decode().strip()!=BASE_HEAD:raise ValueError('EXPLICIT_COMPLETED_BASE_HEAD_REQUIRED')
    path=RUNTIME/run_id;path.mkdir(parents=True,exist_ok=False)
    begin=perf_counter()
    protected=protection();write(path/'BASELINE_PROTECTION.json',protected)
    write(path/'PREREGISTRATION.json',dict(plan(),run_id=run_id,
        started_utc=datetime.now(timezone.utc).isoformat()))
    source_hashes={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'v42_m1_hybrid').glob('*.py')}
    write(path/'EXECUTED_SOURCE_HASHES.json',source_hashes)
    ledger=HybridLedger(path/'NATIVE_RUNTIME_LEDGER.json',CASE_SHA,started=begin)
    errors=[];result=dict(case_sha=CASE_SHA,run_id=run_id,run_path=str(path),errors=errors)
    with ledger.cost('validated_input_reuse','C3A_CSR_STATIC_GRAPH_STRICT_INCUMBENT'):
        case=load_case()
    with ledger.cost('independent_initial_verification','PHASE0_EXACT_TARGETS_AND_SOURCE_IDENTITY'):
        result['phase0']=verify.phase0(case)
    write(REPORTS/'PHASE0_TARGET_AUDIT.json',result['phase0'])
    with ledger.cost('block_model_preparation','ALL_ORIGINAL_ROWS_AND_TYPES'):
        decomp=blocks.build_blocks(case)
        result['decomposition']=blocks.persist_decomposition(case,decomp,path/'decomposition')
        result['independent_partition']=verify.verify_decomposition(case,decomp)
    with ledger.cost('exact_price_initialization','SIGNED_MULTIROW_GRID_COUPLING_VECTOR'):
        source=json.loads((ROOT/'docs/v42_m1_joint_gap_research/artifacts/C3A_REPAIRED_RATIONAL_DUAL.json').read_text())
        prices=pricing.make_prices(case,decomp,source)
    try:
        result['UB']=ub.run(case,ledger,path/'UB',seconds_each=400.)
        point=result['UB'].pop('point')
    except Exception as exc:
        errors.append(dict(phase='UB',error=type(exc).__name__+': '+str(exc)))
        point=np.asarray(case.point).copy()
        result['UB']=dict(status='FAILED_PRESERVED_STRICT_BASELINE',best_validated_global_UB=.6063186498423855)
    np.savez_compressed(path/'FINAL_STRICT_UB_POINT.npz',point=point)
    with ledger.cost('trajectory_pricing_and_certificates','INITIAL_FOUR_FULL96_BLOCKS',track='PRICING'):
        result['PRICING']=pricing.run_pricing(case,decomp,prices,ledger,path/'pricing_initial',seconds_per_unit=120,lp_seconds=90)
    try:
        result['RMP']=dw.run(case,decomp,result['PRICING']['columns'],ledger,path/'rmp',seconds=30)
    except Exception as exc:
        errors.append(dict(phase='RMP',error=type(exc).__name__+': '+str(exc)))
        result['RMP']=dict(status='RMP_FAILED_NO_GLOBAL_OBJECTIVE_AUTHORITY',full_original_dual=None)
    full=result['RMP'].get('full_original_dual')
    if full is not None and perf_counter()-begin<4800:
        with ledger.cost('exact_price_initialization','RMP_GRID_PRICE_VECTOR'):
            update=pricing.make_prices(case,decomp,full)
        with ledger.cost('trajectory_pricing_and_certificates','RMP_FOUR_FULL96_LP_PRICES',track='PRICING'):
            result['RMP_PRICING']=pricing.run_lp_prices(case,decomp,update,ledger,path/'pricing_rmp',lp_seconds=60)
    else:result['RMP_PRICING']=dict(status='NOT_RUN_NO_FINITE_RMP_PI_OR_WALL_BOUNDARY')
    result['ledger']=ledger.persist()
    result['original_preservation']=check_protection(protected)
    for name,expected in source_hashes.items():
        if sha(ROOT/name)!=expected:raise ValueError('EXECUTED_HYBRID_SOURCE_CHANGED:'+name)
    write(path/'NATIVE_PHASE_RESULTS.json',result)
    print('HYBRID_NATIVE_PHASE_FINISHED',ledger.used(),str(path),flush=True)
    return path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    parser.add_argument('--run-id',default='hybrid_may01_20261008_5pct_pilot01');args=parser.parse_args()
    if args.execute:execute(args.run_id)
    else:
        receipt=preflight();print('HYBRID_PREFLIGHT_PASS',receipt['case_sha'],receipt['wall_seconds'])


if __name__=='__main__':main()
