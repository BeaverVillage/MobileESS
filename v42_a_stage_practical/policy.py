from v42_a_stage_compact_rowgen.policy import ROOT,OUT,STATIC,HISTORY,DAY
POLICY=dict(schema='A_PRACTICAL_ROWCOL_STAGE_V1',Threads=1,workers=1,max_workers=4,budget_seconds=28800,
    row_tolerance=1e-6,price_epsilon='1/100000000',target_top_overall_classes=16,target_top_migration_capable_classes=16,
    STAY_recovery_per_class=4,migration_recovery_per_class=2,batch_size=64,stagnation_consecutive_rounds=3,
    original_P1_requires_zero=True,full_native_fractional_LP_coverage=True,integer_certificate_separate=True,
    physics_tolerances_objectives_changed=False,candidates_permanently_deleted=0)
