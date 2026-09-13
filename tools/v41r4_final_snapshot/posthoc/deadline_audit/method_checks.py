from audit_deadlines import *
import gzip

FILES={
 'dayahead/v37/aidc_materializer.py':[(191,206),(390,412),(416,480),(560,573),(831,844)],
 'dayahead/v41/common.py':[(17,45),(47,85),(94,100)],
 'dayahead/v41/data.py':[(39,57)],
 'dayahead/v41r2/reference.py':[(1,95)],
 'dayahead/v41r1/migration.py':[(1,49),(87,133)],
 'dayahead/v40g/domain.py':[(39,57),(73,88),(102,133),(140,172)],
 'dayahead/v41r1/terminal.py':[(59,74),(94,130)],
 'dayahead/v41/temporal_restore.py':[(20,60)],
 'dayahead/v41/scientific_archive.py':[(125,168)],
 'dayahead/v41/actual_dispatch.py':[(118,131),(150,156)],
 'dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt':[(44,61),(363,408),(670,679),(820,833)],
}

def main():
    a=Archive();records=json.loads((HERE/'computed_records.json').read_text(encoding='utf-8'))
    source=[];gitbytes={}
    for name,ranges in FILES.items():
        data=subprocess.check_output(['git','show',f'{COMMIT}:{name}'],cwd=REPO);gitbytes[name]=data
        lines=data.decode('utf-8-sig').splitlines()
        source.append(dict(path=name,commit=COMMIT,sha256=digest(data),bytes=len(data),
            excerpts=[dict(begin=lo,end=min(hi,len(lines)),lines=lines[lo-1:hi]) for lo,hi in ranges]))
    bindings=[];boundaries=[];candidates=[];request_fields=[];raw_field_matches=[]
    for day in sorted({r['day'] for r in a.j('FINAL_RESULT_INDEX.json')}):
        name=f'{RUN}/audit/{day}/domain/DAILY_DOMAIN_AUTHORITY.json'
        body=a.j(name)
        for entry in body['sources']:
            filename=entry['path'].replace('\\','/'); filename='dayahead/'+filename.split('dayahead/',1)[1] if 'dayahead/' in filename else None
            if filename in gitbytes:
                assert digest(gitbytes[filename])==entry['sha256']
                bindings.append(dict(day=day,archive_member=name,source=filename,sha256=entry['sha256'],match=True))
        for policy,stage in [('B1','A0'),('B3','A1')]:
            name=f'{RUN}/{day}/{policy}/dayahead/{stage}/DAY_BOUNDARY_AUDIT.json'; body=a.j(name)
            assert body['H']==body['grid_slots']==96 and body['issue_begin']==24 and body['issue_end_exclusive']==120
            assert not body['terminal_residual_constraint_active'] and not body['service_neutrality_constraint_active']
            boundaries.append(dict(member=name,body=body))
            name=f'{RUN}/{day}/{policy}/dayahead/aidc/migration/MIGRATION_CANDIDATES.parquet'
            table=pq.read_table(io.BytesIO(a.read(name)))
            selected=[r for r in table.to_pylist() if r['selected_migration']]
            expected={r['job_uid']:r for r in records if r['day']==day and r['policy']==policy}
            assert {str(r['job_id']) for r in selected}==set(expected)
            for row in selected:
                final=expected[str(row['job_id'])]
                assert row['GPU_request']==final['requested_GPU'] and row['first_checkpoint_only_user_authorized_revision']
                assert row['structurally_migration_eligible'] and row['migration_eligible']
                candidates.append(dict(day=day,policy=policy,member=name,job_uid=str(row['job_id']),
                    state_at_D00=row['state_at_D00'],source_type=row['candidate_source_type'],
                    selected_migration=row['selected_migration'],migration_eligible=row['migration_eligible'],
                    explicit_option_count=row['explicit_option_count'],selected_checkpoint=row['selected_checkpoint'],
                    first_valid_checkpoint=row['first_valid_checkpoint'],restart_time=row['restart_time'],
                    candidate_deadline_columns=[n for n in table.schema.names if DEADLINE.search(n)]))
        for policy in ('B0','B1','B2','B3'):
            name=f'{RUN}/{day}/{policy}/dayahead/authority/JOB_REQUEST_INPUTS.parquet'
            # Historical May31 B2 failed persistence may omit this file; final jobs still audited.
            if name not in a.index:
                request_fields.append(dict(day=day,policy=policy,member=name,status='NOT_ARCHIVED'))
                continue
            raw=a.read(name); table=pq.read_table(io.BytesIO(raw)); metadata=table.schema.metadata or {}
            dfields=[n for n in table.schema.names if DEADLINE.search(n)]
            mdhits={k.decode():v.decode(errors='replace') for k,v in metadata.items() if DEADLINE.search(v.decode(errors='replace'))}
            request_fields.append(dict(day=day,policy=policy,member=name,status='SCANNED',rows=table.num_rows,fields=table.schema.names,deadline_fields=dfields,metadata_deadline_hits=mdhits))
    assert len(bindings)==31*4 and len(candidates)==677
    compressed=collections.defaultdict(list)
    for n,v in a.index.items():
        if n.endswith('.jsonl.gz'):compressed[v['sha256']].append(n)
    candidate_headers=[]
    for sha,names in compressed.items():
        data=a.read(names[0])
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as handle:
            first=handle.readline()
        obj=json.loads(first); candidate_headers.append(dict(member=names[0],equivalent_members=names,header=obj,deadline_terms=DEADLINE.findall(first.decode())))
    save('method_sources.json',source);save('method_hash_bindings.json',bindings);save('verified_boundaries.json',boundaries)
    save('candidate_artifact_checks.json',candidates);save('request_input_checks.json',request_fields);save('compressed_candidate_headers.json',candidate_headers)
    save('method_archive_sources_used.json',a.used)
    print(json.dumps(dict(method_source_files=len(source),hash_matches=len(bindings),candidate_matches=len(candidates),request_input_files=len(request_fields),candidate_header_files=len(candidate_headers))),flush=True)

if __name__=='__main__':main()
