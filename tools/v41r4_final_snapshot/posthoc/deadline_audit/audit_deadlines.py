"""Read-only archive audit. Does not import any campaign or optimization module."""
import collections, csv, datetime, hashlib, io, json, math, re, subprocess
from pathlib import Path, PurePosixPath
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
CACHE = Path(r'\\?\C:\Users\kjw39\AppData\Local\Temp\V41R4_FinalArchive_Source_20260909\V41R4_May2025_raw')
PARENT = Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/결과 데이터')
CORRECTED = PARENT/'MobileESS_V41R4_Paper_CSV_Export_corrected_20260909_112635'
LOCATOR = PARENT/'MobileESS_V41R4_Paper_CSV_Export'/'TERMINAL_RESIDUAL_REAUDIT.csv'
REPO = Path(r'D:\ChatGPT\Mobile ESS 2\v41r4_final_results_pr')
COMMIT = '33a86d31c27051aedbdb93d60b844216533a45a9'
RUN = 'frozen_artifacts/v41r4_may/loop_wall_v4'
REV = 'frozen_artifacts/v41r4_restoration_revision_v1'
NA = 'NOT_AVAILABLE'
PATTERN = re.compile(r'deadline|latest.?finish|latest.?complet|reservation.?window|sla|due.?time|eligible.?complet|RW_completion|RSP_start|ISSUE_BEGIN|ISSUE_END|safe_duration|requested.*(?:wall|seconds)|qos|state_at_issue', re.I)
DEADLINE = re.compile(r'deadline|latest.?finish|latest.?complet|reservation.?window.?end|sla.?end|due.?time|eligible.?completion.?window', re.I)

def digest(data): return hashlib.sha256(data).hexdigest()
def save(name,obj): (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
class Archive:
    def __init__(self):
        self.verification=json.loads((HERE/'archive_verification.json').read_text(encoding='utf-8'))
        assert self.verification['status']=='PASS'
        self.index={n.split('/',1)[1]:v for n,v in json.loads((HERE/'archive_member_index.json').read_text(encoding='utf-8')).items()}
        self.used={}
    def read(self,name):
        assert name in self.index and ':' not in name and '..' not in PurePosixPath(name).parts,name
        data=CACHE.joinpath(*PurePosixPath(name).parts).read_bytes()
        assert len(data)==self.index[name]['bytes'] and digest(data)==self.index[name]['sha256'],name
        self.used[name]=self.index[name]
        return data
    def j(self,name): return json.loads(self.read(name).decode('utf-8-sig'))
    def resolve(self,path,sha):
        name=str(path).replace('\\','/')
        name='frozen_artifacts/'+name.split('frozen_artifacts/',1)[1]
        assert self.index[name]['sha256']==sha
        return name

def span(parts,lo=-math.inf,hi=math.inf):
    spans=sorted((float(s['start']),float(s['end'])) for s in parts)
    assert all(e>=s for s,e in spans) and all(a[1]<=b[0] for a,b in zip(spans,spans[1:]))
    return math.fsum(max(0,min(e,hi)-max(s,lo)) for s,e in spans)

def walk(obj,path=''):
    if isinstance(obj,dict):
        for key,value in obj.items():
            loc=f'{path}.{key}' if path else key
            if PATTERN.search(key): yield loc,value
            yield from walk(value,loc)
    elif isinstance(obj,list):
        for value in obj: yield from walk(value,path+'[]')

def collect():
    a=Archive(); final=a.j('FINAL_RESULT_INDEX.json'); finalaudit=a.j(REV+'/FINAL_AUDIT.json')
    assert len(final)==124 and finalaudit['counts']['total_accepted']==124 and not finalaudit['pending']
    refs={}; rows=[]; units=[]; field_counts=collections.defaultdict(collections.Counter); special=[]
    selected_uid_days=collections.defaultdict(set); jobkeys=set(); source_map=[]
    for entry in sorted(final,key=lambda r:(r['day'],r['policy'])):
        day,policy=entry['day'],entry['policy']; acc=a.j(entry['acceptance']); assert acc['status']=='PASS'
        joint=a.resolve(acc['new_joint']['path'],acc['new_joint']['sha256'])
        jobs=a.j(joint)['decision']['AIDC_decision']
        if day not in refs:
            refpath=f'{RUN}/{day}/B0/dayahead/FROZEN_JOINT_DECISION.json'
            refs[day]={str(j['job_uid']):j for j in a.j(refpath)['decision']['AIDC_decision']}
        unit=dict(day=day,policy=policy,total_jobs=len(jobs),selected_jobs=0,migrations=0,flagged=0,selected_jobs_with_explicit_deadline_field=0)
        for job in jobs:
            uid=str(job['job_uid']); ref=refs[day][uid]; jobkeys.update(job)
            selected=job['AIDC_site']!='UNASSIGNED'
            if selected:
                unit['selected_jobs']+=1; selected_uid_days[uid].add(day)
                matches=list(walk(job)); deadlines=[(k,v) for k,v in matches if DEADLINE.search(k.rsplit('.',1)[-1])]
                for k,v in matches:
                    field_counts[policy][k]+=1
                if deadlines:
                    unit['selected_jobs_with_explicit_deadline_field']+=1
                    special.append(dict(day=day,policy=policy,job_uid=uid,fields=deadlines))
            old,new=ref['compute_segments'],job['compute_segments']
            delta=span(new,120)-span(old,120)
            flagged=delta>1e-9; migrated=bool(job.get('migration_selected',False))
            unit['flagged']+=flagged; unit['migrations']+=migrated
            assert not flagged or migrated
            if not migrated: continue
            assert selected and len(new)==2 and len(job['migration_events'])==1
            event=job['migration_events'][0]
            assert event['slot_origin']=='D_MINUS_1_ISSUE'
            completion=max(s['end'] for s in new); reference=max(s['end'] for s in old)
            assert completion==job['end_slot'] and reference==ref['end_slot']
            assert span(new)==span(old)==job['safe_duration_slots']
            assert job['RW_completion_slot']==ref['RW_completion_slot']
            cp=job['migration_checkpoint_slot']; ready=job['restart_complete_slot']
            assert cp==event['checkpoint'] and ready==event['restart_end']==new[-1]['start']
            assert completion-reference==ready-cp
            row=dict(day=day,policy=policy,job_uid=uid,requested_GPU=job['requested_GPU'],state_at_issue=job['state_at_issue'],qos=job['qos'],
                terminal_deferral_flagged=flagged,coordinate_system='D_MINUS_1_ISSUE_15_MINUTE_HALF_OPEN',
                reference_start_slot=ref['start_slot'],reference_completion_slot=reference,
                migration_checkpoint_slot=cp,transfer_start_slot=event['transfer_start'],transfer_end_slot=event['transfer_end'],restart_complete_slot=ready,
                optimized_completion_slot=completion,final_completion_slot=completion,D_day_begin_slot=24,D_day_end_slot=120,
                post_day_extension_slots=max(0,completion-120),completion_delay_slots=completion-reference,interruption_slots=ready-cp,
                authoritative_deadline_slot=NA,deadline_source=NA,deadline_semantics='DEADLINE_AUTHORITY_NOT_ESTABLISHED',
                deadline_slack_slots=NA,deadline_slack_hours=NA,within_deadline=NA,
                RW_completion_slot=job['RW_completion_slot'],RSP_start_slot=job['RSP_start_slot'],
                safe_duration_slots=job['safe_duration_slots'],safe_duration_seconds=job['safe_duration_seconds'],
                requested_walltime_seconds=job.get('requested_walltime_seconds',NA),duration_authority=job.get('duration_authority',NA),
                diagnostic_RW_minus_completion_slots=job['RW_completion_slot']-completion,
                diagnostic_RW_minus_completion_hours=(job['RW_completion_slot']-completion)/4,
                diagnostic_completion_le_RW=completion<=job['RW_completion_slot'],
                reference_post_horizon_service_slots=span(old,120),optimized_post_horizon_service_slots=span(new,120),
                post_horizon_GPUh=span(new,120)*job['requested_GPU']/4,
                additional_post_horizon_GPUh=delta*job['requested_GPU']/4,
                reference_compute_segments=old,optimized_compute_segments=new,
                candidate_job_specific_deadline_checked=False,
                source_inside_archive=joint,source_SHA256=a.index[joint]['sha256'])
            rows.append(row)
        source_map.append(dict(day=day,policy=policy,joint=joint,acceptance=entry['acceptance']))
        units.append(unit)
    flagged=[r for r in rows if r['terminal_deferral_flagged']]
    locator_data=LOCATOR.read_bytes(); loc=list(csv.DictReader(io.StringIO(locator_data.decode('utf-8-sig'))))
    key=lambda r:(r['day'],r['policy'],str(r['job_uid']))
    assert {key(r) for r in loc}=={key(r) for r in flagged} and len(flagged)==len(loc)==619
    assert collections.Counter(r['policy'] for r in flagged)=={'B1':306,'B3':313}
    assert collections.Counter(r['policy'] for r in rows)=={'B1':333,'B3':344}
    save('computed_records.json',rows);save('population_units.json',units);save('source_map.json',source_map)
    save('job_field_coverage.json',dict(fields={p:dict(c) for p,c in field_counts.items()},explicit_deadline_fields=special,all_job_keys=sorted(jobkeys),
        selected_unique_uid_count=len(selected_uid_days),selected_repeated_uid_count=sum(len(ds)>1 for ds in selected_uid_days.values()),
        locator=dict(path=str(LOCATOR),sha256=digest(locator_data),usage='cohort keys only; all result values recomputed from archive')))
    save('archive_sources_used.json',a.used)
    print(json.dumps(dict(migrations=len(rows),flagged=len(flagged),unique_flagged=len({r['job_uid'] for r in flagged}),
        explicit_deadline_fields=len(special),units=units[-4:],examples=[r for r in rows if (r['day'],r['job_uid']) in [('2025-05-15','8952973'),('2025-05-01','8571256')]]),ensure_ascii=False),flush=True)

if __name__=='__main__': collect()
