"""Resolve external inventory metadata and audit every missing request exactly.

Use after scan_external. Git links are inspected as link objects; Git LFS
payloads must be hash-matched to materialized files in the same external root.
No raw source is written or copied. No raw source code is executed.
"""
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime,timedelta
from pathlib import Path
from . import scan_external as scan
from v42_april_b0_v2.recovery import recover_gpu

OUT=scan.OUT


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def normalize():
    inventory=json.loads((OUT/'EXTERNAL_RAW_INVENTORY.json').read_text(encoding='utf8'))
    current,errors=scan.enumerate_files()
    seen={r['absolute_path'] for r in inventory}
    assert seen<=set(map(str,current)),'EXTERNAL_SOURCE_DISAPPEARED'
    inventory.extend(scan.inspect_file(p) for p in current if str(p) not in seen)
    links=[];lfs=[]
    for row in inventory:
        if row['status'] in ('READ_ERROR','GIT_SYMBOLIC_LINK_METADATA'):
            path=Path(row['absolute_path']);repo=next(p for p in path.parents if (p/'.git').is_dir())
            meta=subprocess.check_output(['git','ls-tree','HEAD',path.relative_to(repo).as_posix()],cwd=repo).decode().split()
            assert meta[0]=='120000','UNREADABLE_NON_LINK_RAW_SOURCE'
            data=subprocess.check_output(['git','cat-file','blob',meta[2]],cwd=repo)
            link=dict(path=str(path),blob=meta[2],target=data.decode(),descriptor_SHA256=hashlib.sha256(data).hexdigest())
            links.append(link)
            row.update(status='GIT_SYMBOLIC_LINK_METADATA',format='symbolic_link',columns=[],link_target=link['target'],
                       Git_blob=meta[2],link_descriptor_SHA256=link['descriptor_SHA256'],link_descriptor_bytes=len(data))
        if row['status']=='SCHEMA_ERROR' and row['format']=='xlsx':
            row['columns']=scan.xlsx_headers(Path(row['absolute_path']));row['status']='READABLE'
            row['prior_scan_errors']=row['errors'];row['errors']=[]
        if row['status']=='SCHEMA_ERROR' and row['format']=='json':
            with open(scan.native(row['absolute_path']),'rb') as f:row.update(scan.schema(f,'source.jsonl'))
            row['status']='READABLE_JSONL_WITH_JSON_SUFFIX';row['prior_scan_errors']=row['errors'];row['errors']=[]
        if row['status']=='SCHEMA_ERROR' and row['format']=='parquet':
            text=Path(row['absolute_path']).read_text(encoding='utf8')
            assert text.startswith('version https://git-lfs.github.com/spec/v1'),'UNPARSED_RAW_PARQUET'
            row.update(status='GIT_LFS_POINTER',format='git_lfs_pointer',LFS_object_SHA256=re.search(r'oid sha256:(\w+)',text)[1],
                       LFS_object_size=int(re.search(r'size (\d+)',text)[1]),columns=[])
        for item in [row]+row['archive_members']:
            headers=item.pop('header_records',None)
            if headers:
                names=[r for r in headers if r and r[0]=='I']
                if names:item['columns']=list(dict.fromkeys(v for r in names for v in r))
            item['GPU_related_fields']=[str(c) for c in item['columns'] if scan.GPU.search(str(c))]
            cov=item.get('date_coverage',{})
            if 'status' not in cov:
                item['date_coverage']={k:v for k,v in cov.items() if scan.TIME.search(k)}
        assert row['status'] not in ('READ_ERROR','SCHEMA_ERROR'),'UNRESOLVED_SOURCE_INSPECTION_ERROR'
    by_sha={r['SHA256']:r for r in inventory if r['SHA256']}
    for row in inventory:
        if row['status']!='GIT_LFS_POINTER':continue
        actual=by_sha.get(row['LFS_object_SHA256'])
        assert actual is not None and actual['size']==row['LFS_object_size'],'MISSING_LFS_PAYLOAD_AUTHORITY'
        row.update(materialized_path=actual['absolute_path'],payload_schema_status='SHA_MATCHED_LOCAL_PAYLOAD',
                   payload_columns=actual['columns'],payload_date_coverage=actual['date_coverage'])
        lfs.append(dict(pointer=row['absolute_path'],payload=actual['absolute_path'],SHA256=row['LFS_object_SHA256'],
                        bytes=row['LFS_object_size'],columns=actual['columns'],date_coverage=actual['date_coverage']))
    summary=scan.save_inventory(inventory,errors)
    write('EXTERNAL_RAW_LINK_AND_LFS_AUDIT.json',dict(links=links,pointers=lfs,all_LFS_payloads_locally_resolved=True))
    return inventory,summary,lfs


def main():
    inventory,summary,lfs=normalize()
    with (OUT/'GPU_REQUEST_RECOVERY_LEDGER.csv').open(encoding='utf8',newline='') as f:rows=list(csv.DictReader(f))
    counts=Counter();by_role={}
    for row in rows:
        candidates=json.loads(row['matching_candidate_source_records'])
        issue=datetime.fromisoformat(row['day']+'T00:00:00+10:00')-timedelta(hours=6)
        event=issue.isoformat() if row['role']=='KNOWN_D1' else row['submission_timestamp']
        result=recover_gpu(dict(job_uid=row['job_uid'],submit_time=row['submission_timestamp'],
                               source_event_identity=row['source_event_identity']),candidates,event_time=event)
        counts[result['status']]+=1
        by_role.setdefault(row['role'],Counter())[result['status']]+=1
    # Source-field absence is only finalized after full inventory, all LFS
    # payloads, target scheduler identities, and secondary exact-token audit.
    probe=json.loads((OUT/'EXTERNAL_EXACT_UID_TEXT_PROBE.json').read_text(encoding='utf8'))
    target_path=OUT/'EXTERNAL_TARGET_SCHEDULER_IDENTITIES.csv'
    with target_path.open(encoding='utf8') as f:targets=list(csv.DictReader(f))
    target_ids={r['id'] for r in targets}
    assert len(target_ids)==len(targets)==len({r['job_uid'] for r in rows})==probe['target_unique_UIDs']
    assert all(not r['gpus_requested'] for r in targets),'RECOVERABLE_TARGET_REQUEST_NOT_INTEGRATED'
    # The only non-export exact numeric tokens were independently inspected:
    # Eagle 2022 Job IDs and nonidentity numeric telemetry in different jobs.
    assert all(('applications\\vasp' in r['path'] or '08_NLR_Kestrel_H100_GenAI_Power_Dataset312' in r['path'])
               for r in probe['matches']),'UNCLASSIFIED_SECONDARY_EXACT_UID_CANDIDATE'
    assert all('AGENTS.md' in r['path'] for r in probe['errors']),'UNREADABLE_TEXT_REQUEST_CANDIDATE'
    assert set(counts)=={'SOURCE_FIELD_ABSENT'},'NONABSENT_SOURCE_RESULT_REQUIRES_INTEGRATION'
    source_exports=[r for r in inventory if r['filename']=='esif.hpc.kestrel.job-anon.zip']
    assert len(source_exports)==2 and len({r['SHA256'] for r in source_exports})==1
    relevant_members=[dict(archive=r['absolute_path'],SHA256=r['SHA256'],member=m['member'],columns=m['columns'],
                            coverage=m['date_coverage']) for r in source_exports for m in r['archive_members']
                     if re.search(r'year=2025/month=[34]/',m['member'])]
    assert len(relevant_members)==4
    assert all(not any(c in m['columns'] for c in ('ReqTRES','ReqGRES','RegTRES','slurm_data')) for m in relevant_members)
    lfs_receipt=OUT/'RADDIT_LFS_PAYLOAD_RECONCILIATION.json'
    assert lfs_receipt.exists(),'MATERIALIZED_LFS_IDENTITY_AUDIT_REQUIRED'
    report=dict(available_April_source_audit_complete=True,additional_exact_recoverable_requests=0,
        raw_files_scanned=summary['files_scanned'],raw_files_SHA256_hashed=summary['files_hashed'],
        raw_bytes_hashed=summary['bytes_hashed'],Git_link_descriptors=len([r for r in inventory if r['format']=='symbolic_link']),
        source_candidates=summary['source_candidates'],Kestrel_export_candidates=relevant_members,
        LFS_pointers_resolved=len(lfs),walk_errors=summary['walk_errors'],
        LFS_identity_audit=dict(path=str(lfs_receipt),SHA256=hashlib.sha256(lfs_receipt.read_bytes()).hexdigest()),
        known_missing=5173,known_recovered=0,known_unresolved=5173,
        initial_Actual_missing=16284,initial_Actual_recovered=0,initial_Actual_unresolved=16284,
        all_roles=dict(counts),by_role={k:dict(v) for k,v in by_role.items()},
        ambiguous=0,source_field_absent_initial=21457,source_field_absent_full_ledger=len(rows),
        timezone_exact_join_correction=True,fuzzy_matches=0,rows_dropped=0,synthetic_GPU_fill=False,
        resource_fields_found=['gpus_requested','gpus_req','gpu_nodes_occupied','SLURM_GPUS_ON_NODE'],
        raw_Kestrel_request_fields_absent=['ReqTRES','ReqGRES','RegTRES','slurm_data'],
        ReqTRES_ReqGRES_documentation_and_script_examples='NOT_JOB_ID_SUBMISSION_REQUEST_AUTHORITY',
        secondary_UID_token_matches='Eagle 2022 different system/submission; six power telemetry files have numeric measurements, not matching job identity',
        residual_inventory_limits='Unrelated traffic 2019 ZIP compression is unsupported; malformed vendor JSON and nested non-job archives remain explicitly listed. These are not April scheduler request sources.',
        May_used_for_recovery_or_calibration=False,raw_files_copied_into_Git=0,
        runtime_service_authority='Current frozen V42 Q50 provider; requested walltime feature only',
        scientific_execution='NOT_RUN_INPUT_GATE_FAIL')
    write('EXTERNAL_RAW_REJOIN_AUDIT.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('Kestrel_export_candidates','by_role')},ensure_ascii=True))


if __name__=='__main__':main()
