from v42_a_stage_lexrefine.policy import ROOT,OUT,STATIC,DAY,POLICY as REFINE_POLICY
POLICY=dict(REFINE_POLICY,schema='A_PRACTICAL_LEX_EXHAUSTIVE_INTEGER_CASES_V1',control_allocation_seconds=1200,case_allocation_seconds=3600,exact_integer_objective_definition=True,branch='Z=ceil(validLB) OR Z>=ceil(validLB)+1')
