"""Adversarial certificate checks only; no optimization or audit overwrite."""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
from independent_hull import Authority, F, TOL, exact, sha, OUT, PARENT
from folded_pcs_hull import verify_folded_candidate, FAMILY as FOLDED_FAMILY


def check_power(candidate, authority, start):
    # The same verifier primitives as verify_candidates, without its audit writer.
    terms, rhs = authority.reconstructed_candidate(candidate)
    actual = {int(j): exact(w) for j, w in candidate['terms'].items() if exact(w)}
    assert actual == terms, 'SELECTED_COORDINATE_TERMS_MISMATCH'
    assert exact(candidate['rhs']) == rhs, 'SELECTED_COORDINATE_RHS_MISMATCH'
    residual = sum((w * exact(start[j]) for j, w in terms.items()), F(0)) - rhs
    assert residual <= TOL, 'VALIDATED_START_VIOLATION'
    return dict(PASS=True, exact_start_residual=str(residual))


def main():
    watched = [OUT / 'LOCAL_INTEGER_HULL_AUDIT.json',
               OUT / 'INEQUALITY_INDEPENDENT_VERIFICATION.json',
               OUT / 'CANDIDATE_COEFFICIENTS.json',
               OUT / 'independent_hull.py', OUT / 'folded_pcs_hull.py']
    before = {str(p.name): sha(p) for p in watched}
    candidates = json.loads((OUT / 'CANDIDATE_COEFFICIENTS.json').read_text(encoding='utf-8'))
    original_power = next(c for c in candidates
                          if c['family'] == 'LOCAL_CONNECTED_POWER'
                          and len(c['terms']) >= 3 and any(w > 0 for w in c['terms'].values()))
    original_folded = next(c for c in candidates if c['family'] == FOLDED_FAMILY)
    authority = Authority()
    with np.load(PARENT / 'C3A_VALID_START.npz') as z:
        start = z['point'].copy()
    context = {'start': start}
    controls = [dict(kind='ORIGINAL_POWER_ACCEPTED', candidate_id=original_power['id'],
                     result=check_power(original_power, authority, start)),
                dict(kind='ORIGINAL_FOLDED_ACCEPTED', candidate_id=original_folded['id'],
                     result=verify_folded_candidate(original_folded, context, authority))]
    mutations = []

    def test(kind, original, change):
        mutated = deepcopy(original)
        change(mutated)
        mutated['id'] = original['id'] + ':MUTATION:' + kind
        try:
            if mutated['family'] == FOLDED_FAMILY:
                verify_folded_candidate(mutated, context, authority)
            else:
                check_power(mutated, authority, start)
            record = dict(kind=kind, original_candidate_id=original['id'], rejected=False,
                          failure='MUTATION_UNEXPECTEDLY_ACCEPTED')
        except (AssertionError, KeyError, ValueError) as exc:
            record = dict(kind=kind, original_candidate_id=original['id'], rejected=True,
                          rejection_type=type(exc).__name__, reason=str(exc))
        mutations.append(record)

    def increase_positive_coefficient(candidate):
        key = next(j for j, w in candidate['terms'].items() if w > 0)
        candidate['terms'][key] += 1.

    def wrong_selected_column(candidate):
        key = next(iter(candidate['terms']))
        coefficient = candidate['terms'].pop(key)
        with np.load(PARENT / 'C3A_DATA.npz') as z:
            names = z['names'].copy()
        rho = int(np.flatnonzero(names == 'rho_max')[0])
        assert str(rho) not in candidate['terms']
        candidate['terms'][str(rho)] = coefficient

    def wrong_existing_site(candidate):
        candidate['site'] = next(s for s in authority.sites if s != candidate['site'])

    for original, prefix in [(original_power, 'POWER'), (original_folded, 'FOLDED')]:
        test(prefix + '_RHS_MINUS_ONE', original, lambda c: c.__setitem__('rhs', c['rhs'] - 1.))
        test(prefix + '_COEFFICIENT_PLUS_ONE', original, increase_positive_coefficient)
        test(prefix + '_WRONG_EXISTING_SITE', original, wrong_existing_site)
        test(prefix + '_UNKNOWN_SITE_NAME', original, lambda c: c.__setitem__('site', '__NOT_AN_AUTHORIZED_SITE__'))
        test(prefix + '_WRONG_SLOT_SOURCE_MAPPING', original, lambda c: c.__setitem__('slot', (c['slot'] + 1) % 96))
        test(prefix + '_WRONG_SELECTED_COLUMN_SOURCE_MAPPING', original, wrong_selected_column)
    test('FOLDED_GAMMA_MINUS_100', original_folded, lambda c: c.__setitem__('gamma', c['gamma'] - 100.))
    test('FOLDED_NEGATIVE_GAMMA', original_folded, lambda c: c.__setitem__('gamma', -1.))
    after = {str(p.name): sha(p) for p in watched}
    assert before == after, 'PREREGISTERED_PROOF_OR_AUDIT_FILE_CHANGED'
    passed = all(r['rejected'] for r in mutations)
    report = dict(PASS=passed, controls=controls, mutations=mutations,
                  mutation_count=len(mutations), rejected_count=sum(r['rejected'] for r in mutations),
                  no_solver_calls=True, production_constructor_called=False,
                  primary_verification_and_local_hull_audit_not_overwritten=True,
                  immutable_proof_file_hashes_before=before, immutable_proof_file_hashes_after=after,
                  source='CANDIDATE_COEFFICIENTS.json',
                  rejection_scope='Exact certified-schema or original-vertex validity rejection; not a claim that every conceivable alternative coefficient is invalid.')
    (OUT / 'INEQUALITY_MUTATION_REJECTION.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert passed, 'AT_LEAST_ONE_MUTATION_NOT_REJECTED'
    print('INEQUALITY_MUTATION_REJECTION_DONE', len(mutations), 'all rejected', flush=True)


if __name__ == '__main__':
    main()
