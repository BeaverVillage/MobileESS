"""Single-weight Source18r physical Global LB pilot; never builds a full MILP.

The authoritative FULL CSR is partitioned by literal physical vehicle ownership.
Only original equalities eliminate grid helpers. All arithmetic used in the
weight certificate and objective transport is exact Fraction arithmetic.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import traceback

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SAVED = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
OUT = ROOT / 'docs/v42_physical_global_lb_pilot'
BASE = '497609b46faa14ea7e32a9483a333ab32fd264ef'
CASE = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
UNITS = ('MESS01', 'MESS02', 'MESS03', 'MESS04')
FAMILIES = {'arc', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q'}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(value, why):
    if not value:
        raise ValueError(why)


def downward(value):
    result = float(value)
    return float(np.nextafter(result, -np.inf)) if F(result) > value else result


def owner(name):
    name = str(name)
    family = name.split('[', 1)[0]
    if family in FAMILIES:
        unit = name.split('[', 1)[1].split(',', 1)[0]
        require(unit in UNITS, 'UNKNOWN_UNIT')
        return UNITS.index(unit) + 1
    return 0


def load_full():
    A = sparse.load_npz(SAVED / 'FULL_A.npz').tocsr()
    with np.load(SAVED / 'FULL_DATA.npz', allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    from v42_m1_hybrid.blocks import matrix_sha
    from v42_may_campaign_native90.m_model import _domain_sha
    identity = read(SAVED / 'SCIENTIFIC_CASE_IDENTITY.json')
    require(identity['case_sha'] == CASE, 'CASE_DRIFT')
    require(matrix_sha(A) == identity['original_matrix_sha'], 'FULL_CSR_SHA_DRIFT')
    require(_domain_sha(d) == identity['original_domain_sha'], 'FULL_DOMAIN_SHA_DRIFT')
    return A, d, identity


def original_u4(d):
    with np.load(SAVED / 'FRESH_U4/RAW_00.npz') as z:
        dense = z['point']
    with np.load(SAVED / 'CURRENT_C2_AXES.npz') as z:
        columns = z['columns']
    aliases = read(SAVED / 'CURRENT_C2_ALIASES.json')
    size = 1 + max(int(columns.max()), max(p['column'] for p in aliases))
    compact = np.zeros(size)
    compact[columns] = dense[:len(columns)]
    for p in reversed(aliases):
        compact[p['column']] = p['constant'] + sum(float(w) * compact[int(j)] for j, w in p['terms'].items())
    x = compact[:len(d['names'])].copy()
    require(np.isfinite(x).all(), 'U4_NONFINITE')
    return x


def exact_helpers(A, d):
    definitions = {}
    for i, name in enumerate(d['row_names']):
        family = str(name).split('[', 1)[0]
        if not (family.startswith(('response_', 'injection_')) and family.endswith('_binding')):
            continue
        require(d['sense'][i] == '=', 'HELPER_NON_EQUALITY')
        a, b = A.indptr[i:i+2]
        candidate = [int(j) for j, w in zip(A.indices[a:b], A.data[a:b])
                     if str(d['names'][j]).split('[', 1)[0] + '_binding' == family and w == 1.]
        require(len(candidate) == 1, 'HELPER_PIVOT_NOT_UNIQUE')
        j = candidate[0]
        require(j not in definitions, 'HELPER_DUPLICATE_DEFINITION')
        definitions[j] = (i, F(float(d['rhs'][i])),
                          {int(k): -F(float(w)) for k, w in zip(A.indices[a:b], A.data[a:b]) if k != j})

    @lru_cache(maxsize=None)
    def expand(j):
        if j not in definitions:
            return F(0), {j: F(1)}
        _, constant, terms = definitions[j]
        answer = defaultdict(F)
        for k, w in terms.items():
            offset, pieces = expand(k)
            constant += w * offset
            for q, z in pieces.items():
                answer[q] += w * z
        return constant, {q: z for q, z in answer.items() if z}

    return definitions, expand


def project(A, d, i, expand, rho):
    a, b = A.indptr[i:i+2]
    terms = defaultdict(F)
    constant = -F(float(d['rhs'][i]))
    for j, w in zip(A.indices[a:b], A.data[a:b]):
        offset, pieces = expand(int(j))
        w = F(float(w))
        constant += w * offset
        for k, z in pieces.items():
            terms[k] += w * z
    require(d['sense'][i] == '<' and terms.pop(rho) == -1, 'THERMAL_RHO_SIGN_DRIFT')
    terms = {j: w for j, w in terms.items() if w}
    require(all(owner(d['names'][j]) for j in terms), 'RESIDUAL_GLOBAL_COORDINATE')
    return constant, terms


def native0():
    require(not (OUT / 'NATIVE0.json').exists(), 'NATIVE0_ALREADY_SEALED')
    started = time.perf_counter()
    A, d, identity = load_full()
    rho = list(d['names']).index('rho_max')
    require(float(d['constant']) == 0 and d['objective'][rho] == 1
            and np.count_nonzero(d['objective']) == 1, 'ORIGINAL_OBJECTIVE_NOT_RHO')
    x = original_u4(d)
    residual = A @ x - d['rhs']
    violation = np.where(d['sense'] == '=', abs(residual), np.where(d['sense'] == '<', residual, -residual))
    require(float(violation.max()) < 1e-6, 'U4_FULL_REPLAY_FAILED')
    require(np.max(abs(x[d['types'] != 'C'] - np.rint(x[d['types'] != 'C']))) == 0, 'U4_INTEGER_DRIFT')
    require(np.all(x >= d['lower'] - 1e-8) and np.all(x <= d['upper'] + 1e-8), 'U4_BOUND_DRIFT')
    replay = read(SAVED / 'FRESH_U4/RAW_00.REPLAY.json')
    require(replay.get('PASS') is True, 'FROZEN_U4_REPLAY_NOT_PASS')
    # Select the maximum original thermal facet per slot, then the 16 highest
    # distinct slots in the existing U4. No price update or optimization occurs.
    thermal = [(i, re.fullmatch(r'line_thermal_face\[(\d+),(\d+),(\d+)\]', str(n)))
               for i, n in enumerate(d['row_names']) if str(n).startswith('line_thermal_face[')]
    best = {}
    activity = A @ x
    for i, match in thermal:
        require(match is not None, 'THERMAL_ROW_NAME')
        t, k, facet = map(int, match.groups())
        value = float(activity[i] - d['rhs'][i] + x[rho])
        if t not in best or (value, -i) > (best[t][0], -best[t][1]):
            best[t] = (value, i)
    selected = sorted(best.values(), key=lambda p: (-p[0], p[1]))[:16]
    require(len(best) == 96 and len(selected) == 16, 'FULL_HORIZON_SELECTION')
    definitions, expand = exact_helpers(A, d)
    rows = []
    coefficient = defaultdict(F)
    fixed = F(0)
    for value, i in selected:
        b, terms = project(A, d, i, expand, rho)
        # Exact substitution compared against U4 is diagnostic numerical replay;
        # the independent verifier repeats all symbolic substitutions.
        reconstructed = float(b) + sum(float(w) * x[j] for j, w in terms.items())
        require(abs(reconstructed - value) < 1e-9, 'AFFINE_U4_RECONSTRUCTION')
        fixed += b / 16
        for j, w in terms.items():
            coefficient[j] += w / 16
        rows.append(dict(row=i, name=str(d['row_names'][i]), weight='1/16', b=str(b),
                         terms={str(j): str(w) for j, w in sorted(terms.items())},
                         original_RHS=float(d['rhs'][i]), U4_thermal_value=value,
                         original_rho_coefficient=-1., normalized_sense='<'))
    write(OUT / 'WEIGHTS.json', dict(selection='TOP16_DISTINCT_SLOT_MAX_FACETS_FROM_FROZEN_U4',
          generated_vectors=1, weight_iterations=0, rows=rows, fixed_term=str(fixed), fixed_float=float(fixed),
          exact_objective={str(j): str(w) for j, w in sorted(coefficient.items()) if w}))

    owners = np.array([owner(n) for n in d['names']], dtype=np.int8)
    low = np.zeros(A.shape[0], dtype=np.int8)
    high = low.copy()
    occupied = np.flatnonzero(np.diff(A.indptr))
    support = owners[A.indices]
    low[occupied] = np.minimum.reduceat(support, A.indptr[occupied])
    high[occupied] = np.maximum.reduceat(support, A.indptr[occupied])
    mixed = np.flatnonzero(low != high)
    nonunit = np.flatnonzero((low == 0) & (high == 0))
    models = {}
    for code, unit in enumerate(UNITS, 1):
        began = time.perf_counter()
        ii = np.flatnonzero((low == code) & (high == code))
        jj = np.flatnonzero(owners == code)
        B = A[ii][:, jj].tocsr()
        require(B.nnz == A[ii].nnz, 'NONLOCAL_PHYSICAL_COEFFICIENT_DROPPED')
        e = {k: d[k][jj].copy() for k in ('names', 'lower', 'upper', 'types')}
        e.update({k: d[k][ii].copy() for k in ('rhs', 'sense', 'row_names')})
        e['objective'] = np.array([float(coefficient[int(j)]) for j in jj])
        e['constant'] = np.array(0.)
        require(np.isfinite(e['lower']).all() and np.isfinite(e['upper']).all(), 'LOCAL_INFINITE_BOX')
        correction = F(0)
        box = F(0)
        for k, j in enumerate(jj):
            c = coefficient[int(j)]
            delta = c - F(float(e['objective'][k]))
            correction += delta * F(float(e['lower'][k] if delta >= 0 else e['upper'][k]))
            box += c * F(float(e['lower'][k] if c >= 0 else e['upper'][k]))
        require(np.array_equal(e['types'][np.char.startswith(e['names'], 'arc[')],
                               np.full(np.count_nonzero(np.char.startswith(e['names'], 'arc[')), 'B')), 'INTEGER_ROUTES_LOST')
        sparse.save_npz(OUT / f'UNIT_{unit}_A.npz', B)
        np.savez_compressed(OUT / f'UNIT_{unit}_DATA.npz', **e)
        np.savez_compressed(OUT / f'UNIT_{unit}_AXES.npz', rows=ii, columns=jj)
        np.savez_compressed(OUT / f'UNIT_{unit}_START.npz', point=x[jj])
        models[unit] = dict(rows=len(ii), columns=len(jj), binaries=int(np.sum(e['types'] == 'B')),
            nnz=B.nnz, extraction_wall_seconds=time.perf_counter()-began,
            coefficient_rounding_box_correction=str(correction), exact_box_fallback=str(box),
            row_families=dict(Counter(str(n).split('[')[0] for n in e['row_names'])),
            column_families=dict(Counter(str(n).split('[')[0] for n in e['names'])),
            axes_sha=file_sha(OUT / f'UNIT_{unit}_AXES.npz'),
            matrix_sha=file_sha(OUT / f'UNIT_{unit}_A.npz'), data_sha=file_sha(OUT / f'UNIT_{unit}_DATA.npz'))
    records = {str(p): file_sha(p) for p in (SAVED / n for n in (
        'FULL_A.npz', 'FULL_DATA.npz', 'FIXED_AIDC_ANCHOR.json', 'SCIENTIFIC_CASE_IDENTITY.json',
        'FRESH_U4/RAW_00.npz', 'FRESH_U4/RAW_00.REPLAY.json', 'CURRENT_C2_AXES.npz', 'CURRENT_C2_ALIASES.json'))}
    write(OUT / 'NATIVE0.json', dict(PASS=True, base_commit=BASE, case_sha=CASE,
        original_matrix_sha=identity['original_matrix_sha'], original_domain_sha=identity['original_domain_sha'],
        Native_calls=0, full_MILP_calls=0, campaign_calls=0, models=models,
        fixed_term=str(fixed), UB=float(x[rho]), original_objcon=0.,
        U4_original_replay_max_violation=float(violation.max()), U4_saved_replay_PASS=replay.get('PASS'),
        helper_equalities=len(definitions), full_rows=A.shape[0], full_columns=A.shape[1],
        mixed_rows=len(mixed), mixed_families=dict(Counter(str(d['row_names'][i]).split('[')[0] for i in mixed)),
        dropped_nonunit_rows=len(nonunit), dropped_nonunit_families=dict(Counter(str(d['row_names'][i]).split('[')[0] for i in nonunit)),
        source_records=records, wall_seconds=time.perf_counter()-started,
        theorem='projection(FULL) subset product(X_MESS01,...,X_MESS04); all literal single-owner rows and bounds retained',
        terminal_semantics='original terminal_location=one arc ending slot96; no new return-origin condition',
        native_limit_per_unit=29., native_hard_budget=120., workers=1, threads=1))
    print('NATIVE0 PASS', {u: (m['rows'], m['columns'], m['binaries']) for u, m in models.items()}, flush=True)


def unit_solve(unit):
    import gurobipy as gp
    import psutil
    spec = read(OUT / 'NATIVE0.json')['models'][unit]
    target = OUT / unit
    target.mkdir(exist_ok=False)
    started = time.perf_counter()
    A = sparse.load_npz(OUT / f'UNIT_{unit}_A.npz').tocsr()
    with np.load(OUT / f'UNIT_{unit}_DATA.npz') as z:
        d = {k: z[k] for k in z.files}
    with np.load(OUT / f'UNIT_{unit}_START.npz') as z:
        start = z['point']
    require(file_sha(OUT / f'UNIT_{unit}_A.npz') == spec['matrix_sha']
            and file_sha(OUT / f'UNIT_{unit}_DATA.npz') == spec['data_sha'], 'UNIT_STATE_DRIFT')
    model = None
    try:
        model = gp.Model('SOURCE18R_PHYSICAL_' + unit)
        for name, value in dict(Threads=1, TimeLimit=29., MIPGap=0., MIPGapAbs=0.,
            FeasibilityTol=1e-8, OptimalityTol=1e-8, IntFeasTol=1e-8, SoftMemLimit=2.,
            # Gurobi's Windows log writer rejects the Unicode absolute path
            # exposed by the workspace junction. The ASCII relative path points
            # to the same owned file and changes no mathematical input.
            LogFile=str((target/'NATIVE_GUROBI.log').relative_to(ROOT)), OutputFlag=1).items():
            setattr(model.Params, name, value)
        variables = model.addMVar(A.shape[1], lb=d['lower'], ub=d['upper'], vtype=d['types'], obj=d['objective'])
        variables.VarName = d['names'].tolist()
        model.addMConstr(A, variables, d['sense'], d['rhs'])
        model.ObjCon = 0.
        variables.Start = start
        model.update()
        B = model.getA().tocsr()
        checks = dict(CSR_exact=all(np.array_equal(getattr(A, k), getattr(B, k)) for k in ('data', 'indices', 'indptr')),
            RHS_exact=np.array_equal(model.getAttr('RHS'), d['rhs']), senses_exact=np.array_equal(model.getAttr('Sense'), d['sense']),
            bounds_exact=np.array_equal(model.getAttr('LB'), d['lower']) and np.array_equal(model.getAttr('UB'), d['upper']),
            types_exact=np.array_equal(model.getAttr('VType'), d['types']), objective_exact=np.array_equal(model.getAttr('Obj'), d['objective']),
            original_minimization=model.ModelSense == 1, ObjCon_exact=model.ObjCon == 0., Threads1=model.Params.Threads == 1,
            TimeLimit=model.Params.TimeLimit == 29.)
        require(all(checks.values()), 'NATIVE_READBACK_DRIFT')
        del B
        build_seconds = time.perf_counter()-started
        write(target/'READBACK.json', dict(PASS=True, checks=checks, build_seconds=build_seconds,
            rows=model.NumConstrs, columns=model.NumVars, binaries=model.NumBinVars))
        resource_failure = []
        def callback(m, where):
            if psutil.virtual_memory().available < 512 * 1024**2:
                resource_failure.append('RAM_AVAILABLE_BELOW_512MIB')
                m.terminate()
        write(target/'STARTED.json', dict(unit=unit, optimize_calls=1, TimeLimit=29., Threads=1))
        model.optimize(callback)
        mem = psutil.Process().memory_info()
        bound = float(model.ObjBound)
        continuous_bound = float(model.ObjBoundC)
        native_bound = min(bound, continuous_bound)
        valid = (model.Status in (gp.GRB.OPTIMAL, gp.GRB.TIME_LIMIT, gp.GRB.INTERRUPTED)
                 and math.isfinite(native_bound) and abs(native_bound) < gp.GRB.INFINITY)
        require(not resource_failure and model.Status in (gp.GRB.OPTIMAL, gp.GRB.TIME_LIMIT, gp.GRB.INTERRUPTED),
                'RESOURCE_NUMERIC_OR_UNEXPECTED_SOLVER_STATUS')
        incumbent = float(model.ObjVal) if model.SolCount else None
        require(incumbent is None or native_bound <= incumbent + 1e-7, 'BOUND_INCUMBENT_ORDER')
        if valid:
            exact_lb = F(native_bound) + F(spec['coefficient_rounding_box_correction'])
            bound_source = 'CURRENT_NATIVE_GLOBAL_SOLVER_BOUND'
        else:
            exact_lb = F(spec['exact_box_fallback'])
            bound_source = 'PROVEN_LITERAL_FINITE_BOX_FALLBACK'
        write(target/'RESULT.json', dict(PASS=True, unit=unit, status=int(model.Status), optimize_calls=1,
            Native_Runtime=float(model.Runtime), model_build_seconds=build_seconds, total_wall_seconds=time.perf_counter()-started,
            ObjBound=bound if math.isfinite(bound) else None, ObjBoundC=continuous_bound if math.isfinite(continuous_bound) else None,
            selected_solver_bound=native_bound if valid else None, valid_solver_bound=valid,
            bound_source=bound_source, incumbent=incumbent, solver_gap=float(model.MIPGap) if model.SolCount and math.isfinite(model.MIPGap) else None,
            nodes=float(model.NodeCount), SolCount=int(model.SolCount), certified_LB_exact=str(exact_lb), certified_LB=downward(exact_lb),
            coefficient_rounding_box_correction=spec['coefficient_rounding_box_correction'],
            peak_RSS_bytes=int(getattr(mem, 'peak_wset', mem.rss)),
            peak_private_commit_bytes=int(getattr(mem, 'peak_pagefile', getattr(mem, 'private', mem.rss))),
            Gurobi_MaxMemUsed_GB=float(model.MaxMemUsed), RSS_bytes=int(mem.rss), resource_failure=resource_failure))
        if model.SolCount:
            np.savez_compressed(target/'INCUMBENT.npz', point=variables.X)
    except BaseException as error:
        try:
            failed_runtime = float(model.Runtime) if model is not None else 0.
        except BaseException:
            failed_runtime = None
        memory = psutil.Process().memory_info()
        write(target/'ERROR.json', dict(error=repr(error), traceback=traceback.format_exc(),
            Native_Runtime=failed_runtime, Runtime_unknown=failed_runtime is None,
            optimize_started=(target/'STARTED.json').exists(),
            peak_RSS_bytes=int(getattr(memory, 'peak_wset', memory.rss)),
            peak_private_commit_bytes=int(getattr(memory, 'peak_pagefile', getattr(memory, 'private', memory.rss))), STOP=True))
        raise
    finally:
        if model is not None:
            model.dispose()


def run_pilot():
    require(not (OUT/'PILOT_STARTED.json').exists(), 'PILOT_STOP_LATCH_NO_REPEAT')
    require(read(OUT/'INDEPENDENT_NATIVE0.json')['PASS'] is True, 'INDEPENDENT_NATIVE0_REQUIRED')
    write(OUT/'PILOT_STARTED.json', dict(base=BASE, weights_sha=file_sha(OUT/'WEIGHTS.json'),
        execution_source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        runner_sha=file_sha(Path(__file__)), verifier_sha=file_sha(ROOT/'tools/verify_physical_global_lb.py'),
        units=list(UNITS), workers=1, Threads=1, per_unit_TimeLimit=29., cumulative_budget=120.,
        full_MILP_calls=0, weight_iterations=0, campaign_calls=0))
    runtime = 0.
    results = []
    write(OUT/'NATIVE_LEDGER.json', dict(Units=[], Native_Runtime=0., optimize_calls=0, workers=1, Threads=1, full_MILP_calls=0))
    for unit in UNITS:
        require(runtime < 90., 'INSUFFICIENT_BUDGET_FOR_NEXT_UNIT')
        with (OUT/(unit+'.console.log')).open('w', encoding='utf-8') as log:
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--unit', unit], cwd=ROOT,
                                       stdout=log, stderr=subprocess.STDOUT)
        if completed.returncode:
            error_path = OUT/unit/'ERROR.json'
            failed = read(error_path) if error_path.exists() else dict(Native_Runtime=None, Runtime_unknown=True,
                optimize_started=(OUT/unit/'STARTED.json').exists(), error='WORKER_TERMINATED_WITHOUT_RECEIPT')
            failure_runtime = failed.get('Native_Runtime')
            known_runtime = runtime + (failure_runtime or 0.)
            ledger = dict(Units=results, failed_unit=unit, failed_receipt=failed,
                known_Native_Runtime=known_runtime, Native_Runtime=None if failure_runtime is None else known_runtime,
                optimize_calls=len(results)+int(failed['optimize_started']), runtime_incomplete=failure_runtime is None,
                workers=1, Threads=1, full_MILP_calls=0)
            write(OUT/'NATIVE_LEDGER.json', ledger)
            write(OUT/'STOP.json', dict(ledger, reason='UNIT_FAILURE', classification='GLOBAL_LB_NOT_CERTIFIED'))
            raise RuntimeError('UNIT_FAILURE:' + unit)
        result = read(OUT/unit/'RESULT.json')
        runtime += result['Native_Runtime']
        results.append(result)
        write(OUT/'NATIVE_LEDGER.json', dict(Units=results, Native_Runtime=runtime, optimize_calls=len(results),
              workers=1, Threads=1, full_MILP_calls=0))
        if result['Native_Runtime'] > 30. or runtime > 120.:
            write(OUT/'STOP.json', dict(unit=unit, reason='NATIVE_BUDGET_EXCEEDED', Native_Runtime=runtime,
                optimize_calls=len(results), classification='GLOBAL_LB_NOT_CERTIFIED'))
            raise RuntimeError('NATIVE_BUDGET_EXCEEDED')
        print(unit, result['status'], result['certified_LB'], result['Native_Runtime'], flush=True)
    zero = read(OUT/'NATIVE0.json')
    lb = F(zero['fixed_term']) + sum((F(r['certified_LB_exact']) for r in results), F(0))
    ub = F(float(zero['UB']))
    gap = (ub - lb) / ub
    if lb > ub:
        write(OUT/'STOP.json', dict(reason='LB_EXCEEDS_FROZEN_UB', raw_LB=str(lb), UB=str(ub),
            Native_Runtime=runtime, classification='GLOBAL_LB_NOT_CERTIFIED'))
        raise RuntimeError('LB_EXCEEDS_FROZEN_UB')
    # Materiality was preregistered as meeting the user's explicit 3% goal.
    verdict = 'VALID_GLOBAL_LB_MATERIAL' if gap <= F(3, 100) else 'VALID_GLOBAL_LB_NONMATERIAL'
    write(OUT/'RESULT.json', dict(classification=verdict, fixed_term=zero['fixed_term'], Global_LB_exact=str(lb),
        Global_LB=downward(lb), UB=float(ub), Gap_percent=float(gap*100), target_LB_exact=str(ub*F(97,100)),
        Native_Runtime=runtime, Native_calls=4, Full_MILP_calls=0, weight_vectors=1, weight_iterations=0,
        peak_RSS_bytes=max(r['peak_RSS_bytes'] for r in results),
        peak_private_commit_bytes=max(r['peak_private_commit_bytes'] for r in results),
        expansion='REJECT' if verdict.endswith('NONMATERIAL') else 'REVIEW_CRITICAL_GRID_REDUCED_MILP_WITHOUT_NEW_SOLVER_RUN',
        certification_scope='independent exact model/weight/inclusion/rounding/aggregation audit; native B&B bounds trusted under Gurobi numerical contract',
        units=results))


def repair_pre_native_logpath():
    """Archive ONLY the proved zero-optimize file-IO failure; never reset budget.

    No numerical, memory, interrupted, or post-optimize trial can use this path.
    All original physics/weights/source artifacts stay byte-for-byte in place.
    """
    require(not (OUT/'PRE_NATIVE_LOGPATH_REPAIR.json').exists(), 'LOGPATH_REPAIR_ALREADY_USED')
    stop = read(OUT/'STOP.json')
    failed = read(OUT/'MESS01/ERROR.json')
    require(stop['optimize_calls'] == 0 and stop['Native_Runtime'] == 0.
        and stop['failed_unit'] == 'MESS01' and stop['reason'] == 'UNIT_FAILURE', 'REPAIR_REQUIRES_PROVEN_ZERO_NATIVE')
    require(failed['error'] == "GurobiError(10013, 'Unable to write file')"
        and failed['Native_Runtime'] == 0. and failed['optimize_started'] is False
        and not (OUT/'MESS01/STARTED.json').exists(), 'REPAIR_NOT_PRE_NATIVE_LOGPATH_ONLY')
    require(not any((OUT/u).exists() for u in UNITS[1:]), 'REPAIR_PREVIOUS_OTHER_UNITS_EXIST')
    before = {n: file_sha(OUT/n) for n in ('NATIVE0.json', 'WEIGHTS.json', 'INDEPENDENT_NATIVE0.json')}
    archive = OUT/'failed_pre_native_logpath'
    archive.mkdir(exist_ok=False)
    archived = {}
    for name in ('MESS01', 'MESS01.console.log', 'PILOT_STARTED.json', 'NATIVE_LEDGER.json', 'STOP.json'):
        origin, target = OUT/name, archive/name
        require(origin.resolve().is_relative_to(OUT.resolve()) and target.resolve().is_relative_to(OUT.resolve()),
                'REPAIR_MOVE_OUTSIDE_OWNED_WORKSPACE')
        origin.rename(target)
    for p in archive.rglob('*'):
        if p.is_file():
            archived[str(p.relative_to(archive))] = file_sha(p)
    require(before == {n: file_sha(OUT/n) for n in before}, 'REPAIR_MATHEMATICAL_PACKET_DRIFT')
    write(OUT/'PRE_NATIVE_LOGPATH_REPAIR.json', dict(PASS=True, prior_optimize_calls=0, prior_Native_Runtime=0.,
        numerical_errors=0, memory_errors=0, mathematical_packets_unchanged=before, archived_files=archived,
        repair='absolute Unicode LogFile -> ASCII relative LogFile; same owned output; no equation/weight/parameter change',
        budget_reset=False, Native_budget_remaining=120.))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native0', action='store_true')
    parser.add_argument('--run-pilot', action='store_true')
    parser.add_argument('--unit', choices=UNITS)
    parser.add_argument('--repair-pre-native-logpath', action='store_true')
    args = parser.parse_args()
    if args.repair_pre_native_logpath:
        repair_pre_native_logpath()
    elif args.native0:
        native0()
    elif args.unit:
        unit_solve(args.unit)
    elif args.run_pilot:
        run_pilot()
    else:
        parser.error('one explicit mode required')
