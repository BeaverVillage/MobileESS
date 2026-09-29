"""Freeze information-recovery rules before inspecting any V14 challenger metric."""
from common14 import *

def main():
    assert not (ROOT/'PREREGISTRATION.json').exists()
    protocol=dict(time=now(),base=BASE,user_request=record(ROOT/'USER_REQUEST.txt'),
        purpose='Information recovery; no new ML until source identity, exact join, embedding alignment/provenance and baseline parity pass.',
        data_boundary=dict(selection='pre-2025-04-01 only; original V13 population/roles unchanged',
            monolithic_sources='Read submission/index timestamp first; gather permitted row positions; decode outcome payload only from fully permitted row groups or point-selected rows. Never summarize post-April outcomes.',
            May_payload_opened=False,April='EXPOSED_REGRESSION_ONLY; no evaluation without complete gates and frozen callable provider'),
        arms=['J0_STATIC','J1_CURRENT_STATE','J2_STATIC_SEMANTIC','J3_CURRENT_STATE_SEMANTIC','J4_CURRENT_STATE_SEMANTIC_NN','J5_ALL_AUTHORIZED'],
        backend=read(V13/'EXPERIMENT_PROTOCOL.json')['learner'],
        reducer=dict(primary='SEM_SVD32',components=32,TRAIN_only=True,random_state=4009,dimension_search=False,
                     geometry_decision='Document normalization and any required IncrementalPCA32 alternative before challenger VALID metrics.'),
        semantic_neighbors=dict(k=10,metric='cosine',candidate_gate='neighbor_end_time < prediction time',
            fields=['mean_runtime','q50_runtime','q90_runtime','gt4h_fraction','gt12h_fraction','mean_runtime_walltime_ratio','mean_similarity','min_similarity','support_count']),
        exact_join_keys=[['job_id'],['job_id','submit_time'],['job_id','submit_time','start_time'],['job_id','submit_time','start_time','end_time']],
        join_policy='Exact only; exclude ambiguous; timestamp transformation requires independent authority; outcome fields only corroborate identity and never become current-job inputs.',
        populations=['COMMON_JOINED_POPULATION for paired comparison','FULL_V13_POPULATION for coverage diagnostic'],
        C1=read(V13/'EXPERIMENT_PROTOCOL.json')['C1'],
        total_gates={**read(V13/'EXPERIMENT_PROTOCOL.json')['gates'],'J_inference_callable':True},
        grouped_ablation_trigger='Paired min-fold or >4h coverage gain >=0.05 with pinball degradation <=5%; otherwise skip.',
        authority_failure_action='STOP scientific model work immediately; preserve forensic findings and deliver explicit NOT_RUN artifacts. Do not replace failed semantics with a model-family search.',
        new_job_callability='Historical embedding lookup is not a callable future provider.',
        stage_G='Missing-information gap analysis on failure; external discovery only after local missing-authority search.',
        training_started=False,challenger_VALID_metrics_seen=False,
        original_V13_folds=record(V13/'TEMPORAL_FOLD_CONTRACT.json'),
        immutable_prior_receipt=record(ROOT/'BASE_PRESERVATION_RECEIPT.json'))
    write('PREREGISTRATION.json',protocol)
    print('V14_PREREGISTERED',protocol['time'])

if __name__=='__main__':main()
