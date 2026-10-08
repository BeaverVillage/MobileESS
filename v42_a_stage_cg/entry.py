"""Continue only an actually completed, still-open prior integer case."""
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_compact_rowgen.resources import sample
from .policy import OUT

def entry():
    if (OUT/'CG_ENTRY_GATE.json').exists():raise PermissionError('CG_ENTRY_ALREADY_RECORDED')
    prior=read(OUT/'P2_CASE_RESULT.json');checkpoint=read(OUT/'P2_CASE_CHECKPOINT.json');build=read(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json')
    if prior.get('A1_accepted'):raise PermissionError('ACCEPTED_A1_MUST_PROCEED_TO_REQUESTED_CANARIES')
    if prior.get('stop_reason')!="RuntimeError('EXACT_INTEGER_CASE_OPEN_AT_COMPONENT_LIMIT')":raise PermissionError('MEASURED_OPEN_INTEGER_CASE_LIMIT_REQUIRED')
    if not build['PASS'] or not build['proof']['same_integer_feasible_schedules'] or record(build['snapshot']['path'])!=build['snapshot']:raise ValueError('QUALIFIED_EXACT_INTEGER_CG_BUILD_REQUIRED')
    budget=Budget();remaining=budget.remaining();memory=sample()
    if memory['unsafe']:raise RuntimeError('UNSAFE_RAM_OR_SYSTEM_COMMIT_AT_MINIMUM_ONE_WORKER')
    atomic(OUT/'CG_ENTRY_GATE.json',dict(PASS=True,original_case_result=record(OUT/'P2_CASE_RESULT.json'),
        old_open_queue_preserved=record(OUT/'P2_CASE_CHECKPOINT.json'),prior_valid_LB=checkpoint['valid_global_LB'],
        preserved_incumbent=checkpoint['incumbent'],exact_integer_equivalence=record(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json'),
        full_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),deadline=budget.record,remaining_seconds=remaining,
        resources=memory,workers=1,Threads=1,parameter_sweep=False,scientific_physics_tolerances_objectives_unchanged=True))
    print('CG_ENTRY_GATE',remaining,flush=True)
if __name__=='__main__':entry()
