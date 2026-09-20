"""Read saved May01/MESS6 results; never import or run a scientific model.

Requires numpy for the saved NPZ arrays. Output is deterministic apart from the
user-supplied archive receipt. Original JSON/NPZ files are read-only.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

DATE = '2025-05-01'
POLICIES = ('B0', 'B1', 'B2', 'B3')
R = 'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
B = 'independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913'
L = 'independent_screening/IEEE8500_QSAFE_V2_LEGACY_SHELL_20260913'
ACT = {'B0': B+'/actual/B0', 'B1': B+'/actual/B1', 'B2': L+'/B2',
       'B3': R+'/actual_B3_energy_exception_20260914/B3'}
DA = {p: (B+'/'+p+'/DA_INDEPENDENT_CLEAN_96/AC_VALIDATION.json' if p in ('B0','B1')
          else R+'/'+p+'/independent_clean_exact/AC_VALIDATION.json') for p in POLICIES}
FINAL = {'B0': B+'/B1/POLICY_FEASIBLE_SEED_AUDIT.json',
         'B1': B+'/B1/ACCEPTED_AIDC_DEADLINE.json',
         'B2': R+'/B2/FINAL_AUTHORITY.json', 'B3': R+'/B3/FINAL_AUTHORITY.json'}
NA = 'NA'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def clock(slot):
    return f'{DATE}T{slot//4:02}:{slot%4*15:02}:00'


def export(root, out, archive_index):
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output must be a new or empty directory')
    out.mkdir(parents=True, exist_ok=True)
    sources, outputs = {}, {}

    def register(name):
        path = root/name
        sources[name] = {'sha256': sha(path), 'bytes': path.stat().st_size}
        return path

    def read(name):
        return json.loads(register(name).read_text(encoding='utf-8-sig'))

    def arrays(name):
        with np.load(register(name), allow_pickle=False) as z:
            return {k: z[k].copy() for k in z.files}

    def write(name, rows, description, evidence, headers=None):
        columns = list(headers or [])
        columns += list(dict.fromkeys(k for r in rows for k in r if k not in columns))
        def value(v):
            if v is None or isinstance(v, float) and not math.isfinite(v):
                return NA
            return str(v).lower() if isinstance(v, bool) else v
        with (out/name).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows({k: value(r.get(k, NA)) for k in columns} for r in rows)
        outputs[name] = {'rows': len(rows), 'sha256': sha(out/name),
                         'description': description, 'sources': sorted(set(evidence))}

    receipt = json.loads(archive_index.read_text(encoding='utf-8-sig'))
    if receipt['evaluation_date'] != DATE or receipt['verification'] != 'PASS':
        raise ValueError('Archive receipt is not the verified May01 snapshot')
    result_path = R+'/RESULT_WITH_ENERGY_EXCEPTION.json'
    result = read(result_path)
    fleet = read(R+'/FLEET_AUTHORITY.json')
    assert result['date'] == fleet['date'] == DATE and len(fleet['fleet_ids']) == 6
    final = {p: read(FINAL[p]) for p in POLICIES}
    exact = {p: read(DA[p]) for p in POLICIES}
    actual = {p: read(ACT[p]+'/FINAL_ACTUAL/AC_SUMMARY.json') for p in POLICIES}
    z = {p: arrays(ACT[p]+'/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz') for p in POLICIES}
    axis_path = R+'/AXES.json'
    axes = read(axis_path)
    for p in POLICIES:
        register(ACT[p]+'/COMPLETE.json')
        assert sources[ACT[p]+'/COMPLETE.json']['sha256'] == result['policies'][p]['Actual_source']['sha256']
        for k, a in [('node_names','nodes'), ('line_phase_axes','line'), ('transformer_current_axes','tx')]:
            assert np.array_equal(z[p][k], axes[a])
        assert len(exact[p]['slots']) == 96
        for k in ('voltage_pu','line_current_loading_pu','transformer_current_loading_pu','transformer_winding_kva_loading_pu'):
            assert z[p][k].shape[0] == 96 and np.isfinite(z[p][k]).all()
        assert math.isclose(float(z[p]['line_current_loading_pu'].max()), actual[p]['max_phase_line_loading_pu'], abs_tol=1e-12)
        assert exact[p]['metrics'] == result['policies'][p]['DA']
    topo_base = 'IEEE8500_scalability_20260910/audit/'
    lines, tx, busrows = (read(topo_base+n+'.json') for n in ('lines','transformers','buses'))
    overlay = read(R+'/PCC_OVERLAY_INVENTORY.json')
    headroom = read(R+'/HEADROOM_AUTHORITY.json')
    pairs = {'Line.'+v['name']: (v['bus1'],v['bus2']) for v in lines}
    pairs.update({'Transformer.'+v['name']: v['buses'][:2] for v in tx})
    pairs.update({'Transformer.'+v['transformer']: (v['host_bus'],v['PCC_bus']) for v in overlay})
    basebus = lambda s: s.split('.')[0].lower()
    case = dict(evaluation_date=DATE, feeder_name='IEEE8500 remapped PCC overlay',
        actual_bus_count=len({basebus(n) for n in axes['nodes']}), phase_node_count=len(axes['nodes']),
        branch_count=len({tuple(sorted(map(basebus,v))) for v in pairs.values()}),
        line_count=len(lines), transformer_count=len(tx)+len(overlay), switch_count=sum(v['switch'] for v in lines),
        time_resolution_min=15, horizon_intervals=96, horizon_hours=24, aidc_site_count=12,
        mess_count=6, mess_station_count=12, policies='B0;B1;B2;B3',
        source_archive=Path(receipt['archive'].replace('\\','/')).name, source_archive_sha256=receipt['archive_sha256'],
        authority_status=result['status'], mess_service_location_count=24,
        installed_GPU_capacity=headroom['physical_total_GPU'], AIDC_scale=headroom['s_AIDC'],
        branch_definition='Unique undirected line/transformer bus pairs including disabled lines; excludes reactors',
        baseline_mess='OFF; four-hour B0/B1 preserved')
    write('CASE_AUTHORITY.csv', [case], 'May01 six-MESS snapshot, not later September experiments',
          [result_path, R+'/FLEET_AUTHORITY.json', axis_path, R+'/HEADROOM_AUTHORITY.json', R+'/PCC_OVERLAY_INVENTORY.json', topo_base+'lines.json', topo_base+'transformers.json'])
    planning = {p: final[p]['electrical']['rho_max'] if p=='B0' else final[p]['P1'] for p in POLICIES}
    assert final['B0']['day']==DATE and final['B0']['before_optimization'] and final['B0']['seed_source']=='CURRENT_POLICY_REFERENCE_WITH_NO_OPTIONAL_MOVE'
    summary = []
    for p in POLICIES:
        m = exact[p]['metrics']
        row = dict(policy=p, planning_rho_max=planning[p], dayahead_ac_rho_max=m['max_phase_line_loading_pu'],
                   realized_ac_rho_max=actual[p]['max_phase_line_loading_pu'], min_voltage_pu=m['Vmin_pu'],
                   max_voltage_pu=m['Vmax_pu'], voltage_feasible=True, thermal_feasible=True,
                   overall_ac_feasible=exact[p]['status']=='PASS', accepted_schedule=True,
                   source_file=';'.join([FINAL[p],DA[p],ACT[p]+'/FINAL_ACTUAL/AC_SUMMARY.json']),
                   voltage_and_feasibility_scope='DAY_AHEAD_AC', realized_ac_feasible=actual[p]['AC_feasible'],
                   active_mess_count=0 if p in ('B0','B1') else 6,
                   realized_acceptance_status=result['status'] if p=='B3' else 'PASS',
                   operating_440kwh_floor_feasible=False if p=='B3' else NA)
        summary.append(row)
    for scope in ('planning','dayahead_ac','realized_ac'):
        vals = [r[scope+'_rho_max'] for r in summary]
        for row, v in zip(summary, vals):
            row[scope+'_reduction_vs_B0_pct'] = 100*(vals[0]-v)/vals[0]
            row[scope+'_rank'] = 1+sum(x<v for x in vals)
    write('POLICY_RESULT_SUMMARY.csv', summary, 'Each reduction and rank uses only one metric scope',
          [result_path,*FINAL.values(),*DA.values(),*(ACT[p]+'/FINAL_ACTUAL/AC_SUMMARY.json' for p in POLICIES)])
    acrows=[]
    for p in POLICIES:
        for scope in ('DAY_AHEAD_AC','REALIZED_OPERATION_AC'):
            is_actual=scope=='REALIZED_OPERATION_AC'
            slots=read(ACT[p]+'/FINAL_ACTUAL/SLOT_EXTREMA.json') if is_actual else exact[p]['slots']
            m=actual[p] if is_actual else exact[p]['metrics']
            low=min(slots,key=lambda s:s['Vmin_pu']); high=max(slots,key=lambda s:s['Vmax_pu'])
            peak=max(slots,key=lambda s:s['max_phase_line_loading_pu']); witness=peak['line_witness'].split('|')
            vf=(m.get('voltage_violations',0)==0) if is_actual else m['Vmin_pu']>=.95-1e-9 and m['Vmax_pu']<=1.05+1e-9
            tf=all(m[k]<=1+1e-9 for k in ('max_phase_line_loading_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu'))
            converged=m['converged_slots']==96 if is_actual else all(s['converged'] for s in slots)
            settled=m['controls_settled_slots']==96 if is_actual else all(s['controls_settled'] for s in slots)
            assert vf and tf and converged and settled
            row=dict(policy=p,validation_scope=scope,converged=converged,overall_ac_feasible=vf and tf and converged and settled,
                voltage_feasible=vf,thermal_feasible=tf,min_voltage_pu=m['Vmin_pu'],max_voltage_pu=m['Vmax_pu'],
                min_voltage_time=clock(low['slot']),max_voltage_time=clock(high['slot']),max_line_loading=m['max_phase_line_loading_pu'],
                max_loading_element=witness[0],max_loading_phase=witness[-1],max_loading_time=clock(peak['slot']),
                voltage_violation_count=m['voltage_violations'] if is_actual else sum(s['Vmin_pu']<.95-1e-9 or s['Vmax_pu']>1.05+1e-9 for s in slots),
                thermal_violation_count=sum(m[k] for k in ('line_violations','transformer_current_violations','transformer_kVA_violations')) if is_actual else 0,
                source_file=ACT[p]+'/FINAL_ACTUAL/AC_SUMMARY.json;'+ACT[p]+'/FINAL_ACTUAL/SLOT_EXTREMA.json' if is_actual else DA[p],
                controls_settled=settled,max_transformer_phase_current_pu=m['max_transformer_phase_current_pu'],
                max_transformer_winding_kva_pu=m['max_transformer_winding_kva_pu'],numerical_tolerance_pu=1e-9,
                violation_count_unit='Stored category occurrences' if is_actual else 'Violating slots')
            for label,s in [('min',low),('max',high)]:
                node=s.get('V'+label+'_node')
                row[label+'_voltage_bus'],row[label+'_voltage_phase']=node.rsplit('.',1) if node else (NA,NA)
            acrows.append(row)
    write('AC_FEASIBILITY.csv',acrows,'AC feasibility does not imply battery operating-floor compliance',[n for r in acrows for n in r['source_file'].split(';')])
    d1=read(B+'/DEADLINE_ENFORCEMENT.json');d3=read(R+'/DEADLINE_ENFORCEMENT.json');m1=read(R+'/B3_M1/FINAL_AUTHORITY.json')
    duration=d1['process_exited_monotonic']-d1['clock']['start_monotonic']
    runtime=[]
    for p in POLICIES:
        row=dict(policy=p,runtime_s=duration if p=='B1' else NA,runtime_min=duration/60 if p=='B1' else NA,
            time_limit_s=14400 if p in ('B1','B3') else NA,time_limit_min=240 if p in ('B1','B3') else NA,
            termination_status='NOT_OPTIMIZED_REFERENCE' if p=='B0' else 'SEARCH_PROCESS_TERMINATED_AT_ABSOLUTE_DEADLINE' if p in ('B1','B3') else 'RESTORED_ACCEPTANCE_NO_SINGLE_RUNTIME_RECORD',
            time_limit_reached=True if p in ('B1','B3') else NA,feasible_incumbent_available=p!='B0',optimality_proven=False,
            mip_gap=NA,best_bound=NA,final_objective=planning[p],solver_name='NONE' if p=='B0' else 'Gurobi',threads=NA,
            source_file=FINAL[p],runtime_scope='Measured search-process duration only' if p=='B1' else 'End-to-end runtime not recorded',
            time_limit_scope='Final AIDC search component; not complete policy',A1_runtime_s=NA,M1_runtime_s=NA,A2_runtime_s=NA,M2_runtime_s=NA)
        if p=='B1':row['source_file']+=';'+B+'/DEADLINE_ENFORCEMENT.json'
        if p=='B3':
            row.update(A1_runtime_s=duration,M1_runtime_s=m1['wall_seconds'],A2_runtime_s=final[p]['A1_continuous_wall_seconds'],M2_runtime_s=final[p]['MF_wall_seconds'],
                stage_mapping='A1=reused B1 search process; A2=final raw A1 search; M2=MF',
                source_file=';'.join([FINAL[p],B+'/DEADLINE_ENFORCEMENT.json',R+'/DEADLINE_ENFORCEMENT.json',R+'/B3_M1/FINAL_AUTHORITY.json']))
            row['recorded_component_sum_s']=sum(row[k] for k in ('A1_runtime_s','M1_runtime_s','A2_runtime_s','M2_runtime_s'))
        runtime.append(row)
    assert d1['killed_at_deadline'] and d3['killed_at_deadline'] and d1['budget_seconds']==d3['budget_seconds']==14400
    write('RUNTIME_TERMINATION.csv',runtime,'Component sum excludes setup, failed/recovery attempts and postprocessing; not end-to-end runtime',[n for r in runtime for n in r['source_file'].split(';')])
    mess=[]
    for i in range(1,7):
        path=f'{R}/B2/beam/{DATE}/B2/B2/STAGE_{i}.json';tr=read(path)['trace']
        row=dict(policy='B2',mess_id=tr['mess_id'],screen_s=tr['cheap_screen_wallclock_seconds'],restricted_optimization_s=tr['restricted_wallclock_seconds'],full_milp_s=tr['full_MILP_wallclock_seconds'],parent_count=tr['parent_beam_count'],source_file=path)
        row['recorded_component_sum_s']=row['screen_s']+row['restricted_optimization_s']+row['full_milp_s'];row['recorded_component_sum_min']=row['recorded_component_sum_s']/60;mess.append(row)
    write('B2_MESS_OPTIMIZATION_RUNTIME.csv',mess,'Saved completed beam-stage components; excludes restoration and final AC',[r['source_file'] for r in mess])
    for scope in ('REALIZED_OPERATION_AC','DAY_AHEAD_AC'):
        rows=[]
        for t in range(96):
            row=dict(time=clock(t),interval_index=t,validation_scope=scope)
            for p in POLICIES:
                if scope=='REALIZED_OPERATION_AC':
                    vals=z[p]['line_current_loading_pu'][t];idx=int(vals.argmax());rho=float(vals[idx]);label=z[p]['line_phase_axes'][idx]
                else:rho=exact[p]['slots'][t]['max_phase_line_loading_pu'];label=exact[p]['slots'][t]['line_witness']
                fields=label.split('|');row.update({p+'_rho_max':rho,p+'_critical_element':fields[0],p+'_critical_phase':fields[-1],p+'_critical_terminal':fields[1]})
            rows.append(row)
        write('MAY01_MAX_LOADING_TIMESERIES.csv' if scope=='REALIZED_OPERATION_AC' else 'MAY01_DAYAHEAD_MAX_LOADING_TIMESERIES.csv',rows,scope+'; maximum over line terminal-phase channels', [ACT[p]+'/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz' if scope=='REALIZED_OPERATION_AC' else DA[p] for p in POLICIES])
    buses={b['bus'].lower():b for b in busrows}
    coord_path=R+'/PCC_BusCoordinates.dss'
    for name,x,y in re.findall(r'Bus=(\S+)\s+x=([\d.eE+-]+)\s+y=([\d.eE+-]+)',register(coord_path).read_text()):
        buses[name.lower()]=dict(x=float(x),y=float(y),coord_defined=True)
    t=int(z['B0']['line_current_loading_pu'].max(axis=1).argmax());heat=[]
    ratings=dict(zip(axes['line'],axes['line_rating_A']));ratings.update(zip(axes['tx'],axes['tx_rating_A']))
    def coordinates(row):
        for end in ('from','to'):
            b=buses.get(basebus(row[end+'_bus']),{})
            for xy in ('x','y'):row[xy+'_'+end]=b[xy] if b.get('coord_defined') else NA
    for a,k,typ in [('line_phase_axes','line_current_loading_pu','LINE'),('transformer_current_axes','transformer_current_loading_pu','TRANSFORMER')]:
        maxima={}
        for axis,x,y in zip(z['B0'][a],z['B0'][k][t],z['B3'][k][t]):
            elem=axis.split('|')[0];prev=maxima.get(elem,(-math.inf,-math.inf));maxima[elem]=(max(prev[0],float(x)),max(prev[1],float(y)))
        for axis,x,y in zip(z['B0'][a],z['B0'][k][t],z['B3'][k][t]):
            elem,term,bus,phase=axis.split('|');fr,to=pairs[elem]
            row=dict(time=clock(t),element_id=elem,element_type=typ,from_bus=fr,to_bus=to,phase=phase,B0_loading=float(x),B3_loading=float(y),B0_element_max_loading=maxima[elem][0],B3_element_max_loading=maxima[elem][1],terminal=term,terminal_bus=bus,current_rating_A=ratings[axis],validation_scope='REALIZED_OPERATION_AC',data_status='RECORDED')
            coordinates(row);heat.append(row)
    present={r['element_id'] for r in heat}
    for v in lines:
        if 'Line.'+v['name'] in present:continue
        assert not v['enabled']
        row=dict(time=clock(t),element_id='Line.'+v['name'],element_type='LINE',from_bus=v['bus1'],to_bus=v['bus2'],phase=NA,terminal=NA,data_status='DISABLED_ELEMENT_NO_RECORDED_CURRENT',validation_scope='REALIZED_OPERATION_AC')
        coordinates(row);heat.append(row)
    heat_sources=[ACT[p]+'/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz' for p in ('B0','B3')]+[topo_base+n+'.json' for n in ('lines','transformers','buses')]+[R+'/PCC_OVERLAY_INVENTORY.json',coord_path,axis_path]
    write('HEATMAP_B0_B3_SAME_TIME.csv',heat,'Realized B0 critical slot held for B3; terminal/node labels are not assumed primary phase letters',heat_sources)
    h0=float(z['B0']['line_current_loading_pu'][t].max());h3=float(z['B3']['line_current_loading_pu'][t].max())
    hm=dict(critical_time_B0=clock(t),B0_rho_max_at_time=h0,B3_rho_max_at_same_time=h3,reduction_pct_at_same_time=100*(h0-h3)/h0,validation_scope='REALIZED_OPERATION_AC',interval_index=t)
    write('HEATMAP_SAME_TIME_SUMMARY.csv',[hm],'Earliest maximum of saved B0 realized AC line loading',heat_sources)
    refs=read(B+'/REFERENCE_JOBS.json');ref={j['job_uid']:j for j in refs}
    jobs={'B0':refs,'B1':final['B1']['jobs'],'B2':refs,'B3':final['B3']['jobs']};flex=[]
    for p in POLICIES:
        assert len(jobs[p])==len(ref)==1649 and {j['job_uid'] for j in jobs[p]}==set(ref)
        assert {j['operating_day'] for j in jobs[p]}=={DATE}
        path=ACT[p]+'/FINAL_ACTUAL/ACTUATOR.json';act=read(path)['trajectory'];off=p in ('B0','B1')
        energies=[v['energy_after_kWh'] for v in act if v['slot']==95]
        flex.append(dict(policy=p,aidc_shifted_jobs=sum(j['start_slot']!=ref[j['job_uid']]['start_slot'] for j in jobs[p]),aidc_cross_site_jobs=sum(j['AIDC_site']!=ref[j['job_uid']]['AIDC_site'] for j in jobs[p]),aidc_migrations=sum(bool(j.get('migration_selected')) for j in jobs[p]),mess_relocations=len({(v['mess_id'],v['departure_slot']) for v in final[p].get('trajectory_slots',[]) if v.get('departure_slot') is not None}),mess_charge_energy_kwh=sum(max(-v['P_EXEC'],0)*.25 for v in act),mess_discharge_energy_kwh=sum(max(v['P_EXEC'],0)*.25 for v in act),mess_max_active_power_kw=max(abs(v['P_EXEC']) for v in act),mess_max_reactive_power_kvar=max(abs(v['Q_EXEC']) for v in act),mess_active_station_count=len({v['actual_service_id'] for v in act if abs(v['P_EXEC'])>1e-9 or abs(v['Q_EXEC'])>1e-9}),final_soc_min_kwh=NA if off else min(energies),final_soc_max_kwh=NA if off else max(energies),source_file=';'.join([path,FINAL[p],B+'/REFERENCE_JOBS.json']),aidc_and_relocation_scope='FINAL_DAY_AHEAD',power_energy_scope='REALIZED_EXECUTED_ACTUATOR'))
    write('FLEXIBILITY_ACTION_SUMMARY.csv',flex,'AC-side energy integral: positive P discharges. Power maximum is per vehicle. final_soc columns are kWh, not fractions; OFF batteries NA',[n for row in flex for n in row['source_file'].split(';')])
    exceptions=[dict(policy='B3',time=clock(v['slot']),**v,operating_floor_kwh=440,operating_floor_feasible=False,ac_feasible=True,acceptance_status=result['status'],source_file=result_path) for v in result['B3_energy_exception']['energy_floor_exceptions']]
    write('B3_OPERATING_ENERGY_EXCEPTION.csv',exceptions,'Raw accepted operating-floor exception remains distinct from AC pass',[result_path])
    keys=[]
    def key(section,metric,policy,scope,value,unit,src):keys.append(dict(section=section,metric=metric,policy=policy,scope=scope,value=value,unit=unit,source_file=src,verified=value!=NA))
    key('Case','actual_bus_count','ALL','CASE',case['actual_bus_count'],'buses',axis_path)
    for row in summary:key('Performance','rho_max',row['policy'],'PLANNING',row['planning_rho_max'],'pu',row['source_file'])
    for row in summary[1:]:key('Performance','reduction_vs_B0',row['policy'],'PLANNING',row['planning_reduction_vs_B0_pct'],'percent',row['source_file'])
    for row in runtime:key('Runtime','runtime_min',row['policy'],row['runtime_scope'],row['runtime_min'],'min',row['source_file'])
    for row in acrows:key('Feasibility','overall_ac_feasible',row['policy'],row['validation_scope'],row['overall_ac_feasible'],'boolean',row['source_file'])
    for metric in ('critical_time_B0','B0_rho_max_at_time','B3_rho_max_at_same_time','reduction_pct_at_same_time'):key('Heatmap',metric,'B0/B3','REALIZED_OPERATION_AC',hm[metric],'timestamp' if metric=='critical_time_B0' else 'percent' if metric.startswith('reduction') else 'pu',';'.join(heat_sources))
    key('Runtime','time_limit_min','B3','FINAL_AIDC_SEARCH_COMPONENT',240,'min',R+'/DEADLINE_ENFORCEMENT.json')
    key('Energy','operating_floor_feasible','B3','REALIZED_OPERATION_AC',False,'boolean',result_path)
    write('PAPER_KEY_RESULTS.csv',keys,'Maximum 30 results; NA is missing, never zero',[n for row in keys for n in row['source_file'].split(';')])
    # Explicit consistency checks on stored inputs, never simulations.
    bg={p:arrays(ACT[p]+'/ACTUAL_INPUTS.npz') for p in POLICIES}
    background_equal=all(np.array_equal(bg[p][k],bg['B0'][k]) for p in POLICIES for k in ('md','mpv'))
    mapping_equal=read(B+'/MAPPING_FREEZE.json')==read(R+'/MAPPING_FREEZE.json')
    c1=read(B+'/COEFFICIENT_GENERATION.json');c2=read(R+'/COEFFICIENT_GENERATION.json')
    coefficients_equal=[v['artifact']['sha256'] for v in c1['slots']]==[v['artifact']['sha256'] for v in c2['slots']]==final['B0']['electrical']['coefficient_SHAs']
    assert background_equal and mapping_equal and coefficients_equal
    checks=[]
    for n,label,observed in [(1,'Same evaluation date',DATE),(2,'Same remapped topology',mapping_equal),(3,'Same horizon','96 x 15 min'),(4,'Same realized background demand/PV',background_equal),(5,'Same coefficient and rating authority',coefficients_equal),(6,'Scopes separated','planning / day-ahead / realized'),(7,'Four policy results','B0;B1;B2;B3'),(8,'Same heatmap timestamp',clock(t)),(9,'Runtime distinct from limit','Missing totals NA; component sum not total'),(10,'Incumbent distinct from optimum','No global certificate'),(11,'AC authority exists','8 passing policy/scope records'),(12,'Paper-critical completeness','End-to-end B0/B2/B3 runtime unavailable'),(13,'Unique policy rows',4),(14,'Scientific execution count',0)]:
        checks.append(dict(check_id=f'C{n}',check=label,observed=observed,status='UNRESOLVED' if n==12 else 'PASS',evidence=result_path))
    checks.append(dict(check_id='C15',check='Original B3 440kWh floor',observed='9 slots; accepted exception',status='FAIL',evidence=result_path))
    write('VALIDATION_CHECKS.csv',checks,'Extraction integrity is distinct from strict B3 operating-floor compliance',list(sources))
    for n,info in sources.items():assert sha(root/n)==info['sha256'], 'Source changed: '+n
    manifest=dict(date=DATE,mess_count=6,scientific_execution_count=0,result_acceptance=result['status'],
                  raw_archive={k:receipt[k] for k in ('archive_sha256','archive_bytes','source_file_count','verification')},
                  archive_filename=Path(receipt['archive'].replace('\\','/')).name,sources=sources,outputs=outputs)
    (out/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'csv_count':len(outputs),'source_count':len(sources),'output':str(out)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--archive-index',type=Path,required=True)
    args=parser.parse_args()
    export(args.source_root.resolve(),args.output_dir.resolve(),args.archive_index.resolve())
