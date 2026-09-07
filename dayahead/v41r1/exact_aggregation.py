"""Conservative coefficient identity, preserving the original P5 rank.

UID-serial WAN constraints distinguish otherwise similar migratable jobs.
They must remain singleton classes. Count aggregation is exact only when the
complete option columns, resources, eligibility, terminal rules AND all five
objective coefficients coincide. Refinement of an old cohort keeps its old
objective rank, so additional scientific distinctions never change P5.
"""
import hashlib
import json

FIELDS = ('state_at_issue','requested_GPU','start_slot','end_slot','safe_duration_slots',
    'safe_duration_seconds','AIDC_site','Rack_label','initial_Rack_label','qos','partition',
    'protected','eligible_standby','RSP_start_slot','RW_completion_slot',
    'common_terminal_obligation','post_H_site','terminal_class','v41r1_migration_contract',
    'r1_reference_start','r1_reference_end','r1_reference_site','r1_reference_rack',
    'r1_elapsed_seconds_at_issue','r1_first_valid_checkpoint')


def signature(row, opts, costs, capacity):
    # Option and deviation vectors are already in the parent grouping key.
    # Their hashes make the coefficient audit explicit without duplicating the
    # multi-million-option tuple in memory.
    payload=dict(row={k:row.get(k) for k in FIELDS},
        rack_compatibility={s:sorted((p.rack_pool_id,int(getattr(p,'historical_gpu_capacity',capacity.site_capacity[s])))
            for p in capacity.eligible_racks(s,row['requested_GPU'])) for s in capacity.aidc_ids},
        policy='B1',serial_WAN_position=row['job_uid'] if any(o.migrated for o in opts) else None,
        H4_and_power_and_electrical='SAME_CONTEXT_AND_IDENTICAL_GPU_SITE_SLOT_OPTION_COLUMNS',
        WAN='IDENTICAL_FIXED_PATH_AUTHORITY; GPU_PAYLOAD; CHECKPOINT; EXACT_OPTIONS; UID_SERIAL_POSITION')
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def disaggregate(members, option_counts):
    """Frozen UID order after the aggregate choice is fixed; no Actual inputs."""
    ids=sorted(members); choices=[]
    for opt,count in option_counts:
        if int(count)!=count or count<0:raise ValueError('INVALID_AGGREGATE_COUNT')
        choices.extend([opt]*int(count))
    if len(ids)!=len(choices):raise ValueError('AGGREGATE_SERVICE_COUNT_DRIFT')
    return list(zip(ids,choices))
