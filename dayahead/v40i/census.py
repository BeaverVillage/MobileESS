"""Read-only repository/source-lineage census; text matches are not authority."""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import io
import json
import re
import subprocess
import zipfile
import pandas as pd
import pyarrow.parquet as pq
from dayahead.paper_analysis.storage import read, write_json, write_parquet, sha
from dayahead.v40h.identity import file_record, require
from .electrical import ROOT, now, git

UID_KEYS = {'uid', 'job_uid', 'job_id', 'id', 'original_job_uid'}
SITE_KEYS = {'site','site_id','aidc_id','AIDC_site','actual_site','actual_AIDC_site','frozen_AIDC_site',
    'destination_AIDC','source_AIDC','initial_AIDC','current_AIDC','nodelist','nodes_shared'}
RAW_SHA = '3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f'
LINEAGE = [
    ('raw_observations', None, 'Raw Kestrel has actual timestamps and physical node lists, no synthetic AIDC identity or counterfactual allocation history.'),
    ('observation_parser', 'dayahead/tools/audit_v40d_actual_replay.py', 'workload_audit selects id/job_id/start/end/submit/gpus/state/source_member and omits raw nodelist.'),
    ('causal_materializer', 'dayahead/v37/aidc_materializer.py', 'STATE_COLUMNS selects D1-visible causal fields; no node-to-synthetic-AIDC execution mapping.'),
    ('spatial_projection', 'dayahead/v39a/spatial.py', 'production_activity clips scheduled intervals to [24,120); pre-day-only pending jobs do not enter spatial assignment.'),
    ('synthetic_initial_state', 'dayahead/v39e/initial_state.py', 'Synthetic RUNNING snapshot and RW active jobs; a planning assignment is not Actual authority.'),
    ('case_loader', 'dayahead/v40d_actual/inputs.py', 'frozen_jobs retains full temporal UID universe, looks up planning AIDC_assignments; missing placement becomes UNASSIGNED. B0/B2 share B0, B1 uses B1, B3 uses final A1.'),
    ('actual_runtime', 'dayahead/v40d_actual/job_replay.py', 'RUNNING continues at issue; PENDING uses frozen ready or capacity delay. Observed end-minus-start supplies duration only.'),
    ('canonical_actual_segments', 'dayahead/v40g_segments/actual.py', 'Splits fixed migration source/destination, preserves no-compute gaps, uses observed residual service. It cannot invent missing original site.'),
    ('protected_actual_gate', 'dayahead/v40h/actual.py', 'Rejects UNASSIGNED pre-horizon jobs before physical replay.'),
    ('V40I_timing_site_classifier', 'dayahead/v40i/authority.py', 'Timing, actual AIDC site and active-interval segment evidence checked separately; planning fallback prohibited.')]


def role(path):
    p = str(path).lower()
    if 'frozen_job_observations' in p: return 'DERIVED_RAW_TIMING'
    if 'actual' in p and any(x in p for x in ('ledger','segment','trace','execution','replay')): return 'HISTORICAL_ACTUAL_CANDIDATE'
    if any(x in p for x in ('reference_compute','decision','schedule','initial_state','placement','assignment','canonical_b1','common_b0','common_da','restricted_values')): return 'PLANNING_OR_FROZEN_DECISION'
    if any(x in p for x in ('kestrel','node_interval','allocation','nodelist')): return 'RAW_OR_DERIVED_PHYSICAL_NODE_CANDIDATE'
    return 'OTHER_HISTORICAL_EVIDENCE_CANDIDATE'


def inspect_json(node, wanted):
    keys = set(); sightings = []; found = set()
    def walk(x):
        if isinstance(x, dict):
            keys.update(x)
            ids = {str(x[k]) for k in UID_KEYS & x.keys() if isinstance(x[k], (str,int))} & wanted
            # UID-keyed maps remain candidates, not accepted authority.
            ids.update(set(x) & wanted)
            if ids:
                sites = {k: x[k] for k in SITE_KEYS & x.keys()}
                times = {k:x[k] for k in x if any(t in k.lower() for t in ('start','end','finish','interval','compute_active','migration')) and not isinstance(x[k], dict)}
                for uid in ids: sightings.append({'uid':uid,'sites':sites,'timing_and_segment_fields':times})
                found.update(ids)
            for value in x.values():
                if isinstance(value, (dict,list)): walk(value)
        elif isinstance(x,list):
            for value in x:
                if isinstance(value,(dict,list)): walk(value)
    walk(node); return sorted(keys), found, sightings


def lineage(repo):
    rows=[]
    for stage, source, reason in LINEAGE:
        record = file_record(repo/source) if source else None
        commit = git(repo,'log','-1','--format=%H','--',source) if source else None
        rows.append({'stage':stage,'source':record,'source_commit':commit or 'UNCOMMITTED_V40I_IMPLEMENTATION', 'finding':reason})
    return rows


def raw_forensic(repo):
    repo=Path(repo).resolve(); root=repo/ROOT
    roots=read(root/'CENSUS_SEARCH_ROOTS.json')
    archive=next(Path(roots[0]).glob('esif.hpc.kestrel.job-anon.zip'))
    require(sha(archive)==RAW_SHA,'RAW_KESTREL_ARCHIVE_HASH_DRIFT')
    wanted=set(pd.read_parquet(repo/'dayahead/artifacts/v40h_production_integrity/PRE_DAY_COMPLETE_RECLASSIFICATION.parquet').job_uid.astype(str))
    members=[]; frames=[]
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            if not member.endswith('.parquet'): continue
            raw=z.read(member); pf=pq.ParquetFile(io.BytesIO(raw)); names=pf.schema_arrow.names
            columns=[x for x in ('id','start_time','end_time','gpus_requested','nodelist','nodes_shared','jobs_shared') if x in names]
            f=pf.read(columns=columns).to_pandas(); matched=f[f.id.astype(str).isin(wanted)].copy()
            matched['source_member']=member; frames.append(matched)
            import hashlib
            members.append({'member':member,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'schema':str(pf.schema_arrow),'columns':names,'rows':len(f),'blocked_UID_rows':len(matched),
                'timing_authority_present':True,'physical_node_allocation_present':'nodelist' in names,
                'synthetic_AIDC_site_authority_present':False,'counterfactual_active_segment_authority_present':False})
    data=pd.concat(frames,ignore_index=True)
    require(set(data.id.astype(str))==wanted,'RAW_BLOCKED_UID_COVERAGE_INCOMPLETE')
    require(not data.id.astype(str).duplicated().any(),'RAW_BLOCKED_UID_AMBIGUOUS')
    obs=pd.read_parquet(repo/'dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet').set_index('id')
    for r in data.to_dict('records'):
        o=obs.loc[str(r['id'])]
        require(r['start_time']==o.start_time and r['end_time']==o.end_time and r['gpus_requested']==o.gpus_requested,'RAW_OBSERVATION_LINEAGE_DRIFT')
    write_parquet(root/'RAW_BLOCKED_UID_NODE_EVIDENCE.parquet',data)
    result={'raw_authority':file_record(archive),'members':members,'blocked_UID_count':len(wanted),
        'all_blocked_UIDs_found':True,'raw_to_frozen_timing_and_GPU_match':True,
        'physical_node_record_count':sum(bool(len(x)) for x in data.nodelist),
        'physical_node_information_loss':{'classification':'CASE_1_RAW_INFORMATION_DROPPED_BY_ADAPTER',
            'stage':'audit_v40d_actual_replay.workload_audit column projection',
            'field':'nodelist','recoverable_from_raw':True,'restoration_is_sufficient_for_Actual_AIDC_authority':False},
        'counterfactual_AIDC_authority_loss':{'classification':'CASE_2_UPSTREAM_COUNTERFACTUAL_AIDC_AUTHORITY_ABSENT',
            'stage':'RAW_SOURCE_SYNTHETIC_AIDC_DOMAIN_NOT_PRESENT',
            'reason':'Physical Kestrel nodes are not the twelve synthetic AIDC sites. No actual allocation/migration mapping to this case-specific counterfactual domain exists in the raw schema.'},
        'planning_fallback_used':False,'evidence':file_record(root/'RAW_BLOCKED_UID_NODE_EVIDENCE.parquet')}
    write_json(root/'V40I_RAW_TO_REPLAY_LINEAGE.json',result); return result


def scan(repo):
    repo=Path(repo).resolve(); root=repo/ROOT
    blocked=pd.read_parquet(repo/'dayahead/artifacts/v40h_production_integrity/PRE_DAY_COMPLETE_RECLASSIFICATION.parquet')
    wanted=set(blocked.job_uid.astype(str)); cases=defaultdict(set)
    for r in blocked.to_dict('records'): cases[str(r['job_uid'])].add(r['day']+'/'+r['case'])
    paths=set(root.joinpath('CENSUS_TEXT_HITS.txt').read_text(encoding='utf-8').splitlines())
    paths.update(root.joinpath('CENSUS_PARQUET_PATHS.txt').read_text(encoding='utf-8').splitlines())
    index=[]; candidates=[]; errors=[]; sightings_path=root/'CENSUS_TYPED_UID_SIGHTINGS.jsonl'
    with sightings_path.open('w',encoding='utf-8',newline='\n') as stream:
        for number, name in enumerate(sorted(paths)):
            p=Path(name)
            try:
                record=file_record(p); schema=[]; found=set(); sightings=[]
                if p.suffix.lower()=='.parquet':
                    pf=pq.ParquetFile(p); schema=pf.schema_arrow.names
                    uidcols=UID_KEYS & set(schema)
                    if uidcols:
                        fields=[k for k in schema if k in UID_KEYS | SITE_KEYS or any(t in k.lower() for t in ('start','end','interval','compute_active','migration'))]
                        frame=pf.read(columns=fields).to_pandas(); mask=pd.Series(False,index=frame.index)
                        for k in uidcols: mask |= frame[k].astype(str).isin(wanted)
                        matched=frame.loc[mask].to_dict('records')
                        # Arrow lists/timestamps are normalized before the semantic walk.
                        normalized=json.loads(pd.DataFrame(matched).to_json(orient='records',date_format='iso')) if matched else []
                        _,found,sightings=inspect_json(normalized,wanted)
                elif p.suffix.lower()=='.json': schema,found,sightings=inspect_json(read(p),wanted)
                elif p.suffix.lower()=='.csv':
                    with p.open(encoding='utf-8-sig',errors='replace',newline='') as f:
                        reader=csv.DictReader(f); schema=reader.fieldnames or []
                        if UID_KEYS & set(schema): _,found,sightings=inspect_json(list(reader),wanted)
                else:
                    schema=['UNSTRUCTURED_TEXT_OR_JSONL_SEARCH_HIT']; found=set()
                covered=sorted(set().union(*(cases[u] for u in found))) if found else []
                category=role(p)
                row={**record,'schema':schema,'role':category,'producer':'SEE_SOURCE_LINEAGE_OR_UNRECOVERED_HISTORICAL_PRODUCER',
                    'source_code_path':None,'source_commit':None,'contains_UID':bool(found),'contains_site':bool(SITE_KEYS & set(schema)),
                    'contains_interval_start_end':any('start' in k.lower() for k in schema) and any('end' in k.lower() or 'finish' in k.lower() for k in schema),
                    'contains_compute_active':any('compute_active' in k.lower() for k in schema),
                    'migration_gap_represented':any('migration' in k.lower() for k in schema),
                    'matching_blocked_UID_count':len(found),'May_day_coverage':sorted({c[:10] for c in covered}),
                    'blocked_case_coverage':covered,'actual_site_authority_accepted':False,
                    'raw_authority_path':None,'raw_authority_hash':None,
                    'timing_authority_present':category=='DERIVED_RAW_TIMING','site_authority_present':False,'segment_authority_present':False,
                    'adapter_path':str(repo/'dayahead/tools/audit_v40d_actual_replay.py'),
                    'materializer_path':str(repo/'dayahead/v37/aidc_materializer.py'),
                    'actual_replay_loader_path':str(repo/'dayahead/v40d_actual/inputs.py'),
                    'authority_loss_stage':'UNADJUDICATED_CANDIDATE' if found else 'NO_RELEVANT_TYPED_UID',
                    'authority_loss_reason':'A text/schema hit is not counterfactual Actual authority; must pass source-to-case lineage.',
                    'planning_fallback_detected':category=='PLANNING_OR_FROZEN_DECISION','planning_fallback_used':False,
                    'active_interval_coverage':None,'final_authority_classification':'CANDIDATE_ONLY_NOT_AUTHORITY'}
                index.append(row)
                if found:
                    candidates.append({'path':str(p),'role':category,'UIDs':sorted(found),'sites_present':any(s['sites'] for s in sightings)})
                    for sight in sightings: stream.write(json.dumps({'path':str(p),'role':category,**sight},ensure_ascii=False,default=str)+'\n')
            except Exception as exc:
                errors.append({'path':str(p),'error':repr(exc)})
            if number%250==0:
                write_json(root/'CENSUS_SCAN_PROGRESS.json',{'at':now(),'completed':number,'total':len(paths),'typed_candidates':len(candidates),'errors':len(errors)})
                print('census',number,'/',len(paths),'candidates',len(candidates),flush=True)
    write_json(root/'CENSUS_FILE_INDEX.json',index);write_json(root/'CENSUS_TYPED_CANDIDATES.json',candidates)
    write_json(root/'CENSUS_SCAN_ERRORS.json',errors)
    result={'revision':'V40I','status':'INDEX_COMPLETE_REQUIRES_LINEAGE_ADJUDICATION','scanned_files':len(index),
        'scan_errors':errors,'typed_candidates':len(candidates),'source_lineage':lineage(repo),
        'file_index':file_record(root/'CENSUS_FILE_INDEX.json'),'typed_sightings':file_record(sightings_path),
        'search_roots':read(root/'CENSUS_SEARCH_ROOTS.json'),'classification_counts':dict(Counter(x['role'] for x in index)),
        'timing_site_segment_authorities_are_separate':True,'planning_fallback_used':False}
    write_json(root/'V40I_ACTUAL_EXECUTION_AUTHORITY_CENSUS.json',result)
    return result


if __name__=='__main__': print(scan(Path.cwd()))
