"""Provenance classification is frozen BEFORE any runtime-association diagnostics."""
from common7 import *
import pandas as pd,datetime,urllib.request

def main():
    schema=set(read(ROOT/'RAW_SCHEMA_AUDIT.json')['actual_union_fields']);dups=read(ROOT/'REQUEUE_DUPLICATE_SUMMARY.json')
    # New primary documentation was consulted for array identity, independently of outcomes.
    p=LOCAL/'authority/slurm_job_array.source';url='https://slurm.schedmd.com/job_array.html'
    with urllib.request.urlopen(url,timeout=40) as r:p.write_bytes(r.read())
    write('ARRAY_AUTHORITY_SOURCE.json',dict(url=url,downloaded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),**record(p),
      interpretation='Array task index semantically fixed at submission; tasks get lazy per-task records and potentially nonsequential numeric job IDs. This explains sibling IDs, but exact NLR export mapping/initial attempt evidence remains unproven.'))
    base=[
      ('requested_seconds','wallclock_req','Timelimit','maximum requested execution limit, not executed runtime','YES_SCONTROL_TimeLimit','D','Initial/effective/final walltime cannot be resolved from one accounting row.'),
      ('num_gpus_req','gpus_requested','ReqTRES gres/gpu','requested GPU count; internal NLR ReqTRES parser not public','YES_SCONTROL_Gres','D','ReqTRES transformation/update path and original version not recovered.'),
      ('num_nodes_req','nodes_req','ReqNodes','minimum requested nodes','YES_SCONTROL_NumNodes','D','Mutable request descriptor with no effective timestamp.'),
      ('num_cores_req','processors_req','ReqCPUS','requested CPU count','YES_SCONTROL_NumCPUs','D','Mutable request descriptor with no effective timestamp.'),
      ('requested_memory_mib','memory_req','ReqMem','requested memory with per-node/per-CPU scope','YES_SCONTROL_MinMemoryNode_MinMemoryCPU','D','Older Slurm source proves update capability; NLR initial version unknown; per-CPU suffix must not be silently treated as per-node.'),
      ('qos','qos','QOS','effective QoS name; not necessarily explicit original QOSREQ','YES_SCONTROL_QOS','D','Effective/default/updated QoS and original request not distinguished.'),
      ('partition','partition','Partition','queue/partition descriptor','YES_SCONTROL_Partition','D','No initial partition-list/current-partition version authority.'),
      ('account','account_hash','Account','anonymized allocation account','YES_SCONTROL_Account','D','Account can change; internal anonymization algorithm/version also absent.'),
      ('user','user_hash','User','anonymized submitting/owning user','NO_DOCUMENTED_NORMAL_JOB_OWNER_UPDATE','D','Do not equate with mutable Account. Raw owner is submit-known; published 7-hex username/UID transform and stable online category mapping not specified.'),
      ('submit_time','submit_time','Submit','Slurm attempt submission timestamp','YES_REQUEUE_RESET','D','No original attempt key, duplicates collection flag, or complete restart history.'),
      ('submit_hour','submit_time','Submit','UTC hour derived from archive Submit','INHERITS_SUBMIT_RESET','D','Original submission timestamp not reconstructable.'),
      ('submit_day_of_week','submit_time','Submit','UTC weekday derived from archive Submit','INHERITS_SUBMIT_RESET','D','Original submission timestamp not reconstructable.'),
      ('job_name_hash','name_hash','JobName','anonymized job name','YES_SCONTROL_JobName','D','Name can be updated; no original name/version evidence.'),
      ('submit_line_hash','submit_line_hash','SubmitLine','anonymized original submission command concept','NO_NORMAL_UPDATE_PATH_FOUND','D','Upstream concept is submit-known and retained; no NLR hash/export mapping or attestation guaranteeing original value across collection/revisions.'),
      ('submit_script_hash','submit_script_hash','internal script capture; not standard sacct field','anonymized script token','RAW_SUBMITTED_SCRIPT_RETAINED_CONCEPT; NLR_CAPTURE_UNKNOWN','D','Datacard says script can be uncaptured; no capture-time, transformation or immutable version receipt. Non-null hash is not such a receipt.'),
      ('work_dir_hash','work_dir_hash','WorkDir','anonymized working directory','YES_PENDING_SCONTROL_WorkDir','D','Mutable while pending; no original value or hash mapping.'),
      ('job_type_hash','job_type_hash','internal classifier, nonstandard sacct field','anonymized application/job-type category','UNKNOWN_DERIVATION','G','Could be classified after execution; generation code/timing absent.'),
      ('array_task_index','array_pos','ArrayTaskID per datacard','array element index declared with sbatch --array','SEMANTIC_INDEX_FIXED; EXPORT_MAPPING_UNVERIFIED','D','Potentially immutable concept, but archive id/job_id mapping differs from data-card simple labels; no exact NLR export mapping proves original per-task identity.'),
      ('array_range','array_range','ArrayTaskString','array expression represented by accounting record','PENDING_SET_MAY_SHRINK; THROTTLE_MUTABLE','D','Represented remaining task set is not certified original declaration.'),
      ('is_array_job','array_pos','derived array metadata','array membership from task index/range','SEMANTIC_MEMBERSHIP_FIXED; EXPORT_MAPPING_UNVERIFIED','D','Derived candidate inherits unverified array identity mapping; do not certify null as original non-array without source.'),
      ('job_identifier','id','JobID per datacard (observed numeric task identity)','record/task identity','ARRAY_CHILD_IDS_MAY_BE_CREATED_LATER','G','Pure lookup identifier excluded; published ID roles require clarification.'),
      ('numeric_job_identifier','job_id','JobIDRaw per datacard (observed shared array parent)','record/group identity','ARRAY_MAPPING_AMBIGUOUS','G','4104 repeated numeric groups must not be counted as same-job revisions.'),
      ('python_job','python_job','internal derived boolean','Python-job marker','UNKNOWN_DERIVATION','G','Methodology/capture time unavailable; not a certified submit-time feature.'),
      ('reframe_job','reframe_job','internal derived boolean','ReFrame-job marker','UNKNOWN_DERIVATION','G','Methodology/capture time unavailable.'),
      ('resource_shape','gpus_requested','tuple of requested GPU/nodes/cores/memory','derived resource request shape','INHERITS_MUTABLE_REQUEST_FIELDS','D','Cannot regain provenance by combining unresolved request fields.'),
      ('workflow_hash',None,'not supplied','workflow identifier','UNKNOWN','G','No separately declared workflow identifier; no semantic mapping from other tokens.'),
      ('executable_application',None,'not supplied','executable/application identity','UNKNOWN','G','No authorized raw executable field; job_type hash derivation unverified.'),
      ('container_image',None,'not supplied','container/image digest','UNKNOWN','G','No published field.'),
      ('dependency_declaration',None,'Dependency not published','original dependency expression','MUTABLE_SCONTROL_Dependency','G','Absent from archive; cannot infer by correlating jobs.'),
      ('project_category',None,'possible Account alias only','scientific/project category','UNKNOWN','G','No independent source-backed category; account remains unresolved.'),
      ('scheduler_class',None,'possible QoS alias only','scheduler class','UNKNOWN','G','No additional verified field beyond unresolved QoS.'),
    ]
    for c in ['start_time','end_time','wallclock_used','cpu_used','queue_wait','cpu_eff','max_mem_eff','min_mem_eff','avg_mem_eff','cpu_energy_tdp_estimated_max_watt_hours','cpu_energy_tdp_estimated_used_watt_hours','consumed_energy_joules','consumed_energy_raw_joules','consumed_energy_raw_watt_hours']:
        base.append((c,c,c,'execution/outcome quantity','POST_EXECUTION','F','Outcome/label or post-run diagnostic only.'))
    for c in ['state','state_simple','nodes_used','processors_used','nodelist','gpu_nodes_occupied','shared_job_count','nodes_shared','jobs_shared']:
        base.append((c,c,c,'later scheduler/allocation/shared-state quantity','CHANGES_AFTER_SUBMIT','E','No initial snapshot; never a submission-time predictor.'))
    for c in ['day','day_of_week','hour','minute']:
        base.append((c,c,'derived Submit', 'archive-derived clock field','INHERITS_SUBMIT_RESET','D','Derivation is known but original submit event is not.'))
    names={'A':'VERIFIED_SUBMISSION_TIME','B':'VERIFIED_IMMUTABLE','C':'OBSERVABLE_AT_SUBMIT_BUT_MUTABLE_WITH_VERSION_HISTORY','D':'PRESENT_IN_ARCHIVE_BUT_VERSION_UNRESOLVED','E':'POST_SUBMISSION','F':'OUTCOME_LABEL_ONLY','G':'UNSUPPORTED_UNKNOWN'}
    rows=[];lineage=[]
    evidence='NLR datacard; hpc-oda descriptor@218d75f; Slurm23.11 source/current official semantics; REQUEUE_DUPLICATE_SUMMARY.json'
    for feature,published,raw,semantic,mutable,category,reason in base:
        exists=published in schema if published else False
        rows.append(dict(feature=feature,exists_in_archive=exists,available_at_submission_semantically=category=='D' and feature not in ['array_range'],
          can_change_after_submit=mutable,change_observed_in_kestrel='NO_SAME_TASK_REVISION_SEQUENCE; sibling heterogeneity separately counted',
          original_version_reconstructable=False,source_backed=False,strict_runtime_ml_allowed=False,research_only=category=='D',
          authority_category=category,authority_status=names[category],published_field=published,semantic=semantic,reason=reason,source_evidence=evidence))
        transform='hpc-oda nlr_kestrel.yml mapping; datasets.normalize.target_to_mapping_spec -> ingest.jobs_parquet.apply.apply_mapping_spec'
        if feature=='requested_memory_mib':transform+=' -> _memory_slurm_to_mb/_memory_slurm_column (n suffix accepted; c suffix null)'
        if feature in ['submit_hour','submit_day_of_week']:transform='MobileESS common.normalize UTC dt.hour/dt.dayofweek; original Submit unresolved'
        if feature.endswith('_hash') or feature in ['user','account']:transform+='; NLR pre-publication anonymization code NOT_FOUND (downstream hashing function not equivalent)'
        lineage.append(dict(normalized_feature=feature,raw_field=raw,source_system='Kestrel Slurm -> NLR PostgreSQL',collection_method='periodic sacct; command flags/capture schedule unprovided',
          database_column=published if published else 'NOT_PUBLISHED',normalization_code=transform,published_field=published,
          submission_time_semantics=semantic,revision_semantics=mutable,authority_status=names[category],publication_code='NLR load_slurm/anonymization/export unavailable',
          actual_flow='raw Slurm -> collection -> NLR database -> published Parquet -> downstream normalization (not reverse)'))
    frame=pd.DataFrame(rows);frame.to_csv(ROOT/'FEATURE_AUTHORITY_DECISION.csv',index=False,lineterminator='\n');pd.DataFrame(lineage).to_csv(ROOT/'REQUEST_FIELD_LINEAGE.csv',index=False,lineterminator='\n')
    frame.iloc[12:].to_csv(ROOT/'ADDITIONAL_FEATURE_INVENTORY.csv',index=False,lineterminator='\n')
    strict=dict(version='runtime-vnext7-strict-v1',time=datetime.datetime.now(datetime.timezone.utc).isoformat(),features=[],STRICT_CAUSAL_JOB_FEATURE_COUNT=0,NEW_IMMUTABLE_FEATURE_COUNT=0,
      allowed_categories=['A','B','C only with reconstructed exact historical version'],no_model_training=True,no_April_or_May_selection=True,
      constant_bias_not_job_specific=True,feature_order=[],original_time_required_for_clock_features=True,fail_closed_reason='No complete source-backed chain from original submission concept to published feature value and compatible new-job representation.',
      prospective_submit_event='A live controller can observe original accepted request/resources/owner/array declaration/script at submit if captured then. Their current archive columns are not thereby certified. Need signed/versioned event receipt plus ingestion semantics.',
      dataset_contract_not_general_Slurm_knowledge=True,diagnostic_policy='No correlation/MI/model ranking on unresolved features. Long/short archive descriptors explicitly allowed by task section10, never interpreted as causal features. Workflow recurrence only until authority recovered.',
      classifications=record(ROOT/'FEATURE_AUTHORITY_DECISION.csv'),source_receipts=record(ROOT/'AUTHORITY_SOURCE_RECEIPTS.json'),duplicate_audit=record(ROOT/'REQUEUE_DUPLICATE_SUMMARY.json'))
    write('STRICT_CAUSAL_FEATURE_CONTRACT.json',strict)
    write('RESEARCH_PROXY_FEATURE_CONTRACT.json',dict(version='runtime-vnext7-proxy-v1',features=frame.loc[frame.research_only,'feature'].tolist(),
      optimizer_use_allowed=False,production_runtime_allowed=False,original_versions_verified=False,
      interpretation='Archive descriptive proxies only. Useful recurrence or outcome association cannot change authority category.',
      job_type_python_reframe_excluded_as_unknown=True,hash_policy='Use existing opaque tokens only; no dictionary attack, reidentification, new sensitive-source recovery, or claimed reproduction of missing NLR hash algorithm.'))
    write('FEATURE_AUTHORITY_FREEZE.json',dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),before_predictiveness_diagnostics=True,models_trained=0,
      files=[record(ROOT/p) for p in ['FEATURE_AUTHORITY_DECISION.csv','REQUEST_FIELD_LINEAGE.csv','STRICT_CAUSAL_FEATURE_CONTRACT.json','RESEARCH_PROXY_FEATURE_CONTRACT.json']],
      provenance_not_performance_decision=True,strict_count=0))
    print('AUTHORITY_FROZEN',len(rows),'candidates; strict0; no model',flush=True)
if __name__=='__main__':main()
