"""Original FULL cache rejection and causal pre-site witness, never an A1 result."""
from collections import Counter
from dataclasses import asdict,replace
from pathlib import Path
import copy,types
import numpy as np
from .prestart import ROOT,DOC,OUT,RUN,read,put,table,record,digest,resources
from .prestart_acceptance import source_domain,certify

def prepare_case(day,selected,tag):
    from v43_actual import case as source
    output=RUN/'aidc'/tag;output.mkdir(parents=True,exist_ok=True)
    native=read(day['files']['native']['path']);windows=read(day['files']['windows']['path'])
    freeze=dict(selected_jobs=selected,scientific_input={'NATIVE_INPUT.json':day['files']['native'],'WINDOWS.json':day['files']['windows']})
    command_path=output/'FINITE_KNOWN_COMMANDS.json'
    command_path.write_text(__import__('json').dumps(freeze),encoding='utf-8')
    certificate=dict(planning_freeze=record(command_path))
    initial_path=Path(day['files']['initial_running_authority']['path']);initial=read(initial_path)
    ns=dict(source.prepare.__globals__,BUNDLE=Path(day['files']['planning_input']['path']).parent,
        accepted=lambda:(certificate,freeze,native,windows,{}),initialize=lambda out:(copy.deepcopy(initial),initial_path))
    fn=types.FunctionType(source.prepare.__code__,ns,argdefs=source.prepare.__defaults__);fn.__kwdefaults__=source.prepare.__kwdefaults__
    kwargs,identity=fn(output)
    kwargs.pop('power_model');kwargs.pop('forecast',None)
    # Source prepare contains historical Golden labels. The receipt explicitly
    # binds our finite commands and carries no accepted optimizer certificate.
    put(f'AIDC_{tag}_BINDING.json',dict(source_prepare=record(Path(source.__file__)),identity=identity,
        scope='FINITE_ORIGINAL_CONTROLLER_DIAGNOSTIC_NOT_GOLDEN_OR_A1_ACCEPTANCE',new_command_document=record(command_path)))
    return kwargs

def replay(kwargs,arm):
    from v43_actual.vendor.actual import run_actual
    kwargs['arm']=arm
    return run_actual(**kwargs)

def main():
    resources();day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    native=read(day['files']['native']['path']);windows=read(day['files']['windows']['path']);jobs,bounds,seconds,r,raw=source_domain(native,windows)
    old=read(DOC/'source/aidc_pilot/PLANNING_REFERENCE.json')['selected_jobs']
    rejection=certify(old,native,windows,identity={},expected_identity={})
    assert Counter(v['reason'] for v in rejection['violations'])=={'START_WINDOW':414}
    put('PLANNING_CACHE_ORIGINAL_FULL_REJECTION.json',rejection)
    # Pending preplacement at issue is a genuine original option; previous
    # fixed-prefix offline search could not measure this causal action class.
    from v42_job_capability import Option,validate
    prereg=put('AIDC_CAUSAL_PRESITE_PREREGISTRATION.json',dict(rule='FIRST_UID_PENDING_REFERENCE_START_ZERO_FIRST_LEXICAL_OTHER_COMPATIBLE_SITE',
        sites_selected_without_AC_scores=True,all_gang_sizes_scanned=True,zero_time_shift=True,no_added_migration_authority=True,
        scope='Original research model; no customer Source consent inferred; commands at issue apply prospectively, never retroactively'))
    chosen={};census=[]
    for uid,j in sorted(jobs.items()):
        row=dict(uid=uid,state=j.state,GPU_gang=j.gpu,reference_start=j.reference_start,preplace_sites=0)
        if j.state=='PENDING':
            for s in sorted(set(j.initial_sites)-{j.reference_site}):
                o=Option(j.reference_start,s,((s,j.reference_start,j.reference_start+j.service_slots),))
                try:validate(j,o,bounds[uid],r)
                except ValueError:continue
                row['preplace_sites']+=1
                if not chosen and j.reference_start==0 and native['capacities'][s]>=j.gpu:chosen[uid]=asdict(o)
        census.append(row)
    table('ORIGINAL_FULL_PRESITE_DOMAIN_CENSUS.csv',census)
    assert chosen
    base=replay(prepare_case(day,{},'BASE'),'B0')
    trial=replay(prepare_case(day,chosen,'PRESITE'),'B1')
    fresh=replay(prepare_case(day,chosen,'PRESITE_FRESH'),'B1')
    fields=['occupancy_GPU','compute_occupancy_GPU']
    identical=all(np.array_equal(trial[k],fresh[k]) for k in fields)
    assert identical and trial['job_event_ledger']==fresh['job_event_ledger']
    from .aidc_candidate import actual_c1
    p,q,it=actual_c1(trial['occupancy_GPU'],trial['sites'],day)
    bp,bq,bit=actual_c1(base['occupancy_GPU'],base['sites'],day)
    file=RUN/'aidc/CAUSAL_PRESITE_WITNESS.npz'
    np.savez_compressed(file,GPU=trial['occupancy_GPU'],P=p,Q=q,IT=it,base_GPU=base['occupancy_GPU'],base_P=bp,base_Q=bq,delta_P=p-bp,delta_Q=q-bq)
    # Full event trace retained locally. Output receipts prohibit misuse as a
    # complete optimizer freeze or customer SLA certification.
    for tag,x in [('BASE',base),('PRESITE',trial),('PRESITE_FRESH',fresh)]:
        import json
        folder=RUN/'aidc'/tag
        (folder/'EVENT_LEDGERS.json').write_text(json.dumps({k:v for k,v in x.items() if k not in ('occupancy_GPU','compute_occupancy_GPU','physical')},ensure_ascii=False),encoding='utf-8')
    starts={v['uid']:v for v in trial['job_event_ledger'] if v['event']=='RUNNING'}
    actual_commands=[dict(uid=u,command=cmd,actual_start=starts.get(u)) for u,cmd in chosen.items()]
    excess=[v for v in trial['qos_ledger'] if v['total_intentional_burden_seconds']>v['budget_seconds']+1e-6]
    row=[]
    for t in range(120):row.append(dict(slot=t,evaluation_slot=t-24,IT_delta_kw=float((it[t]-bit[t]).sum()),
        reduction_sum_positive_PCC_kw=float(np.maximum(bp[t]-p[t],0).sum()),rebound_sum_positive_PCC_kw=float(np.maximum(p[t]-bp[t],0).sum()),
        signed_PCC_delta_total_kw=float((p[t]-bp[t]).sum())))
    table('AIDC_CAUSAL_SLOT_FLEXIBILITY.csv',row)
    original=read(DOC/'correction/AIDC_REAL_FEASIBILITY.json')
    report=dict(status='CAUSAL_PRESITE_WITNESS_REQUIRES_FULL_SCHEDULE_AND_GRID_ACCEPTANCE',
        installed_GPU=780,domain_jobs=len(jobs),all_gang_counts=dict(Counter(str(j.gpu) for j in jobs.values())),
        original_FULL_preplace_candidate_jobs=sum(x['preplace_sites']>0 for x in census),
        source_FULL_options_individually_valid=True,selected=actual_commands,all_commands_executed=all(v['actual_start'] for v in actual_commands),
        Fresh_event_replay_identical=identical,Actual_model_capacity_violations=trial['receipt']['capacity_violations'],
        strict_intentional_QoS_excess=len(excess),strict_customer_Source_QoS_certified=False,
        known_research_policy192_reclassified=False,new_relaxed_known_policy_used=False,
        time_shift_witness=original['selected_jobs'],time_shift_search_not_global_upper_bound=True,
        migration_witness=None,checkpoint_migration_full_causal_integration_certified=False,
        GPUh_total_change=float((trial['compute_occupancy_GPU']-base['compute_occupancy_GPU']).sum()*.25),
        occupation_GPUh_redistributed=float(np.maximum(base['occupancy_GPU']-trial['occupancy_GPU'],0).sum()*.25),
        slot31=row[55],slot74=row[98],all120_delta_P_max_abs_kw=float(np.max(abs(p-bp))),
        nonzero_Actual_schedule_observed=bool(np.max(abs(p-bp))>1e-9),
        electrical120_AC_PASS=False,original_FULL_joint_Job_verifier_PASS=False,
        dataset=record(file),original_event_receipt=trial['receipt'],baseline_event_receipt=base['receipt'],
        baseline_vs_existing_frozen_P_max_kw=float(np.max(abs(bp-np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz')['ACTUAL_AIDC_P_kw']))),
        exact_slot31_74_power_is_replayed_not_1024_job_count=True,Native_optimizer_calls=0,
        capacity_expansion='NOT_AUTHORIZED_OR_JUSTIFIED_BY_A_SMALL_WITNESS; workload/rack/WAN/deadline redesign required before physical scale comparison')
    put('AIDC_CAUSAL_FLEXIBILITY_CERTIFICATION.json',report)
    print(report['status'],report['nonzero_Actual_schedule_observed'],report['strict_intentional_QoS_excess'],flush=True)

if __name__=='__main__':main()
