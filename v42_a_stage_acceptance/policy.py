from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_a_stage_acceptance_fourday_20261008'
STATIC=ROOT.parent/'v42-a-stage-acceptance-fourday-static'
OLD=Path('C:/Users/kjw39/Documents/Codex/2026-10-07/a-stage-compact-rowgen/docs/v42_a_stage_compact_rowgen_20261008')
BASE='8b90bdda26de480715e243249f62d46ff9bf1a54'
DAYS=('2025-05-19','2025-05-17','2025-05-10','2025-05-12')
POLICY=dict(schema='A_STAGE_FOURDAY_GLOBAL_GAP_CONTINUATION_V1',Threads=1,workers=1,max_workers=4,
    gap=.005,per_day_cumulative_native_seconds=3600,cumulative_native_seconds=14400,
    practical_end_to_end_target_seconds=3600,continuation_wall_guard_seconds=28800,
    run_order=DAYS,source_and_historical_receipts_immutable=True,physics_tolerance_objective_changes=False,
    zero_Phi_before_P1=True,full_domain_bound_required=True,row_promotion_after=19,
    activation_batch=64,stagnation_rounds=3,stagnation_fraction=.01)
POLICY.update(memory_limits_enabled=False,automatic_memory_stop=False,memory_telemetry_only=True)
