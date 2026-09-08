"""Separate fixed development, holdout and full-May reports; explicit denominators."""
from binding import *
import numpy as np,html,time

def metric(z):
    v=z['voltage_pu'];line=z['branch_kinds']=='line';tx=~line
    high=v>1.05+1e-9;low=v<.95-1e-9
    lc=z['phase_current_loading_pu'][:,line]>1+1e-9;tc=z['phase_current_loading_pu'][:,tx]>1+1e-9;tk=z['transformer_total_kva_loading_pu'][:,tx]>1+1e-9
    return dict(rho_max=float(z['phase_current_loading_pu'][:,line].max()),Vmin=float(v.min()),Vmax=float(v.max()),voltage_cells=int((high|low).sum()),voltage_day=bool((high|low).any()),line_day=bool(lc.any()),line_cells=int(lc.sum()),tx_current_day=bool(tc.any()),tx_current_cells=int(tc.sum()),tx_kVA_day=bool(tk.any()),tx_kVA_phase_cells=int(tk.sum()),physically_feasible=not bool(high.any() or low.any() or lc.any() or tc.any() or tk.any()))

def publish():
    from dispatcher import atomic
    frozen=verify_method();rows=[];pairs=[];audits=[]
    for day in frozen['all_days']:
        for policy in ('B0','B1','B2','B3'):
            folder=OUT/'replays'/day/policy
            receipt=folder/'CANDIDATE_RECEIPT.json'
            if not receipt.exists():continue
            r=read(receipt);assert r['status']=='COMPLETE' and r['method_SHA']==sha(OUT/'METHOD_FREEZE.json')
            assert r['started_at']>=frozen['frozen_at'], 'PRE_FREEZE_ACTUAL_CANNOT_ENTER_FINAL_EVIDENCE'
            done=read(folder/'COMPLETE.json');assert done['status']=='PASS'
            ref=read(folder/'ORIGINAL_ACTUAL/REFERENCE.json')
            old=Path(ref['authoritative_root']);available=ref.get('available',True)
            modes={}
            if available:
                assert sha(old/'grid/OPENDSS_PHASE_ARRAYS.npz')==ref['grid_SHA']
                modes['ORIGINAL_ACTUAL']=arrays(old/'grid/OPENDSS_PHASE_ARRAYS.npz')
                score=read(old/'ACTUAL_RESULT.json')['frozen_future_workload_score']
            else:score=read(OUT/'common_inputs'/day/policy/'H4_SCORE.json')
            ev=[];delta=np.zeros((96,4));runtime=0.;search_runtime=0.;proof=True
            if policy in ('B0','B1'):
                modes['ETA95_QSAFE_ACTUAL']=arrays(folder/'CONTROL_COMMON_BINDING/OPENDSS_PHASE_ARRAYS.npz')
                if available:assert all(done['all_grid_arrays_bit_identical'].values())
            else:
                for mode in ('ETA95_ACTUAL','ETA95_QSAFE_ACTUAL'):modes[mode]=arrays(folder/mode/'OPENDSS_PHASE_ARRAYS.npz')
                b=arrays(folder/'ETA95_ACTUAL/EXECUTION.npz');c=arrays(folder/'ETA95_QSAFE_ACTUAL/EXECUTION.npz')
                checks={k:bool(np.array_equal(b[k],c[k])) for k in b if k!='Q_EXEC'};assert all(checks.values())
                a=read(folder/'ETA95_QSAFE_ACTUAL/C_VERSUS_B_AUDIT.json');assert a['status']=='PASS' and a['B_binding']==a['C_binding'] and a['scheduling_optimizer_calls']==0
                continuous=read(folder/'ETA95_QSAFE_ACTUAL/CONTINUOUS_VERIFICATION.json');assert continuous['status']=='PASS'
                ev=read(folder/'ETA95_QSAFE_ACTUAL/Q_CONTROL_EVENTS.json');assert len(ev)==96
                trials=read(folder/'ETA95_QSAFE_ACTUAL/NATIVE_TRIAL_AUDIT.json');assert trials['status']=='PASS'
                for tr in trials['trials']:
                    t=tr['slot'];assert tr['max_actual_slot_applied']==t and tr['start_taps']==ev[t]['start_taps']
                for t,e in enumerate(ev):
                    assert t==0 or ev[t-1]['final_taps']==e['start_taps']
                delta=np.abs(c['Q_EXEC']-b['Q_EXEC'])
                runtime=done['ETA95_QSAFE_ACTUAL']['elapsed_seconds'];search_runtime=sum(e.get('search_runtime_seconds',0.) for e in ev if e.get('robust_search_triggered',False))
                audits.append(dict(day=day,policy=policy,P_and_SoC_bit_identical=True,checks=checks,scheduling_optimizer_calls=0,causal_sequential_verified=True,Q_runtime_seconds=runtime))
            metrics={}
            for mode,z in modes.items():
                m=metric(z);metrics[mode]=m;is_c=mode=='ETA95_QSAFE_ACTUAL'
                rows.append(dict(day=day,policy=policy,trajectory=mode,**m,H4_shortfall_mean_GPUh=float(np.mean(score['realized_shortfall_GPUh'])),Q_intervention_slots=sum(e['status']=='Q_CORRECTED' for e in ev) if is_c else 0,ROBUST_Q_ONLY_UNRESOLVED_slots=sum(e['status']=='ROBUST_Q_ONLY_UNRESOLVED' for e in ev) if is_c else 0,sum_abs_Delta_Q=float(delta.sum()) if is_c else 0.,max_abs_Delta_Q=float(delta.max()) if is_c else 0.,changed_Q_vehicle_slots=int((delta>1e-9).sum()) if is_c else 0,Q_runtime_seconds=runtime if is_c else 0,Q_search_runtime_seconds=search_runtime if is_c else 0,maximum_PCS_norm_utilization=done['maximum_PCS_norm_utilization'] if is_c else None,maximum_PCS_polygon_utilization=done['maximum_PCS_polygon_utilization'] if is_c else None,final_frozen_method_evidence=is_c))
            if policy in ('B2','B3'):
                b,c=metrics['ETA95_ACTUAL'],metrics['ETA95_QSAFE_ACTUAL'];a=metrics.get('ORIGINAL_ACTUAL')
                pairs.append(dict(day=day,policy=policy,old_available=a is not None,eta_delta_rho=b['rho_max']-a['rho_max'] if a else None,Q_delta_rho=c['rho_max']-b['rho_max'],total_delta_rho=c['rho_max']-a['rho_max'] if a else None,eta_voltage_cell_delta=b['voltage_cells']-a['voltage_cells'] if a else None,Q_voltage_cell_delta=c['voltage_cells']-b['voltage_cells']))
    groups=[];cohorts={}
    for label,days in [('development',frozen['development_days']),('holdout',frozen['holdout_days']),('full_may',frozen['all_days'])]:
        complete=[d for d in days if all(any(r['day']==d and r['policy']==p and r['trajectory']=='ETA95_QSAFE_ACTUAL' for r in rows) for p in ('B0','B1','B2','B3'))]
        cohorts[label]=dict(expected_days=len(days),paired_complete_days=complete,all_days_complete=len(complete)==len(days),all_days_physically_feasible=None if len(complete)!=len(days) else all(r['physically_feasible'] for r in rows if r['day'] in days and r['trajectory']=='ETA95_QSAFE_ACTUAL'))
        for policy in ('B0','B1','B2','B3'):
            for mode in ('ORIGINAL_ACTUAL','ETA95_ACTUAL','ETA95_QSAFE_ACTUAL'):
                # All policies use exactly the same completed paired dates in a cohort.
                g=[r for r in rows if r['day'] in complete and r['policy']==policy and r['trajectory']==mode]
                if not g:continue
                rho=[r['rho_max'] for r in g];n=len(g)
                groups.append(dict(cohort=label,policy=policy,trajectory=mode,days=n,expected_days=len(days),rho_mean=float(np.mean(rho)),rho_median=float(np.median(rho)),rho_P90=float(np.percentile(rho,90)),rho_max=max(rho),voltage_days=sum(r['voltage_day'] for r in g),voltage_cells=sum(r['voltage_cells'] for r in g),line_days=sum(r['line_day'] for r in g),line_cells=sum(r['line_cells'] for r in g),tx_current_cells=sum(r['tx_current_cells'] for r in g),tx_kVA_phase_cells=sum(r['tx_kVA_phase_cells'] for r in g),maximum_PCS_norm_utilization=max((r['maximum_PCS_norm_utilization'] for r in g if r['maximum_PCS_norm_utilization'] is not None),default=None),maximum_PCS_polygon_utilization=max((r['maximum_PCS_polygon_utilization'] for r in g if r['maximum_PCS_polygon_utilization'] is not None),default=None),P_EXEC_identity=True if mode=='ETA95_QSAFE_ACTUAL' else None,SoC_energy_identity=True if mode=='ETA95_QSAFE_ACTUAL' else None,tx_current_days=sum(r['tx_current_day'] for r in g),tx_kVA_days=sum(r['tx_kVA_day'] for r in g),Vmin=min(r['Vmin'] for r in g),Vmax=max(r['Vmax'] for r in g),H4_shortfall_mean_GPUh=float(np.mean([r['H4_shortfall_mean_GPUh'] for r in g])),Q_intervention_days=sum(r['Q_intervention_slots']>0 for r in g),Q_intervention_slots=sum(r['Q_intervention_slots'] for r in g),ROBUST_Q_ONLY_UNRESOLVED_days=sum(r['ROBUST_Q_ONLY_UNRESOLVED_slots']>0 for r in g),ROBUST_Q_ONLY_UNRESOLVED_slots=sum(r['ROBUST_Q_ONLY_UNRESOLVED_slots'] for r in g),mean_abs_Delta_Q_all_vehicle_slots=sum(r['sum_abs_Delta_Q'] for r in g)/(n*96*4),mean_abs_Delta_Q_changed_vehicle_slots=sum(r['sum_abs_Delta_Q'] for r in g)/max(1,sum(r['changed_Q_vehicle_slots'] for r in g)),max_abs_Delta_Q=max(r['max_abs_Delta_Q'] for r in g),Q_runtime_total_seconds=sum(r['Q_runtime_seconds'] for r in g),Q_search_runtime_total_seconds=sum(r['Q_search_runtime_seconds'] for r in g),Q_runtime_mean_seconds=float(np.mean([r['Q_runtime_seconds'] for r in g])),physically_feasible_days=sum(r['physically_feasible'] for r in g)))
    status='COMPLETE' if cohorts['full_may']['all_days_complete'] else 'PARTIAL_RUNNING'
    result=dict(performance_implementation='EXACT_STATE_RESTORE_REUSABLE_ENGINE_PERF1',performance_freeze_SHA=sha(OUT/'PERFORMANCE_FREEZE.json'),status=status,updated_at=time.time(),method=frozen['version'],method_SHA=sha(OUT/'METHOD_FREEZE.json'),description=frozen['description'],cohorts=cohorts,groups=groups,daily=rows,paired_effects=pairs,audits=audits,completed_policy_units=sum(r['trajectory']=='ETA95_QSAFE_ACTUAL' for r in rows),scheduling_optimizer_calls=0,holdout_method_tuning=False,original_Actual_missing_policy_units=sum(not p['old_available'] for p in pairs),minimum_Q_deviation_limitation=frozen['paper_facing_wording'],pre_freeze_Actual_results_excluded_from_final_evidence=True,search_code_binding_SHA=sha(OUT/'METHOD_CODE_BINDING.json'),rho_definition='Maximum line phase-current loading over 96 slots; transformer limits separately enforced.',means='All-vehicle mean |DeltaQ| denominator: completed days*96*4. Changed mean: vehicle-slots with |DeltaQ|>1e-9. Units kvar.',partial_denominators='Group statistics use the same completed B0/B1/B2/B3 paired dates. ORIGINAL additionally requires a historical Actual result and is explicitly counted; no synthetic old replay.',audited_BC_policy_units=len(audits),P_and_SoC_identity=all(a['P_and_SoC_bit_identical'] for a in audits) if audits else None)
    atomic(OUT/'REPORT_EVIDENCE.json',result)
    def table(data,keys):
        def f(v):return f'{v:.6f}' if isinstance(v,float) else html.escape(str(v))
        return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+f(r[k])+'</td>' for k in keys)+'</tr>' for r in data)+'</table></div>'
    page='<!doctype html><meta charset="utf-8"><title>V41R4 Actual candidate</title><style>body{font:15px/1.6 system-ui;margin:32px;color:#183046}table{border-collapse:collapse;font-size:12px}td,th{padding:8px;border-bottom:1px solid #dde3eb;text-align:right;white-space:nowrap}.scroll{overflow:auto}h2{margin-top:28px}</style><h1>V41R4 Actual η=.95 + deterministic robust Q search</h1>'
    page+=f'<p>{status} · {result["completed_policy_units"]}/124 policy-days complete. Development: May01–16,18. Holdout: May17,19–31.</p><p>{html.escape(frozen["description"])}</p>'
    for label in cohorts:
        co=cohorts[label];page+=f'<h2>{label}: {len(co["paired_complete_days"])}/{co["expected_days"]} paired days</h2><p>All dates physically feasible: {co["all_days_physically_feasible"] if co["all_days_complete"] else "Not yet determined"}</p>'
        g=[x for x in groups if x['cohort']==label]
        page+=table(g,['policy','trajectory','days','rho_mean','rho_median','rho_P90','rho_max','voltage_days','voltage_cells','line_days','line_cells','tx_current_days','tx_current_cells','tx_kVA_days','tx_kVA_phase_cells','Vmin','Vmax','H4_shortfall_mean_GPUh'])
        page+=table([x for x in g if x['trajectory']=='ETA95_QSAFE_ACTUAL'],['policy','Q_intervention_days','Q_intervention_slots','mean_abs_Delta_Q_all_vehicle_slots','mean_abs_Delta_Q_changed_vehicle_slots','max_abs_Delta_Q','ROBUST_Q_ONLY_UNRESOLVED_days','ROBUST_Q_ONLY_UNRESOLVED_slots','maximum_PCS_norm_utilization','maximum_PCS_polygon_utilization','P_EXEC_identity','SoC_energy_identity','Q_runtime_total_seconds','Q_search_runtime_total_seconds','physically_feasible_days'])
    page+='<p>Every completed B/C pair has identical P, SoC, energy, AIDC and route/location bindings. Exact native AC continuous replay verifies accepted Q and sequential taps. Q runtime includes causal replay using exact slot-start restoration and a reusable engine; Q search runtime counts triggered-slot searches separately. Scheduling optimizer calls = 0. No P fallback or preventive threshold. ROBUST_Q_ONLY_UNRESOLVED denotes failure of the prescribed deterministic search, not physical infeasibility. The accepted point is the minimum-deviation feasible correction found by the prescribed deterministic search. All final evidence uses post-freeze Actual execution; pre-freeze Actual appears only as historical comparison. Historical Actual is preserved. Paired eta and Q effects, hashes and audits: <a href="REPORT_EVIDENCE.json">REPORT_EVIDENCE.json</a>.</p>'
    (OUT/'ACTUAL_METHOD_REPORT.html').write_text(page,encoding='utf-8')
    return result

if __name__=='__main__':print(publish()['status'])
