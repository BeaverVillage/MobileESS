from v42_a_stage_compact_rowgen.policy import ROOT,OUT,STATIC,HISTORY,DAY
POLICY=dict(schema='A_PRACTICAL_INTEGER_V1',Threads=1,max_workers=4,control_allocation_seconds=1200,
    inherited_MIPGap=.005,integer_replay_tolerance=1e-5,continuous_rho_lock_epsilon=1e-7,
    native_control_bound_is_full_domain=False,full_domain_LB_requires_root_row_and_column_closure=True,
    SUM_projection_used_only_for_LP=True,migration_individual_binary_lanes_retained=True,
    checkpoint_nodes=10,checkpoint_seconds=300,physics_tolerances_objectives_changed=False)
