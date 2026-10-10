"""Explicit feasible handoff; certified optimality is a separate assertion."""
from fractions import Fraction
from .authority import active

def enabled():
    m=active()
    return bool(m and m.get('A_anytime_FULL_feasible') is True)

def normal_budget_exception(error):
    return type(error).__name__ in ('BudgetStop','NativeBudgetExhausted') or (
        type(error).__name__=='RuntimeError' and str(error).startswith('BudgetStop: ')
        and str(error).split(': ',1)[1] in ('NATIVE_RUNTIME_CEILING_EXCEEDED','DATE_NATIVE_RUNTIME_BUDGET_EXHAUSTED','A_DATE_NATIVE_BUDGET_EXHAUSTED'))

def a_contract(certified, candidate, physical):
    # Original contract rejects all non-gap failures before returning `gap`.
    # Its Phase I, complete pricing, original rows, integer types and schedule
    # proofs remain prerequisites. No LP or incomplete point is admitted.
    if not enabled():return certified
    valid=(candidate.get('PASS') is True and candidate.get('original_integer_types_restored') is True
        and physical.get('PASS') is True and physical.get('original_job_population_verified') is True
        and physical.get('original_integer_types_restored') is True
        and physical.get('scientific_primal_replay',{}).get('PASS') is True
        and physical.get('integral_max_residual',float('inf'))<=1e-5
        and physical.get('original_P1_objective_consistency') is True
        and 'gap' in certified and certified['gap'] is not None and not certified.get('reason'))
    if not valid:raise ValueError('SVR11_A_COMPLETE_ORIGINAL_INTEGER_PHYSICAL_CERTIFICATES_REQUIRED')
    lower,upper=Fraction(candidate['exact_LB']),Fraction(candidate['exact_UB'])
    if not 0<=lower<=upper:raise ValueError('SVR11_A_EXACT_BOUND_CONFLICT')
    return dict(certified,PASS=True,A1_P1_ONLY_ACCEPTED=True,FULL_feasible_certified=True,
        global_gap_certified=certified.get('PASS') is True,
        original_gap_contract_PASS=certified.get('PASS') is True,
        criterion='FULL original integer and physical feasibility; global gap certification recorded separately',
        original_gap_target=.005,global_optimum_claim=False)

def solver_label(result):
    status=result.get('classification',result.get('status',''))
    if status in ('TIME_LIMIT_FEASIBLE_ACCEPTED','TIME_LIMIT_FEASIBLE'):return 'TIME_LIMIT · FEASIBLE'
    if status in ('TIME_LIMIT_NO_FEASIBLE','TIME_LIMIT_NO_VALID_INCUMBENT'):return 'TIME_LIMIT · NO SOLUTION'
    # A relative gap certificate is not an exact optimum certificate.
    if result.get('native_status')==2 and result.get('exact_gap') in ('0',0):return 'OPTIMAL'
    if result.get('global_gap_certified'):return 'GAP CERTIFIED'
    if result.get('PASS') or result.get('feasible_accepted'):return 'FEASIBLE'
    return status or '대기'
