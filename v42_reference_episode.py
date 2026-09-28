"""Policy-independent, causal reference placement at the execution-episode boundary.

This module has no policy, electrical, runtime-model or optimizer dependency.
Build chronologically ONCE, freeze, then read immutable independent daily slices.
An unresolved obligation is retained and blocks use; it is never moved to fit.
"""
from dataclasses import dataclass
from datetime import date
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import gzip

CONTRACT = 'V42_EPISODE_REFERENCE_V1'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                   ensure_ascii=False, allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class Observation:
    uid: str
    source_record_hash: str
    submit_seconds: int
    state: str
    gpu: int | None
    duration_slots: int | None
    duration_seconds: float | None
    duration_authority: str
    valid_request: bool
    qos: str
    known_start_seconds: int | None = None
    # Optional explicit attempt evidence; not populated from inferred labels.
    attempt_id: str | None = None
    attempt_authority_hash: str | None = None
    attempt_observed_seconds: int | None = None

    def validate(self, issue_seconds):
        if self.state not in ('PENDING', 'RUNNING') or self.submit_seconds > issue_seconds:
            raise ValueError('NONCAUSAL_OBSERVATION')
        if len(self.source_record_hash) != 64:
            raise ValueError('SOURCE_RECORD_HASH_REQUIRED')
        if self.state == 'PENDING' and self.known_start_seconds is not None:
            raise ValueError('FUTURE_START_NOT_AN_INPUT')
        if self.state == 'RUNNING' and (self.known_start_seconds is None or not self.submit_seconds <= self.known_start_seconds <= issue_seconds):
            raise ValueError('CAUSAL_RUNNING_START_REQUIRED')
        if self.valid_request and (type(self.gpu) is not int or self.gpu <= 0 or type(self.duration_slots) is not int
                                   or self.duration_slots <= 0 or self.duration_seconds is None or not math.isfinite(self.duration_seconds)
                                   or self.duration_seconds <= 0 or self.duration_slots != math.ceil(self.duration_seconds / 900)):
            raise ValueError('INVALID_AUTHORIZED_SERVICE')
        if self.attempt_id is not None and (not self.attempt_authority_hash or len(self.attempt_authority_hash) != 64
                or self.attempt_observed_seconds is None or self.attempt_observed_seconds > issue_seconds):
            raise ValueError('EXPLICIT_ATTEMPT_AUTHORITY_REQUIRED')

@dataclass(frozen=True)
class Capacity:
    sites: tuple[tuple[str, int], ...]
    racks: tuple[tuple[str, str, int], ...]
    prior: tuple[tuple[str, float], ...]

    def __post_init__(self):
        caps=dict(self.sites);prior=dict(self.prior)
        if len(caps)!=len(self.sites) or set(caps)!=set(prior) or any(type(c) is not int or c<=0 for c in caps.values()):
            raise ValueError('CAPACITY_AXIS')
        if any(not math.isfinite(w) or w<=0 for w in prior.values()) or len({r[0] for r in self.racks})!=len(self.racks):
            raise ValueError('RACK_PRIOR_AUTHORITY')
        if any(s not in caps or limit<=0 for _,s,limit in self.racks):raise ValueError('RACK_SITE_AUTHORITY')

    def eligible_racks(self, site, gpu):
        return tuple(sorted(r for r,s,c in self.racks if s==site and c>=gpu and dict(self.sites)[site]>=gpu))

    def preference(self, episode_id, gpu):
        prior=dict(self.prior)
        def score(s):
            n=int.from_bytes(hashlib.sha256(f'{CONTRACT}:{episode_id}:{s}'.encode()).digest()[:8], 'big')
            return -math.log((n+1)/(2**64+1))/prior[s], s
        return tuple(sorted((s for s,c in self.sites if c>=gpu and self.eligible_racks(s,gpu)), key=score))

class Reservations:
    """Append-only physical intervals with exact, coalesced site endpoints."""
    def __init__(self):
        self.rows=[];self.events=defaultdict(lambda:defaultdict(int))
    def append(self,row):
        a,b,g,uid,site=row
        self.rows.append(row);self.events[site][a]+=g;self.events[site][b]-=g
    def __iter__(self):return iter(self.rows)

def _events(intervals):
    if isinstance(intervals,Reservations):return intervals.events
    events=defaultdict(lambda:defaultdict(int))
    for a,b,g,uid,s in intervals:events[s][a]+=g;events[s][b]-=g
    return events

def _fits_events(events,start,end,gpu,cap):
    use=0
    for t,delta in sorted(events.items()):
        if t>=end:break
        if t>start and use+gpu>cap:return False
        use+=delta
        if t>=start and use+gpu>cap:return False
    return use+gpu<=cap

def fits(intervals, site, start, end, gpu, capacity):
    """Whole-interval simultaneous site capacity; logical racks are nonadditive."""
    if gpu > dict(capacity.sites)[site] or not capacity.eligible_racks(site,gpu):return False
    if isinstance(intervals,Reservations):
        return _fits_events(intervals.events[site],start,end,gpu,dict(capacity.sites)[site])
    events=defaultdict(int)
    for a,b,g,_,s in intervals:
        if s!=site or b<=start or a>=end:continue
        events[max(a,start)]+=g;events[min(b,end)]-=g
    use=0
    for _,delta in sorted(events.items()):
        use+=delta
        if use+gpu>dict(capacity.sites)[site]:return False
    return True

def reference_action(gpu, duration, release, intervals, capacity, max_start=20000):
    """Shared unknown/new-PENDING rule: no policy label or scoring input exists.

    The supplied intervals are current causal physical/resource state. Different
    state can legitimately produce a different default under the SAME rule.
    """
    if type(gpu) is not int or gpu<=0 or type(duration) is not int or duration<=0 or release<0:
        raise ValueError('REFERENCE_REQUEST')
    # Exact sweep equivalent to scanning every release event and testing the
    # whole interval. Skip a site's overloaded segments, never a feasible start.
    first=[];site_events=_events(intervals)
    for site,cap in sorted(capacity.sites):
        if cap<gpu or not capacity.eligible_racks(site,gpu):continue
        events=site_events[site]
        times=sorted(events);use=0;start=release
        for i,t in enumerate(times[:-1]):
            use+=events[t]
            if use+gpu<=cap:continue
            end=times[i+1]
            if start+duration<=t:break
            if start<end and start+duration>t:start=end
        if start<=max_start:first.append((start,site))
    if not first:return None
    start,site=min(first)
    choices=tuple(s for s,c in sorted(capacity.sites) if capacity.eligible_racks(s,gpu)
                  and _fits_events(site_events[s],start,start+duration,gpu,c))
    assert choices and choices[0]==site
    return dict(start=start,site=site,rack=capacity.eligible_racks(site,gpu)[0],feasible_sites=choices)

def capacity_audit(rows, capacity):
    events=defaultdict(lambda:defaultdict(list));issues=[]
    caps=dict(capacity.sites)
    for r in rows:
        s=r['reference_AIDC_site'];a=r['reference_start_slot'];b=r['reference_end_slot'];g=r['requested_GPU']
        if s is None or g is None:continue
        if s not in caps or r['reference_rack'] not in capacity.eligible_racks(s,g):
            issues.append(dict(kind='RACK_COMPATIBILITY_VIOLATION',site=s,episodes=[r['episode_id']],GPU=g))
        if a is None or b is None:continue
        events[s][a].append((r['episode_id'],g));events[s][b].append((r['episode_id'],-g))
    for site,points in events.items():
        active={};times=sorted(points)
        for i,t in enumerate(times):
            # Half-open intervals: all endpoint deltas applied before inspection.
            for uid,g in points[t]:
                active[uid]=active.get(uid,0)+g
                if active[uid]==0:del active[uid]
            if i+1<len(times) and sum(active.values())>caps[site]:
                issues.append(dict(kind='SITE_CAPACITY_VIOLATION',site=site,start=t,end=times[i+1],
                    GPU=sum(active.values()),capacity=caps[site],episodes=sorted(active),
                    cause='INHERITED_OBLIGATIONS_CONFLICT_UNDER_CURRENT_DURATION_AND_SYNTHETIC_CAPACITY',runtime_dependent=True))
    return issues

class ReferenceBuilder:
    """Single precompute pass; this object is never a policy-day worker state."""
    def __init__(self, capacity):
        self.capacity=capacity;self.history={};self.last_day=None

    def day(self, day, issue_seconds, observations):
        current=date.fromisoformat(day)
        if issue_seconds%900:raise ValueError('ISSUE_GRID')
        if self.last_day is not None and current<=self.last_day:raise ValueError('BUILDER_CHRONOLOGICAL_ONLY')
        rows=[];intervals=Reservations();seen=set();origins={};assigned_order=0
        for o in sorted(observations,key=lambda x:x.uid):
            o.validate(issue_seconds)
            if o.uid in seen:raise ValueError('DUPLICATE_SOURCE_UID')
            seen.add(o.uid);previous=self.history.get(o.uid);boundary=None;continuation=False;new=False
            explicit_new=previous is not None and o.attempt_id is not None and o.attempt_id!=previous['attempt_id']
            if previous is None or explicit_new:
                # Archive/content digests are provenance checks, never placement
                # seeds: an archive may contain records later than this issue.
                episode=digest(dict(contract=CONTRACT,uid=o.uid,submit=o.submit_seconds,attempt=o.attempt_id))
                new=True;authority='EXPLICIT_ATTEMPT' if o.attempt_id is not None else 'SOURCE_RECORD_SUBMISSION_AND_CONTIGUOUS_SNAPSHOTS'
                if previous is not None and o.attempt_observed_seconds<=previous['issue_seconds']:
                    boundary='EPISODE_BOUNDARY_UNRESOLVED'
            else:
                episode=previous['episode_id'];authority=previous['episode_boundary_authority']
                adjacent=(current-date.fromisoformat(previous['operating_day'])).days==1
                identity=(o.source_record_hash==previous['source_record_hash'] and o.submit_seconds==previous['submit_seconds']
                          and o.attempt_id==previous['attempt_id'])
                state_ok=not(previous['state_at_issue']=='RUNNING' and o.state=='PENDING')
                start_ok=(previous['state_at_issue']!='RUNNING' or o.known_start_seconds==previous['known_start_seconds'])
                if previous['state_at_issue']=='PENDING' and o.state=='RUNNING':start_ok=o.known_start_seconds>previous['issue_seconds']
                if not (adjacent and identity and state_ok and start_ok) or previous['boundary_status']=='EPISODE_BOUNDARY_UNRESOLVED':
                    boundary='EPISODE_BOUNDARY_UNRESOLVED'
                else:continuation=True
            inherited=previous if previous is not None and not new else None
            site=inherited['reference_AIDC_site'] if inherited else None
            rack=inherited['reference_rack'] if inherited else None
            r=dict(job_uid=o.uid,episode_id=episode,operating_day=day,state_at_issue=o.state,
                source_record_hash=o.source_record_hash,submit_seconds=o.submit_seconds,known_start_seconds=o.known_start_seconds,
                attempt_id=o.attempt_id,continuation_from_previous_snapshot=continuation,new_episode=new,
                reference_AIDC_site=site,reference_rack=rack,
                reference_site_origin='INHERITED_EPISODE_REFERENCE' if site is not None else 'UNRESOLVED',
                inherited_from_episode_day=inherited['assignment_day'] if inherited else None,
                assignment_day=inherited['assignment_day'] if inherited else None,reference_assignment_order=None,
                requested_GPU=o.gpu,safe_duration_slots=o.duration_slots,safe_duration_seconds=o.duration_seconds,
                duration_authority=o.duration_authority,resource_request_valid=o.valid_request,qos=o.qos,
                start_authority_class='INHERITED_CURRENT_CAUSAL_RUNNING_REMAINING' if o.state=='RUNNING' else 'INHERITED_REFERENCE_ABSOLUTE_START' if site else 'V41R2_ISSUE_RELEASE_FIRST_FIT',
                spatial_eligible=False,temporal_eligible_if_authorized=None,migration_selected_in_reference=False,
                episode_boundary_authority=authority,boundary_status=boundary or 'RESOLVED',
                capacity_feasible=False,rack_compatible=False,grid_information_used=False,policy_output_used=False,future_outcome_used=False,
                reference_start_slot=None,reference_end_slot=None,absolute_start_seconds=None,
                issue_seconds=issue_seconds,status=boundary or 'AWAITING_PLACEMENT')
            if boundary:r['status']=boundary
            elif not o.valid_request:r['status']='RESOURCE_DESCRIPTOR_AUTHORITY_CONFLICT' if site else 'INVALID_REQUEST_PRESERVED_OUTSIDE_CONTROLLED_COHORT'
            elif o.gpu>max(dict(self.capacity.sites).values()):r['status']='OUT_OF_DOMAIN_OVERSIZE_'+o.state
            elif inherited and inherited['requested_GPU']!=o.gpu:r['status']='RESOURCE_DESCRIPTOR_AUTHORITY_CONFLICT'
            elif site is not None:
                # A previous plan is not proof of execution. If a still-PENDING
                # episode's reserved start has passed, do not silently requeue it.
                start=0 if o.state=='RUNNING' else (inherited['absolute_start_seconds']-issue_seconds)//900 if inherited['absolute_start_seconds'] is not None else None
                if start is None or start<0:r['status']='REFERENCE_START_STATE_CONFLICT'
                else:
                    r.update(reference_start_slot=start,reference_end_slot=start+o.duration_slots,
                             absolute_start_seconds=issue_seconds+start*900,status='INHERITED_RESERVED')
                    intervals.append((start,start+o.duration_slots,o.gpu,episode,site))
            rows.append(r);origins[episode]=o
        # Continuing obligations are all reserved before any new placement.
        inherited_issues=capacity_audit(rows,self.capacity)
        blocked=bool(inherited_issues) or any(r['status'] in ('EPISODE_BOUNDARY_UNRESOLVED','REFERENCE_START_STATE_CONFLICT',
            'RESOURCE_DESCRIPTOR_AUTHORITY_CONFLICT','OUT_OF_DOMAIN_OVERSIZE_RUNNING') for r in rows)
        waiting=[r for r in rows if r['status']=='AWAITING_PLACEMENT']
        # Existing deterministic large-gang-first RUNNING then tier/FIFO PENDING.
        def priority(r):
            q=r['qos'].lower();tier=0 if q in ('high','urgent') else 1 if q=='normal' else 2 if q=='standby' else 3
            return (0,-r['requested_GPU'],r['job_uid']) if r['state_at_issue']=='RUNNING' else (1,tier,r['submit_seconds'],r['job_uid'])
        for r in sorted(waiting,key=priority):
            if blocked:r['status']='UNASSIGNED_BY_CONTINUITY_CONFLICT';continue
            gpu=r['requested_GPU'];duration=r['safe_duration_slots'];action=None
            if r['state_at_issue']=='RUNNING':
                for s in self.capacity.preference(r['episode_id'],gpu):
                    if fits(intervals,s,0,duration,gpu,self.capacity):
                        action=dict(site=s,rack=self.capacity.eligible_racks(s,gpu)[0],start=0);break
            else:action=reference_action(gpu,duration,0,intervals,self.capacity)
            if action is None:
                r['status']='NO_COMPATIBLE_FULL_SERVICE_CAPACITY'
                if r['state_at_issue']=='RUNNING':blocked=True
                continue
            assigned_order+=1;start=action['start']
            r.update(reference_AIDC_site=action['site'],reference_rack=action['rack'],reference_start_slot=start,
                reference_end_slot=start+duration,absolute_start_seconds=issue_seconds+900*start,
                assignment_day=day,reference_assignment_order=assigned_order,reference_site_origin='NEW_SYNTHETIC_ASSIGNMENT',status='NEW_RESERVED')
            intervals.append((start,start+duration,gpu,r['episode_id'],action['site']))
        issues=capacity_audit(rows,self.capacity)
        bad={e for i in issues for e in i['episodes']}
        for r in rows:
            site=r['reference_AIDC_site'];gpu=r['requested_GPU']
            r['rack_compatible']=bool(site and gpu and r['reference_rack'] in self.capacity.eligible_racks(site,gpu))
            r['capacity_feasible']=r['status'] in ('NEW_RESERVED','INHERITED_RESERVED') and r['episode_id'] not in bad and r['rack_compatible']
            r['spatial_eligible']=bool(r['state_at_issue']=='PENDING' and r['capacity_feasible'] and 24<=r['reference_start_slot']<120
                and sum(bool(self.capacity.eligible_racks(s,gpu)) for s,_ in self.capacity.sites)>1)
            self.history[r['job_uid']]=dict(r)
        ready=not blocked and not issues and all(r['capacity_feasible'] or (r['state_at_issue']=='PENDING' and r['status'] in
            ('INVALID_REQUEST_PRESERVED_OUTSIDE_CONTROLLED_COHORT','OUT_OF_DOMAIN_OVERSIZE_PENDING','NO_COMPATIBLE_FULL_SERVICE_CAPACITY')) or
            r['status']=='INVALID_REQUEST_PRESERVED_OUTSIDE_CONTROLLED_COHORT' for r in rows)
        self.last_day=current
        return dict(contract=CONTRACT,day=day,ready=ready,rows=rows,issues=issues)

def validate_initial_placement(row, chosen_site, chosen_start):
    """Boundary guard only. No new temporal/migration authorization."""
    if row['state_at_issue']=='RUNNING' or not row['spatial_eligible']:
        if chosen_site!=row['reference_AIDC_site']:raise ValueError('IMMUTABLE_INITIAL_SITE')
    if chosen_start!=row['reference_start_slot']:raise ValueError('TEMPORAL_AUTHORITY_NOT_BOUND')
    return True

def frozen_day(directory, day, *, audit_only=False):
    """Only a frozen manifest and this day are read; no adjacent-worker files.

    audit_only exposes blocked evidence for reproducibility diagnostics, never
    an executable input. Consumers must check the returned ready flag as well.
    """
    if date.fromisoformat(day).isoformat()!=day:raise ValueError('DATE_KEY')
    directory=Path(directory)
    freeze=json.loads((directory/'REFERENCE_LEDGER_FREEZE.json').read_text(encoding='utf8'))
    compressed=directory/'days'/f'{day}.json.gz'
    payload=json.loads(gzip.decompress(compressed.read_bytes()).decode('utf8') if compressed.exists()
                       else (directory/'days'/f'{day}.json').read_text(encoding='utf8'))
    if digest(payload)!=freeze['day_hashes'][day]:raise ValueError('FROZEN_DAY_HASH_MISMATCH')
    if payload['day']!=day or payload['contract']!=CONTRACT:raise ValueError('DAY_CONTRACT_MISMATCH')
    if not audit_only and (not freeze['ready'] or not payload['ready']):raise ValueError('REFERENCE_NOT_READY')
    return payload
