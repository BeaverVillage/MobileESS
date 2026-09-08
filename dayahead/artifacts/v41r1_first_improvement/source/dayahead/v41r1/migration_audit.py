"""Causal candidate/selection evidence; sensitivities never select a destination."""
from collections import Counter
from pathlib import Path
import numpy as np
from .migration import active,target,pending_in_day,state_at_d00,checkpoints,authoritative_checkpoint_boundaries,placement_sites,BEGIN,END,CONTRACT
from dayahead.v40g.domain import options,segments
from dayahead.v40g_segments.canonical import planning_power,import_frozen
from dayahead.v40a.grid import evaluate_grid,controls_from_trajectory
from dayahead.v41.scientific_archive import document,scalar_frame
from dayahead.v41.persistence import table
from dayahead.v41.preflight import record
from dayahead.v41.data import issue_time
import pandas as pd


def persist(output,day,policy,reference,selected,context):
    output=Path(output);selected={r['job_uid']:r for r in selected}
    power=planning_power(import_frozen(reference),context)
    controls=np.zeros((len(context.coefficients),len(context.coefficients[0].control_names)))
    controls[:,:len(context.capacity.aidc_ids)]=power['pcc']
    grid=evaluate_grid(context.coefficients,controls,context.nodes)
    t=grid['critical_slot'];c=context.coefficients[t];branch=grid['critical_line'];k=c.branch_names.index(branch)
    sensitivities={s:float(c.current_matrix[i,k]) for i,s in enumerate(context.capacity.aidc_ids)}
    def stamp(slot):return None if slot is None else (issue_time(day)+pd.Timedelta(seconds=slot*900)).isoformat()
    rows=[];placements=[];before=0;explicit_count=0;enabled=policy in ('B1','B3')
    for ref in sorted(reference,key=lambda r:r['job_uid']):
        uid=ref['job_uid'];job=selected[uid];state=state_at_d00(ref);start=ref['r1_reference_start']
        cp=checkpoints(ref,context.elapsed);opts=options(ref,context.capacity,context.wan,context.elapsed)
        explicit_count+=len(opts)
        cadence=authoritative_checkpoint_boundaries(ref,context.elapsed)
        moves=[o for o in opts if o.migrated];destinations=sorted({o.site for o in moves})
        initial=job['compute_segments'][0]['site'] if job.get('compute_segments') else job['AIDC_site']
        feasible_places=placement_sites(ref,context.capacity)
        old={key:value for key,value in ref.items() if not key.startswith('r1_') and key!='v41r1_migration_contract'}
        before+=any(o.migrated for o in options(old,context.capacity,context.wan,context.elapsed))
        selected_migration=bool(job.get('migration_selected'));event=job.get('migration_events',[None])[0] if selected_migration else None
        reason=None
        if not target(ref):reason='OUTSIDE_D00_RUNNING_OR_SELECTED_DAYD_START'
        elif not enabled:reason='POLICY_MIGRATION_DISABLED'
        elif not cp:reason='NO_VALID_CHECKPOINT_BEFORE_D24'
        elif not moves:reason='NO_VALID_RESTART_BEFORE_D24' if cp[0]+2>=END else 'NO_FEASIBLE_DESTINATION_GPU_RACK_OR_WAN'
        if target(ref):
            source_type='PENDING_AT_D00_TO_RUNNING' if pending_in_day(ref) else 'RUNNING_AT_D00'
            source=initial;dest=job['AIDC_site'] if selected_migration else None
            row=dict(job_id=uid,state_at_D00=state,candidate_source_type=source_type,
                planned_start=stamp(start),planned_start_issue_slot=start,planned_start_day_slot=start-BEGIN,
                planned_duration=ref['safe_duration_slots']*900,planned_duration_slots=ref['safe_duration_slots'],
                cross_midnight=ref['r1_reference_end']>END,initial_site=initial,
                first_valid_checkpoint=stamp(cp[0]) if cp else None,valid_checkpoint_count=len(cp),
                valid_checkpoints=[stamp(v) for v in cp],first_checkpoint_only_user_authorized_revision=True,
                cadence_boundaries_audit_only=[stamp(v) for v in cadence],cadence_boundary_count=len(cadence),
                running_entry_time=stamp(-ref['r1_elapsed_seconds_at_issue']/900) if ref['state_at_issue']=='RUNNING' else stamp(start),
                modeled_execution_start=stamp(start),FIRST_VALID_CHECKPOINT=stamp(cp[0]) if cp else None,
                migration_opportunity_count=int(bool(cp) and enabled),
                structural_migration_opportunity_count=int(bool(cp)),
                opportunity_applicability='FIRST_VALID_CHECKPOINT' if cp else 'NO_IN_DAY_CHECKPOINT',
                stay_or_migrate='MIGRATE' if selected_migration else 'STAY',
                source_IDC=source,destination_IDC=dest,WAN_path=event['fixed_path_links'] if event else [],
                checkpoint=stamp(event['checkpoint']) if event else None,
                pause=[stamp(event['checkpoint']),stamp(event['restart_end'])] if event else None,
                WAN_start=stamp(event['transfer_start']) if event else None,
                WAN_end=stamp(event['transfer_end']) if event else None,restart=stamp(event['restart_end']) if event else None,
                additional_migration_opportunities=0,running_migration_count=int(selected_migration),
                explicit_option_count=len(opts),STAY_option_count=sum(not o.migrated for o in opts),
                structurally_migration_eligible=bool(moves),migration_eligible=bool(moves) and enabled,
                ineligibility_reason=reason,feasible_destination_IDCs=destinations,feasible_destination_count=len(destinations),
                feasible_source_destination_pairs=sorted({(o.initial_site or ref['AIDC_site'],o.site) for o in moves}),
                feasible_destinations_from_selected_initial_site=sorted({o.site for o in moves if (o.initial_site or ref['AIDC_site'])==source}),
                selected_migration=selected_migration,selected_checkpoint=stamp(event['checkpoint']) if event else None,
                selected_destination=dest,restart_time=stamp(event['restart_end']) if event else None,
                source_segment=job['compute_segments'][0] if selected_migration else None,
                pause_segment=dict(start=event['checkpoint'],end=event['restart_end']) if event else None,
                WAN_segment=event,destination_segment=job['compute_segments'][1] if selected_migration else None,
                GPU_request=ref['requested_GPU'],source_line_sensitivity=sensitivities.get(source),
                destination_line_sensitivity=sensitivities.get(dest),
                sensitivity_delta=sensitivities[dest]-sensitivities[source] if dest else None,
                destination_sensitivities={d:sensitivities[d] for d in destinations},
                source_in_day_service_GPUh=sum(max(0,min(END,b)-max(BEGIN,a))*ref['requested_GPU']/4
                    for s,a,b in segments(job)[:1]) if selected_migration else None,
                destination_in_day_service_GPUh=sum(max(0,min(END,b)-max(BEGIN,a))*ref['requested_GPU']/4
                    for s,a,b in segments(job)[1:]) if selected_migration else None,
                has_lower_sensitivity_migration_destination=any(sensitivities[d]<sensitivities[ref['AIDC_site']] for d in destinations))
            rows.append(row)
        if pending_in_day(ref):
            destinations=[s for s in feasible_places if s!=ref['r1_reference_site']]
            placements.append(dict(job_id=uid,state_at_D00=state,reference_site=ref['r1_reference_site'],
                selected_initial_site=initial,planned_start=stamp(start),planned_start_issue_slot=start,
                reference_initial_site=ref['r1_reference_site'],optimized_initial_site=initial,
                feasible_initial_sites=list(feasible_places),prestart_relocation_selected=initial!=ref['r1_reference_site'],
                planned_duration=ref['safe_duration_slots']*900,prestart_relocation_eligible=enabled and bool(destinations),
                structurally_relocation_eligible=bool(destinations),ineligibility_reason=None if enabled and destinations else
                    'POLICY_MIGRATION_DISABLED' if not enabled else 'NO_FEASIBLE_ALTERNATIVE_GPU_RACK_DESTINATION',
                feasible_destinations=destinations,feasible_destination_count=len(destinations),
                selected_prestart_relocation=initial!=ref['r1_reference_site'],
                relocation_staging_start=None,relocation_staging_completion=None,
                placement_decision_time=stamp(BEGIN),transfer_timing_modeled=False,prestart_WAN_bytes=0,
                planned_start_unchanged=job['start_slot']==start,cross_midnight=ref['r1_reference_end']>END,
                GPU_request=ref['requested_GPU'],source_line_sensitivity=sensitivities[ref['r1_reference_site']],
                destination_line_sensitivity=sensitivities[initial],
                sensitivity_difference=sensitivities[initial]-sensitivities[ref['r1_reference_site']],
                feasible_destination_sensitivities={s:sensitivities[s] for s in destinations},
                has_lower_sensitivity_destination=any(sensitivities[s]<sensitivities[ref['r1_reference_site']] for s in destinations)))
    assert all(r['planned_start_unchanged'] for r in placements)
    assert all(r['running_migration_count']<=r['migration_opportunity_count']<=1 and
        r['additional_migration_opportunities']==0 for r in rows)
    frames=dict(migration_candidates=scalar_frame(rows),prestart_relocation_candidates=scalar_frame(placements))
    files={key:table(output/(key.upper()+'.parquet'),frame) for key,frame in frames.items()}
    pending_rows=[r for r in rows if r['candidate_source_type']=='PENDING_AT_D00_TO_RUNNING']
    running_rows=[r for r in rows if r['candidate_source_type']=='RUNNING_AT_D00']
    def population(values):
        return dict(jobs=len(values),STAY_option_count=sum(r['STAY_option_count'] for r in values),
            with_first_valid_checkpoint=sum(r['structural_migration_opportunity_count'] for r in values),
            structurally_migration_capable_count=sum(r['structurally_migration_eligible'] for r in values),
            policy_migration_capable_count=sum(r['migration_eligible'] for r in values),
            feasible_destination_count_distribution=dict(Counter(len(r['feasible_destinations_from_selected_initial_site']) for r in values)),
            union_destination_count_distribution=dict(Counter(r['feasible_destination_count'] for r in values)))
    cross=[r for r in pending_rows if r['cross_midnight']];critical=[r for r in pending_rows if r['planned_start_issue_slot']==96]
    pcross=[r for r in placements if r['cross_midnight']];pcritical=[r for r in placements if r['planned_start_issue_slot']==96]
    summary=dict(status='PASS',contract=CONTRACT,policy=policy,day=day,
        N_RUNNING_AT_D00=sum(state_at_d00(r)=='RUNNING' for r in reference),
        N_PENDING_AT_D00=sum(state_at_d00(r)=='PENDING' for r in reference),
        N_PRE_DAY_COMPLETE=sum(state_at_d00(r)=='COMPLETE' for r in reference),
        N_PENDING_AT_ISSUE_BUT_RUNNING_AT_D00=sum(r['state_at_issue']=='PENDING' and state_at_d00(r)=='RUNNING' for r in reference),
        N_PENDING_AT_D00_STARTING_WITHIN_DAY=len(pending_rows),
        N_PENDING_STARTING_WITHIN_DAY=len(pending_rows),N_PENDING_TO_RUNNING=len(pending_rows),
        N_PENDING_TO_RUNNING_WITH_FIRST_VALID_CHECKPOINT=sum(bool(r['FIRST_VALID_CHECKPOINT']) for r in pending_rows),
        N_RUNNING_AT_D00_WITH_FIRST_VALID_CHECKPOINT=sum(bool(r['FIRST_VALID_CHECKPOINT']) for r in running_rows),
        N_RUNNING_WITH_FIRST_CHECKPOINT_AT_D00=sum(r['FIRST_VALID_CHECKPOINT']==stamp(BEGIN) for r in running_rows),
        populations={'RUNNING_AT_D00':population(running_rows),'PENDING_TO_RUNNING':population(pending_rows)},
        explicit_candidate_combination_count=explicit_count,
        checkpoint_choice_dimension=False,additional_migration_opportunities=0,
        deterministic_checkpoint_count_distribution=dict(Counter(r['valid_checkpoint_count'] for r in rows)),
        audit_only_cadence_boundary_count_distribution=dict(Counter(r['cadence_boundary_count'] for r in rows)),
        N_PENDING_TO_RUNNING_WITH_VALID_CHECKPOINT=sum(r['valid_checkpoint_count']>0 for r in pending_rows),
        N_TOTAL_MIGRATION_CANDIDATES_BEFORE=before,
        N_TOTAL_MIGRATION_CANDIDATES_AFTER=sum(r['migration_eligible'] for r in rows),
        N_NEWLY_ADDED_PENDING_TO_RUNNING_CANDIDATES=sum(r['migration_eligible'] for r in pending_rows),
        N_PENDING_TO_RUNNING_CROSS_MIDNIGHT=len(cross),
        N_CROSS_MIDNIGHT_WITH_VALID_CHECKPOINT=sum(r['valid_checkpoint_count']>0 for r in cross),
        N_CROSS_MIDNIGHT_MIGRATION_ELIGIBLE=sum(r['migration_eligible'] for r in cross),
        N_PENDING_PRESTART_RELOCATION_ELIGIBLE=sum(r['prestart_relocation_eligible'] for r in placements),
        N_PENDING_PRESTART_RELOCATION_INELIGIBLE=sum(not r['prestart_relocation_eligible'] for r in placements),
        N_CROSS_MIDNIGHT_PRESTART_RELOCATION_ELIGIBLE=sum(r['prestart_relocation_eligible'] for r in pcross),
        N_18_COHORT=len(critical),N_18_MIGRATION_ELIGIBLE=sum(r['migration_eligible'] for r in critical),
        N_18_RELOCATION_ELIGIBLE=sum(r['prestart_relocation_eligible'] for r in pcritical),
        N_18_WITH_LOWER_SENSITIVITY_RELOCATION_DESTINATION=sum(r['has_lower_sensitivity_destination'] for r in pcritical),
        GPU_18_COHORT=sum(r['GPU_request'] for r in critical),
        pending_ineligibility_reasons=dict(Counter(r['ineligibility_reason'] for r in pending_rows if r['ineligibility_reason'])),
        selected_RUNNING_AT_D00_migrations=sum(r['selected_migration'] and r['candidate_source_type']=='RUNNING_AT_D00' for r in rows),
        selected_PENDING_TO_RUNNING_migrations=sum(r['selected_migration'] for r in pending_rows),
        selected_prestart_relocations=sum(r['selected_prestart_relocation'] for r in placements),
        critical_reference_branch=branch,critical_reference_day_slot=t,critical_reference_issue_slot=t+BEGIN,
        sensitivity_units='A per kW of PCC control; frozen affine current matrix at B0 reference critical row',
        sensitivities=sensitivities,Actual_reads=0,new_voltage_margin=None,
        candidate_feasibility='Structural GPU/rack/path/timing eligibility; simultaneous occupancy and UID-serial WAN are hard joint-model constraints, not filters against reference occupancy',
        prestart_authority='Existing authorized_options site placement; no pre-start payload or timing model exists, so no checkpoint traffic is fabricated',
        before_count_definition='Legacy structurally feasible issue-RUNNING-only migration options; independent of current policy enable flag',
        at_D00_boundary='State immediately before D00 starts: start==D00 is PENDING-to-RUNNING',files=files)
    document(output/'MIGRATION_ELIGIBILITY_SUMMARY.json',summary)
    return summary
