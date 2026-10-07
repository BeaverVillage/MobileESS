"""Read-only native result analysis. No solver construction or optimize call."""
from run_hamming48 import *
from collections import defaultdict
from dataclasses import asdict
import re, shutil

def grid_closure(A,d):
    # Same stored C3A binding substitution as PR169 window_analysis.grid_closure.
    families=[str(n).split('[')[0] for n in d['names']];defs={};cache={}
    for i,n in enumerate(d['row_names']):
        family=str(n).split('[')[0]
        if family.endswith('_binding'):
            js=A.indices[A.indptr[i]:A.indptr[i+1]];own=[int(j) for j in js if families[j]==family[:-8]]
            assert len(own)==1;defs[own[0]]=i
    def expand(j):
        if j in cache:return cache[j]
        if families[j] in ('Pch','Pdis','Q'):result=({j:1.},0.)
        elif d['lower'][j]==d['upper'][j]:result=({},float(d['lower'][j]))
        else:
            i=defs[j];js=A.indices[A.indptr[i]:A.indptr[i+1]];ws=A.data[A.indptr[i]:A.indptr[i+1]];own=float(ws[list(js).index(j)]);terms=defaultdict(float);constant=float(d['rhs'][i])/own
            for k,w in zip(js,ws):
                if k==j:continue
                part,offset=expand(int(k));constant-=w*offset/own
                for p,v in part.items():terms[p]-=w*v/own
            result=dict(terms),constant
        cache[j]=result;return result
    return expand

def main():
    A,d,old24_center=hc.load();result=read(OUT/'HAMMING48_RESULT.json');a=hc.Authority()
    with np.load(OLD/'UB_LOCAL_NEIGHBORHOOD_POINT.npz') as z:center=z['x'].copy()
    with np.load(OUT/'BEST_VALID_POINT.npz') as z:new=z['x'].copy()
    with np.load(OUT/'NEIGHBORHOOD_RESTRICTION.npz') as z:free=z['free'].copy();fixed=z['fixed'].copy()
    b=np.flatnonzero(d['types']=='B');changed=b[(center[b]>.5)!=(new[b]>.5)]
    assert not np.any((center[fixed]>.5)!=(new[fixed]>.5))
    bits=[dict(column=int(j),name=str(d['names'][j]),old=float(center[j]),new=float(new[j])) for j in changed]
    units=sorted({r['name'].split('[',1)[1].split(',')[0] for r in bits})
    slots=sorted({int(r['name'].rsplit(',',1)[1][:-1]) for r in bits})
    time_rows=[];unit_summaries=[];arc_changes=[];active_events=[]
    threshold=1e-8
    for unit in sorted(a.initial):
        arcs_by_point=[]
        for point in (center,new):arcs_by_point.append([k for k in range(len(a.arcs)) if float(a.value(f'arc[{unit},{k}]',point))>.5])
        old_set,new_set=map(set,arcs_by_point)
        for k in sorted(old_set^new_set):
            s,t,dest,connect,route=a.arcs[k]
            arc_changes.append(dict(MESS=unit,arc=k,kind='STAY' if route is None else 'MOVE',old=int(k in old_set),new=int(k in new_set),source=s,depart=t,destination=dest,connect=connect,energy_kwh=0. if route is None else route.energy_kwh))
        bytime={}
        for t in range(96):
            values=[]
            for point in (center,new):
                values.append(dict(Pch=sum(float(a.value(f'Pch[{unit},{s},{t}]',point)) for s in a.sites),Pdis=sum(float(a.value(f'Pdis[{unit},{s},{t}]',point)) for s in a.sites),Q=sum(float(a.value(f'Q[{unit},{s},{t}]',point)) for s in a.sites),SOC=float(a.value(f'SOC[{unit},{t}]',point)),mode=float(a.value(f'charge_mode[{unit},{t}]',point)),STAY=[a.arcs[k][0] for k in (old_set if point is center else new_set) if a.arcs[k][1]==t and a.arcs[k][-1] is None],MOVE=[k for k in (old_set if point is center else new_set) if a.arcs[k][1]==t and a.arcs[k][-1] is not None]))
            row=dict(MESS=unit,slot=t,old=values[0],new=values[1],delta={f:values[1][f]-values[0][f] for f in ('Pch','Pdis','Q','SOC','mode')})
            time_rows.append(row);bytime[t]=values
            for family in ('Pch','Pdis'):
                old_active=values[0][family]>threshold;new_active=values[1][family]>threshold
                if old_active!=new_active:active_events.append(dict(MESS=unit,slot=t,event='CHARGE' if family=='Pch' else 'DISCHARGE',old=old_active,new=new_active,old_kW=values[0][family],new_kW=values[1][family]))
        summaries=[]
        for which,arcset in enumerate((old_set,new_set)):
            moves=[k for k in arcset if a.arcs[k][-1] is not None]
            summaries.append(dict(MOVE_count=len(moves),STAY_count=len(arcset)-len(moves),movement_energy_kwh=sum(a.arcs[k][-1].energy_kwh for k in moves),charge_events=sum(bytime[t][which]['Pch']>threshold for t in range(96)),discharge_events=sum(bytime[t][which]['Pdis']>threshold for t in range(96)),charge_energy_kwh=a.battery.dt_hours*sum(bytime[t][which]['Pch'] for t in range(96)),discharge_energy_kwh=a.battery.dt_hours*sum(bytime[t][which]['Pdis'] for t in range(96)),Q_kvar_min=min(bytime[t][which]['Q'] for t in range(96)),Q_kvar_max=max(bytime[t][which]['Q'] for t in range(96)),SOC_initial=float(a.value(f'SOC[{unit},0]',(center,new)[which])),SOC_terminal=float(a.value(f'SOC[{unit},96]',(center,new)[which])),SOC_min=min(float(a.value(f'SOC[{unit},{t}]',(center,new)[which])) for t in range(97)),SOC_max=max(float(a.value(f'SOC[{unit},{t}]',(center,new)[which])) for t in range(97))))
        unit_summaries.append(dict(MESS=unit,old=summaries[0],new=summaries[1],delta={k:summaries[1][k]-summaries[0][k] for k in summaries[0]}))
    totals={}
    for k in ('movement_energy_kwh','MOVE_count','STAY_count','charge_events','discharge_events','charge_energy_kwh','discharge_energy_kwh'):totals[k]={label:sum(r[label][k] for r in unit_summaries) for label in ('old','new')};totals[k]['delta']=totals[k]['new']-totals[k]['old']
    diff=dict(PASS=True,node_activity_bits_changed=sum(r['name'].startswith('node_activity[') for r in bits),charge_mode_bits_changed=sum(r['name'].startswith('charge_mode[') for r in bits),total_changed_B=len(bits),affected_discrete_units=units,affected_discrete_slots=slots,outside_B_unchanged=True,changed_bits=bits,STAY_decisions_changed=sum(r['kind']=='STAY' for r in arc_changes),MOVE_decisions_changed=sum(r['kind']=='MOVE' for r in arc_changes),arc_changes=arc_changes,charging_events_changed=sum(r['event']=='CHARGE' for r in active_events),discharging_events_changed=sum(r['event']=='DISCHARGE' for r in active_events),active_power_event_threshold_kW=threshold,active_event_changes=active_events,unit_summaries=unit_summaries,totals=totals,full_96_slot_Pch_Pdis_Q_SOC_trajectory=time_rows,battery_authority=asdict(a.battery),physical_continuous_regions_can_change_outside_discrete_neighborhood=True,diagnostic_only=True)
    physical_changed=[r for r in time_rows if any(abs(r['delta'][f])>threshold for f in ('Pch','Pdis','Q','SOC'))]
    diff.update(affected_physical_continuous_units=sorted({r['MESS'] for r in physical_changed}),affected_physical_continuous_slots=sorted({r['slot'] for r in physical_changed}),derived_route_departures_can_be_outside_binary_slot_labels=True,route_time_note='New MESS04 departs66, connects69, returns82/connects85. These are implied original route auxiliaries; every original B outside64..84 stays fixed. Hamming counts original node_activity/mode B only.')
    write('TRAJECTORY_DIFF.json',diff)
    flat=[]
    for r in time_rows:flat.append(dict(MESS=r['MESS'],slot=r['slot'],**{f'{label}_{k}':v for label in ('old','new','delta') for k,v in r[label].items() if isinstance(v,(float,int))}))
    table('TRAJECTORY_TIME_CENSUS.csv',flat)
    # Recover actual branch/time identities using the same native row axes as PR169.
    axes_source=hc.ORIGINAL_SOURCE_LOCATION/'REDUCTION_AXES.npz'
    copied_axes=OUT/'GRID_SOURCE_REDUCTION_AXES.npz'
    if not copied_axes.exists():shutil.copyfile(axes_source,copied_axes)
    assert sha(copied_axes)==sha(axes_source)
    with np.load(copied_axes) as z:original_keep=z['keep'].copy()
    with np.load(hc.PARENT/'C3_RETAINED_AXES.npz') as z:c3rows=z['rows'].copy()
    with np.load(ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz') as z:c2rows=z['rows'].copy();c1orig=z['C1_original_rows'].copy()
    branch_authority=read(hc.HISTORY/'CRITICAL_BRANCH_AUTHORITY.json');planning=Path(branch_authority['branch_axis_source']);assert sha(planning)==branch_authority['planning_SHA256']
    with np.load(planning) as z:branches=z['branch_names'].copy()
    np.savez_compressed(OUT/'GRID_BRANCH_NAMES.npz',branch_names=branches)
    indices=np.flatnonzero(d['row_names']=='line_thermal_face');rho=int(np.flatnonzero(d['names']=='rho_max')[0]);rho_weights=A[:,rho].toarray().ravel();assert np.all(rho_weights[indices]<0)
    residuals=[np.asarray(A@point-d['rhs']) for point in (center,new)]
    required=[point[rho]+res[indices]/-rho_weights[indices] for point,res in zip((center,new),residuals)]
    gains=required[0]-required[1]
    prior=read(OLD/'CRITICAL_GRID_ROW_DESCRIPTORS.json')['rows']
    center_active=np.flatnonzero(abs(center[rho]-required[0])<=1e-7)
    critical_gain_order=center_active[np.argsort(-gains[center_active],kind='stable')[:100]]
    selection=set(int(indices[i]) for i in np.argsort(-gains,kind='stable')[:100])|set(int(indices[i]) for i in critical_gain_order)|set(int(indices[i]) for r in required for i in np.argsort(-r,kind='stable')[:100])|{int(r['row']) for r in prior}
    index_positions={int(i):j for j,i in enumerate(indices)};full=a.load_matrix();expand=grid_closure(A,d);effects=[];contributions=[]
    for i in sorted(selection):
        p=index_positions[i];originalrow=int(original_keep[int(c1orig[c2rows[c3rows[i]]])])
        native_names=[str(a.full['names'][j]) for j in full.indices[full.indptr[originalrow]:full.indptr[originalrow+1]]]
        axes=[re.fullmatch(r'response_line_(?:P|Q|correction)\[(\d+),(\d+)\]',n) for n in native_names];axes=[(int(m[1]),int(m[2])) for m in axes if m];assert len(set(axes))==1
        t,line=axes[0]
        row=dict(C3A_row=i,original_FULL_row=originalrow,slot=t,line_index=line,branch_name=str(branches[line]),center_required_rho=float(required[0][p]),new_required_rho=float(required[1][p]),required_rho_reduction=float(gains[p]),center_slack_rho=float(center[rho]-required[0][p]),new_slack_rho=float(new[rho]-required[1][p]),center_near_critical=abs(center[rho]-required[0][p])<=1e-7,new_near_critical=abs(new[rho]-required[1][p])<=1e-7)
        effects.append(row)
        js=A.indices[A.indptr[i]:A.indptr[i+1]];ws=A.data[A.indptr[i]:A.indptr[i+1]];terms=defaultdict(float);constant=0.
        for j,w in zip(js,ws):
            if j==rho:continue
            part,offset=expand(int(j));constant+=w*offset
            for k,v in part.items():terms[k]+=w*v
        const=(constant-float(d['rhs'][i]))/-rho_weights[i]
        values_by_point=[]
        for point in (center,new):
            grouped=defaultdict(lambda:defaultdict(float))
            for j,w in terms.items():
                family=str(d['names'][j]).split('[',1)[0];unit=str(d['names'][j]).split('[',1)[1].split(',')[0];grouped[unit][family]+=w*point[j]/-rho_weights[i]
            values_by_point.append({u:dict(v) for u,v in grouped.items()})
        assert abs(const+sum(sum(v.values()) for v in values_by_point[0].values())-row['center_required_rho'])<=1e-8
        assert abs(const+sum(sum(v.values()) for v in values_by_point[1].values())-row['new_required_rho'])<=1e-8
        contributions.append(dict(C3A_row=i,branch_name=row['branch_name'],slot=t,frozen_constant=const,center=values_by_point[0],new=values_by_point[1]))
    effects.sort(key=lambda r:-r['required_rho_reduction']);table('CRITICAL_GRID_EFFECT.csv',effects)
    critical=[r for r in effects if r['center_near_critical']]
    write('GRID_EFFECT_AUDIT.json',dict(PASS=True,all_retained_thermal_rows_evaluated=len(indices),all_center_active_rows=len(center_active),positive_required_rho_reductions=int((gains>1e-8).sum()),selected_rows=len(effects),selection='union top100 all reductions, top100 center-active reductions, top100 center required rho, top100 new required rho, all PR169 critical descriptors',largest_critical_row_improvements=sorted(critical,key=lambda r:-r['required_rho_reduction'])[:20],largest_critical_row_improvements_in_binary_block=sorted((r for r in critical if 64<=r['slot']<=84),key=lambda r:-r['required_rho_reduction'])[:20],new_near_critical_rows=[r for r in effects if r['new_near_critical']][:20],largest_all_row_improvements=effects[:20],MESS_affine_contributions=contributions,branch_identity_from_original_native_row=True,source_reduction_axes_SHA256=sha(copied_axes),branch_planning_SHA256=sha(planning),binding_method_source_SHA256=sha(OLD/'window_analysis.py'),correlation_not_causality=True,no_LB_claim=True))
    old24=read(OUT/'HAMMING24_AUTHORITY.json');newUB=result['UB_new'];original=.6694159238756877;delta=UB-newUB;prior_gain=original-UB
    saturation='still strong' if delta>=.001 and delta>=prior_gain*.5 else 'diminishing' if delta>0 else 'apparently saturated within this one time-limited search'
    H_old_center_to_new_center=int(np.count_nonzero((old24_center[free]>.5)!=(center[free]>.5)))
    H_best_from_old_center=int(np.count_nonzero((old24_center[free]>.5)!=(new[free]>.5)))
    compare=dict(Hamming24=dict(center_UB=old24['center_UB'],radius=24,Runtime=old24['Runtime'],Work=old24['Work'],best_valid_UB=old24['best_valid_UB'],absolute_improvement=prior_gain),Hamming48=dict(center_UB=UB,radius=48,Runtime=result['Runtime'],Work=result['Work'],best_valid_UB=newUB,absolute_improvement=delta),incremental_gain_48=delta,gain_48_over_gain_24=delta/prior_gain,diagnostic=saturation,diagnostic_not_proof=True,centers_differ=True,wall_time_and_concurrency_not_controlled=True,Hamming_old24_center_to_new48_center=H_old_center_to_new_center,Hamming_best_from_original_H24_center=H_best_from_old_center,best_excluded_by_original_H24_radius=H_best_from_old_center>24,best_excluded_by_hypothetical_radius24_at_current_center=result['H_best']>24,original_H24_center_point_SHA256=sha(hc.PARENT/'C3A_VALID_START.npz'),radius_only_causal_attribution_not_proven=True)
    write('UB_COMPARISON.json',compare)
    gap=dict(UB_original=original,UB_old=UB,UB_new=newUB,LB_valid=LB,global_LB_changed=False,neighborhood_ObjBound_used_as_global_LB=False,absolute_improvement=delta,relative_UB_improvement=delta/UB,gap_new=(newUB-LB)/newUB,gap_new_percent=100*(newUB-LB)/newUB,original_absolute_separation=original-LB,current_starting_separation=UB-LB,additional_poor_incumbent_attribution=delta,cumulative_poor_incumbent_attribution=original-newUB,fraction_original_separation_removed=(original-newUB)/(original-LB),fraction_current_remaining_separation_removed=delta/(UB-LB),remaining_separation=newUB-LB,remaining_difference_is_not_proven_integrality_gap=True)
    write('GAP_UPDATE.json',gap)
    if result['HAMMING_BOUNDARY_ACTIVE']:
        recommendation='같은 새 검증 중심·슬롯64..84·binary 집합·params·300초·1 thread에서 Hamming 반경만 96으로 확대한 단일 primal 실험. 이 작업에서는 실행하지 않는다.'
    else:
        recommendation=f'이번 새 검증 incumbent rho={newUB}를 중심/start로 사용하고 슬롯64..84·Hamming48·동일 params·1 thread에서 TimeLimit=600초인 단일 primal 실험. center/outside 고정값을 새 incumbent로 갱신하고 시간 budget만 늘린다. 이 작업에서는 실행하지 않는다.'
    write('NEXT_EXPERIMENT_RECOMMENDATION.json',dict(count=1,executed=False,recommendation=recommendation,center_UB=newUB,center_point='BEST_VALID_POINT.npz',center_point_SHA256=sha(OUT/'BEST_VALID_POINT.npz'),rationale='H_best33<48, native TIME_LIMIT이며 마지막 엄격한 개선이247.087초에 나왔다. 추가 gain은 H24의4.31%로 줄었지만 현재 반경의 최적성도 증명되지 않아, 새 center에서 한 번의 더 긴 primal 탐색만 추천한다.'))
    with (OUT/'INCUMBENT_TRACE.csv').open(encoding='utf-8',newline='') as stream:trace=list(csv.DictReader(stream))
    result['strict_improvement_events_excluding_initial']=sum(r['is_new_incumbent']=='True' and r['previous_best']!='' for r in trace)
    write('HAMMING48_RESULT.json',result)
    write('VERIFICATION.json',dict(PASS=bool(read(OUT/'CENTER_INCUMBENT_VALIDATION.json')['PASS'] and read(OUT/'MIP_START_VALIDATION.json')['PASS'] and read(OUT/'BEST_CANDIDATE_FULL_REPLAY.json')['PASS'] and result['optimize_calls']==1 and not result['callback_errors'] and result['solver_exception'] is None and protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']),center_replay_PASS=True,start_replay_PASS=True,best_solver_original_full_replay_PASS=read(OUT/'BEST_CANDIDATE_FULL_REPLAY.json')['PASS'],optimize_calls=1,settings_equal_H24=True,free_names_equal_H24=True,continuous_original_bounds_unchanged=True,original_physics_unchanged=True,tolerances_unchanged=True,global_LB_unchanged=True,outside_B_unchanged=True,sweeps=0,next_experiment_executed=False,historical_evidence_unchanged=protected()==read(OUT/'BASE_IDENTITY.json')['protected_before'],all_incumbent_callback_points_saved=True,callback_events=result['MIPSOL_events'],native_SolCount=result['SolCount'],native_SolCount_definition='Native solution-pool count; can differ from number of MIPSOL events',saved_best_valid_point_SHA256=sha(OUT/'BEST_VALID_POINT.npz')))
    print('ANALYSIS_COMPLETE',newUB,gap['gap_new_percent'],diff['node_activity_bits_changed'],diff['charge_mode_bits_changed'],saturation,flush=True)
if __name__=='__main__':main()
