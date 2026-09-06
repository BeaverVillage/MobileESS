"""Independent Day-D placement and inherited RUNNING migration authority.

The final pre-start addendum freezes starts/admission. First placement has no
checkpoint payload. Both D00 populations share checkpoint/WAN/restart rules.
"""
from copy import deepcopy
from dayahead.v38.authority import checkpoint_slots

H=96
BEGIN=24
END=120
CONTRACT='V41R1_D00_RUNNING_AND_PENDING_PRESTART_RELOCATION_V2'


def active(row):return row.get('v41r1_migration_contract')==CONTRACT


def state_at_d00(row):
    start=int(row.get('r1_reference_start',row['start_slot']))
    end=int(row.get('r1_reference_end',row['end_slot']))
    if end<=BEGIN:return 'COMPLETE'
    return 'RUNNING' if start<BEGIN else 'PENDING'


def pending_in_day(row):
    return (active(row) and state_at_d00(row)=='PENDING' and
        row['r1_reference_site']!='UNASSIGNED' and BEGIN<=row['r1_reference_start']<END)


def target(row):
    return active(row) and (state_at_d00(row)=='RUNNING' or pending_in_day(row))


def attach(jobs):
    result=deepcopy(jobs)
    for row in result:
        row.update(v41r1_migration_contract=CONTRACT,r1_reference_start=int(row['start_slot']),
            r1_reference_end=int(row['end_slot']),r1_reference_site=row['AIDC_site'],
            r1_reference_rack=row['Rack_label'],initial_Rack_label=row['Rack_label'])
    return result


def fixed_pending(row):
    return active(row) and not pending_in_day(row)


def placement_sites(row,capacity):
    if not pending_in_day(row):return (row['AIDC_site'],)
    return tuple(s for s in capacity.aidc_ids if capacity.site_capacity[s]>=row['requested_GPU']
        and capacity.eligible_racks(s,row['requested_GPU']))


def checkpoints(row,elapsed=None):
    if not target(row):return ()
    start=row['r1_reference_start'];end=row['r1_reference_end']
    if pending_in_day(row):
        return tuple(start+t for t in checkpoint_slots(0,END-start) if start+t<end)
    if row['state_at_issue']=='RUNNING':
        if elapsed is None or row['job_uid'] not in elapsed:
            raise ValueError('RUNNING_MIGRATION_CAUSAL_ELAPSED_AUTHORITY_MISSING')
        elapsed_seconds=elapsed[row['job_uid']]+BEGIN*900
    else:elapsed_seconds=(BEGIN-start)*900
    return tuple(BEGIN+t for t in checkpoint_slots(elapsed_seconds,H) if BEGIN+t<end)


def check(reference,candidate):
    if not active(reference) or not active(candidate):raise ValueError('MIGRATION_REVISION_AUTHORITY_REQUIRED')
    for k in ('v41r1_migration_contract','r1_reference_start','r1_reference_end','r1_reference_site','r1_reference_rack',
              'safe_duration_slots','safe_duration_seconds','state_at_issue','requested_GPU','RSP_start_slot','RW_completion_slot'):
        if reference.get(k)!=candidate.get(k):raise ValueError('MIGRATION_COMMON_AUTHORITY_CHANGED:'+k)
    if candidate['start_slot']!=reference['r1_reference_start']:raise ValueError('REFERENCE_PLANNED_START_MUST_REMAIN_UNCHANGED')
    if (candidate['AIDC_site']=='UNASSIGNED')!=(reference['r1_reference_site']=='UNASSIGNED'):
        raise ValueError('FROZEN_ADMISSION_CHANGED')
    if candidate.get('migration_selected'):
        if not target(reference):raise ValueError('MIGRATION_OUTSIDE_D00_RUNNING_OR_INDAY_PENDING')
        parts=candidate['compute_segments'];cp=candidate['migration_checkpoint_slot'];ready=candidate['restart_complete_slot']
        if not max(BEGIN,candidate['start_slot'])<cp<ready<END:
            raise ValueError('RUNNING_MIGRATION_TIME_BOUNDARY')
        if pending_in_day(reference) and cp!=checkpoints(reference)[0]:
            raise ValueError('EXISTING_FIRST_CHECKPOINT_AUTHORITY_CHANGED')
        if not pending_in_day(reference) and parts[0]['site']!=reference['r1_reference_site']:
            raise ValueError('CARRY_IN_INITIAL_SITE_CHANGED')
        if not ready<min(END,parts[-1]['end']):raise ValueError('NO_USEFUL_IN_DAY_DESTINATION_SERVICE')
    else:
        if candidate['end_slot']!=reference['r1_reference_end']:raise ValueError('NONMIGRATED_RUNTIME_CHANGED')
        if not pending_in_day(reference) and candidate['AIDC_site']!=reference['r1_reference_site']:
            raise ValueError('FIXED_INITIAL_SITE_CHANGED')


def model_boundary(model,jobs,options_by_uid,slots):
    import re,hashlib
    if slots!=H:raise ValueError('SCIENTIFIC_DAY_MUST_HAVE_96_SLOTS')
    count=0
    for row in jobs:
        for opt in options_by_uid[row['job_uid']]:
            assert opt.start==row['r1_reference_start']
            if opt.migrated:
                assert BEGIN<=opt.checkpoint<=opt.transfer_start<opt.transfer_end<opt.transfer_end+1<END
                if pending_in_day(row):assert opt.checkpoint==checkpoints(row)[0]
                count+=1
    model.update();names=[v.VarName for v in model.getVars()]
    timed=[n for n in names if re.match(r'^(GPU|PCC|v_squared|line_p|line_q|line_delta|tx_p|tx_q)\[',n)]
    indices=[int(n.split('[',1)[1].split(',',1)[0]) for n in timed]
    assert min(indices)==0 and max(indices)==95
    return dict(status='PASS',H=H,issue_begin=BEGIN,issue_end_exclusive=END,
        post_H_grid_variables=0,minimum_day_slot=0,maximum_day_slot=95,
        terminal_residual_constraint_active=False,service_neutrality_constraint_active=False,
        extended_horizon_active=False,new_voltage_margin=None,grid_slots=slots,migration_option_count=count,
        model_variable_names_sha256=hashlib.sha256(chr(10).join(names).encode()).hexdigest())


class FrozenWanView:
    """Memoize deterministic scalar authority queries within one context."""
    def __init__(self,authority):
        self.authority=authority;self.rates={};self.payloads={}
    def __getattr__(self,name):return getattr(self.authority,name)
    def path_capacity_bytes(self,source,destination,slot):
        key=(source,destination,slot)
        if key not in self.rates:self.rates[key]=self.authority.path_capacity_bytes(*key)
        return self.rates[key]
    def payload_bytes(self,gpu):
        if gpu not in self.payloads:self.payloads[gpu]=self.authority.payload_bytes(gpu)
        return self.payloads[gpu]
