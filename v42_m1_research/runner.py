"""Explicit bounded two-track M1 research; production defaults remain unchanged."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from time import perf_counter
import traceback
import numpy as np
from v42_unified.audit import ROOT,write,git
from v42_unified.storage import setup,sha
from .case import load_case,REPORTS
from .ledger import ResearchLedger


def snapshot(track):
    r={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'v42_m1_research').glob('*.py')}
    write(REPORTS/(track+'_EXECUTED_SOURCE_HASHES.json'),r)


def run(execute=False,run_id='joint_gap_20261008'):
    started=perf_counter();setup()
    c=load_case()
    from .check_ub import validate_candidate
    baseline=validate_candidate(c,c.point)
    write(REPORTS/'UB_BASELINE_INTEGER_PHYSICAL_REPLAY.json',baseline)
    if not baseline['PASS']:raise ValueError('FULL_ORIGINAL_BEST_INTEGER_REPLAY_REQUIRED')
    if not execute:
        print('RESEARCH_PREFLIGHT_PASS Native optimize=0',c.case_sha,baseline['objective']);return
    output=(ROOT/'runtime/v42_m1_joint_gap_research'/run_id).resolve()
    if not output.is_relative_to((ROOT/'runtime/v42_m1_joint_gap_research').resolve()):raise ValueError('NEW_D_RUN_ID_REQUIRED')
    output.mkdir(parents=True,exist_ok=False)
    write(output/'EXPLICIT_RESEARCH_ONCE.json',dict(case_sha=c.case_sha,
        user_authorized_May01_research=True,production_default_optimize_allowed=False,
        starting_v42_HEAD=git('rev-parse','HEAD').decode().strip(),started_utc=datetime.now(timezone.utc).isoformat()))
    ledger=ResearchLedger(output/'NATIVE_RUNTIME_LEDGER.json',c.case_sha)
    ledger.started=started;ledger.persist()
    result=dict(case_sha=c.case_sha,baseline=baseline['objective'],run_path=str(output),errors=[])
    # Sequential models avoid competition with each other and preserve existing
    # external processes. Validation runs after solver return, outside Runtime.
    from . import ub
    snapshot('UB')
    try:
        result['UB']=ub.run(c,ledger,REPORTS)
        np.savez_compressed(output/'FINAL_VALID_UB_POINT.npz',point=result['UB'].pop('point'))
        write(output/'UB_TRACK_RESULT.json',result['UB'])
        print('UB_TRACK_FINISHED',result['UB']['best_validated_global_UB'],flush=True)
    except BaseException as exc:
        result['errors'].append(dict(track='UB',error=type(exc).__name__+':'+str(exc),traceback=traceback.format_exc()))
        write(output/'UB_TRACK_FAILURE.json',result['errors'][-1]);print('UB_TRACK_FAILED',str(exc),flush=True)
    ledger.persist();write(REPORTS/'NATIVE_RUNTIME_LEDGER.json',ledger.persist())
    from . import lb
    snapshot('LB')
    try:
        with ledger.cost('model_preparation_and_validation','MULTITIME_R_PREPARATION','LB'):
            result['LB'],candidate,dual=lb.run_pilot(c,ledger,lp_seconds=300,mip_seconds=1200)
        if dual is not None:np.savez_compressed(output/'MULTITIME_R_DUAL.npz',dual=dual)
        if candidate is not None:
            with ledger.cost('validation','R_POINT_ORIGINAL_FULL_REPLAY','LB'):
                r=validate_candidate(c,candidate)
            write(output/'MULTITIME_R_POINT_ORIGINAL_REPLAY.json',r)
        write(output/'LB_TRACK_RESULT.json',result['LB'])
        print('LB_R_TRACK_FINISHED',result['LB']['independently_certified_R_LB'],flush=True)
        if hasattr(lb,'run_joint_disjunction'):
            result['JOINT_DISJUNCTION']=lb.run_joint_disjunction(c,ledger,output,leaf_seconds=300)
            write(output/'JOINT_DISJUNCTION_RESULT.json',result['JOINT_DISJUNCTION'])
            print('LB_JOINT_DISJUNCTION_FINISHED',flush=True)
        else:
            result['JOINT_DISJUNCTION']=dict(status='NOT_PROVEN',reason='No independently verified joint disjunction implementation')
    except BaseException as exc:
        result['errors'].append(dict(track='LB',error=type(exc).__name__+':'+str(exc),traceback=traceback.format_exc()))
        write(output/'LB_TRACK_FAILURE.json',result['errors'][-1]);print('LB_TRACK_FAILED',str(exc),flush=True)
    result['ledger']=ledger.persist()
    write(REPORTS/'NATIVE_RUNTIME_LEDGER.json',result['ledger'])
    write(output/'RESEARCH_TRACK_RESULTS.json',result)
    print('RESEARCH_NATIVE_FINISHED',result['ledger']['Native_Runtime_sum'],flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',help='Explicit new Native M1 research, within one combined5400sledger')
    parser.add_argument('--run-id',default='joint_gap_20261008')
    args=parser.parse_args();run(args.execute,args.run_id)


if __name__=='__main__':main()
