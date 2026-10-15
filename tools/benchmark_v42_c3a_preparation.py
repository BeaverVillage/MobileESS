"""Native0 differential audit of real saved C2/FULL/C3A matrices.

Run outside a production campaign. Inputs are read only; all result files are
created in a new output directory. No old point, bound or certificate is used
to accelerate the candidate calculation.
"""
import argparse
import ast
from collections import defaultdict
from fractions import Fraction as Q
import importlib.util
import json
import os
from pathlib import Path
import sys
from time import perf_counter

for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'

import numpy as np
from scipy import sparse


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference-root', 'execution', 'raw', 'c2', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--baseline-intervals', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root))
    import psutil
    for process in psutil.process_iter(['pid','cmdline']):
        argv=process.info['cmdline'] or []
        if (process.pid!=os.getpid() and '--execute' in argv
                and any(Path(a).name=='run_v42_production_campaign.py' for a in argv)):
            raise RuntimeError('LARGE_NATIVE0_AUDIT_REQUIRES_CAMPAIGN_WORKER_FREE')
    import gurobipy as gp
    def forbidden(*a, **k):
        raise AssertionError('NATIVE_OPTIMIZER_FORBIDDEN_IN_PREPARATION_AUDIT')
    for name in ('optimize', 'presolve', 'computeIIS'):
        setattr(gp.Model, name, forbidden)
    from v42_integration.release_date_case import ARCHIVE
    from v42_bootstrap.m1 import native_inputs
    from v42_integration.m_engine import file_record
    from v42_m1_hybrid.blocks import matrix_sha
    # Only the MESS route/battery inputs are needed. Do not reconstruct the
    # AIDC public context or bypass the old execution's frozen adapter gate.
    identity=json.loads((args.raw/'INPUT_AND_SOURCE_IDENTITY.json').read_text())
    bundle_path=ARCHIVE/'raw'/identity['day']/'NATIVE_INPUT_TEMPLATE_B1.json'
    bundle=json.loads(bundle_path.read_text())
    if any(bundle['route_table'][key]!=identity['route_table'][key] for key in ('sha256','bytes')):
        raise AssertionError('SAVED_MESS_ROUTE_AUTHORITY_DRIFT')
    # B1/B2 have distinct file aliases for the same frozen route bytes.
    bundle['route_table']=dict(identity['route_table'])
    sites, initial, routes, battery, receipt = native_inputs(bundle)
    graph = (sites, initial,
             [(s,t,s,t+1,None) for s in sites for t in range(96)] +
             [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],
             battery, receipt)
    del bundle
    def data(path):
        with np.load(path, allow_pickle=True) as packet:
            return {k:packet[k] for k in packet.files}
    A = sparse.load_npz(args.c2/'C2_A.npz'); d = data(args.c2/'C2_DATA.npz')
    full = sparse.load_npz(args.raw/'FULL_A.npz'); fd = data(args.raw/'FULL_DATA.npz')
    B = sparse.load_npz(args.raw/'C3A_A.npz'); e = data(args.raw/'C3A_DATA.npz')
    with np.load(args.raw/'CURRENT_C3A_AXES.npz') as packet:
        rows = packet['rows'].copy()
    saved = json.loads((args.raw/'CURRENT_EXACT_C3A_PROOF.json').read_text())
    if matrix_sha(A) != saved['baseline_matrix_SHA256'] or matrix_sha(B) != saved['selected_matrix_SHA256']:
        raise AssertionError('REAL_MATRIX_SHA_MISMATCH')
    helper = load('v42_ultracompact.independent_interval', root/'v42_ultracompact/independent_interval.py')
    load('v42_ultracompact.polytope', root/'v42_ultracompact/polytope.py')
    verifier = load('v42_ultracompact.current_verify', root/'v42_ultracompact/current_verify.py')
    producer = load('v42_ultracompact.current', root/'v42_ultracompact/current.py')
    profile = defaultdict(lambda:dict(calls=0, wall_seconds=0.))
    def timed(name, fn):
        def wrapped(*a, **k):
            began = perf_counter()
            try:return fn(*a, **k)
            finally:
                profile[name]['calls'] += 1
                profile[name]['wall_seconds'] += perf_counter()-began
        return wrapped
    for name in ('exact_sources', 'union_upper', 'minimal', 'vertices', 'farkas'):
        setattr(producer, name, timed(name, getattr(producer, name)))
    events = []
    def progress(event):
        event = dict(event, audit_wall_seconds=perf_counter()-started)
        events.append(event)
        (args.output/'PROGRESS.json').write_text(json.dumps(event, indent=2))
        print(json.dumps(event), flush=True)
    captured = []
    original_interval = helper.interval
    def capture(vectors, ts, reach, points, limit):
        result = original_interval(vectors, ts, reach, points, limit)
        captured.append(result.copy())
        return result
    helper.interval = capture
    started = perf_counter()
    from v42_integration.preparation_profile import measure
    with measure(args.output,'M_C3A_SAVED_MATRIX_DIFFERENTIAL'):
        ultra = producer.reduce_current_c3a(A,d,graph,progress,physical_original=(full,fd))
    elapsed = perf_counter()-started
    helper.interval = original_interval
    checks = dict(matrix_SHA=matrix_sha(ultra.A)==matrix_sha(B),
                  retained_rows=np.array_equal(ultra.row_ids, rows),
                  lower_bit_exact=np.array_equal(ultra.d['lower'].view(np.uint64), e['lower'].view(np.uint64)),
                  upper_bit_exact=np.array_equal(ultra.d['upper'].view(np.uint64), e['upper'].view(np.uint64)),
                  independent_verifier_PASS=ultra.proof['PASS'])
    intervals = np.stack((np.concatenate(captured[::2]),np.concatenate(captured[1::2])),axis=1)
    np.save(args.output/'ALL_INTERVALS.npy', intervals)
    if args.baseline_intervals:
        baseline = np.load(args.baseline_intervals)
        checks['all_interval_values_bit_exact'] = np.array_equal(intervals.view(np.uint64),baseline.view(np.uint64))
    expected_bounds=json.loads((args.raw/'CURRENT_C3A_BOUND_PROOFS.json').read_text())
    for bound in expected_bounds:
        for key in ('old_lower','old_upper','new_lower','new_upper'):bound[key]=float(bound[key])
    checks['all_bound_certificates_identical']=ultra.bounds==expected_bounds
    checks['all_row_certificates_identical']=ultra.certificates==json.loads((args.raw/'CURRENT_C3A_ROW_CERTIFICATES.json').read_text())
    # Compare current-machine baseline/candidate on the same stratified subset.
    dirs, constants, times, defs = verifier.affine(A,d,sites,sorted(initial))
    reach = np.zeros((len(initial),96,len(sites)), bool)
    for name in d['names']:
        if str(name).startswith('Pch['):
            u,s,t = str(name)[4:-1].split(',')
            reach[sorted(initial).index(u),int(t),sites.index(s)] = True
    planes = verifier.physical_pcs_authority(full,fd,graph)
    limit = Q(float(battery.p_limit)); planes += [(Q(1),Q(0),limit),(Q(-1),Q(0),limit)]
    from itertools import combinations
    points = set()
    for (a,b,c),(p,q,r) in combinations(planes,2):
        den=a*q-b*p
        if den:
            x=(c*q-b*r)/den;y=(a*r-c*p)/den
            if all(s*x+t*y<=u for s,t,u in planes):points.add((x,y))
    tree = ast.parse((args.reference_root/'v42_ultracompact/current_verify.py').read_text())
    verify = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify_current_c3a')
    definitions = [n for n in verify.body if isinstance(n,ast.FunctionDef) and n.name in ('enclosure','interval')]
    scope = dict(np=np,Q=Q,units=sorted(initial),N=len(sites),reach=reach,points=points,limit=limit)
    exec(compile(ast.Module(body=definitions,type_ignores=[]),'<reference-interval>','exec'),scope)
    sample = [ultra.bounds[i]['column'] for i in np.linspace(0,len(ultra.bounds)-1,min(2048,len(ultra.bounds)),dtype=int)]
    vectors=[dirs[j] for j in sample];ts=[times[j] for j in sample]
    sample_times={};results={}
    for name,fn in [('reference',scope['interval']),('candidate',lambda vs,tt:original_interval(vs,tt,reach,points,limit))]:
        began=perf_counter();values=[]
        for start in range(0,len(sample),256):
            vs=vectors[start:start+256];tt=ts[start:start+256]
            values.append(np.stack((fn(vs,tt),fn([{k:-v for k,v in row.items()} for row in vs],tt)),axis=1))
        sample_times[name]=perf_counter()-began;results[name]=np.concatenate(values)
    checks['sample_interval_bit_exact']=np.array_equal(results['reference'].view(np.uint64),results['candidate'].view(np.uint64))
    report=dict(PASS=all(checks.values()),checks=checks,Native_calls=0,
                candidate_C3A_wall_seconds=elapsed,previous_C3A_wall_seconds=saved['wall_seconds'],
                previous_verifier_wall_seconds=saved['independent_verifier_wall_seconds'],
                candidate_proof=ultra.proof,profile=dict(profile),sample_seconds=sample_times,
                sample_speedup=sample_times['reference']/sample_times['candidate'],
                sources=[file_record(root/'v42_ultracompact'/name) for name in ('current.py','current_verify.py','independent_interval.py','polytope.py')])
    (args.output/'RESULT.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
    if not report['PASS']:raise AssertionError('REAL_C3A_DIFFERENTIAL_AUDIT_FAILED')


if __name__ == '__main__':
    main()
