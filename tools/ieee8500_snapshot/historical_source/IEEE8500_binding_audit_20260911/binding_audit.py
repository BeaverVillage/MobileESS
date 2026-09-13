"""Read-only artifact/source audit. No production imports, solver, or OpenDSS calls."""
import gzip,hashlib,json,time
from collections import Counter,defaultdict
from pathlib import Path
import pandas as pd
H=Path(__file__).parent;P=H.parent/'IEEE8500_production_20260911'
R=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
D=R/'frozen_artifacts/v41r4_may/audit/2025-05-21/domain'
I=R/'frozen_artifacts/v41r3_may/inputs/2025-05-21'
read_set={}
def rec(p):
    p=Path(p);h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    r=dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest());read_set[str(p)]=r;return r
def read(p):rec(p);return json.loads(Path(p).read_text(encoding='utf-8'))
def save(name,v):(H/name).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
refs=read(I/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json');by={x['job_uid']:x for x in refs}
domain=read(D/'DAILY_DOMAIN_AUTHORITY.json');base=read(D/'base/V41R1_FULL_CANDIDATE_MANIFEST.json');full=read(D/'combined/V41R1_FULL_CANDIDATE_MANIFEST.json')
restoration=read(R/'dayahead/artifacts/v41r3_fast_power_scale_freeze/V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json')
service=read(I/'common_q90_v3/COMMON_DA_SERVICE_AUTHORITY.json');receipt=read(I/'common_q90_v3/COMMON_INPUT_RECEIPT.json')
capacity=read(domain['capacity']['path']);preflight=read(P/'preflight/NON_ELECTRICAL_INPUT_AND_BINDING_AUDIT.json')
ledger_path=service['source_ledger']['path'];rec(ledger_path)
ledger=pd.read_parquet(ledger_path,columns=['job_id','PARTIAL_shared','requested_nodes','requested_gpus','workload_class','protected'])
ledger.index=ledger.job_id.astype(str)
assert set(ledger.index)==set(by)
assert (ledger.PARTIAL_shared.astype(bool)==(ledger.requested_gpus<4*ledger.requested_nodes)).all()
for r in (service['source_snapshot'],service['ML_snapshot']):assert rec(r['path'])['sha256']==r['sha256']
counts=Counter();per_job=[];digests={};base_lost=[];group_keys=defaultdict(list)
bp=Path(base['candidate_artifact']['path']);fp=Path(full['candidate_artifact']['path']);rec(bp);rec(fp)
hb=hashlib.sha256();hf=hashlib.sha256()
bm={x['job_id']:x for x in base['jobs']};fm={x['job_id']:x for x in full['jobs']}
with gzip.open(bp,'rb') as fb,gzip.open(fp,'rb') as ff:
    for rawb,rawf in zip(fb,ff,strict=True):
        hb.update(rawb);hf.update(rawf);b=json.loads(rawb);f=json.loads(rawf);uid=f['job_id'];assert uid==b['job_id'];r=by[uid]
        assert hashlib.sha256(rawb).hexdigest()==bm[uid]['candidate_row_SHA']
        assert hashlib.sha256(rawf).hexdigest()==fm[uid]['candidate_row_SHA']
        bs={tuple(o) for o in b['options']};fs={tuple(o) for o in f['options']};assert len(fs)==len(f['options'])
        if not bs<=fs:base_lost.append(uid)
        added=fs-bs;opts=f['options'];temporal=len({o[1] for o in opts})>1;spatial=len({o[0] for o in opts})>1;migration=any(o[3]>=0 for o in opts)
        relocation=any(o[3]<0 and o[0]!=r['AIDC_site'] for o in opts)
        assert all(o[1]!=r['start_slot'] and o[3]<0 for o in added)
        assert [r['AIDC_site'],r['start_slot'],r['end_slot'],-1,-1,-1,''] in opts
        partial=bool(ledger.loc[uid,'PARTIAL_shared'])
        row=dict(job_id=uid,state=r['state_at_issue'],PARTIAL_shared=partial,base_candidates=len(bs),restored_temporal_candidates=len(added),total_candidates=len(fs),temporal_options=temporal,spatial_options=spatial,migration_options=migration,standalone_relocation_options=relocation)
        per_job.append(row);counts.update(jobs=1,base_candidate_count=len(bs),restored_temporal_candidate_count=len(added),total_candidate_count=len(fs),jobs_with_temporal_options=int(temporal),jobs_with_spatial_options=int(spatial),jobs_with_migration_options=int(migration),jobs_with_standalone_relocation_options=int(relocation),PARTIAL_shared_jobs=int(partial),PARTIAL_shared_temporal_jobs=int(partial and temporal),PARTIAL_shared_spatial_jobs=int(partial and spatial),PARTIAL_shared_migration_jobs=int(partial and migration))
        # The original P5 grouping uses exact option/cost equality, not sorted UID ranks.
        # Same GPU, duration, reference site/start/end and options imply same costs;
        # migration UIDs remain singleton. Save only a sufficient witness here.
        if not migration:
            key=(r['requested_GPU'],r['safe_duration_slots'],r['AIDC_site'],r['start_slot'],r['end_slot'],hashlib.sha256(json.dumps(opts,separators=(',',':')).encode()).hexdigest(),r['AIDC_site'] if r['state_at_issue']=='RUNNING' else '')
            group_keys[key].append(uid)
assert hb.hexdigest()==base['candidate_set_SHA'];assert hf.hexdigest()==full['candidate_set_SHA']
assert counts['total_candidate_count']==domain['total_count']==preflight['full_candidate_count']
assert counts['restored_temporal_candidate_count']==domain['restored_count']
assert counts['jobs_with_temporal_options']==domain['eligible_temporal_jobs']
assert not base_lost
save('PER_JOB_BINDING_CENSUS.json',per_job)
power_sources=['dayahead/v39a/power.py','dayahead/v39a/contracts.py','dayahead/v28r2/c1_affine.py','dayahead/v28r2/formulation.py','dayahead/v40g_segments/canonical.py','dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json']
model_sources=['dayahead/v40g/optimizer.py','dayahead/v40g/domain.py','dayahead/v41/objectives.py','dayahead/v41/reserve.py','dayahead/v41/temporal_restore.py','dayahead/v41/frozen_candidates.py','dayahead/v41/common.py','dayahead/v41r1/bounded_solver.py','dayahead/v41r1/feasible_seed.py','dayahead/v41r1/exact_aggregation.py','dayahead/v41r1/migration.py','dayahead/v41r1/terminal.py','dayahead/v41r1/migration_factor.py','dayahead/v41r1/migration_admission.py','v41r4_runtime.py','v41r4_domain.py','v41r4_b3_equivalent.py','v41r4_loop_runtime.py','v41r4_loop_budget.py','dayahead/v41r3/authority.py','dayahead/v37/aidc_materializer.py']
power_records=[rec(R/p) for p in power_sources]
model_records=[rec(R/p) for p in model_sources]
ieee_records=[rec(P/p) for p in ['non_electrical_inputs.py','aidc_search8500.py','run_support.py','grid8500.py','production_campaign.py','production_campaign_v2.py','ac8500.py']]
for r in preflight['input_files']:rec(r['path'])
for r in domain['sources']:rec(r['path'])
authority_checks=[]
for label,obj in [('daily_domain',domain),('common_receipt',receipt)]:
    def walk(v):
        if isinstance(v,dict):
            if 'path' in v and 'sha256' in v:
                now=rec(v['path']);authority_checks.append(dict(label=label,path=v['path'],expected_sha256=v['sha256'],observed_sha256=now['sha256'],match=v['sha256']==now['sha256']))
            else:
                for x in v.values():walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    walk(obj)
duplicates=[u for u in group_keys.values() if len(u)>1]
save('P5_GROUPING_WITNESSES.json',dict(note='Sufficient exact-equality groups: identical options, GPU, duration, reference geometry imply identical costs. Original P5 gives members one shared cohort weight; IEEE8500 gives different UID weights.',groups=duplicates))
v=dict(status='FAIL_CLOSE',classification='NONAUTHORITATIVE_PRE_AIDC_BINDING_AUDIT',scientific_result_use_allowed=False,restart_allowed=False,audit_mode='READ_ONLY_BINDING_ONLY_NO_PRODUCTION_IMPORTS_NO_OPTIMIZATION_NO_AC',selected_operating_date='2025-05-21',installed_GPU_capacity=sum(capacity['site_capacity'].values()),site_GPU_capacity=capacity['site_capacity'],GPU_capacity_matches_runtime=capacity['site_capacity']==preflight['GPU_capacities'],counts=dict(counts),expected_contract=dict(jobs_with_temporal_options=452,restored_temporal_candidate_count=117252,base_candidate_count=4772575,total_candidate_count=4889827),expected_contract_local_evidence=dict(authority=rec(R/'dayahead/artifacts/v41r3_fast_power_scale_freeze/V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json'),day_binding_source=rec(R/'dayahead/v41r3/authority.py'),source_day='2025-05-04',eligible_jobs=restoration['eligible_jobs'],restored=restoration['restored_temporal_candidates'],base=restoration['base_candidates'],total=restoration['total_candidates']),daily_domain=rec(D/'DAILY_DOMAIN_AUTHORITY.json'),candidate_compressed_artifact=rec(fp),candidate_decompressed_stream_sha256=hf.hexdigest(),base_decompressed_stream_sha256=hb.hexdigest(),base_options_retained=True,workload_reference=rec(I/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'),workload_service_authority=rec(I/'common_q90_v3/COMMON_DA_SERVICE_AUTHORITY.json'),workload_input_receipt=rec(I/'common_q90_v3/COMMON_INPUT_RECEIPT.json'),ML_snapshot=rec(I/'V41_ML_SNAPSHOT_2025-05-21.json'),PARTIAL_shared=dict(status='INCLUDED',definition='requested_gpus < 4 * requested_nodes',source_ledger=rec(ledger_path),ledger_UIDs_equal_reference_UIDs=True,reference_UIDs_equal_candidate_UIDs=True,shared_work_is_aggregate_GPU_occupancy_not_independent_facility_power=True,**{k:v for k,v in counts.items() if k.startswith('PARTIAL')}),AIDC_power_sources=power_records,B1_A1_V41R4_production_sources=model_records,IEEE8500_executed_sources=ieee_records,authority_reference_hash_checks=authority_checks,all_checked_authority_links_match=all(x['match'] for x in authority_checks),P5_sufficient_shared_cohort_witness_groups=len(duplicates),mismatches=[dict(id='USER_EXPECTED_CANDIDATE_CONTRACT_NOT_BOUND',detail='Actual May21 daily domain is 39 / 16392 / 1341947, while requested contract is 452 / 117252 / 4889827. The latter values are traced to May04. Audit does not authorize changing date or workload.'),dict(id='B1_A1_MODEL_SEARCH_AUTHORITY_REPLACED',detail='IEEE8500 uses new aidc_search8500.neighborhood/run instead of retained v40g.optimizer + BoundedLex + v41r4 B1/A1 adapters. It does not construct the original full model.'),dict(id='P5_OBJECTIVE_AUTHORITY_CHANGED',detail='Original P5 uses original exact cohort rank; IEEE8500 vector uses sorted individual UID rank. Identical non-migrating cohort witness groups exist.'),dict(id='P1_P5_STAGE_PROCEDURE_CHANGED',detail='Original P1 -> P2 -> P3 -> P4 -> P5 solves with locks were replaced by rho objectives, every-fifth P2 neighborhood, and acceptance-only P3/P4/P5 comparison.')],original_preflight_PASS_is_not_final_binding_PASS=True,production_restart_count_during_audit=0,OpenDSS_calls_during_audit=0)
save('BINDING_AUDIT.json',v)
save('READ_ONLY_SOURCE_SHA256.json',dict(files=list(read_set.values()),description='Only input/authority/source and current stopped-run evidence read; no legacy B1/B2/B3 performance or Actual data files read.'))
print(json.dumps({k:v[k] for k in ['status','installed_GPU_capacity','counts','all_checked_authority_links_match','P5_sufficient_shared_cohort_witness_groups']},indent=2))
