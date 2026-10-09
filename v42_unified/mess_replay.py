"""Independent frozen PR162 C3A replay; never transfer its point to May12."""
from contextlib import ExitStack
import json
import pickle
from time import perf_counter
from unittest.mock import patch
import numpy as np
from scipy import sparse
from .audit import ROOT, REPORTS, M_HEAD, write
from .storage import FrozenStore, sha
from .replay import pinned, read, forbid_native


def graph_from_bundle(bundle):
    from v42_bootstrap.m1 import native_inputs
    sites, initial, routes, battery, receipt = native_inputs(bundle)
    arcs = [(s,t,s,t+1,None) for s in sites for t in range(96)]
    arcs += [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    return sites, initial, arcs, battery, receipt


def run():
    start = perf_counter()
    out = ROOT/'docs/v42_m1_ultracompact_exact_20261006'
    parent = ROOT/'docs/v42_m1_supercompact_exact_20261006'
    authority = pinned(out/'ULTRACOMPACT_CURRENT_AUTHORITY_M1.json', M_HEAD)
    for key, name in [('selected_matrix_SHA256','C3A_A.npz'), ('selected_data_SHA256','C3A_DATA.npz'),
                      ('selected_start_SHA256','C3A_VALID_START.npz')]:
        if sha(out/name) != authority[key]:
            raise ValueError('C3A_AUTHORITY_DRIFT:'+name)
    freeze = pinned(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')
    store = FrozenStore()
    source = 'C:/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL'
    data_path = store.copy(dict(path=source+'/DATA.pkl', sha256=freeze['source_data_sha256']))
    with data_path.open('rb') as stream:
        data = pickle.load(stream)
    bundle = data[0]
    store.copy(bundle['route_table'])
    graph = graph_from_bundle(store.operational_view(bundle))
    import v42_ultracompact.verify as verifier
    with ExitStack() as stack:
        forbid_native(stack)
        stack.enter_context(patch.object(verifier, 'graph_inputs', lambda: graph))
        stack.enter_context(patch.object(verifier, 'write', lambda n, r: write(REPORTS/('M1_'+n), r)))
        independent = verifier.run()
    # Decode C2 aliases independently from the frozen C1 -> C2 proof packet.
    A = sparse.load_npz(parent/'C1_A.npz')
    with np.load(parent/'C1_DATA.npz') as z:
        d = {k:z[k].copy() for k in z.files}
    with np.load(parent/'C2_RETAINED_AXES.npz') as z:
        cols = z['columns'].copy()
    with np.load(out/'C3A_VALID_START.npz') as z:
        y = z['point'].copy()
    x = np.zeros(A.shape[1]); x[cols] = y
    defined = set(map(int, cols))
    for row in reversed(read(parent/'C2_ELIMINATION_CERTIFICATES.json')):
        j = row['column']
        if j in defined:
            raise ValueError('DUPLICATE_ORIGINAL_ALIAS_DEFINITION')
        x[j] = row['constant']
        for k, w in row['terms'].items():
            if int(k) not in defined or w != 1.:
                raise ValueError('UNPROVED_ORIGINAL_ALIAS_TRANSPORT')
            x[j] += w*x[int(k)]
        defined.add(j)
    if len(defined) != len(x):
        raise ValueError('INCOMPLETE_ORIGINAL_ALIAS_TRANSPORT')
    from v42_integrated.matrix import audit
    c1 = audit(A, d, x, integral=True, tolerance=1e-8)
    identity = pinned(parent/'CURRENT_ORIGINAL_MODEL_CENSUS.json', M_HEAD)['identity']
    # Recheck original CSR and bounds, types, objective, axes, RHS from D copies.
    matrix_path = store.copy(dict(path=source+'/FULL_A.npz', sha256=identity['matrix_sha256']))
    original_data_path = store.copy(dict(path=source+'/FULL_DATA.npz', sha256=identity['data_sha256']))
    full_A = sparse.load_npz(matrix_path)
    with np.load(original_data_path) as z:
        full_d = {k:z[k].copy() for k in z.files}
    original_x = x[:full_A.shape[1]].copy()
    raw = audit(full_A, full_d, original_x, integral=True, tolerance=1e-6)
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    sites, initial, arcs, battery, _ = graph
    values = dict(zip(map(str, full_d['names']), map(float, original_x)))
    for unit in initial:
        for k in range(len(arcs)):
            values.setdefault(f'arc[{unit},{k}]', 0.)
        for site in sites:
            for t in range(96):
                for f in ('Pch','Pdis','Q'):
                    values.setdefault(f'{f}[{unit},{site},{t}]',0.)
    selected = {u:[k for k in range(len(arcs)) if values[f'arc[{u},{k}]'] > .5] for u in initial}
    plan = dict(values=values, initial_sites=initial, chosen_arcs=selected, mode='MILP')
    physical = validate(plan, sites, [a[-1] for a in arcs if a[-1] is not None], battery, 96)
    extra = supplemental_physical(plan, sites, battery)
    passed = independent['PASS'] and c1['PASS'] and raw['PASS'] and physical['PASS'] and extra['charge_mode_and_connection_PASS']
    current = pinned(ROOT/'docs/v42_m1_group_branching_20261008/FINAL_DECISION.json', M_HEAD)
    gap_percent = 100*(current['new_UB']-current['new_valid_global_LB'])/current['new_UB']
    if gap_percent != current['new_global_gap_percent'] or current['M1_ACCEPTED'] is not False:
        raise ValueError('HISTORICAL_GLOBAL_GAP_STATUS_DRIFT')
    result = dict(PASS=bool(passed), native_optimize_calls=0, authority=authority,
                  independent_C2_to_C3=independent, C1_original_alias_replay=c1,
                  original_full_rows=raw, original_physical=physical, original_mode_connection=extra,
                  original_input_day=bundle['day'], original_jobs=len(data[1]),
                  input_data_sha256=freeze['source_data_sha256'], repairs=0,
                  original_objective=float(full_d['objective']@original_x+float(full_d['constant'])),
                  historical_M1_global_LB=current['new_valid_global_LB'], historical_M1_global_UB=current['new_UB'],
                  historical_M1_global_gap_percent=current['new_global_gap_percent'], M1_ACCEPTED=False,
                  May12_new_anchor_M1_result='NOT_RUN_NOT_CERTIFIED', old_1499_job_point_reused_for_1782_jobs=False,
                  D_source_copies=store.seal(), replay_wall_seconds=perf_counter()-start)
    write(REPORTS/'M1_C3A_ORIGINAL_REPLAY.json', result)
    if not passed:
        raise ValueError('C3A_ORIGINAL_PHYSICAL_REPLAY_FAILED')
    return result


if __name__ == '__main__':
    r = run()
    print('C3A_ORIGINAL_REPLAY', r['PASS'], r['historical_M1_global_gap_percent'], r['replay_wall_seconds'])
