"""Static field/source search across every JSON and Parquet archive member."""
from audit_deadlines import *
import time

def main():
    a=Archive(); bysha=collections.defaultdict(list)
    for name,meta in a.index.items():
        if name.endswith(('.json','.parquet','.py','.md','.txt','.ps1','.csv')):
            bysha[meta['sha256']].append(name)
    pattern=re.compile(rb'"([A-Za-z0-9_ .-]*(?:deadline|latest.finish|latest.completion|reservation.window.end|sla.end|due.time|eligible.completion.window)[A-Za-z0-9_ .-]*)"\s*:',re.I)
    fields=collections.defaultdict(lambda:dict(member_count=0,unique_contents=0,key_occurrences=0,examples=[]))
    parquet={}; texts=[]; start=last=time.monotonic(); done=0; size=0; failed=[]
    requested_schema={}; boundary=[]; binds=[]; field_authorities=[]; gz_inventory=[]
    for sha,names in bysha.items():
        name=names[0]; data=a.read(name); done+=1; size+=len(data)
        if name.endswith('.json'):
            lower=data.lower()
            has_term=any(term in lower for term in (b'deadline',b'latest',b'reservation_window',b'reservation window',b'sla',b'due',b'eligible_completion',b'eligible completion'))
            counts=collections.Counter(m.group(1).decode() for m in pattern.finditer(data)) if has_term else {}
            for key,count in counts.items():
                stat=fields[key];stat['member_count']+=len(names);stat['unique_contents']+=1;stat['key_occurrences']+=count*len(names)
                if len(stat['examples'])<4: stat['examples'].append(name)
        elif name.endswith('.parquet'):
            schema=pq.read_schema(io.BytesIO(data)); keys=[key for key in schema.names if PATTERN.search(key)]
            selected=[key for key in keys if DEADLINE.search(key)]
            base=PurePosixPath(name).name
            group=parquet.setdefault(base,dict(member_count=0,unique_contents=0,schemas=[],deadline_fields={}))
            group['member_count']+=len(names);group['unique_contents']+=1
            if schema.names not in group['schemas']:group['schemas'].append(schema.names)
            if selected:
                table=pq.read_table(io.BytesIO(data),columns=selected)
                for key in selected:
                    stats=group['deadline_fields'].setdefault(key,dict(rows=0,nonnull_rows=0,samples=[],examples=[]))
                    col=table[key];stats['rows']+=len(col)*len(names);stats['nonnull_rows']+=(len(col)-col.null_count)*len(names)
                    if len(stats['examples'])<4:stats['examples'].append(name)
                    for v in col.to_pylist()[:3]:
                        if v not in stats['samples']:stats['samples'].append(v)
            if base in ('JOB_REQUEST_INPUTS.parquet','JOB_CLASSES.parquet'):
                requested_schema.setdefault(base,[]).append(dict(representative=name,equivalent_members=names,columns=schema.names))
        else:
            hits=[dict(line=i,text=line[:1500]) for i,line in enumerate(data.decode('utf-8-sig',errors='replace').splitlines(),1) if DEADLINE.search(line)]
            if hits:texts.append(dict(member=name,equivalent_members=names,hits=hits[:100]))
        if time.monotonic()-last>20:
            print(json.dumps(dict(stage='field_scan',unique_members=done,GB=round(size/1e9,2),seconds=round(time.monotonic()-start))),flush=True);last=time.monotonic()
    for day in sorted({r['day'] for r in a.j('FINAL_RESULT_INDEX.json')}):
        dp=f'{RUN}/audit/{day}/domain/DAILY_DOMAIN_AUTHORITY.json'
        binds.append(dict(member=dp,body=a.j(dp)))
        for policy,stage in [('B1','A0'),('B3','A1')]:
            name=f'{RUN}/{day}/{policy}/dayahead/{stage}/DAY_BOUNDARY_AUDIT.json'
            boundary.append(dict(member=name,body=a.j(name)))
        for policy in ('B0','B1','B2','B3'):
            name=f'{RUN}/{day}/{policy}/dayahead/aidc/AIDC_FIELD_AUTHORITY.json'
            if name in a.index:field_authorities.append(dict(member=name,body=a.j(name)))
    for n in a.index:
        if n.endswith('.gz'):gz_inventory.append(n)
    save('field_scan.json',dict(JSON_deadline_key_findings=dict(fields),parquet_schemas=parquet,text_findings=texts,
        requested_input_schemas=requested_schema,unique_content_files_scanned=done,member_files_covered=sum(map(len,bysha.values())),bytes_scanned=size,
        scan_elapsed_seconds=time.monotonic()-start,gzip_members=gz_inventory,scope='Every JSON key, every Parquet column name, text/CSV deadline terms. Equal member content deduplicated by SHA256; all numeric values remain archive-only.'))
    save('domain_bindings.json',binds);save('boundaries.json',boundary);save('aidc_field_authorities.json',field_authorities)
    save('scan_sources_used.json',a.used)
    print(json.dumps(dict(status='PASS',unique_files=done,JSON_deadline_fields=dict(fields),parquet_types_with_deadline={k:v['deadline_fields'] for k,v in parquet.items() if v['deadline_fields']}),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
