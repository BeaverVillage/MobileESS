"""Exact evaluation of saved fractional coordinates against proven local facets."""
import csv
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parent


def exact(v):
    return Fraction(*float(v).as_integer_ratio())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    with (OUT/'CANDIDATE_VALID_INEQUALITIES.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    candidates = json.loads((OUT/'CANDIDATE_COEFFICIENTS.json').read_text(encoding='utf-8'))
    pool = {q['id']:q for q in candidates}
    basic = json.loads((OUT/'INEQUALITY_INDEPENDENT_VERIFICATION.json').read_text(encoding='utf-8'))
    folded = json.loads((OUT/'FOLDED_INEQUALITY_INDEPENDENT_VERIFICATION.json').read_text(encoding='utf-8'))
    approved = {q['id'] for q in basic['candidate_results'] if q['PASS']}
    approved |= {q['id'] for q in folded['reports'] if q['PASS']}
    assert basic['PASS'] and folded['PASS'] and set(pool) == approved
    with np.load(OUT/'PURE_LP_POINT.npz') as z:
        x = z['x']
    parent = OUT.parent/'v42_m1_ultracompact_exact_20261006'
    with np.load(parent/'C3A_VALID_START.npz') as z:
        start = z['point']
    witnesses = []
    for family in ('AGGREGATE_CONNECTED_POWER', 'LOCAL_CONNECTED_POWER', 'FOLDED_PCS_CONNECTED_POWER'):
        row = max((r for r in rows if r['family'] == family), key=lambda r:float(r['baseline_signed_violation']))
        cut = pool[row['id']]
        residual = sum((exact(w)*exact(x[int(j)]) for j,w in cut['terms'].items()), Fraction(0))-exact(cut['rhs'])
        start_residual = sum((exact(w)*exact(start[int(j)]) for j,w in cut['terms'].items()), Fraction(0))-exact(cut['rhs'])
        assert residual > 0 and start_residual <= exact(1e-8)
        witnesses.append(dict(id=cut['id'],family=family,MESS=cut['MESS'],slot=cut['slot'],site=cut['site'],
            exact_signed_violation=str(residual),signed_violation_float=float(residual),
            exact_start_signed_violation=str(start_residual),independently_proven_candidate=True,
            captured_projection_outside_tested_conservative_local_hull=True,
            compared_tolerance=1e-8, violation_to_tolerance_ratio=float(residual)/1e-8))
    report = dict(PASS=True, no_optimize_calls=True, no_model_build_calls=True,
        coefficient_and_point_arithmetic='Exact dyadic binary64 interpreted as Fraction',
        original_point_raw_matrix_replay_PASS=False,
        not_an_exact_C3A_feasible_point_or_optimality_certificate=True,
        statement='The saved projected coordinates violate independently valid local facets exactly. This does not prove that every LP optimum violates them, or quantify the global integer gap.',
        source_SHA256={n:sha(OUT/n) for n in ('PURE_LP_POINT.npz','CANDIDATE_COEFFICIENTS.json','INEQUALITY_INDEPENDENT_VERIFICATION.json','FOLDED_INEQUALITY_INDEPENDENT_VERIFICATION.json')},
        witnesses=witnesses)
    (OUT/'LOCAL_HULL_SEPARATION_WITNESS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(witnesses,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
