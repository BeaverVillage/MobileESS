from pathlib import Path
from v42_a_stage_phase1.setup import POLICY as PREVIOUS
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008'
STATIC=ROOT.parent/'v42-a-stage-residual-static'
HISTORY=ROOT/'docs/v42_a_stage_phase1_pricing_20261007'
DAY='2025-05-19'
POLICY=dict(PREVIOUS,schema='PHASE1_RESIDUAL_MIGRATION_V1',cumulative_budget_seconds=1200,
    budget_accounting='max(elapsed wall since RUN_STARTED, sum of every native Runtime); no resets',
    max_phase1_rounds=3,max_P1_rounds=0,max_pricing_workers=4,batch_maximum=64,
    STAY_limit_while_verified_migration_remains=32,migration_batch_limit=32,
    target_top_overall_classes=16,target_top_migration_capable_classes=16,
    targeted_class_order='union top16 overall and top16 migration-capable by residual influence; score descending then class ID',
    STAY_recovery_per_class=4,migration_recovery_per_class=2,
    query_order='complete migration-only native compact LP first, then complete STAY-only native LP for every targeted class',
    candidate_order='residual improvement score descending, exact rc ascending, stable class/site/path identity',
    STAY_fill='only after all targeted migration queries and recovery completed',
    duplicate_effect_key='class ID + exact physical coupling coefficient hash',
    second_batch_gate_relative_reduction=.01,nonmaterial_gate_relative_reduction=.01,
    max_new_native_columns_per_round=100000,
    scientific_domain_cap=False,permanently_deleted_candidates=0,
    final_closure='not authorized; certified zero -> artificial-free original replay -> STOP',
    start_model='PR176 final expanded active model including all48 activations; certify new initial optimum before new pricing',
    historical_R2='saved current optimal R2 is attributed before execution; retained final-expanded inclusion witness is not called an optimum',
    residual_score='heuristic signed effect from exact original coupling and global-row resource coefficients; original Pi controls admissibility')
for obsolete in ('cumulative_native_seconds','native_plus_pricing_wall_seconds'):
    POLICY.pop(obsolete)
