"""Rebuild April physical inputs with immutable classification and exact raw joins."""
from collections import Counter
from copy import deepcopy
import math
import pandas as pd
from v42_april_port.audit import read, write, table, record, checked, load_april_requests
from v42_april_port.builder import timestamp, B0_FLAGS
from v42_april_b0_v2.reference import build_reference
from v42_final.runtime import FrozenQ50
from v42_final.common import MODEL
from v42_temporal.timeshift import WaitAuthority
from v42_may01.state import cohort_key
from .freeze import ROOT, OUT
from .population import classify, common_arm_population
from .cc4 import bind

PRIOR = ROOT/'docs/v42_april_port_from_may_pipeline'

def distributions(records):
    result = {}
    for group in ('MODELABLE','UNMODELABLE'):
        rows = [r for r in records if r['group']==group]
        result[group] = dict(events=len(rows))
        for field in ('state','population','submission_date','submission_hour','qos','partition','nodes_req','processors_req','memory_req','array_pos'):
            result[group][field] = dict(Counter(str(r.get(field)) for r in rows))
        values = [r['requested_seconds'] for r in rows if isinstance(r.get('requested_seconds'),(int,float)) and math.isfinite(r['requested_seconds'])]
        result[group]['requested_walltime_feature'] = dict(finite_count=len(values),
            quantiles=None if not values else pd.Series(values).quantile([0,.25,.5,.75,1]).to_dict())
    return dict(unit='day/role event; repeated known jobs retained', distributions=result,
        exclusion_rule_changed_after_diagnostics=False, acceptance_threshold=None,
        limitation='Coverage is conditional on source modelability, not representative of unknown GPU demand.')

def main():
    spec = read(OUT/'PREREGISTRATION.json')
    for stem in ('V42_PHYSICAL_MODELABILITY','V42_FLEXIBILITY_ELIGIBILITY'):
        auth = read(OUT/'POPULATION'/(stem+'_AUTHORITY.json'))
        checked(auth['rule'])
    cc4 = bind()
    first = read(PRIOR/'APRIL/DAY_20250401/INPUT_PROVENANCE.json')
    requests, _, projections = load_april_requests(first['archive'])
    provider = FrozenQ50()  # Integrity check of the same frozen provider; no fitting.
    runtime_auth = read(PRIOR/'MAY_PIPELINE/MAY_RUNTIME_AUTHORITY.json')
    for p in runtime_auth['provider']['payloads']: checked(p)
    ts_auth = read(ROOT/'docs/v42_ts_cc4_temporal_refinement/TS_HIERARCHICAL_BACKOFF_AUTHORITY.json')
    train = pd.read_parquet(checked(ts_auth['TRAIN_source']))
    wait = WaitAuthority(train, pd.Timestamp(ts_auth['TRAIN_cutoff']))
    ledger=[]; byday=[]; representation=[]; manifest=[]; refs=[]; refaudits=[]; flexrows=[]
    all_ids=set(); physical_ids=set(); excluded_ids=set(); memberships=[]; gates=[]
    for day in spec['days']:
        folder = 'DAY_'+day.replace('-','')
        pp = PRIOR/'APRIL'/folder/'PLANNING_INPUT_BUNDLE.json'
        ap = PRIOR/'APRIL'/folder/'ACTUAL_INPUT_BUNDLE.json'
        provp = PRIOR/'APRIL'/folder/'INPUT_PROVENANCE.json'
        p=read(pp); a=read(ap); prov=read(provp)
        checked(prov['snapshot'])
        for source in prov['daily_sources'].values(): checked(source)
        selected = {}; rawcounts = {}; missingcounts = {}
        for role, rows in [('KNOWN_D1',p['known_population']),('ACTUAL_POST_ISSUE',a['post_issue_arrivals'])]:
            out=[]; rawcounts[role]=len(rows)
            for row in rows:
                uid=row['job_uid']; candidates=requests.get(uid,[])
                if len(candidates)!=1: raise ValueError('EXACT_RAW_IDENTITY_REQUIRED')
                raw=candidates[0]
                if row['source_member']!=raw['source_member'] or row['source_row']!=raw['source_row']:
                    raise ValueError('RAW_ROW_IDENTITY_DRIFT')
                result=classify(row,raw,p['capacities'],p['rack_compatibility'],runtime_auth['provider']['available_at'])
                # The Q50 cache is BASE-bound, generated from this exact source and
                # immutable model. Verify event/service identity; do not substitute walltime.
                q=row['Q50_total_seconds']; elapsed=row['elapsed_seconds']
                if isinstance(q,(int,float)) and math.isfinite(q):
                    remaining=max(0,q-elapsed) if row['state']=='RUNNING' else q
                    if row['service_slots']!=math.ceil(remaining/900): raise ValueError('CACHED_SERVICE_IDENTITY_DRIFT')
                membership=dict(day=day,population=role,job_uid=uid,submission_time=row['submit_time'],**result)
                memberships.append(membership); all_ids.add(uid)
                if result['modelable']:
                    physical_ids.add(uid); out.append(dict(row,compatible_sites=result['compatible_sites']))
                    age=(timestamp(row['runtime_inference_event_time'])-timestamp(row['submit_time'])).total_seconds()
                    cohort=cohort_key(raw['qos'],raw['partition'],raw['gpus_requested'],raw['requested_seconds'],raw['nodes_req'])
                    ts=wait.evaluate(row['state'],cohort,age)
                    # Eligibility candidates are not complete-option execution certificates.
                    prestart=row['state']=='PENDING' and row['service_slots']>0 and len(result['compatible_sites'])>1
                    flexrows.append(dict(day=day,population=role,job_uid=uid,
                        can_timeshift=ts['can_timeshift'],TS_slots=ts['TS_slots'],TS_proof=ts,
                        can_prestart_place=prestart,can_checkpoint_migrate=None,
                        checkpoint_status='REQUIRES_REFERENCE_WAN_COMPLETE_OPTION_BINDING',
                        candidate_J_FLEX=ts['can_timeshift'] or prestart,
                        executable_J_FLEX_certified=False,
                        fixed_service_retained_in_all_arms=True))
                else:
                    excluded_ids.add(uid)
                    ledger.append(dict(day=day,population=role,job_uid=uid,submission_time=row['submit_time'],
                        classification=result['classification'],exclusion_reason=result['reasons'],
                        source_field_status=result['source_field_status'],raw_source=first['archive']['path'],
                        source_sha256=first['archive']['sha256'],source_member=row['source_member'],source_row=row['source_row']))
                t=timestamp(row['submit_time'])
                representation.append(dict(day=day,job_uid=uid,group='MODELABLE' if result['modelable'] else 'UNMODELABLE',
                    population=role,state=row['state'],submission_date=t.strftime('%Y-%m-%d'),submission_hour=t.hour,**raw))
            selected[role]=out; missingcounts[role]=len(rows)-len(out)
        p=deepcopy(p); a=deepcopy(a)
        p['known_population']=selected['KNOWN_D1']; a['post_issue_arrivals']=selected['ACTUAL_POST_ISSUE']
        known_ids={r['job_uid'] for r in p['known_population']}
        a['observed_known_episodes']=[r for r in a['observed_known_episodes'] if r['job_uid'] in known_ids]
        a['known_immutable_GPU_map']={r['job_uid']:r['GPU_gang'] for r in p['known_population']}
        p['forecast_inputs'].update(CC4_bound=True,CC4_date_projection=record(OUT/'CC4'/(folder+'.json')))
        p['forecast_inputs']['current_CC4']=cc4[day]
        for b in (p,a):
            b.update(schema='V42_MODELABLE_DAY_INPUT_BUNDLE_V1',J_PHYSICAL_frozen=True,
                flags=dict(B0_FLAGS,COMMON_CC4_USED=True),input_gate_PASS=False,
                status='PHYSICAL_INPUT_COMPLETE_EXECUTION_BINDING_PENDING',
                request_version_history='UNVERIFIED_SOURCE_PROXY', no_GPU_imputation=True)
        full=selected['KNOWN_D1']+selected['ACTUAL_POST_ISSUE']
        for role in selected:
            candidates={f['job_uid'] for f in flexrows if f['day']==day and f['population']==role and f['candidate_J_FLEX']}
            common_arm_population(selected[role],candidates)
        gate=dict(day=day,J_PHYSICAL_GPU_COMPLETE=all(type(r['GPU_gang']) is int and r['GPU_gang']>0 for r in full),
            runtime_complete=all(r['runtime_authority']==MODEL and type(r['service_slots']) is int for r in full),
            compatible_complete=all(r['compatible_sites'] for r in full),CC4_date_bound=True,
            forecast_raw_complete=p['forecast_inputs']['complete'],Actual_raw_complete=a['realized_inputs']['complete'],
            network_static_complete=p['network_authority']['network_static_complete'],
            electrical_adapter_bound=False,Actual_physical_occupancy_generated=False,
            input_fields_complete=True, executable_bundle_complete=False,
            raw_completeness_required=False,request_versions_verified=False)
        if not all(gate[k] for k in ('J_PHYSICAL_GPU_COMPLETE','runtime_complete','compatible_complete','forecast_raw_complete','Actual_raw_complete','network_static_complete')):
            raise ValueError('MODELABLE_INPUT_INCOMPLETE')
        # Causal grid-blind initial-state preflight. It is not a frozen executable
        # schedule and does not view Actual, voltage or line results.
        rr, audit=build_reference(p['known_population'],p['capacities'],p['rack_compatibility'],issue_time=p['issue_time'])
        refs.extend(dict(day=day,**r) for r in rr)
        running=[r for r in p['known_population'] if r['state']=='RUNNING']
        audit.update(day=day,preflight_only=True,observed_running_jobs=len(running),
            observed_running_GPU=sum(r['GPU_gang'] for r in running),total_installed_GPU=sum(p['capacities'].values()),
            capacity_lower_bound_infeasible=sum(r['GPU_gang'] for r in running)>sum(p['capacities'].values()))
        refaudits.append(audit)
        gate['reference_preflight_ready']=audit['full_reference_ready']; gates.append(gate)
        rawset={r['job_uid'] for r in read(pp)['known_population']+read(ap)['post_issue_arrivals']}
        physet={r['job_uid'] for r in full}
        byday.append(dict(day=day,RAW_KNOWN=rawcounts['KNOWN_D1'],MODELABLE_KNOWN=len(selected['KNOWN_D1']),
            UNMODELABLE_KNOWN=missingcounts['KNOWN_D1'],RAW_ACTUAL=rawcounts['ACTUAL_POST_ISSUE'],
            MODELABLE_ACTUAL=len(selected['ACTUAL_POST_ISSUE']),UNMODELABLE_ACTUAL=missingcounts['ACTUAL_POST_ISSUE'],
            raw_unique_jobs=len(rawset),modelable_unique_jobs=len(physet),unmodelable_unique_jobs=len(rawset-physet),
            modelable_job_fraction=len(physet)/len(rawset),unmodelable_job_fraction=len(rawset-physet)/len(rawset),
            GPUH_COVERAGE='NOT_IDENTIFIABLE_FROM_SOURCE'))
        write(OUT,'BUNDLE/'+folder+'/PLANNING_INPUT_BUNDLE.json',p)
        write(OUT,'BUNDLE/'+folder+'/ACTUAL_INPUT_BUNDLE.json',a)
        write(OUT,'BUNDLE/'+folder+'/SOURCE_PROVENANCE.json',dict(prov,
            inherited_planning_cache=record(pp),inherited_actual_cache=record(ap),
            modelable_rule=record(OUT/'POPULATION/V42_PHYSICAL_MODELABILITY_RULE.md'),
            Runtime_cache_reused=True,Runtime_cache_exact_base=True,
            raw_GPU_rejoined=True,raw_population_retained_in_BASE=True,
            exclusion_ledger='POPULATION/V42_UNMODELABLE_WORKLOAD_LEDGER.csv'))
        manifest.append(dict(day=day,planning=record(OUT/'BUNDLE'/folder/'PLANNING_INPUT_BUNDLE.json'),
            actual=record(OUT/'BUNDLE'/folder/'ACTUAL_INPUT_BUNDLE.json')))
        print(day, 'physical',len(full),'running GPU',audit['observed_running_GPU'],'reference ready',audit['full_reference_ready'],flush=True)
    if physical_ids & excluded_ids: raise ValueError('UID_MODELABILITY_CHANGED_ACROSS_EVENTS')
    table(OUT,'POPULATION/V42_UNMODELABLE_WORKLOAD_LEDGER.csv',ledger,list(ledger[0]))
    table(OUT,'POPULATION/APRIL_MODELABILITY_BY_DAY.csv',byday,list(byday[0]))
    table(OUT,'POPULATION/PHYSICAL_MEMBERSHIP.csv',memberships,list(memberships[0]))
    table(OUT,'POPULATION/FLEXIBILITY_CANDIDATES.csv',flexrows,list(flexrows[0]))
    summary=dict(raw_unique_jobs=len(all_ids),modelable_unique_jobs=len(physical_ids),unmodelable_unique_jobs=len(excluded_ids),
        modelable_job_fraction=len(physical_ids)/len(all_ids),unmodelable_job_fraction=len(excluded_ids)/len(all_ids),
        raw_events=len(memberships),modelable_events=len(memberships)-len(ledger),unmodelable_events=len(ledger),
        classifications=dict(Counter(r['classification'] for r in ledger)),
        reasons=dict(Counter(reason for r in ledger for reason in r['exclusion_reason'])),
        GPUH_COVERAGE='NOT_IDENTIFIABLE_FROM_SOURCE',excluded_GPUh=None,
        J_PHYSICAL_frozen=True,J_FLEX_rule_frozen=True,J_FLEX_executable_population_frozen=False,
        candidate_flex_events=sum(r['candidate_J_FLEX'] for r in flexrows),same_physical_population_all_four_arms=True,
        Runtime=MODEL,missing_GPU_imputed=0,arbitrary_coverage_threshold=None)
    write(OUT,'POPULATION/APRIL_MODELABILITY_SUMMARY.json',summary)
    write(OUT,'POPULATION/REPRESENTATIVENESS_AUDIT.json',distributions(representation))
    write(OUT,'BUNDLE/APRIL_INPUT_MANIFEST.json',dict(days=manifest,physical_input_complete_days=30,
        executable_complete_days=0,raw_files_copied_to_git=False,raw_archive=first['archive'],projections=projections))
    table(OUT,'BUNDLE/APRIL_DAY_INPUT_GATE.csv',gates,list(gates[0]))
    columns=['day','job_uid','state_at_D1_cutoff','reference_site','reference_start','service_slots','GPU_gang','runtime_authority',
        'site_authority_source','start_authority_source','fallback_used','queue_rule','compatible_sites','status','reason']
    table(OUT,'REFERENCE/V42_COMMON_REFERENCE_SCHEDULE.csv',refs,columns)
    write(OUT,'REFERENCE/V42_COMMON_REFERENCE_AUTHORITY.json',dict(frozen_executable_schedule=False,
        status='GRID_BLIND_PREFLIGHT_ONLY',preflight_ready_days=sum(a['full_reference_ready'] for a in refaudits),
        issue_origin_to_day_origin_slots=24,audits=refaudits,
        missing_GPU_is_not_blocker=True,population_retuned_after_capacity_check=False,
        grid_reads=0,Actual_reads=0,May_reads=0,optimizer_calls=0))
    write(OUT,'POPULATION/MAY_RULE_COMPATIBILITY_AUDIT.json',dict(status='CODE_SCHEMA_COMPATIBLE',
        inherited_audit=record(PRIOR/'MAY_PIPELINE/MAY_GPU_AUTHORITY_AUDIT.json'),
        checks=dict(raw_positive_requested_GPU_required=True,requested_GPU_to_GPU_gang_unchanged=True,
            missing_GPU_never_modelled=True,current_Runtime_supersedes_requested_walltime=True,
            historical_capacity_admission_filter_not_copied=True,nonflex_jobs_retained=True),
        row_numeric_reproduction=False,May_metadata_job_payloads_read=False,
        limitation='Code/schema semantics verified; no May job-by-job numeric population reproduction claimed.',
        May_outcomes_used=False))
    print(summary,flush=True)

if __name__=='__main__': main()
