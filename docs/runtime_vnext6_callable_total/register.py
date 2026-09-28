"""Registration before reading development outcomes; strict authority amendment."""
from paths import *
from datetime import datetime,timezone

REQUEST=['requested_seconds','num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib','qos','partition','account','user']
def main():
    sources=[RAW.parent/'datacard.md',HPC/'docs/how-to/ingest-slurmctld.md',HPC/'tests/unit/test_slurmctld_parser.py']
    rows=[]
    for k in REQUEST:
        mutable=k not in ['user','requested_memory_mib']
        rows.append(dict(field=k,exists_at_submission_in_scheduler=True,
          mutable_after_submit='DOCUMENTED_SCHEDULER_CAPABILITY' if mutable else 'NOT_CERTIFIED_IMMUTABLE',
          archived_value_initial_or_final='UNKNOWN_PERIODIC_SACCT_DATABASE_EXTRACT',revision_history_found=False,
          immutable_source_evidence=False,production_feature=False,status='REQUEST_VERSION_UNVERIFIED'))
    write('REQUEST_VERSION_AUTHORITY_AUDIT.json',dict(time=datetime.now(timezone.utc).isoformat(),fields=rows,
        REQUEST_VERSION_AUTHORITY_FOUND=False,MUTABLE_REQUEST_FEATURE_COUNT=7,UNVERIFIED_REQUEST_FEATURE_COUNT=9,
        count_definition='7 documented mutable capabilities, not 7 observed modified jobs; 9 unverified normalized request fields; memory/user not certified immutable',
        ingestion='Periodic sacct -> PostgreSQL load_slurm; triggers update derived columns. Internal load/update functions not public. Raw Slurm JSONB and job_steps excluded. Dataset release version is not request revision history.',
        clock='sacct Submit resets on requeue; duplicates option needed for original. Attempt history absent. submit_hour/weekday excluded too.',
        searched_scope=[str(RAW.parent),str(HPC.parent),'official NLR dataset302 current catalog and local datacard','SchedMD sacct/scontrol documentation'],
        search_limit='No claim that private NLR logs do not exist. No authenticated internal scheduler source available. No contact messages sent.',
        source_files=[record(p) for p in sources],urls=['https://data.nlr.gov/submissions/302','https://slurm.schedmd.com/sacct.html','https://slurm.schedmd.com/scontrol.html'],
        user_amendment='Exclude unverified request features; do not upgrade archive proxy; continue immutable subset baseline and full-feature research comparator.'))
    write('FEATURE_CONTRACT.json',dict(version='strict-empty-request-subset-v1',input_predictors=[],
        internal_feature_order=['constant_bias'],internal_feature_types=['float64'],constant_bias=1.0,
        availability='Constructed constant is independent of every job field, ID, timestamp and outcome; available at all times.',
        categorical_mappings={},missing_rules='No request feature consumed; missing event_time invalid; request metadata optional echo only.',
        excluded_request_fields=REQUEST,excluded_clock_fields=['submit_hour','submit_dow'],
        forbidden=['start_time','end_time','runtime_seconds','queue_wait','state','utilization','completion_status'],
        immutable_job_specific_feature_count=0,SUBMISSION_TIME_FEATURES_STRICTLY_VERIFIED=True,
        verification_scope='Only the deterministic constant input; NOT certification of archive requests or initial submit timestamp.',
        IMMUTABLE_FEATURE_ONLY_MODEL_TRAINABLE=True,
        M3='NOT_SCIENTIFICALLY_VALID_STRICT_ARM: walltime-relative inverse transform requires unverified requested_seconds',
        baseline_B0='Existing full-feature frozen research model, excluded from production selection',
        walltime_cap='No cap in production candidate. Archive walltime cap only retrospective research diagnostic.'))
    write('EXPERIMENT_PROTOCOL.json',dict(version=1,time=datetime.now(timezone.utc).isoformat(),
        logical_freeze_cutoff='2025-03-31T08:00:00Z',actual_execution_year=2026,
        retrospective='Logical pre-April information experiment, not a claim this artifact physically existed in March 2025.',
        target='max(0,end-start) seconds; no queue wait; completed-by-event-time records; missing/negative time order excluded, zero retained',
        population='Positive archived GPU request cohort; cohort/weights/strata are retrospective archive descriptors, NOT certified original requests. Strict model never reads them.',
        TRAIN=dict(end_after='2024-09-15T08:00:00Z',end_before='2025-03-14T08:00:00Z'),
        DEV=dict(submit_from='2025-03-15T00:00:00Z',submit_before='2025-03-22T00:00:00Z',mature_before='2025-03-23T00:00:00Z'),
        CAL_FIT=dict(submit_from='2025-03-23T00:00:00Z',submit_before='2025-03-26T00:00:00Z',mature_before='2025-03-27T00:00:00Z'),
        CAL_VALID=dict(submit_from='2025-03-27T00:00:00Z',submit_before='2025-03-30T00:00:00Z',mature_before='2025-03-31T08:00:00Z'),
        APRIL=dict(submit_from='2025-04-01T00:00:00Z',submit_before='2025-05-01T00:00:00Z',mature_before='2025-05-01T00:00:00Z'),
        models=['W0_ARCHIVED_WALLTIME','B0_FROZEN_FULL_FEATURE_RESEARCH','M1_DIRECT_STRICT_CONSTANT','M2_LOG1P_STRICT_CONSTANT'],
        M3='excluded: unverified walltime needed at inference',quantiles=[.5,.9],
        lgbm=dict(n_jobs=1,random_state=4005,deterministic=True,force_col_wise=True,verbosity=-1,num_leaves=31,learning_rate=.02,n_estimators=800,min_child_samples=100,reg_lambda=1,max_bin=255),
        weighting='Uniform; no mutable GPU or request derived training weights',
        calibration='Signed global Q90 residual order statistic ceil(.9*(n+1)) on CAL_FIT, nonnegative monotone outputs. Q50 untouched.',
        selection='Select M1/M2 by lowest DEV raw Q90 pinball, then direct M1 tie within 1e-6. Calibration method fixed here. Require independent DEV raw and CAL_VALID calibrated gates. If fail, serialize best research candidate, no promotion.',
        final_fit='Exactly one final refit per Q50/Q90 after selection and calibration frozen on unchanged TRAIN membership; numerical equality to development boosters required. Never absorb DEV or CAL.',
        gates=dict(coverage=[.88,.92],gpu_coverage=[.88,.94],pinball_vs_W0_B0='<= both',reservation_vs_W0_max=.8,
          long_actual_gt4h_coverage_min=.85,high_gpu_ge16_coverage_min=.85,stratum_min_N=100,
          zero_support='INCONCLUSIVE -> no promotion',CPU_single_p99_ms_max=50,CPU_single_max_ms_max=200),
        uncertainty=dict(unit='UTC submission day',paired=True,draws=1000,seed=60928,interval=.95,minimum_days=3),
        backend=dict(subset='first 50000 TRAIN rows sorted end,id',workload='M1/M2 Q50/Q90 same 4 tasks, identical to strict full training configuration',
          compare=['CPU_SINGLE','CPU_MULTIPROCESS_4','GPU'],per_fit_threads=1,
          tolerance=dict(max_abs_seconds=.1,relative_pinball=.001,coverage_difference=.001),
          selection='fastest numerically equivalent backend; GPU requires >=20% speed advantage; unsupported GPU recorded, not invented. Constant-feature workload has no useful tree splits.'),
        checkpoint=dict(interval_seconds=1800,thresholds_seconds=[900,1800,3600],
          adequate=dict(overrun_checkpoint_fraction_max=.15,accuracy_each_min=.8,remaining_MAE_seconds_max=3600),
          scope='Completed April records only, checkpoints start+1800*k strictly before end; no survival fit'),
        queue=dict(day='2025-04-02',slot_seconds=900,horizon_slots=96,
          reference='Replay frozen V42 existing P2 admission/site trajectory using its selected sites and walltime to reproduce starts; pure first-fit W0/ML numeric-site pair additionally isolated, same arrival/tier/id order and existing known occupancy.',
          temporal_counterfactual='Keep frozen known background occupancy; change ONLY arriving-job duration to Q90; report this restricted scope. Fixed actual elapsed duration counterfactual is retrospective diagnostic, not observed scheduling fact.',
          overrun='Actual-end truth belongs to isolated event simulator only. Scheduler sees completed/running status and causal elapsed, preserves occupancy and STAY, extends one slot. No expected walltime residual.',
          no_grid_or_optimizer_calls=True),
        locked_data='Never open April outcome/input payload until selection and provider bundle freeze. No May partition or May outcome used.',
        full_feature_new_training=False,survival_training=False))
    print('REGISTERED_STRICT_CONSTANT_ONLY',flush=True)
if __name__=='__main__':main()
