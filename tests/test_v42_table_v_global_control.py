"""Native0 Global Gap controller invariants and negative certificate attacks."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
import pytest

stage=os.environ.get('V42_PREPARATION_SOURCE_UNDER_TEST')
if stage:
    spec=importlib.util.spec_from_file_location('v42_integration.staged_global_control',Path(stage)/'v42_integration/table_v_global_control.py')
    control=importlib.util.module_from_spec(spec);sys.modules[spec.name]=control;spec.loader.exec_module(control)
else:
    from v42_integration import table_v_global_control as control


def scope(stage='A1'):
    return dict(source_sha='source',case_sha='case-'+stage,day='2025-05-01',arm='B1' if stage=='A1' else 'B3',
        stage=stage,matrix_sha='original-full-matrix-'+stage,domain_sha='domain',objective_sha='objective')


def upper(binding):
    return dict(PASS=True,binding=binding,original_FULL_replayed=True,integer_point=True,point_sha='point')


def lower(binding,kind):
    return dict(PASS=True,binding=binding,full_domain_pricing_complete=True,phase_I_zero_certified=True,
        original_FULL_integer_model=True,native_bound_valid=True,original_FULL_relaxation_proved=True,
        K=16 if kind=='K16' else 32 if kind=='K32' else 48)


@pytest.mark.parametrize('target,origin',[('.005','DW_FULL_PRICING'),('.005','ORIGINAL_INTEGER_MILP'),('.03','K16'),('.03','K32'),('.03','K48')])
def test_certified_target_causes_early_stage_termination(target,origin):
    binding=scope();bank=control.GlobalGapControl(binding,float(target))
    bank.offer_upper(1.,upper(binding));bank.offer_lower(.999,origin,lower(binding,origin))
    assert bank.target_met()
    assert bank.finish('NATIVE_BUDGET_EXHAUSTED')['termination_reason']=='GLOBAL_GAP_TARGET_MET'


def test_target_unmet_continues_real_nonduplicate_improvement_operations():
    binding=scope();bank=control.GlobalGapControl(binding,.005)
    bank.offer_upper(1.,upper(binding));bank.offer_lower(.8,'DW_FULL_PRICING',lower(binding,'DW_FULL_PRICING'))
    assert not bank.target_met()
    assert bank.begin_operation('ORIGINAL_FULL_BRANCH_AND_BOUND','model-1')
    bank.offer_lower(.997,'ORIGINAL_INTEGER_MILP',lower(binding,'ORIGINAL_INTEGER_MILP'))
    assert bank.target_met() and set(bank.bounds()['certified_LB_by_origin'])=={'DW_FULL_PRICING','ORIGINAL_INTEGER_MILP'}


def test_same_model_without_new_search_state_cannot_be_reexecuted():
    bank=control.GlobalGapControl(scope(),.005)
    assert bank.begin_operation('JOINT','same-matrix-domain-objective')
    assert not bank.begin_operation('JOINT','same-matrix-domain-objective')
    assert bank.begin_operation('JOINT','different-matrix-domain-objective')


@pytest.mark.parametrize('missing',('LB','UB'))
def test_missing_certificate_cannot_certify_gap(missing):
    binding=scope();bank=control.GlobalGapControl(binding,.005)
    if missing=='LB':bank.offer_upper(1.,upper(binding))
    else:bank.offer_lower(1.,'DW_FULL_PRICING',lower(binding,'DW_FULL_PRICING'))
    assert not bank.target_met() and bank.bounds()['Global_Gap'] is None
    with pytest.raises(ValueError):bank.finish('GLOBAL_GAP_TARGET_MET')


def test_restricted_joint_and_heuristic_bound_rejected():
    binding=scope();bank=control.GlobalGapControl(binding,.03)
    for kind in ('RESTRICTED_JOINT','HEURISTIC_SCORE','RESTRICTED_MASTER'):
        with pytest.raises(ValueError):bank.offer_lower(.999,kind,lower(binding,kind))
    assert not bank.lower


@pytest.mark.parametrize('key',control.SCOPE_KEYS)
def test_other_source_case_stage_matrix_objective_rejected(key):
    binding=scope();bank=control.GlobalGapControl(binding,.005);other=deepcopy(binding);other[key]='other'
    with pytest.raises(ValueError):bank.offer_lower(.999,'ORIGINAL_INTEGER_MILP',lower(other,'ORIGINAL_INTEGER_MILP'))
    with pytest.raises(ValueError):bank.offer_upper(1.,upper(other))


def test_full_feasible_solution_retained_when_budget_exhausted_above_target():
    binding=scope();bank=control.GlobalGapControl(binding,.03)
    bank.offer_upper(1.,upper(binding));bank.offer_lower(.4,'K48',lower(binding,'K48'))
    result=bank.finish('NATIVE_BUDGET_EXHAUSTED',Native_Runtime=1800.,cumulative_native_seconds=1800.)
    assert result['termination_reason']=='NATIVE_BUDGET_EXHAUSTED'
    assert result['FULL_feasible'] and result['physical_execution_allowed']
    assert not result['global_gap_certified']


def test_certified_lb_and_ub_are_monotone_and_separate_sources_preserved():
    binding=scope();bank=control.GlobalGapControl(binding,.005)
    bank.offer_upper(1.,upper(binding));bank.offer_upper(1.1,upper(binding))
    bank.offer_lower(.8,'DW_FULL_PRICING',lower(binding,'DW_FULL_PRICING'))
    bank.offer_lower(.7,'DW_FULL_PRICING',lower(binding,'DW_FULL_PRICING'))
    bank.offer_lower(.9,'ORIGINAL_INTEGER_MILP',lower(binding,'ORIGINAL_INTEGER_MILP'))
    assert bank.bounds()['Global_UB']==1. and bank.bounds()['Global_LB']==.9
    assert bank.bounds()['certified_LB_by_origin']['DW_FULL_PRICING']==.8


def test_inconsistent_bounds_do_not_create_false_zero_gap():
    binding=scope();bank=control.GlobalGapControl(binding,.005)
    bank.offer_upper(1.,upper(binding));bank.offer_lower(1.001,'K48',lower(binding,'K48'))
    assert bank.bounds()['Global_Gap'] is None and not bank.target_met()
    assert bank.bounds()['physical_execution_allowed']


def test_append_only_trace_contains_source_bounds_native_and_canonical_reason(tmp_path):
    binding=scope();bank=control.GlobalGapControl(binding,.005,tmp_path)
    bank.offer_upper(1.,upper(binding),Native_Runtime=2.,cumulative_native_seconds=2.)
    bank.finish('NO_FURTHER_CERTIFIED_IMPROVEMENT',Native_Runtime=2.,cumulative_native_seconds=2.)
    bank.close()
    import json
    rows=[json.loads(line) for line in (tmp_path/'GLOBAL_GAP_TRACE.jsonl').read_text(encoding='utf8').splitlines()]
    assert all(row['binding']==binding for row in rows)
    assert rows[-1]['termination_reason']=='NO_FURTHER_CERTIFIED_IMPROVEMENT'
    assert rows[-1]['cumulative_native_seconds']==2.
