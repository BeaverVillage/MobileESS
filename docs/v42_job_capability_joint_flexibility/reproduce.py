"""Read-only historical audit + synthetic canaries. Never imports native pipelines.

Usage: python docs/v42_job_capability_joint_flexibility/reproduce.py --workspace PATH
Large full-period membership is local and SHA-bound, not a production freeze.
"""
from pathlib import Path
import argparse, hashlib, json, sys, importlib.util, ast, math
from dataclasses import replace
from datetime import datetime, timezone
from collections import Counter
import pandas as pd
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from v42_job_capability import (legacy_r0_bounds, build_domain, capability, executable_domains,
    solve_joint, resources_used, checkpoint_records, ACTION_CLASSES)


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def dump(name,value):
    (HERE/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False,
        default=lambda x:x.item() if hasattr(x,'item') else str(x))+'\n',encoding='utf-8')


def csv(name,rows):
    pd.DataFrame(rows).to_csv(HERE/name,index=False,lineterminator='\n')


def record(p):return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)


def run(work):
    old=work/'v42_flexibility_pr/docs/v42_aidc_workload_flexibility'
    episode=work/'v42_reference_episode_pr/docs/v42_aidc_reference_episode_continuity'
    integrated=work/'v42_integrated_pr'
    native=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
    local=work/'V42_JOB_CAPABILITY_LOCAL';local.mkdir(exist_ok=True)
    prereg=record(HERE/'PREREGISTRATION.json')
    sources=list(old.glob('*'))+list(episode.rglob('*'))+list((integrated/'v42').glob('*.py'))
    sources += [native/p for p in ['dayahead/v41r1/migration.py','dayahead/v41r1/migration_admission.py',
        'dayahead/v41r1/terminal.py','dayahead/v41/temporal_restore.py','dayahead/v40g/domain.py',
        'dayahead/v41/objectives.py','dayahead/v40a/grid.py','pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json']]
    sources += [work/'ieee123_per_mess_pr/docs/IDC_MIGRATION_DATA_AUTHORITY_V1.md',
        integrated/'docs/v42_final/V42_SERVICE_FEASIBILITY_AUDIT.json']
    sources=sorted(set(p for p in sources if p.is_file() and '__pycache__' not in str(p)))
    before={str(p):sha(p) for p in sources}
    dump('SOURCE_MANIFEST.json',dict(registered_input=prereg,files=[record(p) for p in sources],
        external_sources_read_only=True,semantic_ML_branch_not_imported_or_modified=True))

    # Historical reproduction from published frozen evidence, not a new May run.
    pop=pd.read_csv(old/'REFERENCE_POPULATION.csv')
    r0=pd.read_csv(old/'FLEXIBLE_MEMBERSHIP_R0.csv')
    vals=[legacy_r0_bounds(r) for r in pop.to_dict('records')]
    gate=np.array([v[0] for v in vals]);lower=np.array([v[1] for v in vals]);upper=np.array([v[2] for v in vals])
    assert np.array_equal(gate,pop.eligible_standby.to_numpy())
    assert np.array_equal(lower,r0.lower_slot.to_numpy()) and np.array_equal(upper,r0.upper_slot.to_numpy())
    assert np.array_equal(upper>lower,r0.temporal_domain.to_numpy())
    historical=[]
    for label,mask in [('STORED_GATE',gate),('RESTORED_DOMAIN',upper>lower),('PUBLISHED_STANDALONE_WITNESS',r0.temporal_flexible)]:
        historical.append(dict(definition=label,jobs=int(mask.sum()),job_percent=float(mask.mean()*100),
            day_GPUh=float(r0.loc[mask,'day_GPUh'].sum()),day_GPUh_percent=float(r0.loc[mask,'day_GPUh'].sum()/r0.day_GPUh.sum()*100)))
    dump('R0_REPRODUCTION.json',dict(PASS=True,N=len(pop),bounds_mismatches=0,gate_mismatches=0,
        reference_jobdays=len(pop),day_GPUh_denominator=float(r0.day_GPUh.sum()),definitions=historical,
        scope='Published PR75 evidence only; standalone witness membership retained, not recomputed as joint feasibility',
        new_May_evaluation_run=False))
    # Required old R1/R2 and distributions are audited without promoting them.
    for rule in ('R1','R2'):
        rows=pd.read_csv(old/f'FLEXIBLE_MEMBERSHIP_{rule}.csv')
        assert len(rows)==len(pop) and rows[['day','job_uid']].equals(r0[['day','job_uid']])
    for name in ('ELIGIBILITY_FUNNEL.csv','SHIFT_WINDOW_DISTRIBUTION.csv','COHORT_LATENCY_STATISTICS.csv'):
        assert len(pd.read_csv(old/name))>0

    train=pd.read_csv(old/'TRAIN_MEMBERSHIP.csv.gz')
    cutoff=pd.Timestamp('2025-01-01T00:00:00Z')
    assert pd.to_datetime(train.start_time,utc=True).lt(cutoff).all()
    assert pd.to_datetime(train.end_time,utc=True).lt(cutoff).all()
    assert (train.queue_seconds>=0).all() and not train.id.duplicated().any()
    stats=[]
    dims=['qos','partition','workload_class','protected','gpu_bucket','wall_bucket','requested_nodes']
    for key,g in train.groupby('cohort',sort=True):
        stats.append(dict(cohort=key,**{d:g.iloc[0][d] for d in dims},N=len(g),
            Q25_seconds=g.queue_seconds.quantile(.25),median_seconds=g.queue_seconds.median(),
            Q75_seconds=g.queue_seconds.quantile(.75),Q90_seconds=g.queue_seconds.quantile(.9),
            max_seconds=g.queue_seconds.max(),mean_seconds=g.queue_seconds.mean(),
            max_observed_start=g.start_time.max(),cutoff=str(cutoff)))
    csv('TRAIN_COHORT_LATENCY_STATISTICS.csv',stats)
    stat=pd.DataFrame(stats).set_index('cohort')
    ledger=pd.read_parquet(episode/'CANONICAL_REFERENCE_LEDGER.parquet')
    assert ledger.operating_day.max()<'2025-05-01'
    snapshots=[];snapshot_sources=[]
    snapshot_days=sorted(p.parent.name for p in (work/'V42_FINAL_LOCAL/policy_snapshots').glob('*/D1_AIDC_SNAPSHOT.parquet')
                         if '2024-03-15'<=p.parent.name<='2025-04-30')
    for day in snapshot_days:
        p=work/'V42_FINAL_LOCAL/policy_snapshots'/day/'D1_AIDC_SNAPSHOT.parquet'
        snapshot_sources.append(record(p))
        sources.append(p);before[str(p)]=snapshot_sources[-1]['sha256']
        q=pd.read_parquet(p,columns=['id','operating_day','qos','partition','gpus_requested','nodes_req','wallclock_seconds','request_versions'])
        snapshots.append(q)
    snap=pd.concat(snapshots,ignore_index=True).rename(columns={'id':'job_uid'})
    snap.job_uid=snap.job_uid.astype(str);ledger.job_uid=ledger.job_uid.astype(str)
    f=ledger.merge(snap,on=['operating_day','job_uid'],validate='one_to_one',suffixes=('','_snapshot'))
    assert len(f)==len(ledger)
    # D-1 issue time, not operating-day label, controls feature availability.
    # Jan01 operates after cutoff but its Dec31 issue precedes the freeze.
    f['split']=np.where(f.issue_seconds < int(cutoff.timestamp()),'PRE_CUTOFF_ISSUE_INVENTORY','PREMAY_VALIDATION')
    # Existing operational QoS labels, never a fabricated semantic class.
    f['protected']=~f.qos.isin(['normal','standby'])
    f['workload_class']=np.select([f.qos.eq('normal'),f.qos.eq('standby'),f.qos.isin(['high','urgent'])],
        ['NORMAL_QUEUE_CONTROLLED','STANDBY_QUEUE_CONTROLLED','HIGH_PROTECTED'],default='FIXED_PROTECTED')
    f['gpu_bucket']=pd.cut(f.gpus_requested,[0,1,4,16,64,np.inf],labels=['1','2-4','5-16','17-64','65+']).astype(str)
    f['wall_bucket']=pd.cut(f.wallclock_seconds,[0,3600,14400,86400,np.inf],labels=['<=1h','1-4h','4-24h','>24h']).astype(str)
    f['requested_nodes']=f.nodes_req.astype(int)
    f['cohort']=f[dims].astype(str).agg('|'.join,axis=1)
    f['cohort_N']=f.cohort.map(stat.N).fillna(0).astype(int)
    f['median_seconds']=f.cohort.map(stat.median_seconds)
    f['Q25_seconds']=f.cohort.map(stat.Q25_seconds)
    f['full_service_GPUh']=f.requested_GPU*f.safe_duration_slots/4
    v=f.split.eq('PREMAY_VALIDATION')
    assert f.loc[v,'issue_seconds'].min()>=cutoff.timestamp()
    assert pd.to_datetime(train.start_time,utc=True).max().timestamp()<f.loc[v,'issue_seconds'].min()
    base=v & f.state_at_issue.eq('PENDING') & ~f.protected & f.resource_request_valid
    comparisons=[];funnels=[];budgets=[]
    for rule in ('T0_CURRENT','T1_COHORT_MEDIAN','T2_CONSERVATIVE_Q25'):
        proxy=base & f.qos.eq('standby')
        if rule!='T0_CURRENT':
            metric='median_seconds' if rule=='T1_COHORT_MEDIAN' else 'Q25_seconds'
            proxy |= base & f.cohort_N.ge(100) & f[metric].ge(900)
        f[rule+'_eligibility_proxy']=pd.array(np.where(v,proxy,None),dtype='boolean')
        comparison=dict(rule=rule,population='PREMAY_VALIDATION_JOBDAYS',denominator_jobs=int(v.sum()),
            denominator_full_service_GPUh=float(f.loc[v,'full_service_GPUh'].sum()),
            eligibility_proxy_jobs=int(proxy.sum()),eligibility_proxy_job_percent=float(proxy.sum()/v.sum()*100),
            eligibility_proxy_GPUh=float(f.loc[proxy,'full_service_GPUh'].sum()),
            eligibility_proxy_GPUh_percent=float(f.loc[proxy,'full_service_GPUh'].sum()/f.loc[v,'full_service_GPUh'].sum()*100),
            temporal_candidate_jobs=None,executable_jobs=None,executable_GPUh=None,
            reason='FINAL_SERVICE_AND_HISTORICAL_REQUEST_VERSION_AUTHORITY_MISSING',
            full_service_identity='DURATION_LEDGER_ONLY_NOT_EXECUTED',
            cross_midnight_eligibility_proxy=int((proxy & f.reference_end_slot.gt(120)).sum()),
            reference_carryout_GPUh=float((f.loc[proxy,'reference_end_slot'].sub(120).clip(lower=0)*f.loc[proxy,'requested_GPU']/4).sum()))
        comparisons.append(comparison)
        for stage,mask in [('ALL',v),('PENDING',v&f.state_at_issue.eq('PENDING')),('BASE_UNPROTECTED_VALID_REQUEST',base),('COHORT_QOS_PROXY',proxy)]:
            funnels.append(dict(rule=rule,stage=stage,jobs=int(mask.sum()),full_service_GPUh=float(f.loc[mask,'full_service_GPUh'].sum()),scope='ELIGIBILITY_ONLY'))
        funnels.append(dict(rule=rule,stage='FINAL_SERVICE_EXECUTABLE',jobs=None,full_service_GPUh=None,scope='NOT_AVAILABLE'))
        values=(f.loc[proxy&~f.qos.eq('standby'),'Q25_seconds']//900*900) if rule=='T2_CONSERVATIVE_Q25' else pd.Series(dtype=float)
        budgets.append(dict(rule=rule,scope='NONSTANDBY_EMPIRICAL_PROXY_ONLY',N=len(values),
            mean_seconds=values.mean(),median_seconds=values.median(),Q25_seconds=values.quantile(.25),
            Q75_seconds=values.quantile(.75),Q90_seconds=values.quantile(.9),max_seconds=values.max(),
            standby_budget='FINAL_AUTHORIZED_WINDOW_PENDING',reason='T1_PR75_R1_HAS_NO_COHORT_BUDGET_CAP; T2_ONLY'))
    for name in ('can_timeshift','can_prestart_place','can_checkpoint_migrate','FLEX','FIX'):
        f[name]=pd.array([None]*len(f),dtype='boolean')
    f['capability_reason']='NOT_FINALIZED_SERVICE_AND_NATIVE_BINDING'
    f['capability_selected_action']=None
    membership=local/'FULL_PREMAY_CAPABILITY_MEMBERSHIP.csv.gz'
    f.to_csv(membership,index=False,compression={'method':'gzip','mtime':0},lineterminator='\n')
    dump('POPULATION_SCOPE.json',dict(total_jobdays=len(f),unique_source_jobs=f.job_uid.nunique(),
        first_day=f.operating_day.min(),last_day=f.operating_day.max(),days=f.operating_day.nunique(),
        snapshot_days=len(snapshot_days),snapshot_first_day=snapshot_days[0],empty_snapshot_days=len(snapshot_days)-f.operating_day.nunique(),
        validation_first_day=f.loc[v,'operating_day'].min(),validation_jobdays=int(v.sum()),
        train_history_inventory_jobdays=int((~v).sum()),TRAIN_statistics_N=len(train),TRAIN_cohorts=len(stat),
        original_request_version_values=f.request_versions.value_counts(dropna=False).to_dict(),
        actual_executable_capability_percentages=None,missing_is_not_false=True,
        full_membership=record(membership),snapshots=snapshot_sources,
        unavailable_energy='No new population PCC/power attribution without bound frozen power authority'))
    csv('TIMESHIFT_RULE_COMPARISON.csv',comparisons)
    csv('TIMESHIFT_ELIGIBILITY_FUNNEL.csv',funnels)
    csv('TIMESHIFT_DELAY_BUDGET_DISTRIBUTION.csv',budgets)

    spec=importlib.util.spec_from_file_location('canary_fixtures',ROOT/'tests/test_v42_job_capability.py')
    fixture_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture_module)
    # Extract only the pure inherited phase function; no native pipeline import.
    tree=ast.parse((integrated/'v42/checkpoints.py').read_text(encoding='utf-8'))
    pure=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='checkpoint_records'],type_ignores=[])
    ns={'math':math};exec(compile(pure,'inherited_checkpoint_records','exec'),ns)
    mapping_delays=[];phase_comparisons=0
    for elapsed in [0.,1.,899.,900.,1799.,1800.,1801.,57238.3]+[float(x*317+0.25) for x in range(100)]:
        j,_,_,_=fixture_module.fixture('E');j=replace(j,elapsed_seconds=elapsed)
        expected=ns['checkpoint_records'](None,0,6,causal_elapsed_seconds=elapsed,elapsed_observed_slot=0,include_current=True)
        actual=checkpoint_records(j,0,6)
        assert [x[0] for x in actual]==[x['control_slot'] for x in expected]
        assert all(abs(a[1]-e['physical_checkpoint_seconds'])<1e-8 for a,e in zip(actual,expected))
        mapping_delays.extend(cp*900-physical for cp,physical in actual);phase_comparisons+=1
    dump('CHECKPOINT_PHASE_AUDIT.json',dict(PASS=True,compared_elapsed_cases=phase_comparisons,
        physical_cadence_seconds=1800,control_grid_seconds=900,carry_in_phase_source='CAUSAL_ELAPSED_SECONDS',
        modeled_start_required=False,issue_D00_phase_reset_count=0,backward_rounding_count=0,
        mapping_delay_seconds=dict(min=min(mapping_delays),max=max(mapping_delays),
            P50=float(np.quantile(mapping_delays,.5)),P95=float(np.quantile(mapping_delays,.95))),
        exact_current_boundary_checked=True,scope='SYNTHETIC_PHASE_EQUIVALENCE'))
    memberships=[];domains_audit=[];screens=[];spatial=[];migration=[];canaries=[];total_options=0
    degeneracy=None
    for case in 'ABCDEFGHIJ':
        j,b,r,g=fixture_module.fixture(case)
        opts,a=build_domain(j,b,r)
        witnessed=executable_domains({j.uid:j},{j.uid:opts},r,g)[j.uid]
        masks=capability(j,witnessed)
        result=solve_joint({j.uid:j},{j.uid:opts},r,g)
        selected=result['selected'][j.uid]
        memberships.append(dict(population='SYNTHETIC_CANARY_ONLY',uid=case,full_service_GPUh=j.gpu*j.service_slots/4,
            temporal_candidate=a['temporal_candidate'],**masks,selected_action=selected.action(j),migration_selected=selected.migrated))
        domains_audit.append(dict(uid=case,before=a['attempted_complete_options'],after=len(opts),globally_witnessed=len(witnessed),
            **{'N_'+k:a['after_by_class'].get(k,0) for k in ACTION_CLASSES},
            **{'BEFORE_'+k:a['before_by_class'].get(k,0) for k in ACTION_CLASSES}))
        for reason,n in a['rejected'].items():screens.append(dict(uid=case,reason=reason,count=n,scope='SAFE_HARD_REJECTION_OR_BRANCH_SKIP'))
        sites={s:{o.initial_site for o in witnessed if o.start==s} for s in {o.start for o in witnessed}}
        spatial.append(dict(uid=case,can_prestart_place=masks['can_prestart_place'],max_sites_at_one_start=max(map(len,sites.values())),
            GPUh=j.gpu*j.service_slots/4,current_site_only=all(o.initial_site==j.reference_site for o in witnessed),
            rack_rejections=a['rejected'].get('RACK_COMPATIBILITY',0),site_gpu_rejections=a['rejected'].get('SITE_GPU',0),
            residency='SYNTHETIC_EXPLICIT_SITES; native all12 prestaging modeled only'))
        moving=[o for o in witnessed if o.migrated]
        migration.append(dict(uid=case,can_checkpoint_migrate=masks['can_checkpoint_migrate'],
            checkpoint_count=len({o.checkpoint for o in moving}),destinations=len({o.destination for o in moving}),
            WAN_infeasible=a['rejected'].get('WAN_TRANSFER_IMPOSSIBLE',0),restart_infeasible=a['rejected'].get('WAN_RESTART',0),
            useful_service_rejections=a['rejected'].get('NO_CAUSAL_CHECKPOINT_OR_USEFUL_SERVICE',0),
            payload_bytes=j.gpu*r.bytes_per_gpu,transfer_slots_min=min((o.transfer_end-o.transfer_start for o in moving),default=None),
            transfer_slots_max=max((o.transfer_end-o.transfer_start for o in moving),default=None),
            assumption_class='SYNTHETIC_SCALE_FOR_UNIT_TEST; NOT_NATIVE_PAYLOAD'))
        for o in opts:
            assert sum(b-a for _,a,b in o.segments)==j.service_slots
            assert sum(n for key,n in resources_used(j,o).items() if key[0]=='GPU')==j.gpu*j.service_slots
        total_options+=len(opts)
        canaries.append(dict(case=case,PASS=True,capabilities=masks,options=len(opts),selected=selected.action(j),
            rho=result['passes'][0]['value'],passes=result['passes'],binary_variables=result['binary_variables'],
            full_service_GPUh=j.gpu*j.service_slots/4,elapsed_seconds=result['elapsed_seconds'],
            post_H_GPUh=sum(max(0,end-max(96,start))*j.gpu/4 for _,start,end in selected.segments)))
        if case=='F':
            pair=[next(o for o in opts if o.action(j)==k) for k in ('STAY','SHIFT_PREPLACE_MIGRATE')]
            forced=[solve_joint({j.uid:j},{j.uid:pair},r,g,secondary=False,force=(j.uid,k)) for k in (0,1)]
            degeneracy=dict(PASS=True,scope='SYNTHETIC_CONSTRUCTIVE_COUNTEREXAMPLE',
                rho_values=[x['passes'][0]['value'] for x in forced],actions=[o.action(j) for o in pair],
                intervention_tuples=[(int(o.migrated),abs(o.start-j.reference_start),int(o.initial_site!=j.reference_site)) for o in pair],
                secondary_selected=solve_joint({j.uid:j},{j.uid:pair},r,g)['selected'][j.uid].action(j))
            assert abs(degeneracy['rho_values'][0]-degeneracy['rho_values'][1])<1e-12
    csv('CAPABILITY_MEMBERSHIP.csv',memberships)
    csv('JOINT_OPTION_DOMAIN_AUDIT.csv',domains_audit)
    csv('OPTION_PRESCREEN_AUDIT.csv',screens)
    csv('PRESTART_PLACEMENT_AUDIT.csv',spatial)
    csv('MIGRATION_CAPABILITY_AUDIT.csv',migration)
    m=pd.DataFrame(memberships);overlaps=[]
    masks=['can_timeshift','can_prestart_place','can_checkpoint_migrate']
    for label,mask in [(n,m[n]) for n in ['temporal_candidate',*masks,'FLEX','FIX']]+[
        (name,(m[masks].to_numpy()==bits).all(axis=1)) for name,bits in
        [('TS_ONLY',(1,0,0)),('PS_ONLY',(0,1,0)),('MG_ONLY',(0,0,1)),('TS_PS',(1,1,0)),
         ('TS_MG',(1,0,1)),('PS_MG',(0,1,1)),('TS_PS_MG',(1,1,1))]]:
        overlaps.append(dict(population='SYNTHETIC_ONLY_NOT_SCIENTIFIC_SHARE',category=label,jobs=int(mask.sum()),
            job_percent=float(mask.mean()*100),GPUh=float(m.loc[mask,'full_service_GPUh'].sum()),
            GPUh_percent=float(m.loc[mask,'full_service_GPUh'].sum()/m.full_service_GPUh.sum()*100)))
    csv('CAPABILITY_OVERLAP_SUMMARY.csv',overlaps)
    dump('PRIMARY_ONLY_DEGENERACY_AUDIT.json',degeneracy)
    dump('BOUNDED_JOINT_MILP_CANARY.json',dict(PASS=True,solver='scipy.optimize.milp/HiGHS',
        scope='TEN_SMALL_SYNTHETIC_CASES',full_native_campaign=False,canaries=canaries))
    dump('SERVICE_PRESERVATION_AUDIT.json',dict(PASS=True,scope='SYNTHETIC_OPTIONS',
        options_checked=total_options,full_service_identity_violations=0,duplicate_compute=0,
        gang_splitting=0,post_H_resource_capacity_checked=True,native_service_authority_finalized=False,
        electrical_security_after_H_claimed=False))
    dump('FLEXIBILITY_CAUSALITY_AUDIT.json',dict(PASS=True,scope='INPUT_INTERFACE_PERTURBATION_AND_TRAIN_CUTOFF',
        future_field_perturbation_test='test_no_future_fields_in_input_and_causal_perturbation',
        future_leakage_count=0,train_start_labels_after_cutoff=0,May_training_records=0,
        validation_current_job_queue_reads=0,pre_submission_rejected=True,
        historical_request_version_certified=False,production_causal_certification=False,
        TRAIN_membership=record(old/'TRAIN_MEMBERSHIP.csv.gz'),preregistration=prereg))
    after={str(p):sha(p) for p in sources}
    assert before==after
    dump('INPUT_PRESERVATION.json',dict(PASS=True,files=len(before),changed=0,
        before_aggregate_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        after_aggregate_sha256=hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest()))
    dump('SOURCE_MANIFEST.json',dict(registered_input=prereg,files=[record(p) for p in sources],
        external_sources_read_only=True,semantic_ML_branch_not_imported_or_modified=True))
    print(json.dumps(dict(historical=historical,train=len(train),cohorts=len(stat),population=len(f),
        validation=int(v.sum()),rule_comparison=comparisons,canary_options=total_options,
        domain=domains_audit,protected_sources=len(before)),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    run(parser.parse_args().workspace)
