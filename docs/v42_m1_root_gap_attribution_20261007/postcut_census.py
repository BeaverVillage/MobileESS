"""Compare saved complete LP points only after the cut loop is complete.

No optimizer, native model builder, production cut constructor, or pipeline is
imported or called.  Candidate coefficients are the unchanged saved JSON pool.
Floating point violations are point diagnostics, not rational validity proofs,
LP primal feasibility certificates, or independently certified bound gains.
"""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                  MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
from scipy import sparse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
PARENT = ROOT/'docs/v42_m1_ultracompact_exact_20261006'
TOL = 1e-8
FAMILIES = ('node_activity', 'charge_mode')
CANDIDATE_SHA = '614ce27f21723896390e608defbcbedd56ed93cfc15af0beb8215afe91b0807b'
DATA_SHA = '20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467'
BASE = '1d922c91eb27056a5ccc79c92ef18146707099ab'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def truth(value):
    return value is True or str(value).lower() == 'true'


def close(a, b, tol=1e-12):
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b)) <= tol


def cut_identity(q):
    return (q['id'], q['family'], q['MESS'], int(q['slot']), q['site'],
            tuple(sorted((int(j), float(w)) for j,w in q['terms'].items() if float(w))),
            float(q['rhs']))


class Inputs:
    def __init__(self):
        self.hashes = {}

    def capture(self, path):
        path = Path(path)
        assert path.is_file(), f'MISSING_INPUT: {path}'
        self.hashes.setdefault(str(path), sha(path))
        return path

    def json(self, name):
        return json.loads(self.capture(OUT/name).read_text(encoding='utf-8'))

    def csv(self, name):
        with self.capture(OUT/name).open(encoding='utf-8', newline='') as stream:
            return list(csv.DictReader(stream))

    def x(self, name, columns):
        with np.load(self.capture(OUT/name), allow_pickle=False) as z:
            x = z['x']
        assert x.shape == (columns,) and np.isfinite(x).all(), f'INCOMPLETE_POINT: {name}'
        return x


def fractional_stats(values):
    mask = (values > TOL) & (values < 1-TOL)
    mass = np.minimum(values, 1-values)
    return dict(binary_count=int(values.size), fractional_count=int(mask.sum()),
        fractionality_rate=float(mask.mean()) if values.size else 0.,
        sum_min_x_1mx=float(mass.sum()),
        max_min_x_1mx=float(mass.max(initial=0)),
        mean_min_x_1mx=float(mass.mean()) if values.size else 0.,
        fractional_variable_mass=float(mass[mask].sum()),
        min_value=float(values.min()) if values.size else None,
        max_value=float(values.max()) if values.size else None,
        binary_bound_violation=float(max((-values).max(initial=0), (values-1).max(initial=0))))


def candidate_stats(violation, indices, selected):
    indices = np.asarray(indices, dtype=np.int64)
    vals = violation[indices]
    sel = selected[indices]
    mask = vals > TOL
    unselected = ~sel
    most = int(indices[int(np.argmax(vals))]) if indices.size else None
    return dict(candidate_count=int(indices.size),
        violated_count=int(mask.sum()),
        max_signed_violation=float(vals.max()) if vals.size else None,
        max_positive_violation=float(vals.max(initial=0)),
        sum_positive_violation_above_tolerance=float(vals[mask].sum()),
        selected_candidate_count=int(sel.sum()),
        selected_violated_count=int((mask & sel).sum()),
        unselected_candidate_count=int(unselected.sum()),
        unselected_violated_count=int((mask & unselected).sum()),
        most_violated_candidate_index=most)


def main():
    # This guard is deliberately before loading any matrix/points or writing.
    assert (OUT/'LP_STRENGTHENING_SUMMARY.json').is_file(), 'FINAL_CUT_LOOP_NOT_COMPLETE'
    inputs = Inputs()
    inputs.capture(__file__)
    summary = inputs.json('LP_STRENGTHENING_SUMMARY.json')
    trace = inputs.csv('LP_STRENGTHENING_TRACE.csv')
    scope = inputs.json('EXPERIMENT_SCOPE.json')
    assert scope['base_exact_head'] == BASE
    rounds = [int(float(r['round'])) for r in trace]
    assert rounds == list(range(len(trace))) and 1 <= len(trace)-1 <= 10
    assert summary['rounds'] == len(trace)-1 and summary['MILP_calls_during_loop'] == 0
    assert summary['baseline_rows_deleted'] == 0
    assert all(int(float(r['total_cuts'])) == 32*j for j,r in enumerate(trace))
    tokens = []
    for path in sorted(OUT.glob('LP_ROUND_*_ONCE.json')):
        token = inputs.json(path.name)
        j = int(path.name.split('_')[2])
        if token['optimize_calls'] == 0:
            assert token.get('operator_checkpoint', False)
            continue
        assert token['optimize_calls'] == 1 and token['round'] == j
        tokens.append(j)
    assert sorted(tokens) == rounds[1:], 'INCOMPLETE_OR_EXTRA_CUT_ROUND_CALL'

    candidates = inputs.json('CANDIDATE_COEFFICIENTS.json')
    assert inputs.hashes[str(OUT/'CANDIDATE_COEFFICIENTS.json')] == CANDIDATE_SHA
    ids = {q['id']:i for i,q in enumerate(candidates)}
    assert len(ids) == len(candidates) == 46136
    selected = inputs.json('SELECTED_CUTS.json')
    assert len(selected) == summary['cuts'] == int(float(trace[-1]['total_cuts']))
    assert len({q['id'] for q in selected}) == len(selected)
    assert all(q['id'] in ids and cut_identity(q) == cut_identity(candidates[ids[q['id']]]) for q in selected)
    selected_positions = np.asarray([ids[q['id']] for q in selected], dtype=np.int64)
    mapping = inputs.csv('DISCRETE_VARIABLE_FAMILY_MAP.csv')
    columns = int(float(trace[0]['columns']))
    assert columns == 306040 and all(int(float(r['columns'])) == columns for r in trace)
    assert len(mapping) == len({int(r['column']) for r in mapping}) == 9322
    assert Counter(r['family'] for r in mapping) == {'node_activity':8938, 'charge_mode':384}
    data_path = inputs.capture(PARENT/'C3A_DATA.npz')
    assert inputs.hashes[str(data_path)] == DATA_SHA
    with np.load(data_path, allow_pickle=False) as z:
        names,types = z['names'],z['types']
    assert {int(r['column']) for r in mapping} == set(map(int,np.flatnonzero(types!='C')))
    assert all(str(names[int(r['column'])]) == r['name'] for r in mapping)
    group_columns = {f:np.asarray([int(r['column']) for r in mapping if r['family']==f],dtype=np.int64)
                     for f in FAMILIES}
    all_discrete = np.concatenate([group_columns[f] for f in FAMILIES])
    del names,types

    # Evaluation matrix from the saved coefficients only.  This is sparse
    # arithmetic, not a native solver model or a fresh candidate constructor.
    rr,cc,ww = [],[],[]
    for i,q in enumerate(candidates):
        js = [int(j) for j in q['terms']]
        assert len(set(js)) == len(js) and all(0 <= j < columns for j in js)
        assert math.isfinite(float(q['rhs']))
        for j,w in q['terms'].items():
            assert math.isfinite(float(w))
            if float(w):
                rr.append(i);cc.append(int(j));ww.append(float(w))
    C = sparse.csr_matrix((ww,(rr,cc)),shape=(len(candidates),columns))
    rhs = np.asarray([float(q['rhs']) for q in candidates],dtype=float)
    del rr,cc,ww
    candidate_families = sorted({q['family'] for q in candidates})
    candidate_groups = {f:np.asarray([i for i,q in enumerate(candidates) if q['family']==f],dtype=np.int64)
                        for f in candidate_families}
    all_candidates = np.arange(len(candidates),dtype=np.int64)
    pure = inputs.json('PURE_LP_RESULT.json')
    baseline_candidate_csv = inputs.csv('CANDIDATE_VALID_INEQUALITIES.csv')
    original_violations = Counter(r['family'] for r in baseline_candidate_csv if truth(r['baseline_violated']))
    reports,flat = [],[]
    baseline = None
    for j,r in enumerate(trace):
        name = 'PURE_LP_POINT.npz' if j == 0 else f'LP_ROUND_{j:02d}_POINT.npz'
        result = pure if j == 0 else inputs.json(f'LP_ROUND_{j:02d}_RESULT.json')
        replay = result['independent_relaxed_matrix_replay'] if j == 0 else result['independent_replay']
        assert truth(r['raw_matrix_replay_PASS']) == replay['PASS']
        assert close(r['max_raw_row_violation'],replay['max_row_violation'])
        x = inputs.x(name,columns)
        if j == 0:
            assert all(float(m['LP_value']) == x[int(m['column'])] for m in mapping)
        discrete = {f:fractional_stats(x[group_columns[f]]) for f in FAMILIES}
        discrete_total = fractional_stats(x[all_discrete])
        assert discrete_total['fractional_count'] == sum(v['fractional_count'] for v in discrete.values())
        violation = C@x-rhs
        assert np.isfinite(violation).all()
        selected_mask = np.zeros(len(candidates),dtype=bool)
        selected_mask[selected_positions[:int(float(r['total_cuts']))]] = True
        residual = {f:candidate_stats(violation,ix,selected_mask) for f,ix in candidate_groups.items()}
        residual_total = candidate_stats(violation,all_candidates,selected_mask)
        assert residual_total['violated_count'] == sum(v['violated_count'] for v in residual.values())
        assert residual_total['selected_candidate_count'] == int(float(r['total_cuts']))
        for stats in [residual_total,*residual.values()]:
            index = stats.pop('most_violated_candidate_index')
            stats['most_violated_candidate_id'] = candidates[index]['id'] if index is not None else None
        report = dict(round=j,point_file=name,point_SHA256=inputs.hashes[str(OUT/name)],
            total_cuts=int(float(r['total_cuts'])),LP_objective_proxy=float(r['rho']),
            valid_global_LB_from_saved_trace=float(r['valid_global_LB']),
            native_Status=result['Status'],
            raw_original_matrix_replay_PASS=replay['PASS'],
            raw_original_max_row_violation=replay['max_row_violation'],
            raw_original_max_bound_violation=replay['max_bound_violation'],
            raw_replay_provenance='Completed saved RESULT receipt; postcut census does not create a new raw matrix certificate.',
            discrete_by_family=discrete,discrete_total=discrete_total,
            remaining_candidate_violations_by_family=residual,remaining_candidate_violations_total=residual_total)
        if baseline is None:
            baseline = report
            assert discrete_total['fractional_count'] == 7454
            assert all(residual[f]['violated_count'] == original_violations.get(f,0) for f in candidate_families), \
                'BASELINE_CANDIDATE_EVALUATION_DOES_NOT_RECONCILE'
        report['change_from_original_pure_LP'] = dict(
            fractional_count=discrete_total['fractional_count']-baseline['discrete_total']['fractional_count'],
            sum_min_x_1mx=discrete_total['sum_min_x_1mx']-baseline['discrete_total']['sum_min_x_1mx'],
            violated_candidates=residual_total['violated_count']-baseline['remaining_candidate_violations_total']['violated_count'])
        reports.append(report)
        line = {k:v for k,v in report.items() if not isinstance(v,(dict,list))}
        for prefix,stats in [('all_discrete',discrete_total),('all_candidates',residual_total),
                             *discrete.items(),*residual.items()]:
            line.update({prefix+'__'+k:v for k,v in stats.items()})
        line.update({'change_from_pure__'+k:v for k,v in report['change_from_original_pure_LP'].items()})
        flat.append(line)
        del x,violation
    changed = [p for p,h in inputs.hashes.items() if sha(p)!=h]
    assert not changed, f'INPUT_CHANGED_DURING_CENSUS: {changed}'
    report = dict(workflow_integrity_PASS=True,scope='POSTCUT_SAVED_POINT_DIAGNOSTIC_ONLY',
        exact_base=BASE,optimize_calls=0,native_model_build_calls=0,candidate_constructor_calls=0,
        candidate_coefficients_SHA256=CANDIDATE_SHA,all_input_hashes_unchanged=True,
        input_SHA256=inputs.hashes,completed_cut_rounds=len(reports)-1,
        selected_cuts=len(selected),fractionality_and_violation_tolerance_unchanged=TOL,
        candidate_arithmetic='Direct binary64 sparse evaluation of the unchanged saved JSON; signed violation >1e-8.',
        minimum_mass_definition='sum(min(x,1-x)) over every original binary in the complete 9322-column map',
        retained_fractionality_is_not_a_proof_of_gap_causality=True,
        fractional_point_and_candidate_violations_are_not_valid_LB_certificates=True,
        raw_numeric_FAIL_from_any_round_is_explicitly_preserved=any(not r['raw_original_matrix_replay_PASS'] for r in reports),
        all_original_raw_matrix_replays_PASS=all(r['raw_original_matrix_replay_PASS'] for r in reports),
        rounds=reports)
    # No output is written until the complete input/provenance checks succeed.
    (OUT/'CUT_POINT_DIAGNOSTIC.json').write_text(json.dumps(report,ensure_ascii=False,
        indent=2,allow_nan=False)+'\n',encoding='utf-8')
    fields = list(dict.fromkeys(k for r in flat for k in r))
    with (OUT/'CUT_POINT_DIAGNOSTIC.csv').open('w',encoding='utf-8',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader();writer.writerows(flat)
    print(json.dumps(dict(completed_cut_rounds=len(reports)-1,
        final_fractional_by_family={f:v['fractional_count'] for f,v in reports[-1]['discrete_by_family'].items()},
        final_fractional_total=reports[-1]['discrete_total']['fractional_count'],
        final_violated_candidates=reports[-1]['remaining_candidate_violations_total']['violated_count'],
        no_optimize_calls=True,no_native_build_calls=True),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
