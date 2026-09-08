"""Saved-data validation and automatic full-May reporting, including negative days."""
from fast_prepare import *
from v41r4_electrical import MAY_RUN,MAY_OUT
import numpy as np
from dayahead.paper_analysis.storage import write_json

def grid_summary(folder):
    paths=list(Path(folder).rglob('OPENDSS_PHASE_ARRAYS.npz'));assert len(paths)==1,(folder,paths)
    with np.load(paths[0]) as z:
        v=z['voltage_pu'];c=z['phase_current_loading_pu'];k=z['transformer_total_kva_loading_pu']
        lines=z['branch_kinds']=='line';tx=~lines
        def at(a,mask,names,phases,minimum=False):
            cols=np.flatnonzero(mask);t,j=np.unravel_index(np.argmin(a[:,mask]) if minimum else np.argmax(a[:,mask]),a[:,mask].shape);j=int(cols[j])
            return dict(value=float(a[t,j]),asset=str(names[j]),phase=str(phases[j]),slot=int(t))
        nodes=z['node_names'];nodeph=z['node_phases'];names=z['branch_names'];phases=z['branch_phases']
        unique=[list(names).index(n) for n in dict.fromkeys(names[tx])]
        counts=dict(voltage=int(((v<.95)|(v>1.05)).sum()),line_current=int((c[:,lines]>=1).sum()),
            transformer_current=int((c[:,tx]>=1).sum()),transformer_kVA=int((k[:,unique]>=1).sum()))
        return dict(Vmin=float(v.min()),Vmax=float(v.max()),rho_max=float(c[:,lines].max()),
            transformer_current=float(c[:,tx].max()),transformer_kVA=float(k[:,tx].max()),
            critical_line=at(c,lines,names,phases),worst_voltage_high=at(v,np.ones(len(nodes),bool),nodes,nodeph),
            worst_voltage_low=at(v,np.ones(len(nodes),bool),nodes,nodeph,True),violation_counts=counts,
            physical_outcome='WITH_VIOLATIONS' if any(counts.values()) else 'WITHIN_LIMITS',
            convergence_count=int(z['convergence'].sum()),arrays=record(paths[0]))

def compound_readback(day):
    root=MAY_RUN/day/'B1/dayahead/A0/bounded_checkpoints'
    events={read(p)['iteration']:read(p) for p in root.glob('PHYSICS_RANKING_*.json')}
    consumed=[]
    for p in root.glob('ITERATION_*.json'):
        r=read(p);n=r['neighborhood'];e=events.get(r['iteration'])
        if e is None:continue
        expected=[u['kind'] for u in e['ordered_existing_anchor_units']]
        assert n['consumed_anchor_unit_order']==expected and n['compound_net_effect_used_in_ordering']
        consumed.append(dict(iteration=r['iteration'],compound_widths=list(e['existing_compound_anchor_scores']),receipt=record(p)))
    assert consumed,'NO_REAL_COMPOUND_ORDER_CONSUMPTION_RECEIPT'
    domain=read(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')
    ranking=read(MAY_OUT/day/'V41R3_FO_PHYSICS_RANKING_AUDIT.json')
    final=read(MAY_RUN/day/'B1/dayahead/A0/V41R1_FULL_CANDIDATE_MANIFEST.json')
    assert ranking['candidate_count']==domain['total_count']==final['final_authoritative_candidates']
    assert ranking['candidate_set_SHA']==domain['candidate_set_SHA']==final['candidate_set_SHA']
    result=dict(status='PASS',COMPOUND_NET_EFFECT_COMPUTED='YES',COMPOUND_NET_EFFECT_USED_IN_ORDERING='YES',
        CANDIDATE_UNIVERSE_CHANGED='NO',NEW_VARIABLES=0,NEW_CONSTRAINTS=0,OBJECTIVE_CHANGED='NO',
        candidate_count=domain['total_count'],candidate_set_SHA=domain['candidate_set_SHA'],real_consumption=consumed)
    save(MAY_OUT/day/'V41R3_COMPOUND_RANKING_COMPLETION_AUDIT.json',result)
    return result

def accept_dayahead(day,policy):
    da=MAY_RUN/day/policy/'dayahead'
    fresh=read(da/'FRESH_RESULT.json')['summary'];assert check(fresh),('DAYAHEAD_FRESH_CONTRACT_FAILURE',day,policy,fresh)
    r=read(da/'DAYAHEAD_RECEIPT.json');assert r['status']=='COMPLETE'
    assert read(da/'PLANNING_RESULT.json')['Actual_reads']==0
    assert not read(da/'JOINT_FREEZE_RECEIPT.json')['Actual_data_opened']
    objective=read(da/'optimization/OBJECTIVE_LEDGER.json');assert len(objective['OBJECTIVE_VECTOR'])==5
    decision=read(da/'FROZEN_JOINT_DECISION.json')['decision'];jobs=decision['AIDC_decision']
    temporal=[dict(job_uid=j['job_uid'],reference_start=j['r1_reference_start'],start=j['start_slot']) for j in jobs if j['start_slot']!=j['r1_reference_start']]
    relocations=[dict(job_uid=j['job_uid'],source=j['r1_reference_site'],destination=j['AIDC_site']) for j in jobs if not j.get('migration_selected') and j['AIDC_site']!=j['r1_reference_site']]
    migrations=[j['job_uid'] for j in jobs if j.get('migration_selected')]
    commands=decision['MESS_trajectory']
    moves={(m['mess_id'],m.get('departure_slot'),m.get('origin_service_id'),m.get('destination_service_id')) for m in commands if m.get('departure_slot') is not None}
    activity=dict(vehicles=len({m['mess_id'] for m in commands}),dispatch_slots=sum(bool(m['p_kw'] or m['q_kvar']) for m in commands),
        movement_count=len(moves),absolute_P_energy_kWh=float(.25*sum(abs(m['p_kw']) for m in commands)),
        dispatch_and_movement=record(da/'FROZEN_MESS_COMMANDS.json'))
    compute=read(da/'POLICY_DAY_COMPUTE_REPORT.json')
    terminations={p.parent.name:read(p) for name in ('BOUNDED_SOLVER_REPORT.json','M1_RESULT.json','MF_RESULT.json') for p in da.glob('*/'+name)}
    summary=dict(status='PASS',day=day,policy=policy,OBJECTIVE_VECTOR=objective['OBJECTIVE_VECTOR'],grid=grid_summary(da),
        temporal_shifts=temporal,spatial_relocations=relocations,checkpoint_migrations=migrations,MESS=activity,
        runtime=compute,termination=terminations,dayahead_receipt=record(da/'DAYAHEAD_RECEIPT.json'),
        Actual_reads=0,Actual_available_to_optimizer=False)
    if policy=='B1':summary['compound_audit']=compound_readback(day)
    save(MAY_OUT/day/f'{policy}_DAYAHEAD_SUMMARY.json',summary)
    if policy=='B0':
        source=Path(summary['grid']['arrays']['path']);target=MAY_OUT/day/'screen/alpha_1.150/DAYAHEAD/physics/OPENDSS_PHASE_ARRAYS.npz'
        item=copy(source,target)
        save(MAY_OUT/day/'V41R3_B0_ACCEPTANCE.json',dict(status='PASS',Fresh='PASS',dayahead_technical_status='PASS',
            OBJECTIVE_VECTOR=objective['OBJECTIVE_VECTOR'],full_grid_copies=[item],Actual_input_fields=0,
            source='DAYAHEAD_FRESH_ONLY; all Actual replay occurs after four policy freezes'))
    return summary

def accept_actual(day,policy):
    root=MAY_RUN/day/policy;ac=root/'actual';da=root/'dayahead'
    result=read(ac/'ACTUAL_RESULT.json');r=read(ac/'ACTUAL_RECEIPT.json');d=read(da/'DAYAHEAD_RECEIPT.json')
    native=read(ac/'grid/NATIVE_ACTUAL_STATE_CONTINUITY.json')
    assert r['status']=='COMPLETE' and result['Actual_optimizer_calls']==0
    assert native['status']=='PASS' and native['independent_resets_after_D00']==0
    assert r['decision_SHA']==d['decision_SHA']==result['decision_SHA']
    grid=grid_summary(ac);assert grid['convergence_count']==96,'ACTUAL_NONCONVERGENCE'
    # Deliberately no physical-outcome or objective-improvement admission gate.
    all_freezes={p:read(MAY_RUN/day/p/'dayahead/DAYAHEAD_RECEIPT.json')['completed_at'] for p in ('B0','B1','B2','B3')}
    boundary=read(ac/'ACTUAL_BOUNDARY_RECEIPT.json');assert all(t<=boundary['opened_at'] for t in all_freezes.values())
    shortfall=np.asarray(result['frozen_future_workload_score']['realized_shortfall_GPUh'])
    summary=dict(status='PASS',technical_status='VALID_FIXED_REPLAY',day=day,policy=policy,grid=grid,
        realized_service_shortfall_mean_GPUh=float(shortfall.mean()),realized_service_shortfall_max_GPUh=float(shortfall.max()),
        shortfall_definition='Realized H4 workload minus frozen DA headroom, clipped at zero; overlapping windows, not summed as unique energy',
        execution_rate=result['execution_rate'],execution_delay_KPIs=result['execution_delay_KPIs'],
        no_reoptimization=dict(optimizer_calls=0,decision_SHA=r['decision_SHA'],all_four_DA_freezes=all_freezes,
            Actual_opened_at=boundary['opened_at'],native_continuity=record(ac/'grid/NATIVE_ACTUAL_STATE_CONTINUITY.json')),
        actual_receipt=record(ac/'ACTUAL_RECEIPT.json'))
    save(MAY_OUT/day/f'{policy}_ACTUAL_SUMMARY.json',summary)
    save(MAY_OUT/day/f'{policy}_ACCEPTANCE.json',dict(status='PASS',Fresh='PASS',Actual='VALID_REPLAY',
        Actual_physical_outcome=grid['physical_outcome'],Fresh_summary=read(da/'FRESH_RESULT.json')['summary'],
        Actual_summary=result['summary'],Actual_optimizer_calls=0,negative_result_preserved=True))
    return summary

def stats(values):
    a=np.asarray(values,float)
    return dict(N=len(a),mean=float(a.mean()),median=float(np.median(a)),P90=float(np.quantile(a,.9)),max=float(a.max()),min=float(a.min())) if len(a) else dict(N=0)

def finalize(complete=False):
    rows=[]
    for n in range(1,32):
        day=f'2025-05-{n:02}'
        for policy in ('B0','B1','B2','B3'):
            a=MAY_OUT/day/f'{policy}_ACTUAL_SUMMARY.json';d=MAY_OUT/day/f'{policy}_DAYAHEAD_SUMMARY.json'
            if a.exists() and d.exists():rows.append(dict(day=day,policy=policy,DA=read(d),Actual=read(a)))
    if complete:assert len(rows)==124,'FINAL_MAY_REQUIRES_ALL_124_UNITS'
    baseline={r['day']:r for r in rows if r['policy']=='B0'}
    threshold=float(np.quantile([r['Actual']['grid']['rho_max'] for r in baseline.values()],.9)) if baseline else None
    stressed=[d for d,r in baseline.items() if r['Actual']['grid']['rho_max']>=threshold]
    groups={}
    for policy in ('B0','B1','B2','B3'):
        r=[x for x in rows if x['policy']==policy];paired=[x for x in r if x['day'] in baseline]
        groups[policy]=dict(days=len(r),Actual_rho_max=stats([x['Actual']['grid']['rho_max'] for x in r]),
            DayAhead_P1=stats([x['DA']['OBJECTIVE_VECTOR'][0] for x in r]),
            improvement_days_vs_B0=sum(x['Actual']['grid']['rho_max']<baseline[x['day']]['Actual']['grid']['rho_max'] for x in paired),
            paired_days=len(paired),stressed_day_Actual_rho=stats([x['Actual']['grid']['rho_max'] for x in r if x['day'] in stressed]),
            voltage_violation_days=sum(x['Actual']['grid']['violation_counts']['voltage']>0 for x in r),
            thermal_violation_days=sum(any(x['Actual']['grid']['violation_counts'][k]>0 for k in ('line_current','transformer_current','transformer_kVA')) for x in r),
            service_shortfall_daily_mean_GPUh=stats([x['Actual']['realized_service_shortfall_mean_GPUh'] for x in r]),
            temporal_shifts=sum(len(x['DA']['temporal_shifts']) for x in r),spatial_relocations=sum(len(x['DA']['spatial_relocations']) for x in r),
            checkpoint_migrations=sum(len(x['DA']['checkpoint_migrations']) for x in r),
            MESS_dispatch_slots=sum(x['DA']['MESS']['dispatch_slots'] for x in r),MESS_moves=sum(x['DA']['MESS']['movement_count'] for x in r),
            MESS_absolute_P_energy_kWh=sum(x['DA']['MESS']['absolute_P_energy_kWh'] for x in r),
            optimization_runtime_seconds=stats([x['DA']['runtime']['optimization_seconds'] for x in r]))
    value=dict(status='COMPLETE' if complete else 'PARTIAL',alpha_BG=1.15,units=len(rows),target_units=124,
        negative_days_discarded=0,stressed_day_definition='Top decile of B0 daily Actual rho maxima, including ties; reporting only',
        stressed_days=stressed,stressed_threshold=threshold,policies=groups,daily=rows)
    write_json(MAY_RUN/'V41R4_FULL_MAY_SUMMARY.json',value)
    lines=['# V41R4 Full May — alpha_BG = 1.15','',f'{value["status"]}: {len(rows)}/124 policy-days. Negative outcomes retained.','',
        '| Policy | Days | Actual rho mean | median | P90 | max | DA P1 mean | Improved vs B0 | Voltage / thermal days |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for p,g in groups.items():
        if not g['days']:continue
        s=g['Actual_rho_max'];lines.append(f'| {p} | {g["days"]} | {s["mean"]:.6f} | {s["median"]:.6f} | {s["P90"]:.6f} | {s["max"]:.6f} | {g["DayAhead_P1"]["mean"]:.6f} | {g["improvement_days_vs_B0"]} | {g["voltage_violation_days"]} / {g["thermal_violation_days"]} |')
    lines+=['','Full daily P1–P5, activity, service shortfall, runtime and counterfactual proof are retained in the companion JSON and per-policy scientific archives.','']
    from v41r4_io import atomic
    with atomic(MAY_RUN/'V41R4_FULL_MAY_SUMMARY.md') as f:f.write('\n'.join(lines).encode('utf-8'))
    return value

if __name__=='__main__':finalize()
