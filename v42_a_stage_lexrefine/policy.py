from v42_a_stage_lexfull.policy import ROOT,OUT,STATIC,DAY,POLICY as FULL_POLICY
POLICY=dict(FULL_POLICY,schema='A_PRACTICAL_LEX_INTEGER_REFINEMENT_V1',control_allocation_seconds=1200,integer_partition='objective<=UB-1 OR objective>=UB',native_bound_full_domain_only_after_complete_relevant_domain=True)
