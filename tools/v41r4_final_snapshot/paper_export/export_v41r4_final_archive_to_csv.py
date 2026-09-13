"""Archive-only scientific CSV projection. No project imports, solvers, or host provenance reads."""
import argparse, ast, collections, csv, datetime as dt, hashlib, io, json, math, os
from pathlib import Path, PurePosixPath
import shutil, sys, tempfile, time, traceback
import numpy as np
from archive_intake import intake, longpath

NA='NOT_AVAILABLE'
VERSION='V41R4_FINAL_ARCHIVE_PAPER_CSV_EXPORT_V1'
POLICIES=('B0','B1','B2','B3')
DEFAULT_ROOT=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터')
DEFAULT_ARCHIVE=DEFAULT_ROOT/'V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz'
SCHEMAS={
'00_experiment_authority':'''campaign_version evaluation_month expected_days expected_policies expected_policy_days completed_policy_days alpha_BG AIDC_equivalent_GPU AIDC_site_count MESS_count MESS_Pmax_kW_per_unit MESS_Smax_kVA_per_unit MESS_Emax_kWh_per_unit MESS_Emin_kWh_per_unit MESS_initial_kWh_per_unit MESS_terminal_kWh_per_unit eta_charge eta_discharge PCS_polygon_faces grid_model grid_slots_per_day grid_interval_min voltage_lower_pu voltage_upper_pu traffic_links traffic_slots_per_day traffic_interval_min traffic_model_id runtime_model_id H4_model_id source_archive_filename source_archive_size_bytes source_archive_SHA256'''.split(),
'01_policy_day_summary':'''day policy completion_status P1_rho_planning P2_H4_shortfall_GPUh P3_migrations P4_reference_deviation P5_stable_tie DA_rho_max DA_Vmin_pu DA_Vmax_pu DA_tx_current_max_pu DA_tx_kVA_max_pu DA_voltage_violation_count DA_line_violation_count DA_tx_current_violation_count DA_tx_kVA_violation_count DA_converged_slots DA_physical_outcome DA_critical_line DA_critical_line_phase DA_critical_line_slot DA_critical_line_rho DA_Vmax_bus DA_Vmax_phase DA_Vmax_slot DA_Vmin_bus DA_Vmin_phase DA_Vmin_slot DA_critical_tx_current_asset DA_critical_tx_current_phase DA_critical_tx_current_slot DA_critical_tx_current_rho DA_critical_tx_kVA_asset DA_critical_tx_kVA_phase DA_critical_tx_kVA_slot DA_critical_tx_kVA_rho AIDC_selected_job_count AIDC_eligible_job_count temporal_shift_count spatial_relocation_count checkpoint_migration_count MESS_vehicle_count MESS_dispatch_slots MESS_move_count MESS_abs_P_energy_kWh optimization_runtime_s'''.split(),
'02_actual_summary':'''day policy completion_status actual_method Actual_rho_max Actual_Vmin_pu Actual_Vmax_pu Actual_tx_current_max_pu Actual_tx_kVA_max_pu Actual_voltage_violation_cells Actual_line_violation_cells Actual_tx_current_violation_cells Actual_tx_kVA_violation_cells Actual_voltage_violation_day Actual_line_violation_day Actual_tx_current_violation_day Actual_tx_kVA_violation_day Actual_physically_feasible Actual_converged_slots Actual_H4_shortfall_mean_GPUh Actual_H4_shortfall_max_GPUh execution_rate Actual_optimizer_calls decision_SHA development_or_holdout final_frozen_method_evidence'''.split(),
'03_q_correction_summary':'''day policy development_or_holdout Q_intervention_slots Q_intervention_rate Q_unresolved_slots Q_unresolved_day sum_abs_delta_Q_kvar mean_abs_delta_Q_all_vehicle_slots_kvar mean_abs_delta_Q_changed_vehicle_slots_kvar max_abs_delta_Q_kvar changed_Q_vehicle_slots maximum_PCS_norm_utilization maximum_PCS_polygon_utilization Q_runtime_s Q_search_runtime_s P_EXEC_identity SoC_energy_identity AIDC_decision_identity route_location_identity preQ_rho_max preQ_Vmin_pu preQ_Vmax_pu preQ_voltage_violation_cells preQ_line_violation_cells preQ_tx_current_violation_cells preQ_tx_kVA_violation_cells preQ_physically_feasible postQ_rho_max postQ_Vmin_pu postQ_Vmax_pu postQ_voltage_violation_cells postQ_line_violation_cells postQ_tx_current_violation_cells postQ_tx_kVA_violation_cells postQ_physically_feasible Q_delta_rho Q_delta_voltage_cells global_optimum_proven'''.split(),
'04_mess_timeseries':'''day policy slot timestamp mess_id location_service_id connected moving origin_service_id destination_service_id departure_slot arrival_slot P_DA_kW Q_DA_kvar P_Actual_kW Q_Actual_kvar delta_Q_kvar SoC_kWh SoC_pct PCS_norm_utilization PCS_polygon_utilization Q_intervention Q_intervention_status regulator_taps_start regulator_taps_final'''.split(),
'05_grid_timeseries':'''day policy trajectory slot timestamp rho_line_max critical_line critical_line_phase Vmin_pu Vmin_bus Vmin_phase Vmax_pu Vmax_bus Vmax_phase tx_current_max_pu tx_current_asset tx_current_phase tx_kVA_max_pu tx_kVA_asset tx_kVA_phase voltage_violation_count line_violation_count tx_current_violation_count tx_kVA_violation_count converged regulator_taps capacitor_states'''.split(),
'06_aidc_decisions':'''day policy job_uid requested_GPU reference_site optimized_site reference_start_slot optimized_start_slot start_shift_slots safe_duration_seconds safe_duration_slots time_shifted site_changed checkpoint_migrated reference_terminal_remaining_slots optimized_terminal_remaining_slots terminal_residual_delta_slots cross_midnight_reference cross_midnight_optimized terminal_constraint_binding'''.split(),
'07_ml_performance':'''domain metric value unit evaluation_scope N source_inside_archive'''.split(),
'08_policy_aggregate_statistics':'''policy N_days P1_mean P1_median P1_P90 P1_min P1_max DA_rho_mean DA_rho_median DA_rho_P90 DA_rho_min DA_rho_max Actual_rho_mean Actual_rho_median Actual_rho_P90 Actual_rho_min Actual_rho_max Vmin_global Vmax_global voltage_violation_days thermal_violation_days temporal_shift_total spatial_relocation_total checkpoint_migration_total MESS_dispatch_slots_total MESS_moves_total MESS_abs_P_energy_kWh_total optimization_runtime_mean_s optimization_runtime_median_s optimization_runtime_max_s Actual_H4_shortfall_mean_GPUh'''.split(),
'09_paired_policy_comparisons':['day'],
'10_mess_utilization_statistics':'''day policy MESS_nameplate_total_P_kW MESS_nameplate_total_S_kVA MESS_nameplate_total_E_kWh max_simultaneous_abs_P_kW max_net_discharge_P_kW max_net_charge_P_kW max_simultaneous_apparent_power_kVA P_nameplate_utilization_max S_nameplate_utilization_max mean_connected_MESS max_connected_MESS total_discharge_energy_kWh total_charge_energy_kWh absolute_P_energy_kWh max_unit_P_utilization max_unit_PCS_utilization B0_feeder_peak_kW MESS_nameplate_to_B0_peak_ratio MESS_actual_max_P_to_B0_peak_ratio'''.split()}

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def clean(v):
    if v is None:return NA
    if isinstance(v,(bool,np.bool_)):return 'TRUE' if v else 'FALSE'
    if isinstance(v,(np.integer,)):return int(v)
    if isinstance(v,(float,np.floating)) and not math.isfinite(v):return 'NaN'
    if isinstance(v,(dict,list,tuple,np.ndarray)):return json.dumps(v.tolist() if isinstance(v,np.ndarray) else v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return v

class Source:
    def __init__(self,info):
        self.info=info;self.root=Path(info['source_extracted']);self.used={};self.errors=[];self.warnings=[];self.missing=[]
        inventory=json.loads((Path(info['cache'])/'INVENTORY.json').read_text())
        self.inventory={r['path'].split('/',1)[1]:r for r in inventory}
    def path(self,rel):
        parts=PurePosixPath(str(rel).replace('\\','/')).parts
        if not parts or '..' in parts or ':' in str(rel) or str(rel).startswith(('/','\\')):raise ValueError('EXTERNAL_SOURCE_FORBIDDEN:'+str(rel))
        return self.root.joinpath(*parts)
    def exists(self,rel):return str(rel).replace('\\','/') in self.inventory
    def use(self,rel,expected=None):
        rel=str(rel).replace('\\','/');p=self.path(rel)
        if rel not in self.used:
            h=sha(p);assert h==self.inventory[rel]['sha256'],('EXTRACTED_SOURCE_CHANGED',rel)
            self.used[rel]=dict(source_inside_archive=rel,sha256=h,bytes=p.stat().st_size)
        if expected:assert self.used[rel]['sha256']==expected,('AUTHORITY_HASH_MISMATCH',rel)
        return p
    def j(self,rel):return json.loads(self.use(rel).read_text(encoding='utf-8-sig'))
    def npz(self,rel):
        with np.load(self.use(rel),allow_pickle=False) as z:return {k:z[k] for k in z.files}
    def parquet(self,rel):
        import pandas as pd
        return pd.read_parquet(self.use(rel))
    def resolve(self,original,expected=None):
        name=str(original).replace('\\','/')
        for marker in ('/frozen_artifacts/','/dayahead/'):
            if marker in name:
                rel=name.split(marker,1)[1];rel=marker.strip('/')+'/'+rel
                if self.exists(rel):self.use(rel,expected);return rel
        return None
    def check(self,test,label,detail=None):
        if not test:self.errors.append(dict(check=label,detail=detail))
        return bool(test)

def timestamp(day,slot):
    return (dt.datetime.fromisoformat(day+'T00:00:00+10:00')+dt.timedelta(minutes=15*slot)).isoformat()

def project_grid(s,folder,day,policy,trajectory,limits):
    z=s.npz(folder+'/OPENDSS_PHASE_ARRAYS.npz');summary=s.j(folder+'/OPENDSS_SUMMARY.json')
    if s.exists(folder+'/OPENDSS_OUTPUT_MANIFEST.json'):
        man=s.j(folder+'/OPENDSS_OUTPUT_MANIFEST.json')
        for n in ('OPENDSS_PHASE_ARRAYS.npz','OPENDSS_SUMMARY.json'):s.use(folder+'/'+n,man['files'][n]['sha256'])
    v=z['voltage_pu'];r=z['phase_current_loading_pu'];k=z['transformer_total_kva_loading_pu'];tx=z['branch_kinds']=='transformer';line=z['branch_kinds']=='line'
    assert v.shape[0]==r.shape[0]==96 and line.any() and tx.any()
    li=np.flatnonzero(line);ti=np.flatnonzero(tx);tol=limits['inherited_hard_comparison_tolerance']
    vc=(v<limits['hard_limits']['Vmin']-tol)|(v>limits['hard_limits']['Vmax']+tol)
    lc=r[:,line]>1+tol;tc=r[:,tx]>1+tol;kc=k[:,tx]>1+tol
    rows=[]
    for t in range(96):
        il=li[np.argmax(r[t,line])];it=ti[np.argmax(r[t,tx])];ik=ti[np.nanargmax(k[t,tx])];iv=int(v[t].argmin());av=int(v[t].argmax())
        rows.append(dict(day=day,policy=policy,trajectory=trajectory,slot=t,timestamp=timestamp(day,t),
            rho_line_max=float(r[t,il]),critical_line=str(z['branch_names'][il]),critical_line_phase=str(z['branch_phases'][il]),
            Vmin_pu=float(v[t,iv]),Vmin_bus=str(z['node_names'][iv]),Vmin_phase=str(z['node_phases'][iv]),
            Vmax_pu=float(v[t,av]),Vmax_bus=str(z['node_names'][av]),Vmax_phase=str(z['node_phases'][av]),
            tx_current_max_pu=float(r[t,it]),tx_current_asset=str(z['branch_names'][it]),tx_current_phase=str(z['branch_phases'][it]),
            tx_kVA_max_pu=float(k[t,ik]),tx_kVA_asset=str(z['branch_names'][ik]),tx_kVA_phase='TOTAL_ASSET',
            voltage_violation_count=int(vc[t].sum()),line_violation_count=int(lc[t].sum()),tx_current_violation_count=int(tc[t].sum()),tx_kVA_violation_count=int(kc[t].sum()),
            converged=bool(z['convergence'][t]),regulator_taps=z['regulator_taps'][t].tolist(),capacitor_states=z['capacitor_states'][t].tolist()))
    exact=dict(rho_max_AC=float(r[:,line].max()),Vmin_pu=float(v.min()),Vmax_pu=float(v.max()),transformer_phase_current_loading_max=float(r[:,tx].max()),transformer_total_kva_loading_max=float(np.nanmax(k[:,tx])))
    for name,value in exact.items():s.check(abs(value-summary[name])<1e-11,'GRID_SUMMARY_ARRAY_EQUALITY',[day,policy,trajectory,name])
    for name,val in [('voltage',vc),('line_current',lc),('transformer_current',tc),('transformer_kva',kc)]:s.check(int(val.sum())==summary[name+'_violation_count'],'GRID_VIOLATION_COUNT_EQUALITY',[day,policy,trajectory,name])
    s.check(int(z['convergence'].sum())==summary['convergence_count'],'GRID_CONVERGENCE_COUNT_EQUALITY',[day,policy,trajectory])
    if trajectory in ('DAYAHEAD_FRESH','ETA95_QSAFE_ACTUAL'):s.check(z['convergence'].all(),'FINAL_96_SLOT_CONVERGENCE',[day,policy,trajectory])
    return rows,summary,z

def grid_fields(summary,prefix,suffix='cells'):
    return {prefix+'rho_max':summary['rho_max_AC'],prefix+'Vmin_pu':summary['Vmin_pu'],prefix+'Vmax_pu':summary['Vmax_pu'],
        prefix+'tx_current_max_pu':summary['transformer_phase_current_loading_max'],prefix+'tx_kVA_max_pu':summary['transformer_total_kva_loading_max'],
        prefix+'voltage_violation_'+suffix:summary['voltage_violation_count'],prefix+'line_violation_'+suffix:summary['line_current_violation_count'],
        prefix+'tx_current_violation_'+suffix:summary['transformer_current_violation_count'],prefix+'tx_kVA_violation_'+suffix:summary['transformer_kva_violation_count'],
        prefix+'converged_slots':summary['convergence_count'],prefix+'physically_feasible':not summary['physical_violation']}

def extrema_to_summary(rows):
    d={}
    for key,kind,asset,phase in [('rho_line_max','critical_line','critical_line','critical_line_phase'),('Vmin_pu','Vmin','Vmin_bus','Vmin_phase'),('Vmax_pu','Vmax','Vmax_bus','Vmax_phase'),('tx_current_max_pu','critical_tx_current','tx_current_asset','tx_current_phase'),('tx_kVA_max_pu','critical_tx_kVA','tx_kVA_asset','tx_kVA_phase')]:
        x=(min if key=='Vmin_pu' else max)(rows,key=lambda r:r[key]);p='DA_'+kind
        d[p+('_bus' if kind in ('Vmin','Vmax') else '_asset' if 'tx_' in kind else '')]=x[asset]
        d[p+'_phase']=x[phase];d[p+'_slot']=x['slot']
        if kind not in ('Vmin','Vmax'):d[p+'_rho']=x[key]
    return d

def write_csv(out,name,rows,headers):
    headers=list(headers)+sorted(set().union(*(r.keys() for r in rows))-set(headers)) if rows else list(headers)
    p=out/(name+'.csv')
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows({k:clean(r.get(k,NA)) for k in headers} for r in rows)
    parts=[p]
    if p.stat().st_size>500_000_000:
        parts=[];f=None;size=0
        with p.open(encoding='utf-8-sig',newline='') as src:
            rd=csv.reader(src);head=next(rd)
            for row in rd:
                b=io.StringIO(newline='');csv.writer(b).writerow(row);line=b.getvalue();n=len(line.encode('utf-8'))
                if f is None or size+n>470_000_000:
                    if f:f.close()
                    q=out/f'{name}_part{len(parts)+1:03d}.csv';parts.append(q);f=q.open('w',encoding='utf-8-sig',newline='');csv.writer(f).writerow(head);size=3+len(','.join(head).encode('utf-8'))+2
                f.write(line);size+=n
        if f:f.close()
        p.unlink() # Only this newly-created CSV is replaced by its parts; no source writes.
    metadata=[];total=0
    for p in parts:
        with p.open(encoding='utf-8-sig',newline='') as f:
            rd=csv.DictReader(f);assert rd.fieldnames==headers;count=0;first=last=None
            for r in rd:
                assert None not in r and all(v is not None for v in r.values())
                key={k:r[k] for k in ('day','policy','trajectory','slot','mess_id','job_uid','domain','metric') if k in r}
                if first is None:first=key
                last=key;count+=1
        assert p.stat().st_size<=500_000_000
        metadata.append(dict(filename=p.name,row_count=count,byte_size=p.stat().st_size,SHA256=sha(p),first_key=first,last_key=last));total+=count
    assert total==len(rows)
    return dict(table=name,row_count=total,part_count=len(parts),columns=headers,parts=metadata)

def project_jobs(s,day,policy,decision,reference):
    refs={str(r['job_uid']):r for r in reference}; rows=[]
    for job in sorted(decision,key=lambda r:str(r['job_uid'])):
        uid=str(job['job_uid']);ref=refs[uid]
        # Archived canonical decisions use issue-relative coordinates, D midnight=24, end=120.
        # Residual is remaining compute service after the boundary, including migration interruption.
        def residual(j):
            return sum(max(0,float(seg['end'])-max(float(seg['start']),120.)) for seg in j['compute_segments'])
        rt,ot=residual(ref),residual(job)
        start,rs=float(job['start_slot'])-24,float(ref['start_slot'])-24
        initial=job.get('initial_AIDC',job['AIDC_site']);refinitial=ref.get('initial_AIDC',ref['AIDC_site'])
        row=dict(day=day,policy=policy,job_uid=uid,requested_GPU=job['requested_GPU'],reference_site=ref['AIDC_site'],optimized_site=job['AIDC_site'],
            reference_start_slot=rs,optimized_start_slot=start,start_shift_slots=start-rs,safe_duration_seconds=job['safe_duration_seconds'],safe_duration_slots=job['safe_duration_slots'],
            time_shifted=start!=rs,site_changed=job['AIDC_site']!=ref['AIDC_site'],checkpoint_migrated=bool(job.get('migration_selected',False)),
            reference_terminal_remaining_slots=rt,optimized_terminal_remaining_slots=ot,terminal_residual_delta_slots=ot-rt,
            cross_midnight_reference=rt>0,cross_midnight_optimized=ot>0,terminal_constraint_binding=ot==rt,
            selected=job['AIDC_site']!='UNASSIGNED',eligible_standby=job.get('eligible_standby',NA),state_at_issue=job['state_at_issue'],
            initial_site=initial,initial_site_changed=initial!=refinitial,final_site_changed=job['AIDC_site']!=ref['AIDC_site'],
            terminal_invariant_pass=ot<=rt+1e-9,terminal_definition='COMPUTE_SEGMENT_SERVICE_AFTER_ISSUE_SLOT_120',
            reference_end_slot=float(ref['end_slot'])-24,optimized_end_slot=float(job['end_slot'])-24)
        s.check(ot<=rt+1e-9,'AIDC_TERMINAL_RESIDUAL_INCREASE',dict(day=day,policy=policy,job_uid=uid,reference=rt,optimized=ot,migrated=row['checkpoint_migrated']))
        rows.append(row)
    return rows

def get_runtime(s,da,policy):
    report=da+'/POLICY_DAY_COMPUTE_REPORT.json'
    if s.exists(report):return s.j(report).get('optimization_seconds',NA)
    # A true zero is accepted only from a persisted computation field.
    for name in ('PLANNING_RESULT.json','optimization/OBJECTIVE_LEDGER.json'):
        obj=s.j(da+'/'+name)
        for d in (obj,obj.get('component_source',{})):
            if 'optimization_seconds' in d:return d['optimization_seconds']
    return NA

def build(s):
    tables={name:[] for name in SCHEMAS}; index=s.j('FINAL_RESULT_INDEX.json');package=s.j('PACKAGE_INFO.json')
    rev='frozen_artifacts/v41r4_restoration_revision_v1';run='frozen_artifacts/v41r4_may/loop_wall_v4'
    audit=s.j(rev+'/FINAL_AUDIT.json');s.check(audit['status']=='COMPLETE' and audit['counts']['total_accepted']==124,'FINAL_ARCHIVE_AUDIT_COMPLETE')
    rule=s.j(rev+'/RULE_FREEZE.json');mrel=s.resolve(rule['actual_method']['path'],rule['actual_method']['sha256']);assert mrel
    method=s.j(mrel);msha=s.used[mrel]['sha256'];refs={};ml_days=[];unit_sources=[];feeder_peaks={}
    for entry in sorted(index,key=lambda x:(x['day'],x['policy'])):
        day,policy=entry['day'],entry['policy'];da=f'{run}/{day}/{policy}/dayahead';ac=entry['final_actual'];acroot=ac.split('/replays/')[0];ci=f'{acroot}/common_inputs/{day}/{policy}'
        acceptance=s.j(entry['acceptance']);joint=s.resolve(acceptance['new_joint']['path'],acceptance['new_joint']['sha256']);assert joint,('MISSING_ACCEPTED_DECISION',day,policy)
        frozen=s.j(joint);decision=frozen['decision'];rec=s.j(ac+'/CANDIDATE_RECEIPT.json');done=s.j(ac+'/COMPLETE.json')
        s.check(acceptance['status']=='PASS' and rec['status']=='COMPLETE' and done['status']=='PASS','COMPLETED_UNIT',[day,policy])
        s.use(acroot+'/METHOD_FREEZE.json',rec['method_SHA']);s.check(rec['method_SHA']==msha,'UNIFORM_ACTUAL_METHOD',[day,policy])
        # Verify all file references used below against both archive manifest and final candidate receipt.
        for rel,h in rec['files'].items():
            name=rel.replace('\\','/')
            if name.endswith(('OPENDSS_SUMMARY.json','OPENDSS_PHASE_ARRAYS.npz','EXECUTION.npz','ACTUATOR.json','Q_CONTROL_EVENTS.json','C_VERSUS_B_AUDIT.json','COMPLETE.json')):s.use(ac+'/'+name,h)
        fresh=entry['acceptance'].rsplit('/',1)[0]+'/accepted_fresh' if acceptance['old_primary_fresh']=='FAIL' else da+'/fresh'
        control=policy in ('B0','B1');post=ac+('/CONTROL_COMMON_BINDING' if control else '/ETA95_QSAFE_ACTUAL');pre=post if control else ac+'/ETA95_ACTUAL'
        frows,fs,fz=project_grid(s,fresh,day,policy,'DAYAHEAD_FRESH',method)
        arows,asum,az=project_grid(s,post,day,policy,'ETA95_QSAFE_ACTUAL',method)
        prows,psum,pz=project_grid(s,pre,day,policy,'ETA95_ACTUAL',method)
        tables['05_grid_timeseries'].extend(frows+arows+prows)
        original_ref=s.j(ac+'/ORIGINAL_ACTUAL/REFERENCE.json')
        original_folder=None
        if original_ref.get('available'):
            original_folder=s.resolve(original_ref.get('authoritative_root','')+'/OPENDSS_PHASE_ARRAYS.npz')
            if original_folder:original_folder=original_folder.rsplit('/',1)[0]
            else:
                candidate=f'{run}/{day}/{policy}/actual'
                for ending in ('grid',''):
                    q=candidate+('/'+ending if ending else '')
                    if s.exists(q+'/OPENDSS_PHASE_ARRAYS.npz'):original_folder=q;break
            if original_folder:
                s.use(original_folder+'/OPENDSS_PHASE_ARRAYS.npz',original_ref.get('grid_SHA'))
                orows,_,_=project_grid(s,original_folder,day,policy,'ORIGINAL_ACTUAL',method);tables['05_grid_timeseries'].extend(orows)
        ledgerpath=da+'/optimization/OBJECTIVE_LEDGER.json';ledger=s.j(ledgerpath);vec=ledger['OBJECTIVE_VECTOR'];assert len(vec)==5
        if day not in refs:refs[day]=s.j(f'{run}/{day}/B0/dayahead/FROZEN_JOINT_DECISION.json')['decision']['AIDC_decision']
        jrows=project_jobs(s,day,policy,decision['AIDC_decision'],refs[day]);tables['06_aidc_decisions'].extend(jrows)
        cmds={(int(r['slot']),r['mess_id']):r for r in decision['MESS_trajectory']};ids=sorted({k[1] for k in cmds});assert len(cmds)==384 and len(ids)==4
        e=s.npz(post+'/EXECUTION.npz');b=s.npz(pre+'/EXECUTION.npz');actuator=s.j(post+'/ACTUATOR.json');act={(int(r['slot']),r['mess_id']):r for r in actuator['trajectory']}
        mess_audit=s.j(ci+'/ACTUAL_MESS_AUDIT.json');assert ids==mess_audit['ids'];moves=mess_audit['moves']
        for r in mess_audit['frozen_commands']:
            c=cmds[int(r['slot']),r['mess_id']];s.check(c['p_kw']==r['p_kw'] and c['q_kvar']==r['q_kvar'],'ACCEPTED_MESS_COMMAND_IDENTITY',[day,policy])
        s.check(done['binding']['AIDC_schedule_SHA']==acceptance['new_identity']['AIDC'],'ACCEPTED_AIDC_IDENTITY',[day,policy])
        P=e['P_EXEC'];Q=e['Q_EXEC'];dQ=Q-b['Q_EXEC'];mask=np.abs(dQ)>1e-9
        norm=np.hypot(P,Q)/method['pcs_kva'];angles=2*np.pi*np.arange(method['pcs_inner_polygon_faces'])/method['pcs_inner_polygon_faces']
        polygon=np.max(P[:,:,None]*np.cos(angles)+Q[:,:,None]*np.sin(angles),axis=2)/(method['pcs_kva']*np.cos(np.pi/method['pcs_inner_polygon_faces']))
        events=s.j(post+'/Q_CONTROL_EVENTS.json') if s.exists(post+'/Q_CONTROL_EVENTS.json') else []
        by_event={int(x['slot']):x for x in events}
        q_audit=s.j(post+'/C_VERSUS_B_AUDIT.json') if not control else None
        identity_p=bool(np.array_equal(P,b['P_EXEC']));identity_soc=bool(np.array_equal(e['energy_after'],b['energy_after']) and np.array_equal(e['SoC_after'],b['SoC_after']))
        identity_loc=bool(np.array_equal(e['locations'],b['locations']))
        if q_audit:
            s.check(q_audit['P_EXEC_bit_identical'] and identity_p,'Q_ONLY_P_IDENTITY',[day,policy]);s.check(q_audit['SoC_energy_bit_identical'] and identity_soc,'Q_ONLY_SOC_IDENTITY',[day,policy])
            identity_aidc=q_audit['B_binding']['AIDC_schedule_SHA']==q_audit['C_binding']['AIDC_schedule_SHA']==done['binding']['AIDC_schedule_SHA']
            identity_loc=identity_loc and q_audit['B_binding']['locations_SHA']==q_audit['C_binding']['locations_SHA']
        else:identity_aidc=done['binding']['AIDC_schedule_SHA']==acceptance['new_identity']['AIDC']
        s.check(done['scheduling_optimizer_calls']==0,'ACTUAL_SCHEDULING_OPTIMIZER_CALLS_ZERO',[day,policy])
        cohort='development' if day in method['development_days'] else 'holdout' if day in method['holdout_days'] else NA
        native_path=post+'/NATIVE_ACTUAL_STATE_CONTINUITY.json'
        native=s.j(native_path) if s.exists(native_path) else None
        names_path=f'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/replays/{day}/B0/CONTROL_COMMON_BINDING/NATIVE_ACTUAL_STATE_CONTINUITY.json'
        names=s.j(names_path)['regulators'] if s.exists(names_path) else None
        for t in range(96):
            ev=by_event.get(t,{});start_taps=ev.get('start_taps',NA)
            if native:start_taps=native['start_taps'][t]
            for m,mid in enumerate(ids):
                c=cmds[t,mid];a=act[t,mid];move=next((v for v in moves if v['mess_id']==mid and float(v['departure_slot'])<=t<float(v['actual_connection_ready_slot'])),None)
                row=dict(day=day,policy=policy,slot=t,timestamp=timestamp(day,t),mess_id=mid,location_service_id=a['actual_service_id'],connected=a['connected'],
                    moving=bool(move and t<float(move['actual_arrival_slot'])),origin_service_id=move['origin_service_id'] if move else c.get('origin_service_id'),
                    destination_service_id=move['destination_service_id'] if move else c.get('destination_service_id'),departure_slot=move['departure_slot'] if move else c.get('departure_slot'),
                    arrival_slot=move['actual_arrival_slot'] if move else None,P_DA_kW=c['p_kw'],Q_DA_kvar=c['q_kvar'],
                    P_Actual_kW=float(P[t,m]),Q_Actual_kvar=float(Q[t,m]),delta_Q_kvar=float(dQ[t,m]),SoC_kWh=float(e['energy_after'][t,m]),SoC_pct=float(e['SoC_after'][t,m]*100),
                    PCS_norm_utilization=float(norm[t,m]),PCS_polygon_utilization=float(polygon[t,m]),Q_intervention=bool(mask[t,m]),
                    Q_intervention_status=ev.get('status','CONTROL_COMMON_BINDING_NO_Q_CONTROL' if control else NA),regulator_taps_start=start_taps,regulator_taps_final=az['regulator_taps'][t].tolist())
                for k,tap in enumerate(az['regulator_taps'][t]):row[f'{names[k] if names else "regulator_index_"+str(k)}_tap_final']=float(tap)
                if isinstance(start_taps,list):
                    for k,tap in enumerate(start_taps):row[f'{names[k] if names else "regulator_index_"+str(k)}_tap_start']=float(tap)
                tables['04_mess_timeseries'].append(row)
        selected=[r for r in jrows if r['selected']];runtime=get_runtime(s,da,policy)
        da_P=np.array([[cmds[t,mid]['p_kw'] for mid in ids] for t in range(96)])
        departures={(r['mess_id'],r.get('departure_slot')) for r in decision['MESS_trajectory'] if r.get('departure_slot') is not None}
        drow=dict(day=day,policy=policy,completion_status='COMPLETE',**dict(zip(SCHEMAS['01_policy_day_summary'][3:8],vec)),**grid_fields(fs,'DA_','count'),**extrema_to_summary(frows),
            DA_physical_outcome='PASS' if not fs['physical_violation'] else 'FAIL',AIDC_selected_job_count=len(selected),AIDC_eligible_job_count=sum(bool(r['eligible_standby']) for r in jrows),
            temporal_shift_count=sum(r['time_shifted'] for r in jrows),spatial_relocation_count=sum(r['initial_site_changed'] for r in jrows),checkpoint_migration_count=sum(r['checkpoint_migrated'] for r in jrows),
            MESS_vehicle_count=len(ids),MESS_dispatch_slots=int(np.count_nonzero(np.abs(da_P)>1e-9)),MESS_move_count=len(departures),MESS_abs_P_energy_kWh=float(np.abs(da_P).sum()*.25),optimization_runtime_s=runtime,
            final_site_change_count=sum(r['final_site_changed'] for r in jrows),terminal_residual_violation_jobs=sum(not r['terminal_invariant_pass'] for r in jrows),
            primary_fresh_status=acceptance['old_primary_fresh'],restoration_status=acceptance['local_restoration'],full_PQ_fallback=acceptance['full_PQ_fallback'])
        tables['01_policy_day_summary'].append(drow)
        h4=s.j(ci+'/H4_SCORE.json');rate=s.j(ci+'/ACTUAL_EXECUTION_RATE.json');delay=s.j(ci+'/ACTUAL_EXECUTION_DELAY_KPIS.json')
        ar=dict(day=day,policy=policy,completion_status='COMPLETE',actual_method=done['method_version'],**grid_fields(asum,'Actual_'),
            Actual_H4_shortfall_mean_GPUh=float(np.mean(h4['realized_shortfall_GPUh'])),Actual_H4_shortfall_max_GPUh=float(np.max(h4['realized_shortfall_GPUh'])),execution_rate=rate['START_EXECUTION_RATE'],
            Actual_optimizer_calls=done['scheduling_optimizer_calls'],decision_SHA=acceptance['new_joint']['sha256'],AIDC_decision_SHA=done['binding']['AIDC_schedule_SHA'],
            development_or_holdout=cohort,final_frozen_method_evidence=rec['method_SHA'],**{'execution_'+k:v for k,v in rate.items()},**delay)
        ar['decision_SHA']=frozen['decision_SHA']
        for k in ('voltage','line','tx_current','tx_kVA'):ar['Actual_'+k+'_violation_day']=ar['Actual_'+k+'_violation_cells']>0
        tables['02_actual_summary'].append(ar)
        qr=dict(day=day,policy=policy,development_or_holdout=cohort,Q_intervention_slots=done.get('intervention_slots',int(mask.any(axis=1).sum())),
            Q_unresolved_slots=done.get('ROBUST_Q_ONLY_UNRESOLVED_slots',0 if control else NA),
            sum_abs_delta_Q_kvar=float(np.abs(dQ).sum()),mean_abs_delta_Q_all_vehicle_slots_kvar=float(np.abs(dQ).mean()),
            mean_abs_delta_Q_changed_vehicle_slots_kvar=float(np.abs(dQ)[mask].mean()) if mask.any() else float('nan'),max_abs_delta_Q_kvar=float(np.abs(dQ).max()),changed_Q_vehicle_slots=int(mask.sum()),
            maximum_PCS_norm_utilization=done['maximum_PCS_norm_utilization'],maximum_PCS_polygon_utilization=done['maximum_PCS_polygon_utilization'],
            Q_runtime_s=NA,Q_search_runtime_s=sum(e.get('search_runtime_seconds',0) for e in events) if events else NA,
            P_EXEC_identity=identity_p,SoC_energy_identity=identity_soc,AIDC_decision_identity=identity_aidc,route_location_identity=identity_loc,
            **grid_fields(psum,'preQ_'),**grid_fields(asum,'postQ_'),Q_delta_rho=asum['rho_max_AC']-psum['rho_max_AC'],Q_delta_voltage_cells=asum['voltage_violation_count']-psum['voltage_violation_count'],
            global_optimum_proven=False,paper_facing_interpretation=method['paper_facing_wording'],final_method_SHA=msha,
            control_common_binding=control)
        qr['Q_intervention_rate']=qr['Q_intervention_slots']/96;qr['Q_unresolved_day']=qr['Q_unresolved_slots']>0 if qr['Q_unresolved_slots']!=NA else NA
        tables['03_q_correction_summary'].append(qr)
        conn=np.array([[bool(act[t,mid]['connected']) for mid in ids] for t in range(96)])
        ratios=np.divide(e['energy_after'],e['SoC_after'],out=np.full_like(e['energy_after'],np.nan),where=e['SoC_after']!=0);capacity=float(np.nanmedian(ratios))
        assert np.allclose(ratios,capacity,rtol=0,atol=1e-8)
        ur=dict(day=day,policy=policy,MESS_nameplate_total_P_kW=len(ids)*method['active_power_limit_kw'],MESS_nameplate_total_S_kVA=len(ids)*method['pcs_kva'],MESS_nameplate_total_E_kWh=len(ids)*capacity,
            max_simultaneous_abs_P_kW=float(np.abs(P).sum(axis=1).max()),max_net_discharge_P_kW=float(np.maximum(P.sum(axis=1),0).max()),max_net_charge_P_kW=float(np.maximum(-P.sum(axis=1),0).max()),
            max_simultaneous_apparent_power_kVA=float(np.hypot(P,Q).sum(axis=1).max()),mean_connected_MESS=float(conn.sum(axis=1).mean()),max_connected_MESS=int(conn.sum(axis=1).max()),
            total_discharge_energy_kWh=float(np.maximum(P,0).sum()*.25),total_charge_energy_kWh=float(np.maximum(-P,0).sum()*.25),absolute_P_energy_kWh=float(np.abs(P).sum()*.25),
            max_unit_P_utilization=float(np.abs(P).max()/method['active_power_limit_kw']),max_unit_PCS_utilization=float(norm.max()),B0_feeder_peak_kW=NA,MESS_nameplate_to_B0_peak_ratio=NA,MESS_actual_max_P_to_B0_peak_ratio=NA,trajectory='ETA95_QSAFE_ACTUAL')
        ur['P_nameplate_utilization_max']=ur['max_simultaneous_abs_P_kW']/ur['MESS_nameplate_total_P_kW'];ur['S_nameplate_utilization_max']=ur['max_simultaneous_apparent_power_kVA']/ur['MESS_nameplate_total_S_kVA']
        tables['10_mess_utilization_statistics'].append(ur)
        if policy=='B0':ml_days.append((day,da,ci,h4))
        unit_sources.append(dict(day=day,policy=policy,objective=ledgerpath,accepted_joint=joint,final_Fresh=fresh,final_Actual=post,pre_Q=pre,common_inputs=ci,original_Actual=original_folder))
        if policy=='B3':print('PROJECTED',day,flush=True)
    return tables,method,unit_sources,ml_days

def authority(s,tables,method,ml_days):
    _,da,ci,_=ml_days[0];ml=s.j(da+'/ml/ML_SNAPSHOT.json');ma=s.j(ci+'/ACTUAL_MESS_AUDIT.json')
    rule=s.j('frozen_artifacts/v41r4_restoration_revision_v1/RULE_FREEZE.json')
    capacity=np.asarray(ml['future_service_capacity_gpu']);assert capacity.shape[0]==96
    s.check(np.all(capacity.sum(axis=1)==capacity.sum(axis=1)[0]),'FIXED_AIDC_CAPACITY')
    # These constants are parsed from the archived frozen restoration rule, not imported from code.
    import re
    energy=re.search(r'energy (\d+)\.\.(\d+)kWh, E0=ET=(\d+)kWh',rule['fallback'])
    first=tables['10_mess_utilization_statistics'][0];dt_manifest=s.parquet(da+'/grid/FEEDER_SYSTEM_96.parquet')
    timestamps=dt_manifest['timestamp'];interval=(timestamps.iloc[1]-timestamps.iloc[0]).total_seconds()/60
    physics_record=s.j(da+'/authority/AUTHORITY_MANIFEST.json')
    row=dict(campaign_version='V41R4',evaluation_month='2025-05',expected_days=31,expected_policies=4,expected_policy_days=124,completed_policy_days=len(tables['01_policy_day_summary']),
        alpha_BG=method['alpha_BG'],AIDC_equivalent_GPU=int(capacity.sum(axis=1)[0]),AIDC_site_count=capacity.shape[1],MESS_count=len(ma['ids']),
        MESS_Pmax_kW_per_unit=method['active_power_limit_kw'],MESS_Smax_kVA_per_unit=method['pcs_kva'],MESS_Emax_kWh_per_unit=first['MESS_nameplate_total_E_kWh']/len(ma['ids']),
        MESS_Emin_kWh_per_unit=int(energy[1]) if energy else NA,MESS_initial_kWh_per_unit=list(ma['initial_energy'].values())[0],MESS_terminal_kWh_per_unit=int(energy[3]) if energy else NA,
        eta_charge=method['eta_charge'],eta_discharge=method['eta_discharge'],PCS_polygon_faces=method['pcs_inner_polygon_faces'],
        grid_model=NA,grid_slots_per_day=len(dt_manifest),grid_interval_min=interval,voltage_lower_pu=method['hard_limits']['Vmin'],voltage_upper_pu=method['hard_limits']['Vmax'],
        traffic_links=NA,traffic_slots_per_day=NA,traffic_interval_min=NA,traffic_model_id=NA,runtime_model_id=ml['runtime_model_id'],H4_model_id=ml['H4_model_id'],
        source_archive_filename=Path(s.info['source_archive']).name,source_archive_size_bytes=s.info['source_archive_size_bytes'],source_archive_SHA256=s.info['source_archive_SHA256'],
        MESS_operating_Emax_kWh_per_unit=int(energy[2]) if energy else NA,repository_commit_SHA=physics_record['scientific_commit'],method_SHA=rule['actual_method']['sha256'],
        grid_timestamp_timezone=str(timestamps.dt.tz),MESS_nominal_capacity_definition='energy_after/SoC_after from archived EXECUTION; verified all nonzero cells')
    tables['00_experiment_authority']=[row]
    s.missing.append(dict(fields=['grid_model','traffic_links','traffic_slots_per_day','traffic_interval_min','traffic_model_id'],reason='No complete final grid/traffic model identification or full traffic graph authority is established by the packaged final result index. External provenance targets intentionally not read.'))

def ml_metrics(s,tables,ml_days,unit_sources):
    rows=[];runtime=[];h4=[];rsources=[];hsources=[];route_samples={};route_sources=[];runtime_missing=0
    for day,da,ci,score in ml_days:
        ml=s.j(da+'/ml/ML_SNAPSHOT.json');replay=s.j(ci+'/ACTUAL_JOB_REPLAY.json')
        pred=ml['PENDING_JOB_Q90_SECONDS'];dur=ml['PENDING_JOB_DURATION_SLOTS'];jobs={str(r['job_uid']):r for r in replay['job_ledger']}
        for uid,q90 in pred.items():
            j=jobs.get(str(uid));label=j.get('actual_runtime_seconds') if j else None
            if j and j['state_at_issue']=='PENDING' and isinstance(label,(int,float)) and math.isfinite(label) and label>0 and j.get('actual_runtime_source')=='KESTREL_OBSERVED_END_MINUS_START':runtime.append((float(q90),float(label),float(dur[uid])*900))
            else:runtime_missing+=1
        rp=np.asarray(ml['H4_RAW_R85_B2_GPUh'],dtype=float);cp=np.asarray(ml['H4_ACTIONABLE_RESERVE_GPUh'],dtype=float);label=np.asarray(score['realized_H4_GPUh'],dtype=float)
        assert rp.shape==cp.shape==label.shape==(81,)
        hist=ml['H4_CAP_HIST'];phys=np.asarray(ml['H4_CAP_PHYS'])
        h4.extend(zip(rp,cp,label,rp>hist,np.minimum(rp,hist)>phys))
        rsources.extend([da+'/ml/ML_SNAPSHOT.json',ci+'/ACTUAL_JOB_REPLAY.json']);hsources.extend([da+'/ml/ML_SNAPSHOT.json',ci+'/H4_SCORE.json'])
    for u in unit_sources:
        if u['policy'] not in ('B2','B3'):continue
        m=s.j(u['common_inputs']+'/ACTUAL_MESS_AUDIT.json');j=s.j(u['accepted_joint'])['decision'];cmd={(r['mess_id'],r['slot']):r for r in j['MESS_trajectory']}
        for move in m['moves']:
            c=cmd.get((move['mess_id'],move['departure_slot']))
            if c and all(k in c for k in ('route_q50_eta_sec','route_safe_eta_sec')):
                key=(u['day'],move['departure_slot'],move.get('route_SHA'),move['actual_eta_seconds'])
                route_samples[key]=(c['route_q50_eta_sec'],c['route_safe_eta_sec'],move['actual_eta_seconds'])
        route_sources.extend([u['common_inputs']+'/ACTUAL_MESS_AUDIT.json',u['accepted_joint']])
    def add(domain,metric,value,unit,scope,n,source):
        rows.append(dict(domain=domain,metric=metric,value=value,unit=unit,evaluation_scope=scope,N=n,source_inside_archive=source))
    if runtime:
        a=np.array(runtime);p,y,slots=a.T;err=y-p;scope='31-day unique (day, pending job_uid) prediction-label pairs; B0 label authority; repeated jobs across issue days retained'
        src='MANIFEST.json: metric_source_groups.runtime'
        for name,val,unit in [('runtime_Q90_empirical_coverage',np.mean(y<=p),'fraction'),('runtime_reservation_15min_coverage',np.mean(y<=slots),'fraction'),('runtime_pinball_loss_Q90',np.mean(np.maximum(.9*err,-.1*err)),'s'),('runtime_MAE_s',np.mean(np.abs(err)),'s'),('runtime_median_AE_s',np.median(np.abs(err)),'s'),('runtime_underprediction_rate',np.mean(err>0),'fraction'),('runtime_mean_underprediction_s',np.mean(err[err>0]) if (err>0).any() else float('nan'),'s')]:add('runtime',name,float(val),unit,scope,len(a),src)
        add('runtime','runtime_unmatched_or_unavailable_label_count',runtime_missing,'job-day pairs',scope,len(runtime)+runtime_missing,src)
    if h4:
        a=np.array(h4);p,c,y,hist,phys=a.T;short=np.maximum(y-c,0);scope='31 days x 81 archived H4 windows, policy-independent realized labels; raw R85_B2 forecast for MAE'
        for name,val,unit in [('H4_raw_coverage',np.mean(y<=p),'fraction'),('H4_actionable_capped_coverage',np.mean(y<=c),'fraction'),('H4_MAE_GPUh',np.mean(np.abs(y-p)),'GPUh'),('H4_mean_shortfall_GPUh',np.mean(short),'GPUh'),('H4_P90_shortfall_GPUh',np.quantile(short,.9),'GPUh'),('H4_historical_cap_activation_count',int(hist.sum()),'windows'),('H4_physical_cap_activation_count',int(phys.sum()),'windows')]:add('H4',name,val,unit,scope,len(a),'MANIFEST.json: metric_source_groups.H4')
    for metric in ('link_Q50_MAE_s','link_Q50_WAPE_pct','link_Q90_empirical_coverage','quantile_crossings'):
        add('traffic',metric,NA,'s' if metric.endswith('_s') else 'pct' if metric.endswith('_pct') else 'count' if metric=='quantile_crossings' else 'fraction','Full link prediction-label validation not packaged with a bound authority',NA,NA)
    if route_samples:
        a=np.array(list(route_samples.values()));p,safe,y=a.T
        for metric,val,unit in [('route_ETA_MAE_s',np.mean(np.abs(p-y)),'s'),('SafeETA_coverage',np.mean(y<=safe),'fraction'),('SafeETA_mean_margin_s',np.mean(safe-y),'s')]:add('traffic',metric,float(val),unit,'Final selected B2/B3 routes, deduplicated day/departure/route/label; not full-link ML validation',len(a),'MANIFEST.json: metric_source_groups.traffic_routes')
    else:
        for metric in ('route_ETA_MAE_s','SafeETA_coverage','SafeETA_mean_margin_s'):add('traffic',metric,NA,NA,'No matched archived route prediction/realized label',0,NA)
    tables['07_ml_performance']=rows
    s.metric_groups=dict(runtime=sorted(set(rsources)),H4=sorted(set(hsources)),traffic_routes=sorted(set(route_sources)))
    s.missing.append(dict(fields=['link_Q50_MAE_s','link_Q50_WAPE_pct','link_Q90_empirical_coverage','quantile_crossings'],reason='The archive lacks an identified full-link validation authority with frozen quantile predictions and matched realized labels. Selected-route metrics are separately scoped.'))

def aggregates(s,tables):
    daily={(r['day'],r['policy']):r for r in tables['01_policy_day_summary']};actual={(r['day'],r['policy']):r for r in tables['02_actual_summary']}
    paired=sorted(set.intersection(*({d for d,p in daily if p==pol} for pol in POLICIES)))
    s.check(len(paired)==31,'SAME_31_PAIRED_DAYS');s.paired=paired
    def stat(vals):
        if any(isinstance(v,str) for v in vals):return {k:NA for k in ('mean','median','P90','min','max')}
        v=np.asarray(vals);return dict(mean=float(v.mean()),median=float(np.median(v)),P90=float(np.quantile(v,.9)),min=float(v.min()),max=float(v.max()))
    for p in POLICIES:
        ds=[daily[d,p] for d in paired];ac=[actual[d,p] for d in paired];r=dict(policy=p,N_days=len(paired))
        for prefix,values in [('P1',[x['P1_rho_planning'] for x in ds]),('DA_rho',[x['DA_rho_max'] for x in ds]),('Actual_rho',[x['Actual_rho_max'] for x in ac])]:r.update({prefix+'_'+k:v for k,v in stat(values).items()})
        r.update(Vmin_global=min(x['Actual_Vmin_pu'] for x in ac),Vmax_global=max(x['Actual_Vmax_pu'] for x in ac),voltage_violation_days=sum(x['Actual_voltage_violation_day'] for x in ac),thermal_violation_days=sum(any(x['Actual_'+k+'_violation_day'] for k in ('line','tx_current','tx_kVA')) for x in ac),Actual_H4_shortfall_mean_GPUh=float(np.mean([x['Actual_H4_shortfall_mean_GPUh'] for x in ac])))
        for out,field in [('temporal_shift_total','temporal_shift_count'),('spatial_relocation_total','spatial_relocation_count'),('checkpoint_migration_total','checkpoint_migration_count'),('MESS_dispatch_slots_total','MESS_dispatch_slots'),('MESS_moves_total','MESS_move_count'),('MESS_abs_P_energy_kWh_total','MESS_abs_P_energy_kWh')]:r[out]=sum(x[field] for x in ds)
        st=stat([x['optimization_runtime_s'] for x in ds])
        for k in ('mean','median','max'):r['optimization_runtime_'+k+'_s']=st[k]
        r['terminal_residual_violation_jobs']=sum(x['terminal_residual_violation_jobs'] for x in ds)
        tables['08_policy_aggregate_statistics'].append(r)
    for day in paired:
        r=dict(day=day)
        for measure,field,source in [('P1','P1_rho_planning',daily),('DA_rho','DA_rho_max',daily),('Actual_rho','Actual_rho_max',actual)]:
            for p in POLICIES:r[p+'_'+measure]=source[day,p][field]
            for p,base in [('B1','B0'),('B2','B0'),('B3','B0'),('B3','B2')]:
                a,b=r[p+'_'+measure],r[base+'_'+measure];r[f'{p}_minus_{base}_{measure}']=a-b
                name=f'{p}_'+('incremental_' if base=='B2' else '')+f'improvement_pct_vs_{base}'+('' if measure=='P1' else '_'+measure)
                r[name]=(b-a)/b*100 if b!=0 else float('nan')
        tables['09_paired_policy_comparisons'].append(r)

def feeder_metrics(s,tables,unit_sources):
    peaks={}
    for u in unit_sources:
        if u['policy']!='B0':continue
        path=f'frozen_artifacts/v41r4_may/loop_wall_v4/{u["day"]}/B0/actual/grid/FEEDER_SYSTEM_96.parquet'
        if not s.exists(path):continue
        frame=s.parquet(path)
        final=s.npz(u['final_Actual']+'/OPENDSS_PHASE_ARRAYS.npz');line=final['branch_kinds']=='line'
        rho=final['phase_current_loading_pu'][:,line].max(axis=1)
        # Stale grid tables in historical subfolders must not supply the final feeder scale.
        if 'feeder_import_P_kW' in frame and len(frame)==96 and np.allclose(frame['rho_max'],rho,rtol=0,atol=1e-10) and np.allclose(frame['Vmax_pu'],final['voltage_pu'].max(axis=1),rtol=0,atol=1e-10):peaks[u['day']]=float(frame['feeder_import_P_kW'].max())
    for row in tables['10_mess_utilization_statistics']:
        if row['day'] in peaks:
            peak=peaks[row['day']];row['B0_feeder_peak_kW']=peak;row['MESS_nameplate_to_B0_peak_ratio']=row['MESS_nameplate_total_P_kW']/peak if peak else float('nan');row['MESS_actual_max_P_to_B0_peak_ratio']=row['max_simultaneous_abs_P_kW']/peak if peak else float('nan')
    if len(peaks)<31:s.missing.append(dict(fields=['B0_feeder_peak_kW','MESS_nameplate_to_B0_peak_ratio','MESS_actual_max_P_to_B0_peak_ratio'],reason='Historical FEEDER_SYSTEM_96 tables do not match the final Actual voltage/loading trajectory, or are absent. Final NPZ arrays do not provide source-terminal active power.',unavailable_days=[d for d in s.paired if d not in peaks]))

def final_validation(s,tables,units):
    expected={(f'2025-05-{d:02d}',p) for d in range(1,32) for p in POLICIES}
    for name in ('01_policy_day_summary','02_actual_summary','03_q_correction_summary','10_mess_utilization_statistics'):
        keys=[(r['day'],r['policy']) for r in tables[name]]
        s.check(len(keys)==124 and len(set(keys))==124 and set(keys)==expected,'124_UNIQUE_POLICY_DAYS',name)
    s.check(len(tables['04_mess_timeseries'])==47616,'MESS_TIMESERIES_47616_ROWS')
    s.check(len(tables['09_paired_policy_comparisons'])==31,'PAIRED_31_ROWS')
    for x in tables['08_policy_aggregate_statistics']:s.check(x['N_days']==31,'AGGREGATE_N31',x['policy'])
    # Cross-check against the archive's final revision audit (not the historical partial report).
    audit=s.j('frozen_artifacts/v41r4_restoration_revision_v1/FINAL_AUDIT.json');da={(r['day'],r['policy']):r for r in tables['01_policy_day_summary']}
    for r in audit['rows']:
        current=da[r['day'],r['policy']]
        for a,b in [('DA_rho_max','max_line'),('DA_Vmin_pu','final_Vmin'),('DA_Vmax_pu','final_Vmax'),('DA_tx_current_max_pu','max_transformer_current'),('DA_tx_kVA_max_pu','max_transformer_kva')]:s.check(current[a]==r[b],'FINAL_AUDIT_CROSSCHECK',[r['day'],r['policy'],a])
    s.missing.extend([
        dict(fields=['Q_runtime_s'],reason='No separately identified end-to-end Q-only wall-clock authority; recorded search_runtime_seconds is exported separately without relabeling total replay time.'),
        dict(fields=['mean_abs_delta_Q_changed_vehicle_slots_kvar'],reason='NaN when the changed-vehicle-slot denominator is zero; it is not replaced by zero.'),
        dict(fields=['origin_service_id','destination_service_id','departure_slot','arrival_slot'],reason='NOT_AVAILABLE denotes no associated move in that slot; no arrival is inferred from another scenario.')])

def finalize(out,s,tables,method,units):
    sortkeys={name:('day','policy') for name in tables}
    sortkeys.update({'04_mess_timeseries':('day','policy','slot','mess_id'),'05_grid_timeseries':('day','policy','trajectory','slot'),'06_aidc_decisions':('day','policy','job_uid'),'07_ml_performance':('domain','metric'),'08_policy_aggregate_statistics':('policy',),'09_paired_policy_comparisons':('day',)})
    metadata=[]
    for name,rows in tables.items():
        rows.sort(key=lambda r:tuple(r.get(k,'') for k in sortkeys[name]))
        metadata.append(write_csv(out,name,rows,SCHEMAS[name]))
        print('CSV',name,len(rows),flush=True)
    # Verify source immutability for every file actually read in this projection.
    for rel,record in s.used.items():assert sha(s.path(rel))==record['sha256'],('SOURCE_CHANGED_AFTER_EXPORT',rel)
    end_sha=sha(s.info['source_archive']);assert end_sha==s.info['source_archive_SHA256'],'ARCHIVE_CHANGED_AFTER_EXPORT'
    stat=Path(s.info['source_archive']).stat();assert stat.st_mtime_ns==s.info['archive_mtime_ns'],'ARCHIVE_MTIME_CHANGED'
    nulls={}
    for name,rows in tables.items():
        columns=set(SCHEMAS[name]).union(*(r.keys() for r in rows))
        nulls[name]={k:sum(r.get(k,NA) is None or (isinstance(r.get(k,NA),str) and r.get(k,NA)==NA) for r in rows) for k in sorted(columns)}
        nulls[name]={k:n for k,n in nulls[name].items() if n}
    status='V41R4_FINAL_ARCHIVE_PAPER_CSV_EXPORT_FAIL_CLOSED' if s.errors else 'V41R4_FINAL_ARCHIVE_PAPER_CSV_EXPORT_PASS'
    total=sum(p['byte_size'] for x in metadata for p in x['parts']);reduction=(1-total/s.info['source_archive_size_bytes'])*100
    scripts={p.name:sha(p) for p in sorted((out/'_scripts').glob('*.py'))}
    errors=collections.Counter(e['check'] for e in s.errors)
    manifest=dict(status=status,exporter_version=VERSION,export_timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        source_archive=s.info['source_archive'],source_archive_size_bytes=s.info['source_archive_size_bytes'],source_archive_SHA256=end_sha,
        archive_file_count=s.info['archive_file_count'],archive_uncompressed_bytes=s.info['raw_bytes'],expected_days=31,expected_policies=4,expected_policy_days=124,
        detected_days=31,detected_policy_days=124,completed_policy_days=124,campaign_status='COMPLETE',missing_policy_days=[],duplicate_policy_days=[],
        CSV_files=metadata,total_CSV_bytes=total,reduction_pct_vs_archive=reduction,NOT_AVAILABLE_metrics=s.missing,NOT_AVAILABLE_cell_counts=nulls,
        validation=dict(status='FAIL' if s.errors else 'PASS',failure_counts=dict(errors),failures=s.errors,checks=['archive completeness and file hashes','124 final acceptance/Actual bindings','P1-P5 vector length 5','separate planning P1 and exact Fresh rho','96-slot final Fresh/Actual convergence','array extrema and violation counts equal persisted summaries','terminal remaining compute service invariant','Q-only P/SoC and frozen AIDC/route identities','all 31 paired dates','CSV schema/row count round trip','500MB limit','archive/source SHA unchanged']),
        external_workspace_read_count=0,raw_archive_unchanged=True,solver_calls=0,optimization_calls=0,ML_training_calls=0,
        source_artifacts=list(s.used.values()),unit_source_map=units,metric_source_groups=getattr(s,'metric_groups',{}),exporter_scripts_SHA256=scripts,
        warnings=s.warnings+['CSV completion_status describes the archived campaign completion, not the export validation. Consult top-level status before publication.',
            'Transformer kVA is an asset-total metric repeated across phase rows by source; violation counts preserve the original phase-row counting convention.',
            'B0/B1 use the same CONTROL_COMMON_BINDING arrays for pre/post Q trajectories; no additional Q-control replay was invented.',
            'Legacy absolute source paths inside archive receipts were only mapped to archive members; never opened on the host.',
            'Historical PARTIAL FULL_MAY_SUMMARY is not the final data source and is not used for aggregates.'],
        definitions=dict(terminal_remaining='Sum max(0, segment_end - max(segment_start,120)) over canonical compute segments. B0 same-day common reference. Includes post-boundary work of migrating RUNNING jobs.',
            slots='Grid/MESS slots 0..95. Job slots converted from archived issue-time origin by subtracting 24 (D00). Timestamps preserve the archive AEST operating day as +10:00.',
            spatial_relocation='Changed initial execution site versus same-day B0; checkpoint migration counted separately. Final-site changes also exported.',
            MESS_dispatch_slots='Vehicle-slots with |accepted DA P| > 1e-9 kW; Q-only activity remains in time series and PCS utilization.',
            SoC='Actual slot-end energy and fraction; SoC_pct=100*fraction.',
            Q_delta='Final Q-safe executed Q minus the pre-Q eta95 executed Q; threshold 1e-9 kvar for changed-vehicle-slot counts.',
            global_optimum='FALSE: '+method['paper_facing_wording'],
            paired_statistics='All four policies use the identical 31 dates; numpy linear quantile P90. No failed pre-Q trajectory or terminal violation is dropped.'))
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=clean),encoding='utf-8')
    if s.errors:(out/'VALIDATION_FAILURES.json').write_text(json.dumps(s.errors,indent=2),encoding='utf-8')
    purposes=['Case-study parameters and source archive authority','Main B0/B1/B2/B3 Day-Ahead performance','Realized-operation evaluation','Q-only AC safety correction','MESS P/Q/SoC/location/tap figures','Line loading, voltage, transformer and regulator figures','Temporal shifting / spatial relocation / migration','ML performance','Main results table','Paired B0/B1/B2/B3 analysis','MESS scale/utilization reviewer analysis']
    readme=['# V41R4 final-archive paper CSV export','',status,'','This paper-data export is a projection of the supplied final raw archive.','It does not replace the full phase-resolved scientific authority.','',
        'All 124 archived completed policy-days are included. No workspace result was read and no optimizer, OpenDSS, SUMO or training was run.',
        'The final result index selects restored May31 B2 and new May31 B3 from the selective Actual namespace, and the other 122 from the accepted robust V2 namespace.','',
        '## Files','']
    readme.extend(f'- `{name}.csv`: {purpose}.' for name,purpose in zip(SCHEMAS,purposes))
    readme.extend(['','## Definitions and use','','UTF-8 BOM, comma separated, TRUE/FALSE booleans, full Python floating-point representation. NOT_AVAILABLE is unavailable/not applicable; NaN is mathematically undefined. Slots are zero-based. All parts repeat headers.',
        'Planning P1, final Fresh line loading, and final Actual line loading are distinct. Line loading excludes transformers. Transformer total-kVA extrema have phase=TOTAL_ASSET.',
        'Original Actual and pre-Q eta95 results in 05 are explicitly labeled historical/pre-control trajectories and do not replace final Actual in 02, 08 or 09.',
        'B0/B1 pre/post Q rows share the verified control binding. Q-only MESS activity is preserved even when active-power dispatch is zero.',
        'AIDC residual is actual remaining canonical compute-segment service after the D-day boundary, compared with same-day B0. Migration interruptions are included; no invariant failure is masked by using start+safe_duration alone.',
        'Traffic route metrics cover selected executed routes, not the full traffic-link model validation. Runtime and H4 metrics are post-hoc comparisons of archived predictions and realized labels only.',
        'MANIFEST.json supplies source hashes, per-unit paths, field availability, precise definitions, and all validation failures. A FAIL_CLOSED export must not be described as validated paper results.','',
        '## Re-run','','Requires Python, numpy, pandas and a Parquet engine such as pyarrow. The scripts never import research project modules. Existing completed/failed export folders are preserved; a new timestamped directory is used.',
        '```text','python _scripts/export_v41r4_final_archive_to_csv.py --archive "<source.tar.gz>" --output "<output folder>"','```','',
        'Temporary archive extraction is a read-only analysis source after intake. It is intentionally excluded from CSV export size. Full raw arrays remain in the unchanged source archive.'])
    (out/'README.md').write_text('\n'.join(readme)+'\n',encoding='utf-8')
    lines=['# Final report','',status,'',f'- Source archive: {s.info["source_archive"]}',f'- Archive SHA256: `{end_sha}`',f'- Archive size: {s.info["source_archive_size_bytes"]:,} bytes',f'- Archive files: {s.info["archive_file_count"]:,}; uncompressed: {s.info["raw_bytes"]:,} bytes',
        '- Detected: 31 days, B0/B1/B2/B3 each 31, 124 policy-days, no missing or duplicate final-index units.',f'- Destination: {out}',f'- CSV export: {total:,} bytes ({total/1e6:.3f} MB); reduction versus source archive: {reduction:.6f}%.',
        '- External workspace reads: 0. Raw archive unchanged (SHA256 and modification time checked).',f'- Validation: {"FAIL" if s.errors else "PASS"}',f'- Failure counts: {dict(errors)}','',
        '| CSV | Rows | MB | Parts | SHA256 |','|---|---:|---:|---:|---|']
    for item in metadata:
        for p in item['parts']:lines.append(f'| {p["filename"]} | {p["row_count"]} | {p["byte_size"]/1e6:.6f} | {item["part_count"]} | {p["SHA256"]} |')
    lines.extend(['','## Unavailable metrics','']+[f'- {", ".join(x["fields"])}: {x["reason"]}' for x in s.missing])
    if s.errors:lines.extend(['','## Validation failures','','All adverse records are retained in the CSVs. Detailed records are in VALIDATION_FAILURES.json. The campaign completeness is independent of these additional paper-data checks.'])
    lines.extend(['','Primary analysis files: 01, 02, 03, 08, 09 and 10. Use them with the validation status above; raw data were never altered.'])
    (out/'FINAL_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',default=str(DEFAULT_ARCHIVE));p.add_argument('--output',default=str(DEFAULT_ROOT/'MobileESS_V41R4_Paper_CSV_Export'));p.add_argument('--intake-report')
    args=p.parse_args();out=Path(args.output).absolute();archive=Path(args.archive).absolute()
    if (out/'MANIFEST.json').exists() or (out/'FINAL_REPORT.md').exists():out=out.with_name(out.name+'_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True,exist_ok=True);(out/'_scripts').mkdir(exist_ok=True)
    for name in ('export_v41r4_final_archive_to_csv.py','archive_intake.py'):
        src=Path(__file__).parent/name;dest=out/'_scripts'/name
        if src.resolve()!=dest.resolve():shutil.copy2(src,dest)
    info_path=Path(args.intake_report) if args.intake_report else out/'ARCHIVE_INTAKE.json'
    if info_path.exists():
        info=json.loads(info_path.read_text(encoding='utf-8-sig'));assert Path(info['source_archive'])==archive;assert sha(archive)==info['source_archive_SHA256']
        if info_path!=out/'ARCHIVE_INTAKE.json':shutil.copy2(info_path,out/'ARCHIVE_INTAKE.json')
    else:
        cache=Path(tempfile.gettempdir())/('V41R4_Archive_Source_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
        info=intake(archive,cache,out/'ARCHIVE_INTAKE.json')
    assert info['status']=='ARCHIVE_INTAKE_PASS' and info['detected_policy_days']==124
    # Enforce the archive-only data boundary even if future edits accidentally use a provenance path.
    source_prefix=str(Path(info['cache'])).replace('\\\\?\\','').lower().rstrip('\\')+'\\'
    archive_norm=str(archive).lower()
    def guard(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            name=os.fsdecode(args[0]).replace('\\\\?\\','').replace('/','\\').lower()
            if name.startswith(('c:\\codex_mobileess_workspace\\','d:\\codex_mobileess_workspace\\')):raise PermissionError('EXTERNAL_WORKSPACE_READ_FORBIDDEN')
            flags=args[2] if len(args)>2 and isinstance(args[2],int) else 0
            if (name==archive_norm or name.startswith(source_prefix)) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):raise PermissionError('RAW_SOURCE_WRITE_FORBIDDEN')
    sys.addaudithook(guard)
    s=Source(info)
    try:
        tables,method,units,ml_days=build(s)
        authority(s,tables,method,ml_days);ml_metrics(s,tables,ml_days,units);aggregates(s,tables);feeder_metrics(s,tables,units);final_validation(s,tables,units)
        finalize(out,s,tables,method,units)
    except Exception as exc:
        failure=dict(status='V41R4_FINAL_ARCHIVE_PAPER_CSV_EXPORT_FAIL_CLOSED',error=repr(exc),traceback=traceback.format_exc(),external_workspace_read_count=0,source_archive=str(archive),source_archive_SHA256=info['source_archive_SHA256'])
        (out/'EXPORT_ERROR.json').write_text(json.dumps(failure,indent=2),encoding='utf-8')
        print(json.dumps(failure,indent=2),flush=True);raise

if __name__=='__main__':main()
