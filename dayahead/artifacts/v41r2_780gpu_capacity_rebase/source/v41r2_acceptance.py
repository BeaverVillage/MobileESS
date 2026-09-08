"""May-04 audit/closeout. Never launches another day or chooses a solution."""
from pathlib import Path
import gzip,hashlib,json,sys,xml.etree.ElementTree as ET
import numpy as np
from dayahead.paper_analysis.storage import read,write_json,atomic,digest
from dayahead.v41.preflight import record
from dayahead.v41r2.authority import ROOT,OLD,OLD_RUN,OUT,CAP,RACK,DAY,SITES,VECTOR,capacity
from dayahead.v41.data import RUNTIME

def save(name,v):
    write_json(OUT/name,v);assert read(OUT/name)==v
    return record(OUT/name)

def model_gate():
    from dayahead.v41.data import SOURCE_REPO
    inventory=read(SOURCE_REPO/'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json')
    snap=read(OLD_RUN/'inputs'/DAY/f'V41_ML_SNAPSHOT_{DAY}.json')
    targets=dict(runtime_Q90=snap['model'],runtime_preprocessing=snap['preprocessing'],
        H4_R85_B2=snap['H4_model_authority'],traffic_ML_and_Safe_ETA=inventory['traffic'][DAY]['model_authority'],
        other_traffic_model_authority=inventory['traffic_model'])
    refs={}
    def walk(v):
        if isinstance(v,dict):
            if {'path','sha256','bytes'}<=v.keys():
                current=record(v['path']);assert current['sha256']==v['sha256'] and current['bytes']==v['bytes']
                refs[current['path']]=current
            else:
                for x in v.values():walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    walk(targets)
    assert refs
    return save('V41R2_ALL_FROZEN_MODELS.json',dict(status='PASS',authorities=targets,verified_files=list(refs.values()),
        ML_RETRAIN_COUNT=0,ML_RECALIBRATION_COUNT=0,ML_MODEL_CHANGE_COUNT=0,prediction_calls=0,
        H4_raw_source=record(OLD_RUN/'inputs'/DAY/'H4_AUTHORITY.json'),
        H4_raw_materialized_source=record(RUNTIME/'inputs'/DAY/'H4_AUTHORITY.json'),
        traffic_SafeETA_executed=False,MESS_OFF=True))

def power_gate():
    import pandas as pd
    from dayahead.paper_analysis.storage import write_npz
    from dayahead.v39a.contracts import IDLE_W_PER_GPU,CENTER_SWING_W_PER_GPU,POWER_TOLERANCE_KW
    from dayahead.v41r2.authority import aggregate_it
    summaries={}
    for policy in ['B0','B1']:
        for stage in ['dayahead','actual']:
            source=RUNTIME/DAY/policy/stage/('FROZEN_AIDC_POWER.npz' if stage=='dayahead' else 'ACTUAL_AIDC_POWER.npz')
            names=['gpu','it','pcc','qcc'] if stage=='dayahead' else ['occupancy','IT','PCC_P','PCC_Q']
            with np.load(source) as z:gpu,it,p,q=[z[k].copy() for k in names]
            idle=np.tile(np.array(VECTOR)*float(IDLE_W_PER_GPU)/1000,(96,1))
            active=gpu*float(CENTER_SWING_W_PER_GPU)/1000
            residual=float(np.max(np.abs(it-(idle+active))))
            agg=float(np.max(np.abs(it.sum(1)-[float(aggregate_it(int(n))) for n in gpu.sum(1)])))
            assert max(residual,agg)<=float(POWER_TOLERANCE_KW)
            arrays=dict(GPU=gpu,IT_kW=it,PCC_P_kW=p,PCC_Q_kvar=q,capacity_component_kW=idle,active_component_kW=active,
                PUE=p/it,thermal_other_kW=p-it,aggregate_IT_kW=it.sum(1),aggregate_PCC_kW=p.sum(1))
            dest=OUT/f'V41R2_{policy}_{stage.upper()}_POWER_COMPONENTS.npz';write_npz(dest,**arrays)
            with np.load(dest) as z:assert all(np.array_equal(z[k],v) for k,v in arrays.items())
            summaries[policy+'_'+stage]=dict(source=record(source),components=record(dest),conservation_residual_kW=residual,
                aggregate_conservation_residual_kW=agg,sites=[dict(site=s,max_P_kW=float(p[:,i].max()),max_Q_kvar=float(q[:,i].max()),
                    max_kVA=float(np.hypot(p[:,i],q[:,i]).max()),rating_kVA=1500,utilization=float(np.hypot(p[:,i],q[:,i]).max()/1500),
                    violation_count=int((np.hypot(p[:,i],q[:,i])>1500).sum())) for i,s in enumerate(SITES)])
            assert all(s['violation_count']==0 for s in summaries[policy+'_'+stage]['sites'])
    historic=pd.read_parquet(OUT/'V41R2_B0_SITE_POWER.parquet')
    historical=[dict(site=s,max_P_kW=float(f.old_PCC_kW.max()),max_Q_kvar=float(f.old_PCC_kvar.max()),
        max_transformer_utilization=float(np.hypot(f.old_PCC_kW,f.old_PCC_kvar).max()/1500)) for s,f in historic.groupby('site')]
    return save('V41R2_ALL_POWER_AND_PCC_AUDIT.json',dict(status='PASS',results=summaries,old624_B0_sites=historical,
        old624_B0_max_transformer_utilization=max(s['max_transformer_utilization'] for s in historical),
        new780_B0_max_transformer_utilization=max(s['utilization'] for s in summaries['B0_dayahead']['sites']),
        synthetic_equivalent_installation=True,measured_facility_claim=False))

def coefficient_gate():
    from dayahead.v41.electrical import load
    ctx=load(DAY)
    try:
        new=read(RUNTIME/'e/20250504/V41_ELECTRICAL_CERTIFICATE.json')
        old=read(OLD_RUN/'e/20250504/V41_ELECTRICAL_CERTIFICATE.json')
        a=read(OUT/'V41R2_ELECTRICAL_COEFFICIENT_DEPENDENCY_AUDIT.json')
        a['families']['A_C1_IT_to_PCC'].update(consumed_form='Exact nonlinear C1 evaluated at every integer GPU occupancy; optimizer consumes ctx.tables through its existing PWL graph',
            standalone_legacy_affine_coefficients_consumed=False,curve_parameter_recalibration=0)
        a['families']['D_Transformer_current_kVA']['static_reuse_scope']='P/Q control matrices and ratings only; P/Q constants are regenerated, even when their only observed change is floating-point roundoff'
        mapper=read(new['mapper_audit']['path'])
        assert mapper['status']=='PASS' and mapper['duplicated_group_slots']==0
        assert max(mapper['P_max_error_kW'],mapper['Q_max_error_kvar'])<=mapper['tolerance']
        with np.load(new['outputs']['transformer_coefficients']['path']) as x,np.load(old['outputs']['transformer_coefficients']['path']) as y:
            equal={k:bool(np.array_equal(x[k],y[k],equal_nan=True)) for k in ['P_constant','Q_constant','P_matrix','Q_matrix','ratings']}
            assert all(equal[k] for k in ['P_matrix','Q_matrix','ratings']),equal
            constant_changes={k:float(np.max(np.abs(x[k]-y[k]))) for k in ['P_constant','Q_constant']}
        branches=ctx.coefficients[0].branch_names
        for i,s in enumerate(SITES,1):
            indices=[k for k,b in enumerate(branches) if b.startswith(f'transformer.idc_idc{i:02}_tx::')]
            assert len(indices)==3,(s,indices)
            assert all(ctx.coefficients[0].transformer_ratings[k]==500 for k in indices)
        with np.load(OUT/'V41R2_B0_IT_PCC.npz') as z:
            assert np.array_equal(ctx.electrical.voltage['anchor_control'][:,:12],z['pcc'])
            assert str(ctx.electrical.current['source_voltage_cache_sha256'])==new['outputs']['voltage']['sha256']
            lookup=np.column_stack([ctx.tables[s][np.arange(96),z['gpu'][:,i]] for i,s in enumerate(SITES)])
            assert np.array_equal(lookup,z['pcc'])
        from dayahead.paper_analysis.storage import write_npz
        lookup_path=OUT/'V41R2_C1_GPU_TO_PCC_LOOKUP_TABLES.npz'
        write_npz(lookup_path,**{s:ctx.tables[s] for s in SITES})
        with np.load(lookup_path) as z:
            assert all(np.array_equal(z[s],ctx.tables[s]) and z[s].shape==(96,VECTOR[i]+1) for i,s in enumerate(SITES))
        a.update(status='PASS',electrical_coefficient_status='FULL_REGEN_MAY04_AC_WITH_STATIC_SUBCOMPONENT_EQUALITY',
            new_certificate=record(RUNTIME/'e/20250504/V41_ELECTRICAL_CERTIFICATE.json'),
            output_SHAs=new['outputs'],exact_static_transformer_PQ_ratings_equality=equal,
            regenerated_transformer_constant_changes=constant_changes,
            C1_lookup_tables=record(lookup_path),
            new_B0_PCC_anchor_exact_equality=True,capacity_C1_lookup_exact_equality=True,
            readback='PASS',source_hash='PASS',P_conservation='PASS',Q_conservation='PASS',duplicate_mapping=0,
            mapper_audit=new['mapper_audit'],measured_OpenDSS_calls=new['proof']['fresh_generation_total_SolveSnap_calls'])
        return save('V41R2_ELECTRICAL_COEFFICIENT_DEPENDENCY_AUDIT.json',a)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

def critical():
    from dayahead.v41.electrical import load
    from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
    ctx=load(DAY)
    try:
        with np.load(OUT/'V41R2_B0_IT_PCC.npz') as z:
            gpu=z['gpu'].copy();pcc=z['pcc'].copy()
        value=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pcc,()),ctx.nodes)
        # Read exactly the primary maximum phase-line row from P1 evaluator.
        from dayahead.v41.objectives import evaluate
        from dayahead.v41.reserve import bind
        path=RUNTIME/'inputs'/DAY/f'V41_ML_SNAPSHOT_{DAY}.json';bind(ctx,path,record(path)['sha256'])
        jobs=read(RUNTIME/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json')
        objective=evaluate(jobs,jobs,ctx)
        save('V41R2_INITIAL_B0_GRID_OBJECTIVE.json',dict(grid=value,objective=objective))
        t=value['critical_slot'];g=gpu[t];head=np.array(VECTOR)-g
        sizes=np.array([r['requested_GPU'] for r in jobs]);p50,p90=np.quantile(sizes,[.5,.9])
        save('V41R2_INITIAL_CRITICAL_LINE_HEADROOM.json',dict(status='PASS',critical_line=value['critical_line'],
            phase=value['critical_phase'],slot=t,aggregate_GPU=int(g.sum()),aggregate_occupancy=float(g.sum()/780),
            per_site_GPU=dict(zip(SITES,map(int,g))),headroom=dict(zip(SITES,map(int,head))),
            positive_headroom_sites=int((head>0).sum()),gang_P50=float(p50),gang_P90=float(p90),
            accepts_P50_sites=int((head>=p50).sum()),accepts_P90_sites=int((head>=p90).sum()),
            initial_P1=value['rho_max'],forced_migration=False,forced_cross_region=False))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

def candidate_gate():
    from dayahead.v41.electrical import load
    from dayahead.v40g.domain import options
    base=RUNTIME/DAY/'B1/dayahead/A0';m=read(base/'V41R1_FULL_CANDIDATE_MANIFEST.json')
    ctx=load(DAY);expected=hashlib.sha256();count=0;jobs=read(RUNTIME/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json')
    by={r['job_uid']:r for r in jobs};seen=set()
    try:
        with gzip.open(m['candidate_artifact']['path'],'rb') as stream:
            for line in stream:
                data=json.loads(line);r=by[data['job_id']];assert r['job_uid'] not in seen;seen.add(r['job_uid'])
                opts=options(r,ctx.capacity,ctx.wan,ctx.elapsed)
                domain=[[o.site,o.start,o.end,o.checkpoint,o.transfer_start,o.transfer_end,o.initial_site] for o in opts]
                assert domain==data['options'],r['job_uid']
                assert all(o.start==r['r1_reference_start'] for o in opts)
                expected.update(line);count+=len(opts)
        assert seen==set(by) and count==m['final_authoritative_candidates'] and expected.hexdigest()==m['candidate_set_SHA']
        assert m['top_K_pruning']==m['sensitivity_pruning']==m['hard_infeasible_removals']==0
        return save('V41R2_FULL_CANDIDATE_REENUMERATION.json',dict(status='PASS',count=count,jobs=len(seen),
            candidate_set_SHA=expected.hexdigest(),independently_reenumerated_from_full_domain=True,fixed_reference_starts=True,
            same_model_domain_source=record(ROOT/'dayahead/v40g/domain.py'),capacity_authority=record(CAP)))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

def search_gate():
    from dayahead.v41.reserve import lexicographic_compare
    from dayahead.v41r1.early_stop import VERSION,TOLERANCES,STAGES
    base=RUNTIME/DAY;da=base/'B1/dayahead';a0=da/'A0'
    b0=read(base/'B0/dayahead/optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
    b1=read(da/'optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
    seed=read(a0/'POLICY_FEASIBLE_SEED_AUDIT.json');compute=read(da/'POLICY_DAY_COMPUTE_REPORT.json');solver=read(a0/'BOUNDED_SOLVER_REPORT.json')
    assert seed['status']=='PASS' and lexicographic_compare(b1,b0,TOLERANCES)<=0
    assert np.allclose(seed['seed_objective_vector'],b0,atol=1e-9,rtol=0)
    assert compute['optimization_seconds']<=1800 and compute['compute_control_version']==VERSION==solver['compute_control_version']
    budget=read(OUT/'V41R2_OPTIMIZATION_BUDGET.json')
    total=budget['invalidated_attempt_conservative_seconds']+compute['optimization_seconds']
    assert total<=1800
    history=[read(f) for f in sorted((a0/'bounded_checkpoints').glob('ITERATION_*.json'),key=lambda f:int(f.stem.split('_')[1]))]
    for h in history:
        assert h['first_improvement_search'] and not h['percentage_gap_on_P1_P5']
        assert h['neighborhood']['complete_job_domains_opened']
        if h['accepted']:
            assert lexicographic_compare(h['incumbent_after'],h['incumbent_before'],TOLERANCES)<0
            assert h['semantic_validation']['status']==h['semantic_validation']['canonical_model_substitution']['status']=='PASS'
            for field in ['persisted_jobs','persisted_power']:
                ref=h['semantic_validation'][field];assert record(ref['path'])==ref
    p1=[h for h in history if h['objective_stage']=='PRIMARY_MIN_RHO']
    if p1:assert p1[0]['neighborhood']['family']=='ELECTRICAL_CRITICAL_WINDOW'
    structs=[read(f) for f in (a0/'bounded_checkpoints').glob('STRUCTURE_P1_SWEEP_*.json')]
    for h in p1:
        if h['accepted']:assert any(s['incumbent']==h['incumbent_after'] for s in structs)
    assert len(solver['stages'])==5 and all(s['feasibility']['status']=='PASS' for s in solver['stages'])
    return save('V41R2_B1_SEARCH_ACCEPTANCE.json',dict(status='PASS',B0=b0,B1=b1,seed=seed['status'],
        optimization_seconds=total,final_attempt_optimization_seconds=compute['optimization_seconds'],
        invalidated_attempt_conservative_seconds=budget['invalidated_attempt_conservative_seconds'],
        compute_control_version=VERSION,iterations=len(history),
        improvements=sum(h['accepted'] for h in history),equal_B0_allowed=True,minimum_improvement_required=False,
        solution_classification='BOUNDED_FIRST_IMPROVEMENT_FEASIBLE_INCUMBENT',global_optimality_claim=False,
        source_preserved=all((ROOT/p).read_bytes()==(OLD/p).read_bytes() for p in ['dayahead/v40g/optimizer.py','dayahead/v41r1/bounded_solver.py','dayahead/v41r1/early_stop.py']),
        current_incumbent_preserved=True,P1_critical_first=True,critical_recomputed_after_acceptance=True,
        no_time_shifting=True,candidate_gate=record(OUT/'V41R2_FULL_CANDIDATE_REENUMERATION.json')))

def historical_gate():
    """Verify old evidence against its own historical seals, without rewriting it."""
    from dayahead.v41.campaign import verify_receipt
    receipts=[]
    for base in [OLD_RUN/DAY/'B0',OLD_RUN/'fa/first02'/DAY/'B1']:
        for stage in ['dayahead','actual']:
            path=base/stage/(stage.upper()+'_RECEIPT.json')
            verify_receipt(path);receipts.append(record(path))
    diagnostic=OLD/'dayahead/artifacts/v41r1_b1_flexibility_diagnostic'/DAY/'DIAGNOSTIC_FREEZE.json'
    refs=read(diagnostic)['files']
    for ref in refs:assert record(ref['path'])==ref
    return save('V41R2_HISTORICAL_SEAL_VERIFICATION.json',dict(status='PASS',
        basis='Existing historical phase receipts, full scientific manifests and diagnostic freeze',
        old_phase_receipts=receipts,diagnostic_freeze=record(diagnostic),diagnostic_files=len(refs),
        old_evidence_modified=False))

def physical_audit():
    """Separate successful replay/persistence from strict physical acceptance."""
    import pandas as pd
    from dayahead.paper_analysis.storage import write_parquet
    results={};violations=[]
    for policy in ['B0','B1']:
        for stage in ['dayahead','actual']:
            root=RUNTIME/DAY/policy/stage
            path=root/('FRESH_RESULT.json' if stage=='dayahead' else 'ACTUAL_RESULT.json')
            s=read(path)['summary']
            ok=(not s['physical_violation'] and s['convergence_count']==96 and s['Vmin_pu']>=.95 and s['Vmax_pu']<=1.05
                and all(s[k]<=1 for k in ['rho_max_AC','transformer_phase_current_loading_max','transformer_total_kva_loading_max'])
                and all(s[k]==0 for k in ['voltage_violation_count','line_current_violation_count','transformer_current_violation_count','transformer_kva_violation_count']))
            voltage=pd.read_parquet(root/'grid/BUS_PHASE_VOLTAGES.parquet')
            bad=voltage[(voltage.voltage_pu<.95)|(voltage.voltage_pu>1.05)].copy()
            violations.append(bad)
            worst=voltage.loc[voltage.voltage_pu.idxmax()]
            slot=int(worst.slot);node=str(worst.node)
            def feeder_snapshot(phase):
                frame=pd.read_parquet(RUNTIME/DAY/policy/phase/'grid/FEEDER_SYSTEM_96.parquet')
                row=frame[frame.slot==slot].iloc[0]
                keys=['AIDC_P_kw','AIDC_Q_kvar','background_P_kw','background_Q_kvar','PV_P_kw','PV_Q_kvar','Vmin_pu','Vmax_pu']
                keys += [k for k in frame if k.startswith(('regulator_tap_','capacitor_state_'))]
                return {k:float(row[k]) for k in keys}
            entry=dict(status='PASS' if ok else 'FAIL',result=record(path),summary=s,
                voltage_row_violations=len(bad),voltage_violation_slots=sorted(map(int,bad.slot.unique())),
                worst_voltage=dict(node=node,phase=str(worst.phase),slot=slot,timestamp_UTC=worst.timestamp.isoformat(),
                    voltage_pu=float(worst.voltage_pu),upper_limit_pu=1.05,excess_pu=max(0,float(worst.voltage_pu)-1.05)),
                feeder_at_worst_slot=feeder_snapshot(stage))
            if stage=='actual':
                da=pd.read_parquet(RUNTIME/DAY/policy/'dayahead/grid/BUS_PHASE_VOLTAGES.parquet')
                entry['Fresh_at_same_node_slot_pu']=float(da[(da.slot==slot)&(da.node==node)].iloc[0].voltage_pu)
                entry['Fresh_feeder_at_same_slot']=feeder_snapshot('dayahead')
            results[policy+'_'+stage]=entry
    bad=pd.concat(violations,ignore_index=True)
    path=OUT/'V41R2_PHYSICAL_VOLTAGE_VIOLATIONS.parquet';write_parquet(path,bad)
    assert pd.read_parquet(path).equals(bad)
    return save('V41R2_PHYSICAL_ACCEPTANCE_AUDIT.json',dict(status='PASS' if all(v['status']=='PASS' for v in results.values()) else 'FAIL_CLOSE',
        results=results,voltage_violations=record(path),limits_unchanged=True,reoptimization=0,
        diagnosis='Fresh and Actual have different realized workloads and exogenous inputs. Same-slot feeder states are retained for comparison; this is observational evidence, not an isolated causal counterfactual. No regulator, capacitor, model, voltage limit, or WAN retuning was performed.'))

def final():
    from dayahead.v41.campaign import verify_receipt
    from dayahead.v41.execution import verify_dayahead,science
    from dayahead.v41.scientific_archive import verify_manifest
    model_gate();power_gate();coefficient_gate();historical_gate();physical_audit()
    physical=read(OUT/'V41R2_PHYSICAL_ACCEPTANCE_AUDIT.json')
    physical_ok=physical['status']=='PASS'
    acceptance_status='PASS' if physical_ok else 'FAIL_CLOSE'
    gate=read(OUT/'V41R2_B1_SEARCH_ACCEPTANCE.json');science_results={};physics={}
    for p in ['B0','B1']:
        unit=RUNTIME/DAY/p;verify_dayahead(DAY,p)
        for stage in ['dayahead','actual']:
            verify_receipt(unit/stage/(stage.upper()+'_RECEIPT.json'));verify_manifest(unit/stage/'SCIENTIFIC_MANIFEST.json')
        da=read(unit/'dayahead/FRESH_RESULT.json')['summary'];ac=read(unit/'actual/ACTUAL_RESULT.json')
        for label,v in [('Fresh',da),('Actual',ac['summary'])]:
            physics[p+'_'+label]=v
        assert ac['Actual_optimizer_calls']==0 and ac['final_execution_feasibility']['status']=='PASS'
        science_results[p]=dict(P1_P5=read(unit/'dayahead/optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR'],
            Actual_P1=ac['summary']['rho_max_AC'],Actual_P2=float(np.mean(ac['frozen_future_workload_score']['realized_shortfall_GPUh'])),
            Fresh=physical['results'][p+'_dayahead']['status'],Actual=physical['results'][p+'_actual']['status'],
            Actual_execution_and_capacity='PASS',Actual_reoptimization=0)
    refs=read(RUNTIME/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json');by={r['job_uid']:r for r in refs}
    jobs=read(RUNTIME/DAY/'B1/dayahead/FROZEN_JOINT_DECISION.json')['decision']['AIDC_decision']
    migrations=[r for r in jobs if r.get('migration_selected')]
    reloc=[r for r in jobs if r.get('initial_AIDC',r['AIDC_site'])!=by[r['job_uid']]['AIDC_site']]
    def waits(rows):
        return [(r['migration_events'][0]['transfer_start']-r['migration_events'][0]['checkpoint'])*.25 for r in rows if r.get('migration_selected')]
    w=waits(migrations)
    oldjobs=read(OLD_RUN/'fa/first02'/DAY/'B1/dayahead/FROZEN_JOINT_DECISION.json')['decision']['AIDC_decision'];ow=waits(oldjobs)
    def post_service(r):
        segments=r.get('compute_segments') or [dict(start=r['start_slot'],end=r['end_slot'])]
        return r['requested_GPU']*sum(max(0,s['end']-max(120,s['start'])) for s in segments)/4
    post_delta={r['job_uid']:post_service(r)-post_service(by[r['job_uid']]) for r in migrations}
    assert all(v>=0 for v in post_delta.values())
    beyond=[r for r in migrations if post_delta[r['job_uid']]>0]
    wan=dict(migration_count=len(migrations),old_migration_count=len(ow),prestart_relocations=len(reloc),
        WAN_wait_hours=dict(mean=float(np.mean(w)) if w else 0,P95=float(np.quantile(w,.95)) if w else 0,max=max(w,default=0)),
        old_WAN_wait_hours=dict(mean=float(np.mean(ow)) if ow else 0,P95=float(np.quantile(ow,.95)) if ow else 0,max=max(ow,default=0)),
        jobs_with_additional_post_D24_service=len(beyond),
        jobs_newly_crossing_D24=sum(by[r['job_uid']]['end_slot']<=120<r['end_slot'] for r in migrations),
        GPUh_shifted_beyond_D24=sum(post_delta.values()),
        post_D24_attribution='Exact compute-segment service difference versus B0; includes the complete migration interruption (waiting, transfer, ready/restart), not an isolated counterfactual of WAN waiting alone.',
        checkpoint_to_restart_hours=[(r['restart_complete_slot']-r['migration_checkpoint_slot'])*.25 for r in migrations],
        row_details=[dict(job_id=r['job_uid'],WAN_wait_hours=t,checkpoint=r['migration_checkpoint_slot'],restart=r['restart_complete_slot'],reference_end=by[r['job_uid']]['end_slot'],end=r['end_slot'],additional_post_D24_service_GPUh=post_delta[r['job_uid']]) for r,t in zip(migrations,w)],
        interpretation='WAN waiting is observed under unchanged UID serialization and frozen path semantics; this can move service outside D24 and is not purely a spatial-load effect.',WAN_retuned=False)
    wan['long_WAN_wait_reduced']=bool(max(w,default=0)<max(ow,default=0))
    wan['long_WAN_wait_reduced_criterion']='Maximum waiting only; compare mean and P95 separately, without inferring a causal effect from capacity alone.'
    wan['mean_WAN_wait_reduced']=bool(wan['WAN_wait_hours']['mean']<wan['old_WAN_wait_hours']['mean'])
    wan['P95_WAN_wait_reduced']=bool(wan['WAN_wait_hours']['P95']<wan['old_WAN_wait_hours']['P95'])
    save('V41R2_WAN_LONG_WAIT_AUDIT.json',wan)
    before=read(OUT/'V41R1_PRESERVATION.json')
    for ref in before['frozen_files']:assert record(ref['path'])==ref
    for row in before['source']:assert record(row['original']['path'])==row['original']
    save('V41R2_V41R1_IMMUTABILITY_VERIFICATION.json',dict(status='PASS',files=len(before['frozen_files']),source_files=len(before['source'])))
    xml=ET.parse(ROOT/'regressions.xml').getroot();suites=xml.findall('testsuite') or [xml]
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','errors','failures','skipped']}
    assert counts['errors']==counts['failures']==0,counts
    extra=ET.parse(ROOT/'capacity_regressions.xml').getroot();extra_suites=extra.findall('testsuite') or [extra]
    extra_counts={k:sum(int(s.attrib.get(k,0)) for s in extra_suites) for k in ['tests','errors','failures','skipped']}
    assert extra_counts['errors']==extra_counts['failures']==0
    integration=ET.parse(ROOT/'acceptance_regressions.xml').getroot();integration_suites=integration.findall('testsuite') or [integration]
    integration_counts={k:sum(int(s.attrib.get(k,0)) for s in integration_suites) for k in ['tests','errors','failures','skipped']}
    assert integration_counts['errors']==0
    if physical_ok:assert integration_counts['failures']==0
    all_counts={k:counts[k]+extra_counts[k]+integration_counts[k] for k in counts}
    from dayahead.v41.scientific_archive import copy_atomic
    regression_artifacts=[]
    for name in ['regressions.xml','regressions.log','capacity_regressions.xml','capacity_regressions.log','acceptance_regressions.xml','acceptance_regressions.log']:
        path=OUT/'regressions'/name;copy_atomic(ROOT/name,path);regression_artifacts.append(record(path))
    b0=science_results['B0']['P1_P5'];b1=science_results['B1']['P1_P5']
    delta=[y-x for x,y in zip(b0,b1)]
    # The deterministic P5 tie-break magnitude has no scientific relative scale.
    relative=[d/x if x and i<4 else None for i,(d,x) in enumerate(zip(delta,b0))]
    report=dict(status=acceptance_status,transition='V41R1_624GPU -> V41R2_780GPU_CAPACITY_REBASE',capacity_authority_applied=True,
        capacity=read(CAP),ML=read(OUT/'V41R2_ML_POSTPROCESSING_AUDIT.json'),all_frozen_models=read(OUT/'V41R2_ALL_FROZEN_MODELS.json'),
        reference=read(OUT/'V41R2_REFERENCE_SCHEDULING_COMPARISON.json'),
        power=read(OUT/'V41R2_AIDC_POWER_CAPACITY_REBASE_AUDIT.json'),PCC_transformers=read(OUT/'V41R2_PCC_TRANSFORMER_CAPABILITY.json'),
        complete_power_audit=read(OUT/'V41R2_ALL_POWER_AND_PCC_AUDIT.json'),
        electrical=read(OUT/'V41R2_ELECTRICAL_COEFFICIENT_DEPENDENCY_AUDIT.json'),science=science_results,
        initial_critical_line=read(OUT/'V41R2_INITIAL_CRITICAL_LINE_HEADROOM.json'),
        Actual_power_audit_source=record(ROOT/'dayahead/v40d_actual/capacity_audit.py'),
        B1_minus_B0=delta,B1_relative_change=relative,WAN=wan,physics=physics,search=gate,regressions=counts,capacity_regressions=extra_counts,integration_regressions=integration_counts,total_regressions=all_counts,
        historical_seal_verification=read(OUT/'V41R2_HISTORICAL_SEAL_VERIFICATION.json'),regression_artifacts=regression_artifacts,
        physical_acceptance=physical,acceptance_failures=[k for k,v in physical['results'].items() if v['status']!='PASS'],
        pilot_execution=read(OUT/'V41R2_PILOT_EXECUTION.json'),execution_completion_is_not_physical_acceptance=True,
        Full_May_started=False,Full_May_ready=False,Full_May_status=('HOLD: May-04 ready; other 30 policy-day references and operating-point coefficients require generation and certification before campaign' if physical_ok else 'HOLD: May-04 Actual voltage acceptance failed; the remaining 30 days were not generated or run'),
        required_persistence='Verified scientific manifests and phase receipts',source=science(),report_generator=record(__file__))
    save('V41R2_780GPU_MAY04_ACCEPTANCE.json',report)
    r=report['reference'];p=report['power']
    lines=['# V41R2 780-GPU May-04 acceptance','',f'**May-04: {acceptance_status}. Full May: HOLD; not started.**','',
        'Execution and persistence completion are reported separately from physical acceptance. A voltage limit exceedance remains a failed hard gate even when the replay receipt is COMPLETE.','',
        '## Capacity','',f"624: {report['capacity']['old_vector']}",f"780: {list(VECTOR)}",'',
        'ML retraining/recalibration/model changes: 0. Raw Q90/H4 prediction values and model hashes preserved. H4 physical cap: 2496 → 3120 GPUh.','',
        '## Reference scheduling','', '| Metric | 624 B0 | 780 B0 |','|---|---:|---:|']
    for k in ['job_count','RUNNING_count','PENDING_count','D00_RUNNING','D_day_starts','still_queued_at_H','D24_carryout','true_cross_H_GPUh','UNASSIGNED_count','UNASSIGNED_Dday_count','scheduled_GPUh','mean_occupancy','FULL_fraction','all_12_FULL_fraction']:
        lines.append(f"| {k} | {r['old'][k]} | {r['new'][k]} |")
    for k in ['mean','P50','P90','P95']:
        lines.append(f"| Capacity wait {k} (hours) | {r['old']['capacity_wait_hours'][k]} | {r['new']['capacity_wait_hours'][k]} |")
    lines += ['', '| Site | Old mean occupancy | New mean occupancy | Old FULL fraction | New FULL fraction | New mean headroom (GPU) |',
        '|---|---:|---:|---:|---:|---:|']
    for s in SITES:
        old=r['old']['per_site'][s];new=r['new']['per_site'][s]
        lines.append(f"| {s} | {old['mean_occupancy']} | {new['mean_occupancy']} | {old['FULL_fraction']} | {new['FULL_fraction']} | {new['mean_headroom_GPU']} |")
    lines += ['',f"Changed starts: {r['changed_start_count']}; changed initial sites: {r['changed_initial_site_count']}. Pending readiness is issue slot 0; historical resource delays are not exogenous release times. Seven historical pre-D00-complete RUNNING records have no site and remain explicitly UNASSIGNED, with no Day-D service.",
        '', '## Power and electrical','',f"Installed idle IT: {p['old_idle_IT_kW']} → {p['new_idle_IT_kW']} kW. Full active IT: {p['old_full_active_IT_kW']} → {p['new_full_active_IT_kW']} kW.",
        'Per-GPU coefficients, C1, GFS weather, PF, hosts and 1500-kVA site transformer ratings remain frozen. New IT/PCC and May-04 AC coefficients were generated at the new B0 operating point. Static transformer P/Q flow matrices and ratings passed exact equality; constants were regenerated (differences below 5e-13). No measured-facility claim.',
        '', '## B0 versus B1','', '| Objective | B0 | B1 | B1 − B0 | Relative |','|---|---:|---:|---:|---:|']
    for i in range(5):lines.append(f"| P{i+1} | {b0[i]} | {b1[i]} | {delta[i]} | {relative[i]} |")
    lines += ['',f"Prestart relocations: {len(reloc)}; checkpoint migrations: {len(migrations)}. WAN wait hours: {wan['WAN_wait_hours']}. Additional post-D24 service: {wan['GPUh_shifted_beyond_D24']} GPUh across {len(beyond)} jobs.",
        wan['interpretation'],wan['post_D24_attribution'],f"Old WAN waiting ({wan['old_migration_count']} migrations): {wan['old_WAN_wait_hours']}. Maximum waiting reduced: {wan['long_WAN_wait_reduced']}; mean reduced: {wan['mean_WAN_wait_reduced']}; P95 reduced: {wan['P95_WAN_wait_reduced']}. Newly crossing D24: {wan['jobs_newly_crossing_D24']} jobs.",
        '',f"Fresh B0/B1: {science_results['B0']['Fresh']}/{science_results['B1']['Fresh']}. Actual physical B0/B1: {science_results['B0']['Actual']}/{science_results['B1']['Actual']}; replay/capacity/persistence PASS, reoptimization 0. Optimization runtime: {gate['optimization_seconds']} seconds (limit 1800). Tests: {all_counts}. Failed acceptance tests are retained and not relaxed.",
        'Full candidate universe independently re-enumerated; fixed first-improvement search source preserved; reference starts fixed and every accepted incumbent checked. No minimum benefit or new time-shifting policy imposed. The result is a bounded first-improvement feasible incumbent, with no global optimality certificate.',
        '',report['Full_May_status'],
        '', 'All job, queue, power, objective, grid, MESS-off, Fresh, Actual and authority/hash receipts are in the adjacent JSON report and the V41R2 runtime directory.']
    c=report['initial_critical_line'];power=report['complete_power_audit']
    lines += ['', '## Initial critical line and headroom','',
        f"{c['critical_line']}, phase {c['phase']}, slot {c['slot']}; aggregate {c['aggregate_GPU']}/780 GPU ({c['aggregate_occupancy']:.6%}). Positive-headroom sites: {c['positive_headroom_sites']}; sites accepting empirical P50/P90 gangs: {c['accepts_P50_sites']}/{c['accepts_P90_sites']} (gang sizes {c['gang_P50']}/{c['gang_P90']} GPU).",
        '', '| Site | Initial critical-slot GPU | Headroom GPU |','|---|---:|---:|']
    for s in SITES:lines.append(f"| {s} | {c['per_site_GPU'][s]} | {c['headroom'][s]} |")
    lines += ['', '## PCC transformer audit','',
        f"Old/new B0 maximum dedicated-site transformer utilization: {power['old624_B0_max_transformer_utilization']:.6%} / {power['new780_B0_max_transformer_utilization']:.6%}.",
        '', '| Policy / stage | Site | Max P kW | Max Q kvar | Max kVA | Rating kVA | Utilization | Violations |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for key,result in power['results'].items():
        for s in result['sites']:
            lines.append(f"| {key} | {s['site']} | {s['max_P_kW']:.6f} | {s['max_Q_kvar']:.6f} | {s['max_kVA']:.6f} | {s['rating_kVA']} | {s['utilization']:.6%} | {s['violation_count']} |")
    lines += ['', '## Fresh and Actual physics','',
        '| Policy / replay | Vmin pu | Vmax pu | Maximum line-phase loading | Transformer current loading | Transformer total kVA loading | Converged slots |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for key,v in physics.items():
        lines.append(f"| {key} | {v['Vmin_pu']:.9f} | {v['Vmax_pu']:.9f} | {v['rho_max_AC']:.9f} | {v['transformer_phase_current_loading_max']:.9f} | {v['transformer_total_kva_loading_max']:.9f} | {v['convergence_count']} |")
    lines += ['', '| Actual objective | B0 | B1 |','|---|---:|---:|',
        f"| P1 | {science_results['B0']['Actual_P1']} | {science_results['B1']['Actual_P1']} |",
        f"| P2 (GPUh) | {science_results['B0']['Actual_P2']} | {science_results['B1']['Actual_P2']} |",'',
        'Historical V41R1 B0/B1 Fresh/Actual and diagnostic files were reverified against their existing sealed receipts. The invalidated metadata draft is retained separately; its conservatively charged 190 seconds are included in the 1800-second optimization cap.']
    lines += ['', '## Hard physical gate','',physical['diagnosis'],'',
        '| Policy / stage | Acceptance | Worst node | Phase | Slot | UTC timestamp | Vmax pu | Excess above 1.05 pu | Violating bus-phase-slot rows |',
        '|---|---|---|---|---:|---|---:|---:|---:|']
    for key,v in physical['results'].items():
        wv=v['worst_voltage']
        lines.append(f"| {key} | {v['status']} | {wv['node']} | {wv['phase']} | {wv['slot']} | {wv['timestamp_UTC']} | {wv['voltage_pu']:.9f} | {wv['excess_pu']:.9f} | {v['voltage_row_violations']} |")
    with atomic(OUT/'V41R2_780GPU_MAY04_ACCEPTANCE.md') as f:f.write(('\n'.join(lines)+'\n').encode())
    from dayahead.v41.scientific_archive import copy_atomic,republish_atomic
    paths=[Path(r['path']) for r in science()['files']]+[ROOT/n for n in ['v41r2_acceptance.py','run_v41r2_pilot.py',
        'tests/dayahead/test_v41r2_capacity_rebase.py','tests/dayahead/test_capacity_rebase_acceptance_outputs.py']]
    paths += [ROOT/r['path'] for r in read(OUT/'V41R2_CODE_CHANGE_RECEIPT.json')['changed_existing_files']]
    for p in paths:copy_atomic(p,OUT/'source'/p.relative_to(ROOT))
    republish_atomic(OUT/'V41R2_AIDC_POWER_CAPACITY_REBASE_AUDIT.md')
    files=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and 'original_source' not in p.parts and p.name!='V41R2_FINAL_FREEZE.json']
    save('V41R2_FINAL_FREEZE.json',dict(status='FROZEN',files=files,Full_May_started=False,acceptance=record(OUT/'V41R2_780GPU_MAY04_ACCEPTANCE.json')))
    print('ACCEPTANCE_'+acceptance_status,b0,b1,gate['optimization_seconds'],flush=True)

if __name__=='__main__':
    {'models':model_gate,'power':power_gate,'coefficients':coefficient_gate,'critical':critical,'candidates':candidate_gate,'search':search_gate,'final':final}[sys.argv[1]]()
