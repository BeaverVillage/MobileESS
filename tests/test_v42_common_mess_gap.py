"""Attack bound scope and verify solver/certificate telemetry without a solve."""
from fractions import Fraction
from pathlib import Path

import pytest

from v42_common_mess.telemetry import admit_solver_bound, verified_gap, root_lp, summarize_full


def full_identity():
    return dict(unrestricted_original_C3A_MILP=True, unrestricted_checks={key:True for key in (
        'all_original_bounds_exact','all_original_integer_types_exact',
        'all_original_rows_and_no_additional_cuts',
        'no_neighborhood_or_hamming_constraint','original_minimization')})


def transport():
    return dict(PASS=True,original_P1_bit_exact=True,integer_and_full_LP_domains_identical=True)


def test_restricted_U4_bound_never_global_even_when_better():
    bound, reason = admit_solver_bound(full_identity(),transport(),unrestricted=False,bound=.999,status=2)
    assert bound is None and reason == 'RESTRICTED_OR_UNPROVEN_DOMAIN'
    full = dict(method='FULL_MILP', solver_global_LB=.85, solver_global_gap_valid=True,
        solver_bound_provenance='EXACT_FULL_C3A_MILP_SOLVER_BOUND')
    restricted = dict(method='U4', solver_global_LB=.999, solver_global_gap_valid=True)
    summary = summarize_full([restricted, full], '1')
    assert summary['solver_global_LB'] == .85
    assert summary['solver_global_gap'] == pytest.approx(.15)


@pytest.mark.parametrize('check', list(full_identity()['unrestricted_checks']))
def test_full_equivalent_solver_bound_requires_every_domain_check(check):
    identity = full_identity(); identity['unrestricted_checks'][check] = False
    assert admit_solver_bound(identity,transport(),unrestricted=True,bound=.95,status=9)[0] is None


def test_full_equivalent_solver_bound_admitted_with_measured_runtime():
    assert admit_solver_bound(full_identity(),transport(),unrestricted=True,bound=.97,status=9) == (.97,None)
    assert admit_solver_bound(full_identity(),transport(),unrestricted=True,bound=.97,status=9,runtime_known=False)[0] is None
    assert admit_solver_bound(full_identity(),transport(),unrestricted=True,bound=.97,status=12)[0] is None
    assert admit_solver_bound(full_identity(),transport(),unrestricted=True,bound=.97,status=9,native_error_code=10014)[0] is None


def test_solver_gap_uses_verified_UB_and_never_becomes_independent_certified_gap():
    row = dict(method='FULL_MILP',Solver_ObjVal=1.1,Solver_ObjBound=.95,Solver_MIPGap=(1.1-.95)/1.1,
        solver_global_LB=.95,solver_global_gap_valid=True,Native_Runtime=17.,
        certified_Global_LB=None,certified_gap=None,
        solver_bound_provenance='EXACT_FULL_C3A_MILP_SOLVER_BOUND')
    summary = summarize_full([row], '1')
    assert summary['solver_global_gap'] == pytest.approx(.05)
    assert summary['Solver_MIPGap'] > summary['solver_global_gap']
    assert 'certified_Global_LB' not in summary and 'certified_gap' not in summary
    assert summary['solver_global_gap_valid'] and not summary['solver_global_gap_target_met']
    assert summary['Full_MILP_Native_Runtime'] == 17.


def test_invalid_inconsistent_nonfinite_and_zero_objective_gap_stay_unavailable():
    assert verified_gap('1',1.01) is None
    assert verified_gap('1',float('nan')) is None
    assert verified_gap('0',-.1) is None
    assert verified_gap('0',0.) == 0.
    assert verified_gap('1',.97) == pytest.approx(.03)


def test_actual_native_root_LP_log_time_excludes_presolve(tmp_path):
    logfile=tmp_path/'native.log'
    logfile.write_text('Presolve time: 3.00s\nRoot relaxation: objective 1.000000e+00, 12 iterations, 0.41 seconds (0.03 work units)\n')
    assert root_lp(logfile)==dict(Root_LP_seconds=.41,Root_LP_status='NATIVE_LOG_REPORTED')
    logfile.write_text('Root relaxation: interrupted, 19 iterations, 60.01 seconds (0.8 work units)\n')
    assert root_lp(logfile)==dict(Root_LP_seconds=60.01,Root_LP_status='NATIVE_LOG_ROOT_INTERRUPTED')
    logfile.write_text('Presolve: All rows and columns removed\n')
    assert root_lp(logfile)['Root_LP_seconds'] is None
    assert root_lp(logfile)['Root_LP_status']=='PRESOLVE_SOLVED_NO_ROOT_LP'


def test_final_solver_summary_preserves_strongest_full_bound_after_failed_retry():
    good=dict(method='FULL_MILP',Solver_ObjVal=1.,solver_global_LB=.98,
        solver_global_gap_valid=True,Native_Runtime=10.,telemetry_receipt={'path':'good.json'},
        original_model_identity={'path':'identity.json'},Root_LP_seconds=.3,B_and_B_Node_count=7)
    bad=dict(method='FULL_MILP',Solver_ObjVal=None,solver_global_LB=None,
        solver_global_gap_valid=False,Native_Runtime=2.,solver_bound_rejection_reason='NUMERIC')
    summary=summarize_full([good,bad], '1')
    assert summary['Solver_ObjVal'] is None
    assert summary['solver_global_LB']==.98 and summary['solver_global_gap_target_met']
    assert summary['full_MILP_telemetry']=={'path':'good.json'}
    assert summary['Full_MILP_Native_Runtime']==12.
    assert summary['Root_LP_seconds']==.3 and summary['B_and_B_Node_count']==7
