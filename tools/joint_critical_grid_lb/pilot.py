"""One Joint16 lower-bound pilot, using frozen Source18r Compact proofs.

No full model is built and no incumbent is promoted to a planning solution.
Build, independent verification, native readback and optimize are separate
stages. A durable latch prevents any second optimize, including after errors.
"""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import argparse
import gc
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import traceback

import numpy as np
import psutil
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from v42_svr11.resources import snapshot
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha

SAVED = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
OUT = ROOT / 'docs/v42_joint_critical_grid_lb_pilot'
TIME_LIMIT = 90
PRIOR = ROOT / 'docs/v42_physical_global_lb_pilot'
BASE = '497609b46faa14ea7e32a9483a333ab32fd264ef'
PARENT = '9383a99f1bdcabbd49c79b3ad9f9ee36d523868a'
CASE = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
WEIGHTS_SHA = '61c84c4bb36b1a35b7f8fd1ad7fec5669cf34b082a3a24cc5069b535d2edde62'
UB = .6760534504652341
OLD_LB = .11666465693783702
FULL_BOUND = .28940049108548904
GIB = 1024**3
FAMILIES = {'route_flow', 'node_activity', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q'}
PHYSICAL_ROWS = {'flow', 'terminal_location', 'initial_SOC', 'terminal_SOC',
                 'energy_balance', 'connected_Pch', 'connected_Pdis',
                 'no_simultaneous_charge', 'no_simultaneous_discharge',
                 'connected_Qmax', 'connected_Qmin', 'PCS16', 'node_activity_link'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(p)


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''):
            h.update(part)
    return h.hexdigest()


def load_data(p):
    with np.load(p, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def upwards(value):
    native = float(value)
    require(math.isfinite(native), 'NONFINITE_RHS')
    return float(np.nextafter(native, np.inf)) if F(native) < value else native


def memory():
    info = psutil.Process().memory_info()
    return dict(time=time.time(), system=snapshot(), RSS_bytes=info.rss,
                Peak_RSS_bytes=getattr(info, 'peak_wset', info.rss),
                Private_Commit_bytes=getattr(info, 'private', info.rss),
                Peak_Private_Commit_bytes=getattr(info, 'peak_pagefile', None))


def admission(sample, extra=2*GIB):
    s = sample['system']
    return s['RAM_available'] >= 4*GIB + extra and s['Commit_available'] >= 6*GIB + extra


def build():
    require(not (OUT / 'NATIVE0.json').exists(), 'SEALED_BUILD_ALREADY_EXISTS')
    started = time.perf_counter()
    pre = memory()
    inherited = read(PRIOR / 'NATIVE0.json')
    identity = read(SAVED / 'SCIENTIFIC_CASE_IDENTITY.json')
    require(identity['case_sha'] == inherited['case_sha'] == CASE, 'CASE_DRIFT')
    # Recheck frozen FULL identity sequentially, then release all FULL arrays.
    original = sparse.load_npz(SAVED / 'FULL_A.npz').tocsr()
    full_d = load_data(SAVED / 'FULL_DATA.npz')
    require(matrix_sha(original) == inherited['original_matrix_sha'] == identity['original_matrix_sha'], 'FULL_SHA')
    require(_domain_sha(full_d) == inherited['original_domain_sha'] == identity['original_domain_sha'], 'FULL_DOMAIN_SHA')
    full_names = full_d['names'].copy()
    rho_original = list(full_names).index('rho_max')
    require(full_d['objective'][rho_original] == 1 and np.count_nonzero(full_d['objective']) == 1
            and float(full_d['constant']) == 0, 'FULL_OBJECTIVE')
    del original, full_d
    gc.collect()
    # Saved certified C3A arrays only. No C3A Gurobi model is constructed.
    source_A = sparse.load_npz(SAVED / 'C3A_A.npz').tocsr()
    d = load_data(SAVED / 'C3A_DATA.npz')
    require(matrix_sha(source_A) == identity['C3A_matrix_sha'], 'C3A_SHA')
    require(_domain_sha(d) == identity['C3A_domain_sha'], 'C3A_DOMAIN_SHA')
    equivalence = read(SAVED / 'ORIGINAL_DOMAIN_EQUIVALENCE.json')
    require(equivalence['PASS'] and equivalence['selected_C3A_integer_and_full_LP_domains_identical'], 'EQUIVALENCE')
    require(read(SAVED / 'CURRENT_EXACT_C3A_PROOF.json')['PASS'], 'SAVED_C3A_PROOF_NOT_PASS')
    require(equivalence['pre_C2_security_independent_proof']['PASS'], 'SAVED_SECURITY_PROOF_NOT_PASS')
    physical = np.array([str(n).split('[', 1)[0] in FAMILIES for n in d['names']])
    rows = np.array([i for i, n in enumerate(d['row_names']) if str(n).split('[', 1)[0] in PHYSICAL_ROWS], dtype=np.int64)
    rho = list(d['names']).index('rho_max')
    cols = np.r_[np.flatnonzero(physical), rho].astype(np.int64)
    local_rho = len(cols)-1
    # Every selected row must have exclusively physical support.
    test = source_A[rows]
    require(np.all(physical[test.indices]), 'PHYSICAL_ROW_SHARED_SUPPORT')
    physical_A = test[:, cols].tocsr()
    del test, source_A
    gc.collect()
    axes = load_data(SAVED / 'CURRENT_C2_AXES.npz')['columns']
    require(len(axes) == len(d['names']), 'C2_C3A_COLUMN_MISMATCH')
    original_to_local = {int(axes[c]): i for i, c in enumerate(cols)}
    require(sha(PRIOR / 'WEIGHTS.json') == WEIGHTS_SHA, 'K16_WEIGHTS_SHA')
    selected = read(PRIOR / 'WEIGHTS.json')['rows']
    require(len(selected) == 16, 'K16_COUNT')
    names = d['names'][cols].copy()
    lower, upper, vtypes = d['lower'][cols].copy(), d['upper'][cols].copy(), d['types'][cols].copy()
    require(lower[local_rho] == 0 and upper[local_rho] == 1 and vtypes[local_rho] == 'C', 'RHO_DOMAIN')
    ii, jj, aa, exact_rows, rhs = [], [], [], [], []
    for k, row in enumerate(selected):
        b = F(row['b'])
        terms = {}
        error = F(0)
        for original_j, coefficient in row['terms'].items():
            original_j = int(original_j)
            require(original_j in original_to_local, 'K16_COLUMN_ELIMINATED')
            j = original_to_local[original_j]
            require(names[j] == full_names[original_j], 'K16_AXIS_NAME_MISMATCH')
            require(str(names[j]).split('[', 1)[0] in {'Pch', 'Pdis', 'Q'}, 'K16_NONPQ')
            coefficient = F(coefficient)
            require(coefficient != 0 and math.isfinite(lower[j]) and math.isfinite(upper[j]), 'BAD_K16_TERM')
            native = float(coefficient)
            require(math.isfinite(native) and native != 0, 'COEFFICIENT_UNDERFLOW_OR_OVERFLOW')
            delta = F(native) - coefficient
            error += max(delta*F(float(lower[j])), delta*F(float(upper[j])))
            terms[str(j)] = str(coefficient)
            ii.append(k); jj.append(j); aa.append(native)
        native_rhs = upwards(-b + error)
        ii.append(k); jj.append(local_rho); aa.append(-1.)
        rhs.append(native_rhs)
        exact_rows.append(dict(original_row=row['row'], name=row['name'], b=str(b), terms=terms,
                               rho_column=local_rho, native_rhs=native_rhs, error_upper_bound=str(error),
                               rhs_outward_extra=str(F(native_rhs)-(-b+error))))
    grid_A = sparse.coo_matrix((aa, (ii, jj)), shape=(16, len(cols))).tocsr()
    A = sparse.vstack((physical_A, grid_A), format='csr')
    data = dict(names=names, c=np.eye(1, len(cols), local_rho).ravel(), lb=lower, ub=upper,
                vtypes=vtypes, rhs=np.r_[d['rhs'][rows], rhs],
                senses=np.r_[d['sense'][rows], np.full(16, '<')],
                row_names=np.r_[d['row_names'][rows], [r['name'] for r in selected]], constant=np.array(0.))
    require(A.shape[0] <= 300000 and A.nnz <= 3000000 and sum(vtypes == 'B') <= 10000, 'SIZE_GATE_STOP')
    with np.load(SAVED / 'FRESH_U4/RAW_00.npz') as z:
        start = z['point'][cols].copy()
    residual = A @ start - data['rhs']
    violation = np.where(data['senses'] == '=', abs(residual), np.where(data['senses'] == '<', residual, -residual))
    require(float(violation.max()) < 1e-8 and np.all(start >= lower-1e-8) and np.all(start <= upper+1e-8), 'U4_JOINT_REPLAY')
    require(np.max(abs(start[vtypes == 'B']-np.rint(start[vtypes == 'B']))) == 0, 'U4_INTEGER')
    require(start[local_rho] == UB, 'U4_RHO')
    sparse.save_npz(OUT / 'JOINT_A.npz', A)
    np.savez_compressed(OUT / 'JOINT_DATA.npz', **data)
    np.savez_compressed(OUT / 'JOINT_AXES.npz', rows=rows, columns=cols)
    np.savez_compressed(OUT / 'JOINT_START.npz', x=start)
    write(OUT / 'K16_EXACT_ROWS.json', dict(rows=exact_rows, physicalrowcount=len(rows), WEIGHTS_sha=WEIGHTS_SHA,
          rounding_policy='native_rhs = ceil_binary64(-b + sum_j max((native_c-exact_c)*lower,(native_c-exact_c)*upper))'))
    proofs = ['ORIGINAL_DOMAIN_EQUIVALENCE.json', 'CURRENT_EXACT_C3A_PROOF.json',
              'CURRENT_SECURITY_PRE_C2_SUMMARY.json', 'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json',
              'EXACT_PHYSICAL_PRESCREEN.json', 'CURRENT_C2_AXES.npz', 'CURRENT_C2_ALIASES.json',
              'CURRENT_C3A_ROW_CERTIFICATES.json', 'CURRENT_C3A_BOUND_PROOFS.json']
    manifest = {p: dict(path=str(SAVED / p), sha256=sha(SAVED / p)) for p in proofs if (SAVED / p).exists()}
    require(read(PRIOR / 'INDEPENDENT_NATIVE0.json')['PASS'] and read(PRIOR / 'GRID_PROVENANCE_AUDIT.json')['PASS'], 'PR209_CERTS')
    write(OUT / 'NATIVE0.json', dict(PASS=True, source=BASE, parent=PARENT, case_sha=CASE,
          original_matrix_sha=identity['original_matrix_sha'], original_domain_sha=identity['original_domain_sha'],
          selected_matrix_sha=identity['C3A_matrix_sha'], selected_domain_sha=identity['C3A_domain_sha'],
          models=dict(rows=A.shape[0], columns=A.shape[1], binaries=int(sum(vtypes == 'B')), nnz=A.nnz,
                      row_families=dict(Counter(str(n).split('[',1)[0] for n in data['row_names'])),
                      column_families=dict(Counter(str(n).split('[',1)[0] for n in names))),
          U4=dict(original_max_violation=inherited['U4_original_replay_max_violation'], original_saved_PASS=inherited['U4_saved_replay_PASS'], joint_max_violation=float(violation.max()),
                  grid_residuals=residual[-16:].tolist(), rho=UB, integer_violation=0),
          saved_equivalence=equivalence, proofs=manifest, Native_optimize_calls=0, full_MILP_calls=0,
          model_extraction_seconds=time.perf_counter()-started, memory_before=pre, memory_after=memory(),
          matrix_sha=matrix_sha(A), files={p:sha(OUT/p) for p in ['JOINT_A.npz','JOINT_DATA.npz','JOINT_AXES.npz','JOINT_START.npz','K16_EXACT_ROWS.json']}))
    print(json.dumps(dict(PASS=True, rows=A.shape[0], columns=A.shape[1], binaries=int(sum(vtypes == 'B')), nnz=A.nnz)))


def safe_attr(model, name):
    try:
        value = getattr(model, name)
        if isinstance(value, (float, np.floating)) and not math.isfinite(value):
            return None
        return value
    except Exception:
        return None


def native():
    require(not (OUT / 'PILOT_STARTED.json').exists(), 'OPTIMIZE_LATCH_EXISTS_NO_RERUN')
    if TIME_LIMIT == 360:
        authorization = read(OUT / 'USER_EXTENSION_AUTHORIZATION.json')
        require(authorization['time_limit_seconds'] == 360 and
                authorization['user_request'] == '90초 짧아 360초 돌려', 'EXPLICIT_360_SECOND_AUTHORIZATION_REQUIRED')
    for p in ['NATIVE0.json', 'INDEPENDENT_NATIVE0.json', 'PHYSICAL_RELATION_AUDIT.json',
              'PRE_RUN_RESOURCE_HOLD.json', 'PRE_LAUNCH_RESOURCE_HOLD.json']:
        require(read(OUT/p)['PASS'], 'PRE_NATIVE_GATE:' + p)
    frozen = read(OUT / 'NATIVE0.json')['files']
    for p, expected in frozen.items():
        require(sha(OUT/p) == expected, 'SEALED_FILE_DRIFT:' + p)
    pre = memory()
    require(admission(pre), 'PRE_BUILD_MEMORY_GATE')
    A = sparse.load_npz(OUT / 'JOINT_A.npz').tocsr()
    d = load_data(OUT / 'JOINT_DATA.npz')
    import gurobipy as gp
    from gurobipy import GRB
    env = gp.Env(empty=True)
    env.setParam('LogFile', str(OUT / 'NATIVE.log'))
    env.start()
    model = gp.Model('Source18r_Joint16_LB_ONLY', env=env)
    for k,v in dict(Threads=1, TimeLimit=TIME_LIMIT, MIPGap=.03, MIPFocus=3,
                    FeasibilityTol=1e-8, IntFeasTol=1e-8, OptimalityTol=1e-8, Seed=42).items():
        model.setParam(k,v)
    create = time.perf_counter()
    x = model.addMVar(len(d['names']), lb=d['lb'], ub=d['ub'], vtype=d['vtypes'].tolist(), obj=d['c'])
    model.addMConstr(A, x, d['senses'], d['rhs'])
    model.ModelSense = GRB.MINIMIZE
    model.ObjCon = float(d['constant'])
    model.update()
    construction_seconds = time.perf_counter()-create
    before_readback = memory()
    native_A = model.getA().tocsr()
    checks = dict(matrix=matrix_sha(native_A) == matrix_sha(A), rhs=np.array_equal(model.getAttr('RHS'),d['rhs']),
                  senses=np.array_equal(model.getAttr('Sense'),d['senses']), lower=np.array_equal(x.LB,d['lb']),
                  upper=np.array_equal(x.UB,d['ub']), types=np.array_equal(x.VType,d['vtypes']),
                  objective=np.array_equal(x.Obj,d['c']), ObjCon=model.ObjCon == 0, ModelSense=model.ModelSense == GRB.MINIMIZE,
                  Rows=model.NumConstrs == A.shape[0], Columns=model.NumVars == A.shape[1], Binary=model.NumBinVars == int(sum(d['vtypes']=='B')),
                  NNZ=model.NumNZs == A.nnz)
    del native_A
    gc.collect()
    readback = dict(PASS=all(checks.values()), checks=checks, matrix_sha=matrix_sha(A),
                    parameters={k:getattr(model.Params,k) for k in ['Threads','TimeLimit','MIPGap','MIPFocus','FeasibilityTol','IntFeasTol','OptimalityTol','Seed']},
                    gurobi_version=list(gp.gurobi.version()), model_build_seconds=construction_seconds,
                    memory_before=pre, memory_after_build=before_readback, memory_after_readback=memory())
    write(OUT / 'NATIVE_READBACK.json', readback)
    require(readback['PASS'], 'NATIVE_READBACK_FAILED')
    with np.load(OUT / 'JOINT_START.npz') as z:
        x.Start = z['x']
    model.update()
    post = memory()
    observed_build_growth = max(0, post['Private_Commit_bytes']-pre['Private_Commit_bytes'])
    expected_growth = max(2*GIB, 4*observed_build_growth)
    safe_memory = admission(post, extra=expected_growth)
    write(OUT / 'MEMORY_ADMISSION.json', dict(PASS=safe_memory, sample=post, RAM_reserve_bytes=4*GIB,
          commit_reserve_bytes=6*GIB, estimated_additional_bytes=expected_growth,
          observed_model_build_private_growth_bytes=observed_build_growth,
          estimation_basis='Model already resident. Reserve max(2 GiB,4x observed model build private growth) for single-thread presolve/root/tree; continuous monitoring enforces system reserves.',
          matrix_arrays_only_in_process='JOINT only; FULL and C3A arrays disposed in prior build process'))
    if not safe_memory:
        write(OUT / 'RESULT.json', dict(classification='JOINT_MEMORY_OR_SIZE_GATE_STOP', Native_optimize_calls=0,
                                      reason='POST_BUILD_RAM_OR_COMMIT_OR_GROWTH_GATE', memory=post))
        model.dispose(); env.dispose()
        return
    from tools.joint_critical_grid_lb.audit_resources_hold import inventory
    peers, peer_errors = inventory()
    heavy_peers = [p for p in peers if p['gurobi_loaded_modules'] or
                   any(token in ' '.join(p['command']).lower() for token in
                       ['--mode native', 'gurobi_cl', 'native_worker', 'v42_svr11.worker', 'run_native', 'run_joint'])]
    write(OUT / 'PRE_OPTIMIZE_PEERS.json', dict(PASS=not heavy_peers and not peer_errors,
          observed_time=time.time(), own_PID_excluded=os.getpid(), peers=peers,
          errors=peer_errors, heavy_peers=heavy_peers))
    require(not heavy_peers and not peer_errors, 'CONCURRENT_HEAVY_GUROBI_GATE')
    # Exclusive create before first optimize: no error/time limit can authorize a retry.
    with (OUT / 'PILOT_STARTED.json').open('x', encoding='utf-8') as f:
        json.dump(dict(Native_optimize_max=1, time=time.time(), pid=os.getpid(),
                       git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                       parameters=readback['parameters'], files=frozen), f, indent=2)
    samples, events = [post], []
    last_sample, last_event, memory_stop = 0., 0., []
    callback_errors = []
    def callback(m, where):
        nonlocal last_sample,last_event
        now = time.monotonic()
        try:
            if now-last_sample >= .5:
                sample = memory()
                samples.append(sample)
                last_sample = now
                if not admission(sample, extra=0):
                    memory_stop.append(sample)
                    m.terminate()
            if where == GRB.Callback.MESSAGE:
                message = m.cbGet(GRB.Callback.MSG_STRING)
                if 'Numerical trouble' in message or 'Out of memory' in message or 'Numeric error' in message:
                    callback_errors.append(message.strip()); m.terminate()
            elif now-last_event >= 1 or where == GRB.Callback.PRESOLVE:
                e = dict(time=now, where=int(where))
                if where == GRB.Callback.MIP:
                    e.update(nodes=m.cbGet(GRB.Callback.MIP_NODCNT), bound=m.cbGet(GRB.Callback.MIP_OBJBND),
                             incumbent=m.cbGet(GRB.Callback.MIP_OBJBST), iterations=m.cbGet(GRB.Callback.MIP_ITRCNT))
                elif where == GRB.Callback.MIPNODE:
                    e.update(nodes=m.cbGet(GRB.Callback.MIPNODE_NODCNT), status=m.cbGet(GRB.Callback.MIPNODE_STATUS))
                elif where == GRB.Callback.PRESOLVE:
                    e.update(columns_deleted=m.cbGet(GRB.Callback.PRE_COLDEL), rows_deleted=m.cbGet(GRB.Callback.PRE_ROWDEL))
                else:
                    return
                # Gurobi sentinel incumbents are finite but not accepted as a bound.
                events.append(e); last_event=now
        except Exception as exc:
            callback_errors.append(repr(exc)); m.terminate()
    wall = time.perf_counter()
    optimize_error = None
    try:
        model.optimize(callback)
    except Exception as exc:
        optimize_error = repr(exc)
    samples.append(memory())
    native_wall = time.perf_counter()-wall
    status = safe_attr(model,'Status')
    bound = safe_attr(model,'ObjBound')
    valid = (status in [GRB.OPTIMAL,GRB.TIME_LIMIT,GRB.INTERRUPTED] and bound is not None
             and math.isfinite(bound) and abs(bound) < GRB.INFINITY and not callback_errors and not optimize_error)
    # Numeric status cannot be relabelled certified. Memory termination retains
    # solver bound only if its ordinary global-bound contract remains available.
    classification = ('JOINT_LB_VALID_MATERIAL' if bound >= FULL_BOUND+.001 else 'JOINT_LB_VALID_NONMATERIAL') if valid else 'JOINT_LB_NOT_CERTIFIED'
    result = dict(classification=classification, numerical_bound_candidate_valid=valid,
         Native_optimize_calls=1, full_MILP_calls=0, separate_LP_calls=0, campaign_calls=0,
         Status=status, ObjBound=bound, ObjBoundC=safe_attr(model,'ObjBoundC'), ObjVal=safe_attr(model,'ObjVal'),
         MIPGap=safe_attr(model,'MIPGap'), NodeCount=safe_attr(model,'NodeCount'), IterCount=safe_attr(model,'IterCount'),
         BarIterCount=safe_attr(model,'BarIterCount'), SolCount=safe_attr(model,'SolCount'),
         Runtime=safe_attr(model,'Runtime'), optimize_wall_seconds=native_wall,
         model_build_seconds=construction_seconds, MaxMemUsed_GB=safe_attr(model,'MaxMemUsed'), MemUsed_GB=safe_attr(model,'MemUsed'),
         UB=UB, PR209_LB=OLD_LB, Source18r_Full_ObjBound=FULL_BOUND, goal_LB=UB*.97,
         global_gap=(UB-bound)/UB if valid else None, delta_PR209=bound-OLD_LB if valid else None,
         delta_Source18r_Full=bound-FULL_BOUND if valid else None, goal_3percent=bool(valid and bound>=UB*.97),
         memory_stop=bool(memory_stop), callback_errors=callback_errors, optimize_error=optimize_error,
         peak_process_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),
         peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples),
         peak_sampled_private_commit_bytes=max(s['Private_Commit_bytes'] for s in samples),
         minimum_RAM_available=min(s['system']['RAM_available'] for s in samples),
         minimum_commit_available=min(s['system']['Commit_available'] for s in samples),
         exact_numeric_BB_certificate=False, incumbent_is_full_UB=False)
    if safe_attr(model,'SolCount'):
        solution=x.X
        np.savez_compressed(OUT/'JOINT_INCUMBENT.npz',x=solution)
        residual=A@solution-d['rhs']
        violation=np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
        result['incumbent_joint_replay']=dict(max_violation=float(max(violation)), rho=float(solution[-1]),
                                             full_feasibility_tested=False, promoted_to_UB=False)
    write(OUT/'MEMORY_TRACE.json',dict(samples=samples, unsafe_samples=memory_stop))
    write(OUT/'NATIVE_EVENTS.json',dict(events=events))
    model.dispose(); env.dispose()
    log=(OUT/'NATIVE.log').read_text(encoding='utf-8',errors='replace')
    result['root_relaxation_completed']='Root relaxation:' in log and ('objective' in log.split('Root relaxation:')[-1].split('\n')[0])
    result['presolve_summary']=[line for line in log.splitlines() if line.startswith(('Presolve removed','Presolved:','Root relaxation:','Explored ','User MIP start'))]
    write(OUT/'RESULT.json',result)
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',choices=['build','native'],required=True)
    ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--time-limit',type=int,choices=[90,360],default=90)
    args=ap.parse_args()
    OUT = args.out.resolve()
    TIME_LIMIT = args.time_limit
    try:
        build() if args.mode=='build' else native()
    except Exception as exc:
        write(OUT / ('BUILD_FAILURE.json' if args.mode=='build' else 'NATIVE_FAILURE.json'),
              dict(error=repr(exc),traceback=traceback.format_exc(), memory=memory(),
                   Native_optimize_started=(OUT/'PILOT_STARTED.json').exists()))
        raise
