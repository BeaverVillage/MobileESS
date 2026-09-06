"""Independent 96-slot day, common per-job terminal-residual hard domain.

Legacy ledgers measure slots from D-1 18:00. ISSUE_BEGIN=24 therefore maps
exactly to day slot 0, and ISSUE_END=120 maps to day slot 96. Neither is an
extended optimization horizon. Pre-day execution is fixed carry-in evidence.
"""
from copy import deepcopy
from pathlib import Path
import pandas as pd

H = 96
ISSUE_BEGIN = 24
ISSUE_END = ISSUE_BEGIN + H
CONTRACT = 'V41R1_PER_JOB_TERMINAL_RESIDUAL_V1'
CARRY_IN = 'PRE_DAY_START_FIXED_CARRY_IN_PENDING_AT_ISSUE'


def active(row):
    return row.get('terminal_contract') == CONTRACT


def residual_coordinates(issue_start, duration):
    day_start = int(issue_start) - ISSUE_BEGIN
    day_residual = max(0, day_start + int(duration) - H)
    issue_residual = max(0, int(issue_start) + int(duration) - ISSUE_END)
    if day_residual != issue_residual:
        raise ValueError('OFF_BY_24_TERMINAL_COORDINATE_ERROR')
    return day_residual


def accounting(start, duration):
    """Day-origin slots; pre-day service is retained explicitly for carry-in."""
    start, duration = int(start), int(duration)
    if duration <= 0:
        raise ValueError('NONPOSITIVE_FULL_DURATION')
    before = min(duration, max(0, -start))
    inside = max(0, min(start + duration, H) - max(start, 0))
    after = max(0, start + duration - max(start, H))
    if before + inside + after != duration:
        raise ValueError('FULL_SERVICE_IDENTITY')
    return before, inside, after


def attach(jobs):
    result = deepcopy(jobs)
    for row in result:
        row.update(terminal_contract=CONTRACT,
            terminal_reference_start_issue_slot=int(row['start_slot']),
            terminal_reference_site=row['AIDC_site'],
            terminal_reference_migration=bool(row.get('migration_selected')),
            terminal_reference_duration_slots=int(row['safe_duration_slots']),
            terminal_reference_duration_seconds=float(row['safe_duration_seconds']),
            terminal_reference_selected=row['AIDC_site'] != 'UNASSIGNED')
        row['terminal_reference_remaining_slots'] = accounting(
            row['start_slot'] - ISSUE_BEGIN, row['safe_duration_slots'])[2]
    return result


def start_bounds(row):
    if not active(row):
        raise ValueError('TERMINAL_CONTRACT_REQUIRED')
    reference = int(row['terminal_reference_start_issue_slot'])
    # Admission and all before-D execution stay frozen. Historical issue-time
    # PENDING jobs may already be running at D00; they are not new decisions.
    if row['state_at_issue'] == 'RUNNING' or not row['terminal_reference_selected'] or reference < ISSUE_BEGIN:
        return reference, reference
    d = int(row['safe_duration_slots'])
    if row['eligible_standby']:
        lower = max(ISSUE_BEGIN, int(row['RSP_start_slot']))
        upper = min(int(row['RW_completion_slot']) - d, ISSUE_END - 1,
                    ISSUE_END - d + int(row['terminal_reference_remaining_slots']))
    else:
        lower = upper = reference
    if not lower <= reference <= upper:
        raise ValueError('COMMON_REFERENCE_OUTSIDE_TERMINAL_DOMAIN:' + row['job_uid'])
    return lower, upper


def authorized_options(row, capacity):
    lower, upper = start_bounds(row)
    reference = int(row['terminal_reference_start_issue_slot'])
    if row['state_at_issue'] == 'RUNNING' or not row['terminal_reference_selected'] or reference < ISSUE_BEGIN:
        return [(row['AIDC_site'], int(row['start_slot']))]
    gpu = int(row['requested_GPU'])
    sites = [s for s in capacity.aidc_ids if capacity.site_capacity[s] >= gpu and capacity.eligible_racks(s, gpu)]
    result = sorted((site, start) for start in range(lower, upper + 1) for site in sites)
    for site, start in result:
        check(row, {**row, 'AIDC_site': site, 'start_slot': start, 'end_slot': start + row['safe_duration_slots']})
    return result


def check(reference, candidate):
    if not active(reference) or not active(candidate):
        raise ValueError('TERMINAL_CONTRACT_DRIFT')
    fields = ('terminal_reference_start_issue_slot', 'terminal_reference_site',
        'terminal_reference_migration', 'terminal_reference_duration_slots',
        'terminal_reference_duration_seconds', 'terminal_reference_selected',
        'terminal_reference_remaining_slots', 'safe_duration_slots', 'safe_duration_seconds',
        'state_at_issue', 'requested_GPU', 'eligible_standby', 'RSP_start_slot', 'RW_completion_slot')
    if any(candidate.get(k) != reference.get(k) for k in fields):
        raise ValueError('COMMON_TERMINAL_REFERENCE_CHANGED')
    if reference['state_at_issue'] != 'PENDING':
        return
    start, d = int(candidate['start_slot']), int(candidate['safe_duration_slots'])
    sref = int(reference['terminal_reference_start_issue_slot'])
    if candidate['end_slot'] != start + d:
        raise ValueError('FULL_DURATION_END_CHANGED')
    if reference['terminal_reference_selected'] and candidate['AIDC_site'] == 'UNASSIGNED':
        raise ValueError('FROZEN_ADMISSION_CHANGED')
    if reference['terminal_reference_selected'] and sref >= ISSUE_BEGIN and residual_coordinates(sref, d) != reference['terminal_reference_remaining_slots']:
        raise ValueError('INVALID_COMMON_TERMINAL_RESIDUAL')
    if not reference['terminal_reference_selected'] or sref < ISSUE_BEGIN:
        if (candidate['AIDC_site'], start, candidate['end_slot'], bool(candidate.get('migration_selected'))) != (
                reference['terminal_reference_site'], sref, sref + d, reference['terminal_reference_migration']):
            raise ValueError('FROZEN_ADMISSION_OR_PRE_DAY_EXECUTION_CHANGED')
        return
    if not ISSUE_BEGIN <= start < ISSUE_END:
        raise ValueError('PENDING_START_OUTSIDE_DAY')
    lower, upper = start_bounds(reference)
    if not lower <= start <= upper:
        raise ValueError('PENDING_START_WINDOW_OR_TERMINAL_INCREASE')
    if max(0, start + d - ISSUE_END) > reference['terminal_reference_remaining_slots']:
        raise ValueError('PER_JOB_TERMINAL_RESIDUAL_INCREASE')
    if candidate.get('migration_selected') != reference.get('migration_selected'):
        raise ValueError('NEW_PENDING_MIGRATION_TYPE_FORBIDDEN')


def persist(output, day, policy, reference, selected, common):
    from dayahead.v41.persistence import table
    from dayahead.v41.preflight import record
    from dayahead.paper_analysis.storage import write_json, digest
    old = {r['job_uid']: r for r in reference}
    rows = []
    for row in selected:
        before = old[row['job_uid']]
        check(before, row)
        if row['state_at_issue'] != 'PENDING' or not row['terminal_reference_selected']:
            continue
        sref = row['terminal_reference_start_issue_slot'] - ISSUE_BEGIN
        start = row['start_slot'] - ISSUE_BEGIN
        pre, inside, tail = accounting(start, row['safe_duration_slots'])
        rp, ri, rt = accounting(sref, row['safe_duration_slots'])
        rows.append(dict(job_id=row['job_uid'], GPU_REQUEST=row['requested_GPU'],
            REFERENCE_START_SLOT=sref, OPTIMIZED_START_SLOT=start,
            PLANNED_DURATION_SECONDS=row['safe_duration_seconds'], PLANNED_DURATION_SLOTS=row['safe_duration_slots'],
            REFERENCE_PRE_DAY_SLOTS=rp, OPTIMIZED_PRE_DAY_SLOTS=pre,
            REFERENCE_IN_DAY_SLOTS=ri, REFERENCE_TERMINAL_REMAINING_SLOTS=rt,
            OPTIMIZED_IN_DAY_SLOTS=inside, OPTIMIZED_TERMINAL_REMAINING_SLOTS=tail,
            TERMINAL_RESIDUAL_DELTA_SLOTS=tail-rt, TERMINAL_CONSTRAINT_BINDING=tail == rt,
            CROSS_MIDNIGHT_REFERENCE=rt > 0, CROSS_MIDNIGHT_OPTIMIZED=tail > 0,
            SITE_REFERENCE=row['terminal_reference_site'], SITE_OPTIMIZED=row['AIDC_site'],
            START_CHANGED=start != sref, SITE_CHANGED=row['AIDC_site'] != row['terminal_reference_site'],
            MIGRATION_CHANGED=bool(row.get('migration_selected')) != row['terminal_reference_migration'],
            DAY_D_SCHEDULING_ELIGIBLE=sref >= 0,
            ACCOUNTING_SCOPE='DAY_D_PENDING' if sref >= 0 else CARRY_IN,
            FULL_SERVICE_IDENTITY=row['safe_duration_slots'] == pre+inside+tail))
    frame = pd.DataFrame(rows)
    if not (frame.TERMINAL_RESIDUAL_DELTA_SLOTS <= 0).all() or not frame.FULL_SERVICE_IDENTITY.all():
        raise ValueError('TERMINAL_NO_DUMPING_OR_SERVICE_FAILURE')
    output = Path(output)
    receipt = table(output / 'PENDING_TERMINAL_RESIDUALS.parquet', frame)
    cross = frame.CROSS_MIDNIGHT_REFERENCE
    summary = dict(status='PASS', contract=CONTRACT, day=day, policy=policy, H=H,
        N_SELECTED_PENDING=len(frame), N_DAY_D_PENDING=int(frame.DAY_D_SCHEDULING_ELIGIBLE.sum()),
        N_FIXED_PRE_DAY_PENDING=int((~frame.DAY_D_SCHEDULING_ELIGIBLE).sum()),
        N_REFERENCE_CROSS_MIDNIGHT=int(cross.sum()), N_OPTIMIZED_CROSS_MIDNIGHT=int(frame.CROSS_MIDNIGHT_OPTIMIZED.sum()),
        N_PRE_DAY_REFERENCE_CROSS_MIDNIGHT=int((cross & ~frame.DAY_D_SCHEDULING_ELIGIBLE).sum()),
        N_IN_DAY_REFERENCE_CROSS_MIDNIGHT=int((cross & frame.DAY_D_SCHEDULING_ELIGIBLE).sum()),
        N_CROSS_MIDNIGHT_START_CHANGED=int((cross & frame.START_CHANGED).sum()),
        N_CROSS_MIDNIGHT_SITE_CHANGED=int((cross & frame.SITE_CHANGED).sum()),
        N_CROSS_MIDNIGHT_MIGRATION_CHANGED=int((cross & frame.MIGRATION_CHANGED).sum()),
        N_TERMINAL_CONSTRAINT_BINDING=int(frame.TERMINAL_CONSTRAINT_BINDING.sum()),
        TOTAL_REFERENCE_TERMINAL_GPUh=float((frame.REFERENCE_TERMINAL_REMAINING_SLOTS*frame.GPU_REQUEST).sum()/4),
        TOTAL_OPTIMIZED_TERMINAL_GPUh=float((frame.OPTIMIZED_TERMINAL_REMAINING_SLOTS*frame.GPU_REQUEST).sum()/4),
        MAX_JOB_TERMINAL_DELTA=int(frame.TERMINAL_RESIDUAL_DELTA_SLOTS.max()),
        MAX_POSITIVE_TERMINAL_VIOLATION=0, TERMINAL_CONSTRAINT_VIOLATIONS=0,
        table=receipt, common_reference_SHA=digest(reference), aggregate_spill_budget=False,
        pre_day_service_note='Issue-time PENDING already started before D00 is frozen carry-in; pre-day + in-day + terminal = full duration. Day-D starts satisfy in-day + terminal = full duration.')
    write_json(output / 'TERMINAL_NO_DUMPING_AUDIT.json', summary)
    write_json(output / 'INDEPENDENT_DAY_TERMINAL_BOUNDARY_AUDIT.json', dict(status='PASS',
        day=day, policy=policy, H=H, source_of_initial_state='AUTHORITATIVE_DAY_D_SNAPSHOT',
        initial_snapshot=common['snapshot'], common_reference=common['files']['COMMON_B0_REFERENCE_JOBS.json'],
        previous_policy_day_terminal_state_used=False, next_day_initial_state='AUTHORITATIVE_DAY_D_SNAPSHOT',
        post_H_decision_variables=0, post_H_grid_slots=0, D_plus_1_scientific_reads_for_terminal_handling=0,
        contract=record(__file__), classification='INDEPENDENT_DAILY_COUNTERFACTUAL_EVALUATION'))
    return summary


def model_boundary(model, jobs, options_by_uid, slots):
    """Inspect constructed columns and actual Gurobi time-indexed variables."""
    import re
    if slots != H:
        raise ValueError('SCIENTIFIC_DAY_MUST_HAVE_96_SLOTS')
    count = 0
    fixed = []
    for row in jobs:
        opts = options_by_uid[row['job_uid']]
        if row['state_at_issue'] == 'PENDING':
            for opt in opts:
                check(row, {**row, 'AIDC_site':opt.site, 'start_slot':opt.start, 'end_slot':opt.end})
                if len(opts) > 1:
                    assert ISSUE_BEGIN <= opt.start < ISSUE_END
                    residual_coordinates(opt.start, row['safe_duration_slots'])
                    count += 1
            if len(opts) == 1:
                fixed.append(row['job_uid'])
        for opt in opts:
            if opt.migrated:
                assert ISSUE_BEGIN <= opt.transfer_start < opt.transfer_end < ISSUE_END
    model.update()
    names = [v.VarName for v in model.getVars()]
    timed = [n for n in names if re.match(r'^(GPU|PCC|v_squared|line_p|line_q|line_delta|tx_p|tx_q)\[', n)]
    indices = [int(n.split('[',1)[1].split(',',1)[0].rstrip(']')) for n in timed]
    assert indices and min(indices) == 0 and max(indices) == H-1
    return dict(status='PASS', H=H, issue_begin=ISSUE_BEGIN, issue_end_exclusive=ISSUE_END,
        timed_model_variable_count=len(timed), minimum_day_index=min(indices), maximum_day_index=max(indices),
        post_H_timed_model_variables=sum(t >= H for t in indices),
        movable_PENDING_options_individually_verified=count, fixed_PENDING_jobs=len(fixed),
        fixed_PENDING_selectors_are_constants=True, terminal_constraint='PER_JOB_DOMAIN_PRUNING_BEFORE_VARIABLE_CREATION',
        aggregate_spill_offsets_allowed=False, full_duration_preserved=True,
        grid_slots=slots, model_variable_names_sha256=__import__('hashlib').sha256('\n'.join(names).encode()).hexdigest())
