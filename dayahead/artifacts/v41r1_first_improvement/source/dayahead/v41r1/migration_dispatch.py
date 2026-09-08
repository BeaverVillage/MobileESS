"""Exact-time deterministic replay of frozen migration progress and WAN order."""
from collections import defaultdict
import heapq
from dayahead.v40d_actual.job_replay import priority_key
from dayahead.v41.actual_audit import NS,SLOT_NS
from dayahead.v41.reserve import require


def execute(rows,original,durations,capacity,wan):
    admitted={u:r for u,r in rows.items() if r['frozen_policy_admitted']}
    migrations=sorted(u for u,r in admitted.items() if r.get('migration_selected'))
    require(wan is not None,'FROZEN_WAN_REPLAY_AUTHORITY_MISSING')
    for u in migrations:
        e=admitted[u]['migration_events'][0];s=e['source_AIDC'];d=e['destination_AIDC']
        require(tuple(e['fixed_path_links'])==tuple(wan.path(s,d)) and e['fixed_path_id']==wan.path_id(s,d),
            'FROZEN_ACTUAL_WAN_PATH_DRIFT')
        require(e['payload_bytes']==wan.payload_bytes(admitted[u]['requested_GPU']),'FROZEN_ACTUAL_WAN_PAYLOAD_DRIFT')
        # Registered WAN authority is a stationary frozen link service curve.
        # Shifting its clock creates no Day+1 forecast or grid calculation.
        for link in e['fixed_path_links']:
            rates={wan.capacity_bytes(link,t) for t in range(96)}
            require(len(rates)==1,'NONSTATIONARY_WAN_REQUIRES_AUTHORITATIVE_EVENT_REPLAY')
    queue=[];serial=0;used=dict.fromkeys(capacity,0);active={};parts=defaultdict(list)
    requests=[];blockers=defaultdict(set);waits=[];states={u:'BEFORE_CHECKPOINT' for u in migrations}
    evidence={};chunks=[];wan_pointer=0;wan_busy_until=0;wan_active=None
    def push(t,kind,uid,payload=None):
        nonlocal serial
        serial+=1;heapq.heappush(queue,(t,serial,kind,uid,payload))
    for u,r in admitted.items():
        require(r['requested_GPU']<=capacity[r['compute_segments'][0]['site']],'FROZEN_GPU_GANG_EXCEEDS_SITE')
        if r['state_at_issue']=='RUNNING':push(0,'INITIAL',u)
        else:push(int(r['start_slot'])*SLOT_NS,'INITIAL',u)
    push(24*SLOT_NS,'BOUNDARY','');push(120*SLOT_NS,'BOUNDARY','')
    while queue:
        t=queue[0][0];events=[]
        while queue and queue[0][0]==t:events.append(heapq.heappop(queue))
        # All releases precede starts at equal timestamps.
        for _,_,kind,u,payload in events:
            if kind not in ('COMPUTE_END','CHECKPOINT'):continue
            site,a,b,phase=active.pop(u);r=admitted[u]
            used[site]-=r['requested_GPU'];require(used[site]>=0,'GPU_RELEASE_UNDERFLOW')
            parts[u].append((u,site,a,b,r['requested_GPU']))
            if kind=='CHECKPOINT':
                states[u]='WAN_WAIT';evidence[u]['ACTUAL_CHECKPOINT_NS']=t
            elif u in states and phase=='SOURCE':states[u]='CANCELLED_COMPLETED_BEFORE_CHECKPOINT'
        for _,_,kind,u,payload in events:
            if kind=='INITIAL':requests.append((u,'SOURCE' if u in states else 'SINGLE',t))
            elif kind=='WAN_END':
                require(wan_active==u,'WAN_RELEASE_ORDER');wan_active=None
                states[u]='RESTART_WAIT';push(t+SLOT_NS,'RESTART_READY',u)
                wan_pointer+=1
            elif kind=='RESTART_READY':requests.append((u,'DESTINATION',t))
        left=[]
        for u,phase,ready in sorted(requests,key=lambda v:(0 if admitted[v[0]]['state_at_issue']=='RUNNING' and v[1]!='DESTINATION' else 1,priority_key(original[v[0]]),v[1])):
            r=admitted[u];site=r['compute_segments'][1 if phase=='DESTINATION' else 0]['site'];g=r['requested_GPU']
            if used[site]+g>capacity[site]:
                if r['state_at_issue']=='RUNNING' and phase!='DESTINATION':
                    raise ValueError('IMMUTABLE_RUNNING_EXECUTION_CAPACITY_CONFLICT:'+u)
                held=sorted(v for v,x in active.items() if x[0]==site);blockers[u].update(held)
                waits.append(dict(job_id=u,event_ns_from_issue=t,blocking_job_ids=held,SITE=site,GPU_REQUEST=g,
                    phase=phase,DELAY_REASON='RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN'))
                left.append((u,phase,ready));continue
            used[site]+=g
            if phase=='DESTINATION':
                offset=evidence[u]['CHECKPOINT_OFFSET_NS'];duration=durations[u]-offset
                evidence[u]['ACTUAL_RESTART_NS']=t;end=t+duration;kind='COMPUTE_END';states[u]='DESTINATION'
            elif u in states:
                event=r['migration_events'][0]
                da_start=(0 if r['state_at_issue']=='RUNNING' else int(r['start_slot']))*SLOT_NS
                offset=int(event['checkpoint'])*SLOT_NS-da_start
                require(offset>0,'FROZEN_CHECKPOINT_PROGRESS_NOT_POSITIVE')
                end=t+min(durations[u],offset);kind='CHECKPOINT' if durations[u]>offset else 'COMPUTE_END'
                evidence[u]=dict(DA_EXECUTION_START_NS=da_start,ACTUAL_EXECUTION_START_NS=t,
                    DA_CHECKPOINT_NS=int(event['checkpoint'])*SLOT_NS,CHECKPOINT_OFFSET_NS=offset,
                    ACTUAL_CHECKPOINT_NS=t+offset,DA_WAN_START_NS=int(event['transfer_start'])*SLOT_NS,
                    DA_RESTART_NS=int(event['restart_end'])*SLOT_NS,source=event['source_AIDC'],
                    destination=event['destination_AIDC'],WAN_path=event['fixed_path_links'],
                    WAN_path_id=event['fixed_path_id'],payload_bytes=event['payload_bytes'],
                    migration_order=migrations.index(u),actual_WAN_chunks=[])
            else:end=t+durations[u];kind='COMPUTE_END'
            active[u]=(site,t,end,phase);push(end,kind,u)
        requests=left
        # Same frozen UID ordering, including waiting for an earlier job's
        # progress checkpoint. Completion before checkpoint cancels as before.
        while wan_pointer<len(migrations) and states[migrations[wan_pointer]]=='CANCELLED_COMPLETED_BEFORE_CHECKPOINT':
            wan_pointer+=1
        if wan_active is None and wan_pointer<len(migrations):
            u=migrations[wan_pointer]
            if states[u]=='WAN_WAIT':
                start=max(t,wan_busy_until,26*SLOT_NS)
                if start>t:push(start,'WAN_WAKE',u)
                else:
                    r=admitted[u];event=r['migration_events'][0];positive=[b for b in event['bytes_by_slot'] if b]
                    e=evidence[u];e['ACTUAL_WAN_START_NS']=start
                    for i,amount in enumerate(positive):
                        require(all(amount<=wan.capacity_bytes(link,0) for link in event['fixed_path_links']),
                            'SHIFTED_FROZEN_WAN_RATE_EXCEEDS_CAPACITY')
                        chunk=dict(job_id=u,start_ns=start+i*SLOT_NS,end_ns=start+(i+1)*SLOT_NS,
                            bytes=amount,path=event['fixed_path_links'])
                        chunks.append(chunk);e['actual_WAN_chunks'].append(chunk)
                    wan_busy_until=start+len(positive)*SLOT_NS;wan_active=u;states[u]='TRANSFERRING'
                    e['ACTUAL_WAN_END_NS']=wan_busy_until;push(wan_busy_until,'WAN_END',u)
    require(not requests and not active and wan_pointer==len(migrations),'FROZEN_PHYSICAL_REPLAY_DID_NOT_DRAIN')
    require(all(sum(b-a for _,_,a,b,g in parts[u])==durations[u] for u in admitted),'EXACT_REALIZED_SERVICE_LOSS')
    require(all(a['end_ns']<=b['start_ns'] for a,b in zip(chunks,chunks[1:])),'ACTUAL_WAN_SERIAL_OVERLAP')
    for u,e in evidence.items():
        executed=len(parts[u])==2;e['migration_executed']=executed
        e['START_DELAY_SECONDS']=(e['ACTUAL_EXECUTION_START_NS']-e['DA_EXECUTION_START_NS'])/NS
        e['WAN_QUEUE_DELAY_SECONDS']=(e['ACTUAL_WAN_START_NS']-e['ACTUAL_CHECKPOINT_NS'])/NS if executed else 0.
        e['RESTART_GPU_QUEUE_DELAY_SECONDS']=(e['ACTUAL_RESTART_NS']-e['ACTUAL_WAN_END_NS']-SLOT_NS)/NS if executed else 0.
        e['TOTAL_MIGRATION_DELAY_SECONDS']=(e['ACTUAL_RESTART_NS']-e['DA_RESTART_NS'])/NS if executed else None
        e['MIGRATION_CARRY_OUT']=executed and e['ACTUAL_RESTART_NS']>=120*SLOT_NS
        e['MIGRATION_COMPLETED_WITHIN_HORIZON']=executed and e['ACTUAL_RESTART_NS']<120*SLOT_NS
        e['state_propagated_to_next_day']=False
        e['cancellation_reason']=None if executed else 'COMPLETED_BEFORE_PROGRESS_CHECKPOINT'
        rows[u]['actual_migration_execution']=e
    return dict(parts=dict(parts),blockers=blockers,waits=waits,evidence=evidence,WAN_chunks=chunks,
        authority='Frozen stationary path capacity and payload chunks, translated in exact time; independent Day-D only')


def persist(output,replay,issue_time):
    import pandas as pd
    from dayahead.v41.scientific_archive import document,scalar_frame
    from dayahead.v41.persistence import table
    issue=pd.Timestamp(issue_time);rows=[]
    for uid,e in sorted(replay['evidence'].items()):
        row=dict(e,job_id=uid)
        names={'DA_EXECUTION_START_NS':'DA_EXECUTION_START','ACTUAL_EXECUTION_START_NS':'ACTUAL_EXECUTION_START',
            'DA_CHECKPOINT_NS':'DA_CHECKPOINT_TIME','ACTUAL_CHECKPOINT_NS':'ACTUAL_CHECKPOINT_TIME',
            'DA_WAN_START_NS':'DA_WAN_START','ACTUAL_WAN_START_NS':'ACTUAL_WAN_START',
            'DA_RESTART_NS':'DA_RESTART_TIME','ACTUAL_RESTART_NS':'ACTUAL_RESTART_TIME'}
        for source,dest in names.items():row[dest]=(issue+pd.Timedelta(e[source],unit='ns')).isoformat() if source in e else None
        row['CHECKPOINT_OFFSET']=e['CHECKPOINT_OFFSET_NS']/NS
        row['START_DELAY']=e['START_DELAY_SECONDS'];row['WAN_QUEUE_DELAY']=e['WAN_QUEUE_DELAY_SECONDS']
        row['TOTAL_MIGRATION_DELAY']=e['TOTAL_MIGRATION_DELAY_SECONDS']
        rows.append(row)
    files=dict(jobs=table(output/'aidc/ACTUAL_MIGRATION_CLOCKS.parquet',scalar_frame(rows)),
        WAN_chunks=table(output/'aidc/ACTUAL_WAN_EXECUTION_CHUNKS.parquet',scalar_frame(replay['WAN_chunks'])))
    document(output/'aidc/ACTUAL_MIGRATION_REPLAY_AUDIT.json',dict(status='PASS',files=files,
        frozen_decisions_preserved=True,checkpoint_progress_preserved=True,WAN_path_payload_order_preserved=True,
        Actual_optimizer_calls=0,propagated_to_next_day=False,authority=replay['authority'],
        carry_out_count=sum(e['MIGRATION_CARRY_OUT'] for e in replay['evidence'].values())))
