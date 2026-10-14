"""Native0 retrospective UID audit. Never promotes PR226 to integrated PASS."""
from pathlib import Path
import argparse
import collections
import csv
import gzip
import hashlib
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from v42_integration.policy import digest
from v42_integration.production_case import ARCHIVE
from v42_integration.known_commands import compile_known_commands


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')


def audit(result_path,native_path,output,planning_path):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    native=json.loads(Path(native_path).read_text(encoding='utf8'))
    issue={str(r['job_uid']):r for r in native['known_population']}
    planned=json.loads(Path(planning_path).read_text(encoding='utf8'))
    selected=set(planned['Known_schedule'])
    rebound_path=Path(planning_path).parents[1]/'CASE/KNOWN_DESCRIPTOR_REFERENCE_REBINDING.json'
    rebinding=json.loads(rebound_path.read_text(encoding='utf8'))
    rebound={r['uid']:r for r in rebinding['rows']}
    original_known_changes={k:set() for k in ('TimeShift','Preplace','Migration')}
    for u,option in planned['Known_schedule'].items():
        row=issue[u]
        if option['start']!=rebound[u]['rebound_reference_start']:original_known_changes['TimeShift'].add(u)
        site=rebound[u]['rebound_reference_site']
        if option['initial_site']!=site:original_known_changes['Preplace'].add(u)
        if option.get('checkpoint',-1)>=0:original_known_changes['Migration'].add(u)
    changed=set().union(*original_known_changes.values())
    write(output/'SAVED_V5_KNOWN_PLANNING_METRICS.json',dict(scope='OLD_V5_STRICT_A2_DIAGNOSTIC_NOT_NEW_E1_E2_OPTIMUM',
        optimized_Known=len(selected),Changed_Known_UIDs=len(changed),
        changes={k:len(v) for k,v in original_known_changes.items()},
        Changed_nominal_model_GPUh=sum(issue[u]['GPU_gang']*issue[u]['service_slots']*.25 for u in sorted(changed)),
        Eligible_nominal_model_GPUh=sum(issue[u]['GPU_gang']*issue[u]['service_slots']*.25 for u in sorted(selected)),
        reference_rebinding_source=str(rebound_path),reference_rebinding_sha256=hashlib.sha256(rebound_path.read_bytes()).hexdigest(),
        Running_remaining_service_boundary_is_not_historical_start_shift=True,
        planning_rho=planned.get('stages',{}).get('A2',{}).get('rho'),new_Known_A1_A2_status='NOT_RUN'))
    print('Reading immutable PR226 event result',flush=True)
    with gzip.open(result_path,'rt',encoding='utf8') as stream:d=json.load(stream)
    metadata=d['carryout']['controller']['metadata'];begin=d['conditional_case']['begin_seconds']
    known=set(metadata)&set(issue);unknown=set(metadata)-set(issue)
    assert len(issue)==1649 and len(known)==1546 and len(unknown)==774
    assert all(not metadata[u]['origin_unknown'] for u in known)
    assert all(metadata[u]['origin_unknown'] for u in unknown)
    active_unmodeled=known-selected
    from datetime import datetime
    slot_zero=datetime.fromisoformat(native['issue_time'].replace('Z','+00:00')).timestamp()
    commands=compile_known_commands(planned['Known_schedule'],slot_zero_seconds=slot_zero)
    observations={r['uid']:r['time_seconds'] for r in d['job_event_ledger'] if r['event']=='SUBMISSION_OBSERVED'}
    branch_rows=[]
    for uid in sorted(metadata):
        m=metadata[uid]
        if uid in unknown:
            assert uid not in commands and observations[uid]>=m['submit_seconds']
            assert m['submit_seconds']>slot_zero
            route='UNKNOWN_LOOKUP_AFTER_OBSERVATION'
        elif uid in selected:route='KNOWN_FROZEN_COMMAND'
        else:route='KNOWN_SOURCE_AUTHORIZED_REFERENCE_FALLBACK'
        command=commands.get(uid,{})
        branch_rows.append(dict(uid=uid,classification='Unknown' if uid in unknown else 'Known',route=route,
            observed_at_seconds=observations[uid],planned_start_seconds=command.get('start_seconds'),
            planned_site=command.get('site'),planned_checkpoint=command.get('checkpoint_control_seconds'),
            observed_at_midnight=m['submit_seconds']<begin))
    with (output/'MAY01_SAVED_UID_BRANCH_REPLAY.csv').open('w',newline='',encoding='utf8') as stream:
        w=csv.DictWriter(stream,fieldnames=list(branch_rows[0]));w.writeheader();w.writerows(branch_rows)
    write(output/'MAY01_SAVED_UID_BRANCH_REPLAY.json',dict(PASS=True,UID_rows=len(branch_rows),
        routes=dict(collections.Counter(r['route'] for r in branch_rows)),Known_in_Unknown_policy_UIDs=0,
        Unknown_UIDs_in_Planning_commands=0,Unknown_pre_midnight_retained=sum(metadata[u]['submit_seconds']<begin for u in unknown),
        replay_kind='SOURCE_UID_ROUTING_AND_NATIVE_COMMAND_CONVERSION_ONLY',
        new_physical_event_execution=False,new_A_M_Optimize_calls=0,new_Fresh_AC_calls=0,
        V5_saved_commands_are_diagnostic_not_new_E1_E2_Known_optimum=True))
    write(output/'SOURCE_UID_CLASSIFICATION.json',dict(Planning_Known=1649,completed_before_Dday=len(set(issue)-known),
        active_Known=len(known),active_Unknown=len(unknown),Unknown_pre_midnight=sum(metadata[u]['submit_seconds']<begin for u in unknown),
        Unknown_Dday_submit=sum(metadata[u]['submit_seconds']>=begin for u in unknown),Known_optimized=len(selected),
        Known_active_optimized=len(selected&known),Known_active_unmodeled=len(active_unmodeled),
        Known_issue_unmodeled=len(set(issue)-selected),
        issue_unmodeled_reasons=dict(collections.Counter(str((r['state'],r.get('planning_eligible'),r['service_slots']))
            for u,r in issue.items() if u not in selected)),
        active_unmodeled_UIDs=sorted(active_unmodeled),issue_unmodeled_UIDs=sorted(set(issue)-selected),
        issue_Known_UID_sha=digest(sorted(issue)),Known_Unknown_disjoint=True,source_classification='D_MINUS_1_ISSUE_UID_ROSTER'))
    from v42_integration.frozen_unknown import coverage_grammar
    from types import SimpleNamespace
    caps=native['capacities'];limit={s:(caps[s],) for s in caps}
    gangs=sorted({metadata[u]['gpu'] for u in unknown})
    runtimes=[metadata[u]['t50_seconds'] for u in unknown]
    write(output/'MAY01_OBSERVED_COVERAGE_INVENTORY.json',dict(
        scope='RETROSPECTIVE_COVERAGE_AUDIT_ONLY_NEVER_COMPILER_INPUT',AIDC_sites=len(caps),installed_GPU=sum(caps.values()),
        observed_Unknown_GPU_gangs=gangs,observed_Unknown_Q50_min_seconds=min(runtimes),observed_Unknown_Q50_max_seconds=max(runtimes),
        compiler_declared_integer_GPU_domain=list(range(1,int(max(caps.values()))+1)),
        missing_observed_GPU_gangs=[g for g in gangs if g>max(caps.values())],
        runtime_upper_default_seconds=604800,runtime_outside_finite_default_UIDs=sum(v>604800 for v in runtimes),
        actual_compatible_site_masks_source='ORIGINAL_SOURCE_REQUEST_COMPATIBLE_SITES_AND_RACK_CHECK',
        actual_compatible_sites_max=max(len(metadata[u]['compatible_sites']) for u in unknown),
        observed_Running_Q50_overrun_UIDs=sum(metadata[u]['state']=='RUNNING' and metadata[u]['accumulated_compute_seconds']>metadata[u]['t50_seconds'] for u in unknown)))
    actions=[];sets={g:{k:set() for k in ('Time-shifting','Pre-placement','Migration','Changed')} for g in ('Known','Unknown')}
    queue={r['job_uid']:r for r in d['queue_ledger']}
    final_references=d['carryout']['controller']['experimental_runtime_state']['references']
    for u,row in queue.items():
        group='Known' if u in known else 'Unknown'
        reference=final_references.get(u,{}).get('reference_start_seconds',metadata[u]['reference_start_seconds'])
        shift=(row.get('admitted_time') is not None and row['admitted_time']>reference+1e-9
            and row.get('policy_action') in ('DELAY','PREPLACE'))
        place=row.get('policy_action')=='PREPLACE'
        migrate=row.get('migration_count',0)>0
        for yes,label in ((shift,'Time-shifting'),(place,'Pre-placement'),(migrate,'Migration')):
            if yes:sets[group][label].add(u);sets[group]['Changed'].add(u)
        if shift or place or migrate:actions.append(dict(uid=u,classification=group,policy_action=row.get('policy_action'),
            start_seconds=row['admitted_time'],site=row['site'],intentional_delay_seconds=row.get('intentional_delay_seconds',0),
            gpu=metadata[u]['gpu'],Q50_seconds=metadata[u]['t50_seconds'],origin_at_issue=u in issue))
    with (output/'PR226_CHANGED_UIDS.csv').open('w',newline='',encoding='utf8') as stream:
        w=csv.DictWriter(stream,fieldnames=list(actions[0]));w.writeheader();w.writerows(sorted(actions,key=lambda r:r['uid']))
    eligible={u for u in unknown if metadata[u]['experimental_contract']['eligible_for_contract']}
    participants={u for u in eligible if metadata[u]['experimental_contract']['participant']}
    gpuwork=lambda users:sum(metadata[u]['gpu']*metadata[u]['t50_seconds']/3600 for u in sorted(users))
    summary={g:{k:len(v) for k,v in rows.items()} for g,rows in sets.items()}
    summary.update(PR226_62_total=sum(len(s['Changed']) for s in sets.values()),
        Unknown_observed=len(unknown),Unknown_observed_eligible=len(eligible),Unknown_participants=len(participants),
        Unknown_changed_nominal_GPUh=gpuwork(sets['Unknown']['Changed']),Unknown_eligible_nominal_GPUh=gpuwork(eligible),
        Unknown_Observed_Eligible_UID_changed_rate=len(sets['Unknown']['Changed'])/len(eligible),
        Unknown_participant_changed_rate=len(sets['Unknown']['Changed'])/len(participants),
        Unknown_changed_nominal_GPUh_rate=gpuwork(sets['Unknown']['Changed'])/gpuwork(eligible),
        Unknown_changed_participant_UIDs=len(sets['Unknown']['Changed']&participants),
        Unknown_committed_delay_obligation_UIDs=sum(metadata[u].get('additional_start_delay_seconds',0)>0 for u in unknown),
        scientific_scope='PR226_INVALID_MIXED_SELECTOR_DIAGNOSTIC_ONLY_NOT_REPAIRED_INTEGRATED_PERFORMANCE',
        actual_PCC_delta_attributable_to_Unknown_only=None)
    assert summary['PR226_62_total']==62
    write(output/'PR226_62_RECONCILIATION.json',summary)
    rows=[r for r in d['experimental_candidate_audit'] if r['uid'] in unknown]
    categories=collections.Counter();unique=collections.defaultdict(set);events=collections.Counter()
    for row in rows:
        for rejected in row.get('rejected',[]):
            reason=rejected.get('reason','UNSPECIFIED');events[reason]+=1;unique[reason].add(row['uid'])
            category=('GPU' if 'CAPACITY' in reason else 'Rack' if 'RACK' in reason else 'WAN' if 'WAN' in reason
                else 'Voltage' if 'VOLTAGE' in reason else 'Transformer' if 'TRANSFORMER' in reason
                else 'Current' if 'CURRENT' in reason else 'QoS' if 'BUDGET' in reason or 'WINDOW' in reason else 'Other')
            categories[category]+=1
    funnel=dict(scope='OLD_PR226_UNKNOWN_ONLY_DIAGNOSTIC_NOT_REPAIRED_FUNNEL',observed_UIDs=len(unknown),participant_UIDs=len(participants),
        candidate_event_rows=len(rows),candidate_generated=sum(r.get('generated',0) for r in rows),
        generated_UIDs=len({r['uid'] for r in rows if r.get('generated',0)>0}),
        physical_and_grid_evaluated_UIDs=len({r['uid'] for r in rows if r.get('physically_and_grid_evaluated',0)>0}),
        q50_hard_pass_UIDs=len({r['uid'] for r in rows if r.get('q50_hard_pass',0)>0}),
        approved_UIDs=len({r['uid'] for r in rows if r.get('approved',0)>0}),
        selected_changed_UIDs=len({r['uid'] for r in rows if r.get('selected_action') in ('DELAY','PREPLACE','CHECKPOINT_MIGRATE')}),
        Actual_executed_changed_UIDs=len(sets['Unknown']['Changed']),rejection_candidate_event_counts=dict(events),
        rejection_unique_UID_counts={k:len(v) for k,v in unique.items()},category_candidate_rejections=dict(categories),
        unique_UID_counts_are_overlapping=True,repeated_rejections_are_not_unique_jobs=True,
        generated_action_candidate_counts=dict(sum((collections.Counter(r.get('generated_action_counts',{})) for r in rows),collections.Counter())),
        not_identifiable_from_saved_detail=['physically_feasible_before_electrical_guard','P1_improvement_without_P2_tie',
            'changed_PCC_delta_Unknown_alone'],repaired_funnel_status='NOT_RUN_REQUIRES_NEW_A1_A2_ANCHOR')
    categories_all=('GPU','Rack','WAN','Voltage','Current','Transformer','QoS','Other')
    funnel['category_candidate_rejections']={k:categories[k] for k in categories_all}
    funnel['TimeShift_eligible_UIDs']=len({r['uid'] for r in rows if r.get('generated_action_counts',{}).get('DELAY',0)>0})
    funnel['Preplace_eligible_UIDs']=len({r['uid'] for r in rows if r.get('generated_action_counts',{}).get('PREPLACE',0)>0})
    funnel['Migration_candidate_UIDs']=len({r['uid'] for r in rows if r.get('generated_action_counts',{}).get('CHECKPOINT_MIGRATE',0)>0})
    write(output/'PR226_UNKNOWN_FUNNEL.json',funnel)
    receipts=[dict(path=str(Path(p).resolve()),bytes=Path(p).stat().st_size,sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
        for p in (result_path,native_path,planning_path)]
    write(output/'NATIVE0_AUDIT_RECEIPT.json',dict(PASS=True,source_receipts=receipts,Native_Optimize_calls=0,Fresh_AC_calls=0,
        reconstructed_UID_classification=True,new_integrated_performance_PASS=False,
        PR226_job_completion=d['receipt']['completed_jobs'],PR226_carryover=d['receipt']['carryout_jobs'],
        repaired_Full96='NOT_RUN',Solver_ledger_preserved_seconds=621.2855198158068,Solver_limit_seconds=3600))
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--result',type=Path,default=Path('docs/v42_experimental_flex_qos_20261014/evidence/control/FINAL_FLEX_COMPARISON/E1_FLEX30_GRID_SENSITIVITY_AWARE/CONDITIONAL_ACTUAL_RESULT.json.gz'))
    p.add_argument('--native',type=Path,default=ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    p.add_argument('--planning',type=Path,default=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/PLANNING_FREEZE.json'))
    a=p.parse_args();audit(a.result,a.native,a.output,a.planning)
