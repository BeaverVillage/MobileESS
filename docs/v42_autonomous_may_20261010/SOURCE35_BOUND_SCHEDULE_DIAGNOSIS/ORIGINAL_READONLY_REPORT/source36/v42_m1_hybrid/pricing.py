"""Finite full-trajectory pricing pilot.  Native calls require a root ledger.

The signed multirow coupling vector is retained exactly as rationals. Native
models receive rounded binary64 objectives only for finding columns/duals;
their objectives or MIP bounds are not independently certified Global LBs.
"""
from dataclasses import dataclass, field
from fractions import Fraction
from hashlib import sha256
import json
from time import perf_counter
import numpy as np
from .blocks import output_directory, verify_decomposition, unit_owner
from .bound import rational_dual, check_signs, certify_global, local_exact_price_bound


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def _file(path):
    return dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest())


def _strings(values):
    return {str(i):str(q) for i,q in values.items() if q}


@dataclass
class Prices:
    case_sha: str
    coupling_dual: dict
    seed_unit_duals: dict
    seed_nonunit_dual: dict
    exact_objectives: dict
    unit_objectives: dict
    nonunit_exact_objective: dict
    nonunit_objective: np.ndarray
    coupling_constant_exact: str
    source_full_dual: dict
    receipt: dict
    full_objective_residual: dict = field(default_factory=dict)


def make_prices(case, decomp, full_dual):
    """c-B.T*lambda from ALL mixed original rows, not one grid scalar."""
    start = perf_counter()
    verify_decomposition(case, decomp)
    y = rational_dual(full_dual, case.A.shape[0])
    check_signs(y, case.d['sense'])
    A = case.A.tocsr()
    coupling = {k:y[int(i)] for k,i in enumerate(decomp.coupling_rows) if int(i) in y}
    exact = {int(j):Fraction(float(c)) for j,c in enumerate(case.d['objective']) if c}
    constant = Fraction(0)
    for k,q in coupling.items():
        i = int(decomp.coupling_rows[k])
        constant += q*Fraction(float(case.d['rhs'][i]))
        for j,a in zip(A.indices[A.indptr[i]:A.indptr[i+1]], A.data[A.indptr[i]:A.indptr[i+1]]):
            j = int(j)
            exact[j] = exact.get(j,Fraction(0))-q*Fraction(float(a))
    objectives, native, seeds = {}, {}, {}
    for u,b in decomp.units.items():
        objectives[u] = {k:exact[int(j)] for k,j in enumerate(b.original_columns)
                         if exact.get(int(j),Fraction(0))}
        native[u] = np.asarray([float(objectives[u].get(k,0)) for k in range(b.A.shape[1])], dtype=np.float64)
        seeds[u] = _strings({k:y[int(i)] for k,i in enumerate(b.original_rows) if int(i) in y})
    b = decomp.nonunit_block
    nonunit_exact = {k:exact[int(j)] for k,j in enumerate(b.original_columns)
                     if exact.get(int(j),Fraction(0))}
    nonunit_native = np.asarray([float(nonunit_exact.get(k,0)) for k in range(b.A.shape[1])], dtype=np.float64)
    nonunit_y = _strings({k:y[int(i)] for k,i in enumerate(b.original_rows) if int(i) in y})
    full_residual = dict(exact)
    # Record full original residual, including retained local/nonunit rows.
    for block in list(decomp.units.values())+[b]:
        for i in block.original_rows:
            i = int(i)
            q = y.get(i)
            if q is None:
                continue
            for j,a in zip(A.indices[A.indptr[i]:A.indptr[i+1]], A.data[A.indptr[i]:A.indptr[i+1]]):
                j = int(j)
                full_residual[j] = full_residual.get(j,Fraction(0))-q*Fraction(float(a))
    residual = _strings(full_residual)
    receipt = dict(case_sha=case.case_sha,
        status='FULL_SIGNED_ORIGINAL_COUPLING_PRICE_VECTOR',
        mixed_original_rows=len(decomp.coupling_rows), active_coupling_rows=len(coupling),
        inequality_signs='minimization: <= lambda<=0; >= lambda>=0; equality free',
        coupling_constant_exact=str(constant), original_objective_constant_exact=str(Fraction(float(case.d['constant']))),
        nonunit_original_domain_retained=True, objective_rounding_certificate_authority=False,
        all_original_mixed_rows_used=True, source_dual_nonzero_rows=len(y),
        full_objective_residual_nonzero_columns=len(residual),
        price_build_wall_seconds=perf_counter()-start, native_optimize_calls=0,
        integer_block_strengthening='NOT_PROVEN')
    return Prices(case.case_sha, _strings(coupling), seeds, nonunit_y, objectives,
                  native, nonunit_exact, nonunit_native, str(constant), _strings(y),
                  receipt, residual)


def persist_prices(case, decomp, prices, output):
    path = output_directory(output)
    if prices.case_sha != case.case_sha or decomp.case_sha != case.case_sha:
        raise ValueError('PRICE_CASE_SHA_DRIFT')
    _write(path/'SOURCE_FULL_DUAL_EXACT.json', prices.source_full_dual)
    _write(path/'FULL_OBJECTIVE_RESIDUAL_EXACT.json', prices.full_objective_residual)
    _write(path/'COUPLING_DUAL_EXACT.json', dict(case_sha=case.case_sha,
        original_rows=decomp.coupling_rows.tolist(),
        original_senses=case.d['sense'][decomp.coupling_rows].tolist(),
        multipliers=prices.coupling_dual,
        weighted_rhs_exact=prices.coupling_constant_exact))
    _write(path/'SEED_NONUNIT_DUAL_EXACT.json', prices.seed_nonunit_dual)
    files = {}
    for u,b in decomp.units.items():
        _write(path/(u+'_PRICE_EXACT.json'), _strings(prices.exact_objectives[u]))
        _write(path/(u+'_SEED_DUAL_EXACT.json'), prices.seed_unit_duals[u])
        np.savez_compressed(path/(u+'_PRICE_NATIVE.npz'), objective=prices.unit_objectives[u],
            original_rows=b.original_rows, original_columns=b.original_columns)
    _write(path/'NONUNIT_PRICE_EXACT.json', _strings(prices.nonunit_exact_objective))
    for p in path.iterdir():
        if p.name.endswith(('_EXACT.json','_PRICE_NATIVE.npz')):
            files[p.name] = _file(p)
    receipt = dict(prices.receipt, files=files)
    _write(path/'PRICE_IDENTITY.json', receipt)
    return receipt


def build_pricing_model(block, price, kind='MILP', point=None, *, env=None):
    """Build the unchanged complete local domain; never call optimize here."""
    import gurobipy as gp
    begin = perf_counter()
    if kind not in ('MILP','LP'):
        raise ValueError('PRICING_KIND_MUST_BE_MILP_OR_LP')
    price = np.asarray(price, dtype=np.float64)
    if price.shape != (block.A.shape[1],) or not np.isfinite(price).all():
        raise ValueError('PRICING_OBJECTIVE_AXIS_OR_FINITE_DRIFT')
    model = gp.Model('V42_FULL96_TRAJECTORY_'+block.unit+'_'+kind, env=env)
    try:
        model.Params.OutputFlag = 0
        model.Params.Threads = 1
        model.Params.FeasibilityTol = 1e-8
        model.Params.OptimalityTol = 1e-8
        model.Params.IntFeasTol = 1e-8
        model.Params.MIPGap = .005
        types = block.d['types'] if kind == 'MILP' else np.full(block.A.shape[1], 'C')
        v = model.addMVar(block.A.shape[1], lb=block.d['lower'], ub=block.d['upper'],
                         vtype=types, obj=price)
        v.VarName = block.d['names'].tolist()
        model.ObjCon = 0.
        model.ModelSense = gp.GRB.MINIMIZE
        model.addMConstr(block.A, v, block.d['sense'], block.d['rhs'])
        if point is not None and kind == 'MILP':
            start = np.asarray(point, dtype=np.float64)
            if start.shape != price.shape or not np.isfinite(start).all():
                raise ValueError('LOCAL_MIP_START_AXIS_DRIFT')
            v.Start = start
        model.update()
        return model, v, dict(unit=block.unit, kind=kind,
            rows=model.NumConstrs, columns=model.NumVars, nnz=model.NumNZs,
            binary_columns=model.NumBinVars, build_wall_seconds=perf_counter()-begin,
            all_original_local_matrix_nonzeros_retained=True, full_96_slot_domain_preserved=True,
            presolve='ORIGINAL_SOLVER_DEFAULT_NO_EXTRA_PRESOLVE_CALL',
            solver_parameters=dict(Threads=1,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,MIPGap=.005),
            finite_memory_limits=False, native_optimize_calls=0)
    except BaseException:
        model.dispose()
        raise


def validate_local_column(case, block, point):
    """Literal local binaries, lifted original integers, and native physics.

    Grid coupling is intentionally not a local-column admission condition;
    global dispatch/UB admission remains an independent full-matrix replay.
    No rounding/clipping/route extraction/repair alters the raw candidate.
    """
    from v42_m1_research.check_ub import matrix_replay, physical_replay, vector_sha
    begin = perf_counter()
    x = np.asarray(point, dtype=np.float64)
    before = vector_sha(x)
    local = matrix_replay(block.A, block.d, x)
    receipt = dict(PASS=False, unit=block.unit, case_sha=case.case_sha, local_C3A=local,
        global_UB=False, grid_coupling_replayed=False, repairs=0, rounding=0, clipping=0,
        native_optimize_calls=0)
    if not local.get('PASS') or not local.get('integer_pattern_exact') or not local.get('exact_binary_0_1'):
        receipt.update(reason='LOCAL_ORIGINAL_DOMAIN_OR_LITERAL_INTEGER_GATE_FAILED',
                       validation_wall_seconds=perf_counter()-begin)
        return receipt
    whole = np.asarray(case.point, dtype=np.float64).copy()
    whole[block.original_columns] = x
    lifted = case.lift(whole)
    names = np.asarray(case.original_d['names'])
    def original_owner(n):
        text = str(n)
        if text.startswith('arc['):
            return text[4:-1].split(',',1)[0]
        return unit_owner(text)
    owned = np.asarray([original_owner(n) == block.unit for n in names])
    discrete = owned & (case.original_d['types'] != 'C')
    binary = owned & (case.original_d['types'] == 'B')
    exact_integer = bool(np.array_equal(lifted[discrete], np.rint(lifted[discrete])))
    exact_binary = bool(np.isin(lifted[binary], (0.,1.)).all())
    receipt['original_FULL_unit_integer_gate'] = dict(PASS=exact_integer and exact_binary,
        checked_discrete_columns=int(discrete.sum()),checked_binary_columns=int(binary.sum()),
        integer_pattern_exact=exact_integer,exact_binary_0_1=exact_binary)
    if not exact_integer or not exact_binary:
        receipt.update(reason='LIFTED_ORIGINAL_UNIT_INTEGER_PATTERN_NOT_LITERAL',
                       validation_wall_seconds=perf_counter()-begin)
        return receipt
    # Independently replay every original FULL row with only this unit support.
    A = case.original_A.tocsr()
    counts = np.diff(A.indptr)
    nonempty = np.flatnonzero(counts)
    local_rows = np.zeros(A.shape[0],dtype=bool)
    if len(nonempty):
        local_rows[nonempty] = np.logical_and.reduceat(owned[A.indices], A.indptr[nonempty])
    rows = np.flatnonzero(local_rows)
    columns = np.flatnonzero(owned)
    d = {k:case.original_d[k][columns] for k in ('names','lower','upper','types','objective')}
    d.update({k:case.original_d[k][rows] for k in ('rhs','sense','row_names')})
    d['constant'] = np.asarray(0.)
    tight = np.asarray([str(n).split('[',1)[0] in ('flow','terminal_location') for n in d['row_names']])
    original = matrix_replay(A[rows][:,columns], d, lifted[columns],
                            tolerance=1e-6,row_tolerances=np.where(tight,1e-8,1e-6))
    physical = physical_replay(case,lifted)
    unchanged = vector_sha(x) == before
    receipt.update(PASS=bool(original['PASS'] and physical['PASS'] and unchanged),
        original_FULL_local_rows=original, original_96_slot_physics=physical,
        point_sha256=before, raw_point_unchanged=unchanged,
        validation_wall_seconds=perf_counter()-begin,
        eligibility='LOCAL_TRAJECTORY_COLUMN_ONLY_REQUIRES_GLOBAL_RECOURSE_AND_FULL_REPLAY_FOR_UB')
    return receipt


def _dual_packet(model, block):
    try:
        raw = np.asarray(model.getAttr('Pi'),dtype=np.float64)
    except Exception:
        return None
    if raw.shape != (block.A.shape[0],) or not np.isfinite(raw).all():
        return None
    checked = raw.copy()
    bad = ((block.d['sense'] == '<') & (checked > 0)) | ((block.d['sense'] == '>') & (checked < 0))
    checked[bad] = 0.
    return raw,checked,int(bad.sum())


def run_pricing(case, decomp, prices, ledger, output, *, seconds_per_unit=120,
                lp_seconds=90, mode='MILP_AND_LP'):
    """Exactly four MILP+four LP calls, or one finite four-LP followup.

    Only ledger.optimize invokes Native. TIME_LIMIT/no Pi falls back to the
    already exact signed seed; no unused-budget loop or pricing closure claim.
    """
    if mode not in ('MILP_AND_LP','LP_ONLY'):
        raise ValueError('FINITE_PRICING_MODE_REQUIRED')
    if not 0 < lp_seconds <= 90 or (mode == 'MILP_AND_LP' and not 0 < seconds_per_unit <= 120):
        raise ValueError('PRICING_PILOT_LIMIT_EXCEEDS_REGISTERED_SMALL_PILOT')
    path = output_directory(output)
    begin = perf_counter()
    identity = persist_prices(case,decomp,prices,path)
    baseline = certify_global(case,decomp,prices.coupling_dual,
                               prices.seed_unit_duals,prices.seed_nonunit_dual)
    _write(path/'BASELINE_EXACT_GLOBAL_LB.json',baseline)
    selected = {u:dict(y) for u,y in prices.seed_unit_duals.items()}
    records, columns, native_wall = [], {u:[] for u in decomp.units}, 0.
    local_certificates = {}
    for u,b in decomp.units.items():
        exact_price = prices.exact_objectives[u]
        seed = local_exact_price_bound(b,exact_price,selected[u])
        local_certificates[u] = dict(seed=seed,selected=seed,source='EXACT_SEED_DUAL')
        if mode == 'MILP_AND_LP':
            raw = np.asarray(case.point)[b.original_columns].copy()
            admission = validate_local_column(case,b,raw)
            np.savez_compressed(path/(u+'_BASELINE_COLUMN.npz'),point=raw,original_columns=b.original_columns)
            baseline_column = dict(source='FROZEN_VALIDATED_CASE_WITNESS',unit=u,admission=admission,
                **_file(path/(u+'_BASELINE_COLUMN.npz')))
            _write(path/(u+'_BASELINE_COLUMN_REPLAY.json'),baseline_column)
            if admission['PASS']:
                columns[u].append(baseline_column)
            model,v,build = build_pricing_model(b,prices.unit_objectives[u], 'MILP',
                raw if admission['PASS'] else None)
            label = u+'_FULL96_MILP_PRICING'
            try:
                model.Params.LogFile = str(path/(label+'.log'))
                before = perf_counter()
                native = ledger.optimize(model,track='PRICING',label=label,
                                          requested_seconds=float(seconds_per_unit))
                wall = perf_counter()-before
                native_wall += wall
                record = dict(label=label,unit=u,kind='MILP',build=build,native=native,
                    native_optimize_wall_seconds=wall,native_ObjBound_global_authority=False,
                    integer_pricing_closure=False)
                if int(model.SolCount) > 0:
                    point = np.asarray(v.X,dtype=np.float64)
                    np.savez_compressed(path/(u+'_MILP_RAW_COLUMN.npz'),point=point,
                        original_columns=b.original_columns,objective_native=prices.unit_objectives[u])
                    replay = validate_local_column(case,b,point)
                    column = dict(source=label,unit=u,admission=replay,
                                  **_file(path/(u+'_MILP_RAW_COLUMN.npz')))
                    record['candidate_column'] = column
                    if replay['PASS']:
                        columns[u].append(column)
                else:
                    record['candidate_column'] = dict(PASS=False,status='NO_RAW_INCUMBENT')
                records.append(record)
                _write(path/(label+'_RESULT.json'),record)
            finally:
                model.dispose()
        model,v,build = build_pricing_model(b,prices.unit_objectives[u],'LP')
        label = u+'_FULL96_LP_PRICING'
        try:
            model.Params.LogFile = str(path/(label+'.log'))
            before = perf_counter()
            native = ledger.optimize(model,track='PRICING',label=label,
                                      requested_seconds=float(lp_seconds))
            wall = perf_counter()-before
            native_wall += wall
            record = dict(label=label,unit=u,kind='LP',build=build,native=native,
                native_optimize_wall_seconds=wall,pricing_closure=False,
                rounded_price_native_objective_is_diagnostic_only=True)
            packet = _dual_packet(model,b)
            if packet is None:
                record.update(dual_status='NO_FINITE_PI_EXACT_SEED_RETAINED')
            else:
                raw,checked,clipped = packet
                np.savez_compressed(path/(u+'_LP_DUAL.npz'),raw_dual=raw,dual=checked,
                    objective_native=prices.unit_objectives[u],original_rows=b.original_rows,
                    original_columns=b.original_columns)
                cert = local_exact_price_bound(b,exact_price,checked)
                record.update(dual_evidence=_file(path/(u+'_LP_DUAL.npz')),
                    signed_rows_zeroed=clipped,exact_local_price_certificate=cert)
                if Fraction(cert['exact_bound']) > Fraction(seed['exact_bound']):
                    selected[u] = _strings(rational_dual(checked,b.A.shape[0]))
                    local_certificates[u].update(selected=cert,source='FRESH_LOCAL_LP_SIGNED_DUAL')
                    record['fresh_dual_adopted'] = True
                else:
                    record['fresh_dual_adopted'] = False
            _write(path/(u+'_SELECTED_DUAL_EXACT.json'),selected[u])
            records.append(record)
            _write(path/(label+'_RESULT.json'),record)
        finally:
            model.dispose()
        # Durable checkpoint after each naturally completed unit.
        _write(path/'PRICING_CHECKPOINT.json',dict(case_sha=case.case_sha,
            finished_units=list(local_certificates),records=records,columns=columns))
    certificate = certify_global(case,decomp,prices.coupling_dual,selected,prices.seed_nonunit_dual)
    nonunit = local_exact_price_bound(decomp.nonunit_block,prices.nonunit_exact_objective,
                                     prices.seed_nonunit_dual)
    exact_sum = Fraction(float(case.d['constant']))+Fraction(prices.coupling_constant_exact)
    exact_sum += Fraction(nonunit['exact_bound'])
    exact_sum += sum((Fraction(local_certificates[u]['selected']['exact_bound']) for u in decomp.units),Fraction(0))
    if exact_sum != Fraction(certificate['exact_bound']):
        raise ValueError('LOCAL_PRICE_SUM_AND_FULL_ORIGINAL_CERTIFICATE_DISAGREE')
    _write(path/'SELECTED_UNIT_DUALS_EXACT.json',selected)
    _write(path/'FINAL_EXACT_GLOBAL_LB.json',certificate)
    elapsed = perf_counter()-begin
    reported_runtime = sum(float(r['native']['Native_Runtime']) for r in records)
    result = dict(case_sha=case.case_sha,status='FINITE_FULL96_PRICING_PILOT_COMPLETED',mode=mode,
        prices=identity,records=records,columns=columns,baseline_exact_certificate=baseline,
        exact_global_certificate=certificate,local_exact_certificates=local_certificates,
        nonunit_exact_certificate=nonunit,exact_decomposition_sum=str(exact_sum),
        decomposition_sum_matches_full_original_exact_bound=True,
        selected_unit_duals=_file(path/'SELECTED_UNIT_DUALS_EXACT.json'),
        seed_nonunit_dual=_file(path/'SEED_NONUNIT_DUAL_EXACT.json'),
        coupling_dual=_file(path/'COUPLING_DUAL_EXACT.json'),
        independently_certified_LB_gain=certificate['independently_certified_LB']-baseline['independently_certified_LB'],
        genuine_integer_block_strengthening='NOT_PROVEN',pricing_closure=False,
        restricted_master_objective_global_authority=False,
        wall_seconds=elapsed,native_optimize_wall_seconds=native_wall,
        native_reported_Runtime_seconds=reported_runtime,
        ledger_optimize_wall_includes_ledger_bookkeeping=True,
        non_native_wall_seconds=max(0.,elapsed-native_wall),unused_budget_retry_loop=False)
    _write(path/'PRICING_RESULT.json',result)
    return result


def run_lp_prices(case,decomp,prices,ledger,output,*,lp_seconds=60):
    return run_pricing(case,decomp,prices,ledger,output,lp_seconds=lp_seconds,mode='LP_ONLY')
