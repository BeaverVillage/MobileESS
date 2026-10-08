"""Adversarial final scientific admission tests; all models are synthetic."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_m1_research.check_joint import (
    VerifiedBound, aggregate_exact_bounds, check_case_identity, check_ledger,
    evaluate_evidence, reconstruct_complete_cover, reconstruct_retained_domain,
    check_exact_integer_replay, evaluate_complete_count_bound)


def case_fixture():
    units = ['MESS01', 'MESS02', 'MESS03', 'MESS04']
    names = [f'node_activity[{u},STA01,{t}]' for t in (66, 72) for u in units]
    # Distinct original grid and physics rows permit a deletion-only audit.
    A = sparse.csr_matrix(np.array([[1.]*8, [2.]+[0.]*7, [0., 3.]+[0.]*6]))
    d = dict(names=np.array(names), lower=np.zeros(8), upper=np.ones(8),
             types=np.full(8, 'B'), objective=np.ones(8), constant=np.array(0.),
             rhs=np.array([8., 2., 3.]), sense=np.array(['<', '<', '<']),
             row_names=np.array(['flow[MESS01,0]', 'line_thermal_face[0,66]', 'voltage_upper[0,72]']))
    return SimpleNamespace(A=A, d=d, case_sha='synthetic_same_case',
                           graph=(['STA01'], {u:'STA01' for u in units}, [], None, {}))


def count_report(case):
    return dict(cover=dict(case_sha=case.case_sha, original_binary_columns=list(range(8)),
                           exact_leaf_rows=[dict(sense='<', rhs=3), dict(sense='>', rhs=4)]),
                leaves=[dict(leaf=0), dict(leaf=1)])


def ledger_fixture():
    calls = [dict(track='LB', label='failed', case_sha='same_case', state='FAILED',
                  Native_Runtime=100., Native_Work=20., requested_seconds=200.,
                  allocated_native_seconds=200., measured_Native_Runtime=100.,
                  runtime_unavailable=False, runtime_accounting_scope='MEASURED',optimize_wall_seconds=110.),
             dict(track='UB', label='finished', case_sha='same_case', state='FINISHED',
                  Native_Runtime=50., Native_Work=10., requested_seconds=100.,
                  allocated_native_seconds=100., measured_Native_Runtime=50.,
                  runtime_unavailable=False, runtime_accounting_scope='MEASURED',optimize_wall_seconds=55.)]
    return dict(case_sha='same_case', total_native_limit_seconds=5400., Threads=1,
                scientific_tolerances=dict(Threads=1, MIPGap=.005, FeasibilityTol=1e-8,
                                           OptimalityTol=1e-8, IntFeasTol=1e-8),
                memory_limits=False, memory_automatic_stop=False, historical_ledgers_modified=False,
                inflight=None, calls=calls, transfers=[], allocations={'LB':3600.,'UB':1800.},
                Native_Runtime_sum=150., native_measured_Runtime_sum=150.,
                track_Runtime={'LB':100.,'UB':50.}, Native_Work_sum=30.,
                non_native_wall_costs=[dict(kind='build', wall_seconds=13.)],
                wall_seconds=200., practical_wall_PASS=True,
                native_accounting_PASS=True, native_runtime_measurement_complete=True)


def test_nested_case_mismatch_rejected_before_joint_gap():
    with pytest.raises(ValueError, match='CASE_MISMATCH'):
        check_case_identity(dict(case_sha='same', leaves=[dict(certificate=dict(case_sha='other'))]), 'same')
    bound = VerifiedBound('other', F(3, 5), 'FULL_ORIGINAL_C3A', 'wrong_case')
    with pytest.raises(ValueError, match='CASE_MISMATCH'):
        aggregate_exact_bounds('same', [bound], F(63, 100))


def test_old_native_bound_cannot_enter_fresh_exact_gap():
    claimed = dict(PASS=True, independently_certified_LB=.5687116104049206,
                   native_BestBd=.5687116104049206, scope='FULL_ORIGINAL_C3A')
    with pytest.raises(ValueError, match='METADATA_OR_NATIVE_BOUND_NOT_ELIGIBLE'):
        aggregate_exact_bounds('same', [claimed], F(.6284141956452488))
    fresh = VerifiedBound('same', F(.5671374761409242), 'FULL_ORIGINAL_C3A', 'fresh_exact_root')
    r = aggregate_exact_bounds('same', [fresh], F(.6284141956452488))
    assert r['independently_certified_Global_LB'] == .5671374761409242
    assert r['preserved_native_Global_LB'] == .5687116104049206
    assert r['certified_Global_Gap_percent_upper'] > r['preserved_native_Global_Gap_percent']
    assert not r['inherited_native_LB_reclassified_exact']


@pytest.mark.parametrize('scope', ['RESTRICTED_NEIGHBORHOOD', 'NATIVE_ObjBound', 'ARCHIVED_HULL_METADATA'])
def test_restricted_native_and_unreplayed_archived_bound_scopes_rejected(scope):
    with pytest.raises(ValueError, match='NOT_GLOBAL_LB'):
        aggregate_exact_bounds('same', [VerifiedBound('same', F(62,100), scope, 'unqualified')], F(63,100))


def test_exact_gap_boundary_has_separate_P1_scope_and_never_P2_acceptance():
    lb = VerifiedBound('same', F(199,200), 'COMPLETE_INTEGER_COVER', 'complete')
    r = aggregate_exact_bounds('same', [lb], F(1))
    assert r['certified_Global_Gap_exact'] == '1/200'
    assert r['M1_P1_GAP_CERTIFIED'] is True
    assert r['M1_ACCEPTED'] is False and r['P2_certificate'] is None
    assert F(r['certified_Global_Gap_fraction_upper']) >= F(1,200)
    too_low = VerifiedBound('same', F(199,200)-F(1,10**12), 'FULL_ORIGINAL_C3A', 'not_enough')
    assert not aggregate_exact_bounds('same', [too_low], F(1))['M1_P1_GAP_CERTIFIED']


def test_bound_exceeding_integer_UB_is_not_hidden_as_zero_gap():
    with pytest.raises(ValueError, match='BOUND_ORDER'):
        aggregate_exact_bounds('same', [VerifiedBound('same', F(2), 'FULL_ORIGINAL_C3A', 'bad')], F(1))


def test_numerically_accepted_near_integer_is_not_an_exact_raw_witness():
    receipt=dict(PASS=True,C3A=dict(integer_pattern_exact=True,exact_binary_0_1=True),
                 original_full_matrix=dict(integer_pattern_exact=True,exact_binary_0_1=True))
    assert check_exact_integer_replay(receipt)
    receipt['C3A']['integer_pattern_exact']=False
    with pytest.raises(ValueError,match='INTEGER_PATTERN_NOT_EXACT'):
        check_exact_integer_replay(receipt)


def test_complete_count_cover_is_reconstructed_from_all_original_rows():
    case = case_fixture()
    leaves, checked = reconstruct_complete_cover(case, count_report(case))
    assert checked['every_original_integer_plan_covered']
    assert checked['all_original_96_slot_rows_in_each_leaf']
    for leaf in leaves:
        assert leaf.A.shape == (4,8)
        assert (leaf.A[:-1] != case.A).nnz == 0
        assert np.array_equal(leaf.d['objective'], case.d['objective'])
    assert leaves[0].d['rhs'][-1] == 3
    assert leaves[1].d['rhs'][-1] == 4


def test_strong_one_leaf_bound_cannot_replace_minimum_of_ALL_leaves(tmp_path):
    case=case_fixture()
    joint=count_report(case)
    for index, dual in enumerate((np.zeros(4), np.array([0.,0.,0.,1.]))):
        path=tmp_path/f'leaf{index}.npz'
        np.savez_compressed(path,dual=dual)
        joint['leaves'][index]['certificates']=[dict(
            PASS=True, independently_certified_LB=999., # Deliberately false metadata.
            dual_evidence=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),npz_key='dual'))]
    bound,checked=evaluate_complete_count_bound(case,joint,run_path=tmp_path)
    assert [r['exact_leaf_LB'] for r in checked['ALL_leaf_certificates']]==['0','4']
    assert bound.exact==F(0)
    assert aggregate_exact_bounds(case.case_sha,[bound],F(6))['certified_Global_Gap_exact']=='1'


def test_incomplete_or_holey_cover_never_promotes_a_child_bound():
    case = case_fixture()
    report = count_report(case)
    report['leaves'].pop()
    with pytest.raises(ValueError, match='INCOMPLETE_LEAF_COVER'):
        reconstruct_complete_cover(case, report)
    report = count_report(case)
    report['cover']['exact_leaf_rows'][1]['rhs'] = 5
    with pytest.raises(ValueError, match='SPLIT_HAS_HOLE'):
        reconstruct_complete_cover(case, report)


def test_cover_cannot_drop_one_vehicle_or_change_original_binary_domain():
    case = case_fixture()
    case.d['names'][3] = 'node_activity[MESS03,STA01,66]'
    with pytest.raises(ValueError, match='ALL_FOUR_FLEETS'):
        reconstruct_complete_cover(case, count_report(case))
    case = case_fixture()
    case.d['types'][0] = 'C'
    with pytest.raises(ValueError, match='NOT_ORIGINAL_BINARY'):
        reconstruct_complete_cover(case, count_report(case))


def requirement(case, row=1):
    a,b=case.A.indptr[row:row+2]
    return dict(case_sha=case.case_sha, selected_original_grid_rows=[dict(
        row=row, family=str(case.d['row_names'][row]).split('[',1)[0],
        sense=str(case.d['sense'][row]), rhs=float(case.d['rhs'][row]),
        original_coefficients_SHA256=hashlib.sha256(case.A.data[a:b].tobytes()).hexdigest(),
        variables=list(map(int,case.A.indices[a:b])))])


def test_retained_R_rebuild_ignores_producer_PASS_and_keeps_all_physics():
    case = case_fixture()
    record = requirement(case)
    record['PASS'] = False  # This flag is irrelevant to independent domain proof.
    R,e,keep,proof = reconstruct_retained_domain(case, record)
    assert list(keep) == [0,1]
    assert R.shape == (2,8) and proof['PASS']
    assert np.array_equal(e['types'], case.d['types'])
    record['selected_original_grid_rows'][0]['rhs'] = 999.
    with pytest.raises(ValueError, match='AFFINE_RHS_DRIFT'):
        reconstruct_retained_domain(case, record)


def test_independent_multiplier_recompute_rejects_hash_mutation_and_no_native_objective(tmp_path):
    assert tmp_path.drive.upper() == 'D:'
    case = case_fixture()
    path = tmp_path/'rational.json'
    # Exact valid signed row multiplier c>=0 leaves the original finite-box LB0.
    path.write_text(json.dumps({'0':'-1/2'}), encoding='utf-8')
    evidence=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    r=evaluate_evidence(case.A,case.d,evidence,case.case_sha,run_path=tmp_path)
    assert r['exact_bound'] == '-4'
    assert not r['native_objective_used'] and not r['native_BestBd_used']
    path.write_text(json.dumps({'0':'1/2'}), encoding='utf-8')
    with pytest.raises(ValueError, match='HASH_DRIFT'):
        evaluate_evidence(case.A,case.d,evidence,case.case_sha,run_path=tmp_path)
    evidence['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='INVALID_DUAL_ROW_SIGN'):
        evaluate_evidence(case.A,case.d,evidence,case.case_sha,run_path=tmp_path)


def test_accounting_includes_failed_calls_and_independent_non_native_costs():
    receipt=ledger_fixture()
    checked=check_ledger(receipt,'same_case')
    assert checked['Native_Runtime_sum']==150.
    assert checked['failed_native_calls']==1
    assert checked['non_native_wall_costs_separate']
    receipt['Native_Runtime_sum']=50. # Omitting the failed call cannot pass.
    with pytest.raises(ValueError, match='RUNTIME_SUM_DRIFT'):
        check_ledger(receipt,'same_case')


def test_enclosing_R_cost_is_derived_exclusive_without_modifying_ledger():
    receipt=ledger_fixture()
    receipt['calls'][0]['label']='JOINT_MULTITIME_R_LP'
    receipt['calls'][1].update(track='LB',label='JOINT_MULTITIME_R_MILP')
    receipt['track_Runtime']={'LB':150.,'UB':0.}
    receipt['non_native_wall_costs']=[dict(kind='model_preparation_and_validation',
                                         label='MULTITIME_R_PREPARATION',track='LB',wall_seconds=178.)]
    before=deepcopy(receipt)
    checked=check_ledger(receipt,'same_case')
    assert receipt==before
    assert checked['raw_non_native_cost_contexts_are_all_exclusive'] is False
    assert checked['measured_native_optimize_wall_seconds']==165.
    assert checked['recorded_exclusive_non_native_wall_seconds']==13.
    assert checked['derived_exclusive_non_native_costs'][0]['nested_native_optimize_wall_seconds']==165.
    assert checked['derived_exclusive_non_native_costs'][0]['raw_recorded_wall_seconds']==178.


@pytest.mark.parametrize('mutation', ['inflight','tolerance','memory','case','measurement'])
def test_unfinished_or_scientifically_incompatible_ledger_rejected(mutation):
    receipt=ledger_fixture()
    if mutation=='inflight':receipt['inflight']=dict(state='IN_FLIGHT')
    elif mutation=='tolerance':receipt['scientific_tolerances']['IntFeasTol']=1e-5
    elif mutation=='memory':receipt['memory_limits']=True
    elif mutation=='case':receipt['calls'][0]['case_sha']='other'
    else:receipt['calls'][0]['runtime_unavailable']=True
    with pytest.raises(ValueError):
        check_ledger(receipt,'same_case')


def test_accounting_unused_transfer_is_proved_at_actual_call_prefix():
    receipt=ledger_fixture()
    receipt['transfers']=[dict(source='UB',target='LB',seconds=1000.,used_before=150.,
                               source_used_before=50.,target_used_before=100.)]
    receipt['allocations']={'LB':4600.,'UB':800.}
    assert check_ledger(receipt,'same_case')['unused_transfers_checked']==1
    receipt['transfers'][0]['seconds']=1800.
    receipt['allocations']={'LB':5400.,'UB':0.}
    with pytest.raises(ValueError, match='ALREADY_SPENT'):
        check_ledger(receipt,'same_case')


def test_LEDGER_overshoot_cannot_be_retroactively_covered_by_transfer():
    receipt=ledger_fixture()
    receipt['calls']=receipt['calls'][:1]
    row=receipt['calls'][0]
    row.update(Native_Runtime=3601.,measured_Native_Runtime=3601.,requested_seconds=3600.,allocated_native_seconds=3600.)
    receipt.update(Native_Runtime_sum=3601.,native_measured_Runtime_sum=3601.,
                   track_Runtime={'LB':3601.,'UB':0.},Native_Work_sum=20.,allocations={'LB':3700.,'UB':1700.})
    receipt['transfers']=[dict(source='UB',target='LB',seconds=100.,used_before=3601.,source_used_before=0.,target_used_before=3601.)]
    with pytest.raises(ValueError, match='CANNOT_BE_BACKFILLED'):
        check_ledger(receipt,'same_case')
