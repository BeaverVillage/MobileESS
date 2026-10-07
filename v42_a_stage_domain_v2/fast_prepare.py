"""Preregister engineering policies before the first fast native diagnostic."""
from pathlib import Path
from v42_pr134_b1.common import atomic,read,record,digest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_a_stage_fast_active_domain_20261007'
OLD=ROOT/'docs/v42_a_stage_v2_stress4_20261007'
CENSUS=ROOT/'docs/v42_a_stage_domain_authority_v2_20261007'
STATIC=ROOT.parent/'v42-a-stage-fast-active-static'
DAYS=('2025-05-17','2025-05-19','2025-05-12','2025-05-10')


def preregister():
    OUT.mkdir(parents=True,exist_ok=True);STATIC.mkdir(parents=True,exist_ok=True)
    policy=dict(PASS=True,schema='FAST_ACTIVE_INITIAL_POLICY_V1',same_site_radius=2,
        extra_stay_per_class=8,migration_extra_seeds=0,mandatory_support_uncapped=True,
        scientific_domain_cap=False,permanent_speed_deletion=False,
        required=['valid_no_flex_anchor','historical_hard_valid_STAY','validated_rescue',
                  'independently_replay_valid_incumbent'],
        migration_initial='finite validated rescue and independently verified incumbent support only',
        induced_native_STAY_and_recombined_migration_counted=True,
        matrix_evidence=record(CENSUS/'MAY19_STATIC_DOMAIN_CENSUS.json'),
        rationale='197537 physical STAY versus34426 historical STAY; old migration seed represented11737638 paths; mandatory support retained, only optional extras capped',
        cap_tuned_after_canary=False,batch=dict(initial=64,minimum=32,maximum=256,
            high_density_threshold=.5,low_density_threshold=.1,
            adaptation='double above high density, halve below low density; pricing statistics only'),
        max_pricing_iterations=4,max_activation_batch=256,
        pricing=dict(migration_scan_limit=4096,migration_order='CANONICAL_BLOCK_KEY_ROTATING_FINITE_PREFIX',
            stay_scan='EXHAUSTIVE_INACTIVE_STAY'),
        canary_native_budget_seconds=300,production_native_budget_seconds=3600,
        preferred_full_A1_seconds=1800,solver_parameter_sweep=False)
    target=OUT/'ACTIVE_DOMAIN_POLICY.json'
    if target.exists():
        prior=read(target)
        if prior!=policy:
            if any(OUT.glob('MAY*_CANARY/FAST_STARTED.json')) or any(prior.get(k)!=policy.get(k)
                for k in ('same_site_radius','extra_stay_per_class','migration_extra_seeds')):
                raise ValueError('IMMUTABLE_INITIAL_POLICY_DRIFT')
            atomic(OUT/'PRE_NATIVE_POLICY_FINALIZATION.json',dict(PASS=True,previous=record(target),
                native_calls_before_finalization=0,initial_selection_caps_changed=False,
                added_explicit_bounded_pricing_scan_and_iteration_policy=True))
            atomic(target,policy)
    else:atomic(target,policy)
    ranking=dict(PASS=True,ranking_only=True,low_grid_benefit_deletion=False,
        score='negative GPU-weighted sum of frozen signed critical thermal-load coefficients over exact occupancy; current anchor utilization weights',
        critical_weights='max(anchor_current_utilization - 90th percentile,0); all frozen branch phases retained',
        ordering='within each class: descending score, absolute reference distance, same site first, start, site',
        score_inputs='same-day original frozen electrical certificate; per-date coefficient digest written before optimize',
        original_physics_coefficients_changed=False,activation_policy_sha256=record(target)['sha256'])
    atomic(OUT/'ACTIVE_STAY_RANKING_POLICY.json',ranking)
    baseline=read(OLD/'MAY19/A1_RESULT.json');stage=baseline['passes'][0]
    values=stage['model_census']
    baseline_doc=dict(PASS=True,classification='COMPLETE_STAY_ALL_ACTIVE_ROOT_TIMEOUT',
        executed_source_commit='d998d92eb96aa2f3497ed868887adb104c346cd9',
        preservation_checkpoint='b4e061bdf2416eccd7aa2a42b3761db1affce8c1',
        original_result=record(OLD/'MAY19/A1_RESULT.json'),preservation=record(OLD/'COMPLETE_STAY_ALL_ACTIVE_PRESERVATION.json'),
        stop_receipt=record(OLD/'FAST_REDESIGN_EXECUTION_STOP_RECEIPT.json'),
        date='2025-05-19',raw_model=values,
        presolved=dict(rows=2958547,cols=3718260,nnz=16895324),
        root_presolved=dict(rows=2930311,cols=3709978,nnz=16393728),
        factor_nonzeros=1562000000,factor_memory_GB=15.,barrier_iterations=52,
        solver_reported_barrier_elapsed_seconds=3605.14,interrupted_root_attempt_seconds=3520.71,
        native_seconds=baseline['native_seconds'],root_completed=False,incumbents=0,
        scientific_infeasibility_proven=False,computational_failure=True,
        clock_caveat='barrier summary elapsed clock and root attempt duration are not exclusive phase timings',
        May12_native_calls=0,May10_native_calls=0)
    atomic(OUT/'COMPLETE_STAY_ALL_ACTIVE_BASELINE.json',baseline_doc)
    authority=dict(PASS=True,authority='AIDC_A_STAGE_DOMAIN_AUTHORITY_V2',
        physical_domain_unchanged=True,reference_is_hard_cut=False,grid_ranking_is_hard_cut=False,
        scientific_input_identity=record(OLD/'STATIC_SOURCE_DATA_IDENTITY.json'),
        domain_defined_not_global_feasibility=True,dates={})
    for day in DAYS:
        path=CENSUS/('MAY'+day[-2:]+'_STATIC_DOMAIN_CENSUS.json');row=read(path)
        authority['dates'][day]=dict(census=record(path),jobs=row['jobs'],classes=row['classes'],
                                    physical=row['new_hard_physical'])
    atomic(OUT/'SCIENTIFIC_DOMAIN_AUTHORITY.json',authority)
    text='''# FAST ACTIVE DOMAIN preregistration\n\nCheckpoint b4e061bdf2416eccd7aa2a42b3761db1affce8c1 preserves the executed all-active sources, gates and exact negative evidence.\n\nThe complete scientific V2 domain and frozen physics remain authoritative. The initial active set retains every valid required STAY support and uses a radius of two same-site slots and at most eight ranked optional STAY extras per class. Required support is uncapped. Migration begins only with finite validated rescue/incumbent support; graph recombinations are counted. No initial cap removes a physical candidate. These choices were fixed from the197537/34426 STAY census and11737638 old migration representation, before fast native results.\n\nActivation batches start at64 and remain32..256; density alone changes the next batch. The native LP is solved before a MILP. Physical-path pricing alone cannot close the native mixed-flow LP. A missing full primitive/block pricing certificate stops MILP and production. LP closure never proves integer closure. Both canaries have at most300 cumulative requested native seconds. Any native termination overshoot is recorded without extending the budget.\n\nThe engineering SPEED_GATE requires completed restricted LP within300 seconds, raw columns at most50% of baseline, factor nonzeros and factor memory at most25% of baseline, and material ordering/root improvement where measurable. Missing factor/ordering evidence fails the gate. These engineering thresholds do not establish scientific feasibility or full-domain optimality. Even SPEED_GATE_PASS cannot authorize production without the pricing gate.\n\nNo solver parameter tournament, tolerance relaxation, resource cutoff, physical modification, other27-date optimization, Planning/Actual/PQ repair or downstream promotion is authorized by this diagnostic. The preferred1800-second full A1 time is a performance target. May17→May19→May12→May10 production is conditional on all gates and May19 root tractability.\n'''
    path=OUT/'PREREGISTRATION.md'
    if path.exists() and path.read_text(encoding='utf8')!=text:raise ValueError('PREREGISTRATION_DRIFT')
    path.write_text(text,encoding='utf8',newline='\n')
    return policy

if __name__=='__main__':preregister()
