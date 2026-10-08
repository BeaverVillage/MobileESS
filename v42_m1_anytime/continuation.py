import argparse
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter
import hashlib
import re
import subprocess
import numpy as np
from v42_unified.audit import git
from v42_unified.storage import sha
from v42_m1_hybrid.final_verify import load_case_read_only,_strict_ub
from v42_m1_hybrid.blocks import build_blocks
from v42_m1_hybrid.verify import phase0,verify_decomposition,verify_rmp_pricing_lower_bounds
from v42_m1_research.check_lb import check_rational_dual_certificate
from .core import ROOT,BASE,CASE,REPORTS,RUNTIME,Ledger,Frontier,write,read,utc,schedule_choice
from . import algorithms as alg

OLD=ROOT/'docs/v42_m1_fast_hybrid_20261008'

def protection():
    prior=read(OLD/'SHA256_MANIFEST.json');files=dict(prior['files'])
    files[(OLD/'SHA256_MANIFEST.json').relative_to(ROOT).as_posix()]=sha(OLD/'SHA256_MANIFEST.json')
    # Protect all previously tracked scientific source and evidence, not just
    # the immediately preceding hybrid manifest.
    for name in git('ls-files').decode().splitlines():
        if name.startswith(('v42_','docs/v42_','tests/test_v42','contract_tests/')) or name in ('V42_CONFIG.json','Start-V42.ps1'):
            files[name]=sha(ROOT/name)
    for name,digest in prior['files'].items():
        if sha(ROOT/name)!=digest:raise ValueError('PRIOR_COMPLETED_MANIFEST_DRIFT:'+name)
    for folder in ('runtime/v42_m1_joint_gap_research','runtime/v42_m1_fast_hybrid'):
        for p in (ROOT/folder).rglob('NATIVE_RUNTIME_LEDGER.json'):
            d=read(p)
            if d.get('inflight') is not None:raise ValueError('EXISTING_NATIVE_STILL_RUNNING_DO_NOT_CONTROL')
            files[p.relative_to(ROOT).as_posix()]=sha(p)
    return files

def check_protection(files):
    for name,digest in files.items():
        if name in ('README.md','.gitattributes'):continue
        if sha(ROOT/name)!=digest:raise ValueError('HISTORICAL_SCIENTIFIC_FILE_CHANGED:'+name)
    return dict(PASS=True,protected_files=len(files),historical_native_ledger_writes=0,production_promoted=False)

def baseline(path):
    started=perf_counter();files=protection();case=load_case_read_only()
    original=phase0(case);decomp=build_blocks(case);partition=verify_decomposition(case,decomp)
    source=read(OLD/'INDEPENDENT_FINAL_VERIFICATION.json')
    if source['case_sha']!=CASE or not source['PASS']:raise ValueError('COMPLETED_BASELINE_CERTIFICATE_REQUIRED')
    packet=OLD/'artifacts/FINAL_STRICT_UB_POINT.npz'
    with np.load(packet,allow_pickle=False) as z:point=z['point'].copy()
    strict=_strict_ub(case,packet,{});strict.update(case_sha=CASE)
    dualpath=OLD/'hybrid_may01_20261008_5pct_pilot01_INITIAL_INDEPENDENT_ORIGINAL_GLOBAL_DUAL_EXACT.json'
    dual=read(dualpath)
    cert=check_rational_dual_certificate(case.A,case.d,dual,case_sha=CASE)
    if F(cert['exact_bound'])!=F(source['final_exact_LB']) or F(strict['exact_Global_UB'])!=F(source['final_exact_UB']):raise ValueError('WARM_START_BOUND_REPLAY_MISMATCH')
    lbpath=path/'BASELINE_EXACT_LB_CERTIFICATE.json';ubpath=path/'BASELINE_STRICT_UB_REPLAY.json'
    write(lbpath,dict(cert,dual_source=str(dualpath),dual_sha256=sha(dualpath),completed_source_HEAD=BASE,independently_recomputed=True))
    write(ubpath,strict);write(path/'BASELINE_PROTECTION.json',files)
    identity=dict(PASS=True,case_sha=CASE,baseline_completed_HEAD=BASE,day='2025-05-01',jobs=1499,
        vehicles=4,sites=len(case.graph[0]),slots=96,objective='min rho_max',source_identity=case.identity,
        independent_original_domain_partition=partition,warm_start_exact_LB=source['final_exact_LB'],warm_start_exact_UB=source['final_exact_UB'],
        baseline_validation_wall_before_T0_seconds=perf_counter()-started,prior_Runtime_not_added=549.057,
        prior_Wall_minutes_not_added=20.109,Native_optimize_calls=0,original_May12_or_other_stage_results_transferred=False)
    write(path/'SCIENTIFIC_CASE_IDENTITY.json',identity)
    case.point=point.copy()
    for matrix in (case.A,case.original_A):
        for array in (matrix.data,matrix.indices,matrix.indptr):array.flags.writeable=False
    for domain in (case.d,case.original_d):
        for array in domain.values():
            if isinstance(array,np.ndarray):array.flags.writeable=False
    return case,decomp,point,dual,source,lbpath,ubpath,files

def plan():
    return dict(case_sha=CASE,source_HEAD=BASE,Native_ceiling_seconds=5400,Native_wall_cutoff_seconds=4500,
        final_wall_ceiling_seconds=5400,final_verification_reserve_seconds=900,fixed_Global_Gap_stop=None,
        UB_pilots={'U1':120,'U2':90,'U3':120,'U4':90},UB_followup_TimeLimits=[180,240,300],
        radius_candidates=list(alg.RADII),lookback_candidates=list(alg.LOOKBACK),route_top_candidates=list(alg.TOP_ROUTES),
        LB_max_passes={'L1':1,'L2':2,'L3':2,'L4':1},LP_per_unit_limit=45,MILP_integer_pilot_per_unit_limit=75,
        RMP_per_pass_limit=30,dual_mixing_weights=['1/8','1/4','1/2'],maximum_scheduler_tasks=4096,
        checkpoints_seconds=[0,600,1200,1800,2400,3600,4500],Threads=1,inner_native_gap=.005,
        original_tolerances=1e-8,MemLimit=None,SoftMemLimit=None,no_memory_automatic_stop=True,
        complete_branch_and_price=False,M1_ACCEPTED=False,P2_certificate=None)

def execute(run_id):
    if ROOT.resolve().drive.upper()!='D:' or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):raise ValueError('D_PATH_SAFE_NEW_ID_REQUIRED')
    if git('rev-parse','HEAD').decode().strip()!=BASE or git('branch','--show-current').decode().strip()!='v42':raise ValueError('AUDITED_COMPLETED_HEAD_REQUIRED')
    path=RUNTIME/run_id;path.mkdir(parents=True,exist_ok=False)
    previous=RUNTIME/'anytime_may01_20261008_frontier01'
    oldfinal=read(previous/'INDEPENDENT_FINAL_VERIFICATION.json')
    if oldfinal['PASS'] or oldfinal['termination']!='SCIENTIFIC_OR_ACCOUNTING_FAILURE_QUARANTINE':raise ValueError('ONLY_AUDITED_INTERFACE_FAILURE_CONTINUATION')
    if read(previous/'FATAL_ERROR.json')['error']!="TypeError:Ledger.cost() got an unexpected keyword argument 'track'":raise ValueError('UNEXPECTED_FAILURE_CANNOT_CONTINUE')
    oldledger=read(previous/'NATIVE_RUNTIME_LEDGER.json')
    if oldledger['inflight'] is not None or any(c['runtime_unavailable'] for c in oldledger['calls']):raise ValueError('PREVIOUS_NATIVE_ACCOUNTING_NOT_CLOSED')
    case,decomp,point,bestdual,source,lbpath,ubpath,protected=baseline(path)
    with np.load(previous/'BEST_STRICT_UB_POINT.npz',allow_pickle=False) as z:point=z['point'].copy()
    strict=_strict_ub(case,previous/'BEST_STRICT_UB_POINT.npz',{});strict.update(case_sha=CASE)
    bestdual=read(previous/'BEST_EXACT_ORIGINAL_DUAL.json')
    lb=check_rational_dual_certificate(case.A,case.d,bestdual,case_sha=CASE)
    if not strict['PASS'] or not lb['PASS'] or F(strict['exact_Global_UB'])!=F(oldfinal['exact_Global_UB']) or F(lb['exact_bound'])!=F(oldfinal['exact_Global_LB']):raise ValueError('CONTINUATION_PAIR_MUST_REPLAY_INDEPENDENTLY')
    write(path/'CONTINUATION_START_STRICT_UB_REPLAY.json',strict)
    write(path/'CONTINUATION_START_EXACT_LB_REPLAY.json',lb)
    case.point=point.copy()
    t0=read(previous/'T0_CLOCK.json')['monotonic_T0']
    if perf_counter()-t0>=3900:raise TimeoutError('ORIGINAL_WALL_WINDOW_TOO_LATE_FOR_CONTINUATION')
    write(path/'PREREGISTRATION.json',dict(plan(),run_id=run_id,predecessor_run_id=previous.name,original_monotonic_T0_preserved=t0,failed_costs_included=True,preparation_completed_utc=utc(),Gap_stop=None))
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'v42_m1_anytime').glob('*.py')}
    write(path/'EXECUTED_SOURCE_HASHES.json',sources)
    write(path/'T0_CLOCK.json',dict(read(previous/'T0_CLOCK.json'),continuation_started_at_original_wall=perf_counter()-t0,previous_segment=previous.name,budget_reset=False))
    ledger=Ledger(path/'NATIVE_RUNTIME_LEDGER.json',t0)
    ledger.calls=[dict(c,completed_predecessor_ledger=str(previous/'NATIVE_RUNTIME_LEDGER.json')) for c in oldledger['calls']]
    ledger.costs=[dict(c,completed_predecessor_run=previous.name) for c in oldledger['costs']]
    ledger.persist()
    frontier=Frontier(path,ledger,source['final_exact_LB'],source['final_exact_UB'],lbpath,ubpath)
    import csv
    def records(file):
        with file.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    frontier.events=records(previous/'FRONTIER_EVENTS.csv')
    frontier.checkpoints=records(previous/'FRONTIER_CHECKPOINTS.csv')
    for r in frontier.checkpoints:
        if r['target_wall_seconds']=='FINAL':r['target_wall_seconds']='SEGMENT01_FINAL'
    frontier.passages={str(F(r['threshold_percent'])):r for r in records(previous/'GAP_FIRST_PASSAGE_TIMES.csv') if r['status']=='REACHED'}
    frontier.lb=F(oldfinal['exact_Global_LB']);frontier.ub=F(oldfinal['exact_Global_UB'])
    frontier.lb_path=frontier.events[-1]['LB_certificate_path'];frontier.ub_path=frontier.events[-1]['UB_certificate_path']
    frontier.lb_hash=frontier.events[-1]['LB_certificate_sha256'];frontier.ub_hash=frontier.events[-1]['UB_certificate_sha256']
    frontier.algorithm='CONTINUATION_INDEPENDENT_PAIR_REPLAY_NO_NEW_IMPROVEMENT'
    write(path/'CONTINUATION_AUDIT.json',dict(PASS=True,predecessor_run=previous.name,old_final_PASS=False,interface_error_fixed=True,original_T0_unchanged=True,failed_Runtime_included=oldledger['Native_Runtime_sum'],failed_Work_included=oldledger['Native_Work_sum'],failure_receipt_sha256=sha(previous/'INDEPENDENT_FINAL_VERIFICATION.json'),historical_ledgers_modified=False,first_passages_not_backdated=True,recovery_completed_wall_seconds=ledger.wall()))
    frontier.save();frontier.start_observer()
    history=[];choices=[];counts={k:0 for k in ('U1','U2','U3','U4','L1','L2','L3','L4')};grid_cache={};rmpdual=None
    prior_audit=read(previous/'ADAPTIVE_SCHEDULER_AUDIT.json')
    history=prior_audit['history'].copy();choices=prior_audit['choices'].copy()
    for row in history:counts[row['method']]+=1
    fatal=None;termination='NATIVE_WALL_WINDOW_CLOSED';latest_rmp=None
    try:
        for iteration in range(len(history),4096):
            if frontier.lb==frontier.ub:termination='EXACT_GLOBAL_OPTIMUM_PROVEN';break
            if ledger.wall()>=4460 or ledger.remaining()<1:break
            method,reason=schedule_choice(history,iteration,ledger.wall())
            # Full LP+exact certification has measured non-Native costs. Avoid
            # beginning a four-unit pass near the Native cutoff.
            if method.startswith('L') and ledger.wall()>3900:method='U3';reason['reason']='FINAL_CERTIFICATE_RESERVE_REQUIRES_SHORTER_UB_TASK'
            if method=='L4' and ledger.wall()>3500:method='U4';reason['reason']='FULL_MILP_PRICE_PASS_RESERVE_REQUIRES_SHORTER_UB_TASK'
            counts[method]+=1;ordinal=counts[method]-1;label=f'{iteration:03d}_{method}_{ordinal:02d}'
            target=path/label;frontier.algorithm=label
            choice=dict(method=method,ordinal=ordinal,reason=reason,wall_seconds=ledger.wall(),remaining_Wall_until_Native_cutoff=4500-ledger.wall(),
                remaining_Native_seconds=ledger.remaining(),current_certified_gap_percent=float(100*frontier.gap()),
                current_UB=float(frontier.ub),current_LB=float(frontier.lb),incumbent_sha256=alg.ub.vector_sha(point))
            choices.append(choice);write(path/'ADAPTIVE_SCHEDULER_AUDIT.json',dict(case_sha=CASE,plan=plan(),choices=choices,history=history,fixed_Gap_stop_used=False))
            begin=perf_counter()
            if method.startswith('U'):
                key=alg.ub.vector_sha(point)
                if key not in grid_cache:
                    with ledger.cost('active_source_grid_projection',label):grid_cache[key]=alg.dynamic_grid(case,point,path/(label+'_GRID_PROJECTION.json'))
                if iteration<4:limit=plan()['UB_pilots'][method]
                else:
                    # More time for demonstrably productive methods; diversity
                    # still changes radius/window/corridor at every ordinal.
                    productive=any(r['method']==method and r['certified_gain']>0 for r in history)
                    limit=300 if productive else (180,240)[ordinal%2]
                row,point=alg.ub_trial(case,point,method,ordinal,ledger,frontier,target,limit,grid_cache[key]);case.point=point.copy()
            else:
                price=bestdual;alpha=None
                if method in ('L2','L3'):
                    if method=='L2' or rmpdual is None:
                        with ledger.cost('RMP_latest_strict_trajectory_feedback',label):latest_rmp=alg.feedback_master(case,decomp,point,ledger,path/(label+'_MASTER'))
                        rmpdual=latest_rmp.get('full_original_dual')
                    if rmpdual is None:
                        row=dict(method=method,certified_gain=0,wall_seconds=perf_counter()-begin,status='NOT_RUN_NO_FINITE_RMP_PI');history.append(row);continue
                    if method=='L2':price=rmpdual
                    else:
                        alpha=('1/8','1/4','1/2')[ordinal%3];price=alg.mix_duals(bestdual,rmpdual,alpha)
                row,adopted,result=alg.lp_round(case,decomp,price,ledger,frontier,target,method,'MILP_AND_LP' if method=='L4' else 'LP_ONLY')
                if adopted is not None:bestdual=adopted
                row['dual_stabilization_weight']=alpha
                if method=='L2' and latest_rmp.get('convexity_duals') is not None:
                    selected=read(target/'SELECTED_UNIT_DUALS_EXACT.json')
                    with ledger.cost('exact_missing_column_lower_bounds',label):closure=verify_rmp_pricing_lower_bounds(case,decomp,rmpdual,selected,latest_rmp['convexity_duals'])
                    write(target/'INDEPENDENT_MISSING_COLUMN_CERTIFICATE.json',closure)
            row['total_task_wall_seconds']=perf_counter()-begin;row['wall_seconds']=row['total_task_wall_seconds'];row['completed_wall_seconds']=ledger.wall()
            history.append(row);write(path/'ADAPTIVE_SCHEDULER_AUDIT.json',dict(case_sha=CASE,plan=plan(),choices=choices,history=history,fixed_Gap_stop_used=False))
            print('ANYTIME_TASK',label,'wall',round(ledger.wall(),2),'UB',float(frontier.ub),'LB',float(frontier.lb),'gap',float(100*frontier.gap()),flush=True)
        else:termination='PREREGISTERED_TASK_COUNT_REACHED'
    except TimeoutError:
        termination='NATIVE_WINDOW_CLOSED_AT_SAFE_SOLVER_BOUNDARY'
    except Exception as exc:
        fatal=dict(error=type(exc).__name__+':'+str(exc),wall_seconds=ledger.wall());termination='SCIENTIFIC_OR_ACCOUNTING_FAILURE_QUARANTINE'
        write(path/'FATAL_ERROR.json',fatal)
    # No callback/process termination. Every started model followed TimeLimit
    # or natural termination. Independent final verification begins now.
    write(path/'NATIVE_PHASE_RESULTS.json',dict(case_sha=CASE,run_id=run_id,run_path=str(path),history=history,
        choices=choices,termination=termination,fatal=fatal,Native_finished_wall_seconds=ledger.wall(),best_exact_LB=str(frontier.lb),best_exact_UB=str(frontier.ub)))
    with ledger.cost('final_independent_strict_UB','BEST_POINT'):
        np.savez_compressed(path/'BEST_STRICT_UB_POINT.npz',point=point)
        strict=_strict_ub(case,path/'BEST_STRICT_UB_POINT.npz',{});strict.update(case_sha=CASE)
        if F(strict['exact_Global_UB'])!=frontier.ub:raise ValueError('FINAL_UB_REPLAY_DIFFERS')
        write(path/'BEST_STRICT_UB_REPLAY.json',strict)
    with ledger.cost('final_independent_exact_LB','BEST_ORIGINAL_DUAL'):
        write(path/'BEST_EXACT_ORIGINAL_DUAL.json',bestdual)
        certificate=check_rational_dual_certificate(case.A,case.d,bestdual,case_sha=CASE)
        if F(certificate['exact_bound'])!=frontier.lb:raise ValueError('FINAL_LB_REPLAY_DIFFERS')
        write(path/'BEST_EXACT_LB_CERTIFICATE.json',dict(certificate,dual_path=str(path/'BEST_EXACT_ORIGINAL_DUAL.json'),dual_sha256=sha(path/'BEST_EXACT_ORIGINAL_DUAL.json')))
    with ledger.cost('final_original_source_protection','ALL_PRIOR_FILES'):
        preservation=check_protection(protected)
        for name,digest in sources.items():
            if sha(ROOT/name)!=digest:raise ValueError('RUNNING_ANYTIME_SOURCE_CHANGED:'+name)
        write(path/'SOURCE_PRESERVATION_AUDIT.json',preservation)
    # Run the same historical regression collection in a separate process,
    # writing only this new run's receipt. TEMP/TMP inherited as D.
    tests=read(OLD/'ZERO_NATIVE_REGRESSION.json');names=sorted({s.split('::')[0] for s in tests['passed']+tests['skipped']})
    names+=['tests/test_v42_m1_anytime.py']
    import os
    env=os.environ.copy();env['V42_ANYTIME_TEST_REPORT']=str(path/'ZERO_NATIVE_REGRESSION.json')
    with ledger.cost('final_zero_native_regression','649_BASELINE_PLUS_NEW'):
        with (path/'FINAL_TESTS.log').open('w',encoding='utf-8') as log:
            proc=subprocess.run(['python','-m','pytest','-q','-p','v42_m1_anytime.pytest_plugin','-o','cache_dir=cache/pytest_anytime',
                '--basetemp='+str(ROOT/'tmp'/('pytest_'+run_id)),*names],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        newtests=read(path/'ZERO_NATIVE_REGRESSION.json')
        if proc.returncode or set(tests['passed'])-set(newtests['passed']):raise ValueError('649_PASS_REGRESSION_NOT_PRESERVED')
    # The observer can record T75 during verification, without a solver being
    # interrupted. If closure/contract failure ended earlier, later checkpoints
    # are explicitly NOT_OBSERVED, never padded with fake measurements.
    frontier.finish();ledger.persist()
    verification=dict(PASS=fatal is None,case_sha=CASE,run_id=run_id,monotonic_wall_seconds=ledger.wall(),
        exact_Global_LB=str(frontier.lb),exact_Global_UB=str(frontier.ub),exact_gap=str(frontier.gap()),
        certified_gap_percent=float(100*frontier.gap()),Native_Runtime=ledger.used(),Work=ledger.work(),
        Native_finished_wall_seconds=read(path/'NATIVE_PHASE_RESULTS.json')['Native_finished_wall_seconds'],
        final_90_minutes_PASS=ledger.wall()<=5400,Native_75_minutes_PASS=max((r['finished_wall_seconds'] for r in ledger.calls),default=0)<=4500,
        strict_UB=read(path/'BEST_STRICT_UB_REPLAY.json'),exact_LB=read(path/'BEST_EXACT_LB_CERTIFICATE.json'),
        tests=dict(passed=len(newtests['passed']),skipped=len(newtests['skipped']),failed=len(newtests['failed'])),
        historical_649_PASS_preserved=True,tests_Native=0,preservation=preservation,termination=termination,
        full_integer_pricing_closure='NOT_PROVEN',M1_ACCEPTED=False,P2_certificate=None)
    write(path/'INDEPENDENT_FINAL_VERIFICATION.json',verification)
    print('ANYTIME_FINAL',verification['PASS'],verification['certified_gap_percent'],verification['monotonic_wall_seconds'],flush=True)
    return path

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--run-id',default='anytime_may01_20261008_frontier02_continuation');args=p.parse_args()
    if args.execute:execute(args.run_id)
    else:
        path=RUNTIME/('preflight_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));path.mkdir(parents=True,exist_ok=False)
        baseline(path);print('ANYTIME_PREFLIGHT_NATIVE_ZERO_PASS',path)
if __name__=='__main__':main()
