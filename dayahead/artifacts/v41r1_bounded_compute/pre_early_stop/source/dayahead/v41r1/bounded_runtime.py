"""Policy-day scope for every optimization component, including MESS children."""
import os
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import OUT,record
from .bounded_solver import PolicyBudget,CONTRACT


def activate(context,policy,output):
    contract=OUT/'F_AND_O_COMPUTE_CONTRACT.json'
    acceptance=os.environ.get('V41_FO_ACCEPTANCE')=='1'
    if not contract.exists() and not acceptance:return False
    if contract.exists():
        value=read(contract)
        if value.get('contract')!=CONTRACT or value.get('status')!='FROZEN':raise ValueError('F_AND_O_COMPUTE_CONTRACT_NOT_FROZEN')
        total=1800.
    else:
        total=float(os.environ.get('V41_FO_ACCEPTANCE_SECONDS','1800'))
    context.v41_bounded_compute=dict(total_seconds=total,fix_and_optimize=True)
    context.v41_policy_budget=PolicyBudget(total);context.v41_policy=policy
    context.v41_a1_output=Path(output)/'A1';context.v41_mf_output=Path(output)/'MF'
    write_json(Path(output)/'POLICY_DAY_COMPUTE_START.json',dict(contract=CONTRACT,policy=policy,day=context.day,
        total_optimization_seconds=total,shared_across='A0/M1/A1/MF and all objective stages',
        mode='COMPUTATIONAL_ACCEPTANCE' if acceptance else 'FROZEN_FULL_MAY',
        source=None if not contract.exists() else record(contract)))
    return True


def finish(context,output):
    if not hasattr(context,'v41_policy_budget'):return
    budget=context.v41_policy_budget
    output=Path(output)
    if budget.used>budget.total+5:raise RuntimeError('POLICY_DAY_SHARED_BUDGET_OVERRUN')
    write_json(Path(output)/'POLICY_DAY_COMPUTE_REPORT.json',dict(contract=CONTRACT,day=context.day,policy=context.v41_policy,
        total_budget_seconds=budget.total,optimization_seconds=budget.used,remaining_seconds=budget.remaining,
        calls=budget.calls,Fresh_and_Actual_in_optimization_budget=False,
        physical_constraint_relaxation=False,scientific_candidate_pruning=False))
    source=output/('A1' if context.v41_policy=='B3' else 'A0')/'V41R1_FULL_CANDIDATE_MANIFEST.json'
    if source.exists():
        value=read(source);value['stage_manifest']=record(source)
    else:
        seed=read(output/'policy_seed/POLICY_REFERENCE_SEED.json')
        from dayahead.paper_analysis.storage import digest
        value=dict(day=context.day,policy=context.v41_policy,status='PASS',
            candidate_set_SHA=digest(seed['jobs']),final_authoritative_candidates=len(seed['jobs']),
            PENDING_relocation_candidates=0,RUNNING_migration_candidates=0,total_destination_arcs=0,
            eligible_relocation_jobs=0,eligible_migration_jobs=0,hard_infeasible_removals=0,reason_counts={},
            authority='POLICY_FIXES_ALL_AIDC_CHOICES; NO_COMPUTATIONAL_PRUNING',top_K_pruning=0,sensitivity_pruning=0)
    write_json(output/'V41R1_FULL_CANDIDATE_MANIFEST.json',value)
    coverage=source.parent/'CANDIDATE_COVERAGE_REPORT.json'
    if coverage.exists():
        value=read(coverage);value['stage_coverage']=record(coverage)
    else:value=dict(total_eligible_candidates=0,unique_candidates_ever_opened=0,fraction_candidates_visited=1.,
        candidates_never_opened=0,scientific_candidate_pruning=0,reason='POLICY_HAS_NO_FREE_AIDC_DECISIONS')
    write_json(output/'CANDIDATE_COVERAGE_REPORT.json',value)
