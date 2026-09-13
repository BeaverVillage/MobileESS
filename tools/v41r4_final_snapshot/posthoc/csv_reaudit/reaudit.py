"""Independent post-hoc audit. Never imports the exporter or scientific runtime."""
import collections
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import statistics
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = Path(r'\\?\C:\Users\kjw39\AppData\Local\Temp\V41R4_FinalArchive_Source_20260909\V41R4_May2025_raw')
OUT = Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\MobileESS_V41R4_Paper_CSV_Export')
RUN = 'frozen_artifacts/v41r4_may/loop_wall_v4'
REV = 'frozen_artifacts/v41r4_restoration_revision_v1'
NA = 'NOT_AVAILABLE'


class Archive:
    def __init__(self):
        self.verification = json.loads((HERE/'archive_verification.json').read_text())
        assert self.verification['status'] == 'PASS'
        raw = json.loads((HERE/'archive_member_index.json').read_text())
        self.index = {name.split('/',1)[1]: v for name,v in raw.items()}
        self.used = {}
    def read(self, name):
        name = str(name).replace('\\','/')
        assert name in self.index and ':' not in name and '..' not in PurePosixPath(name).parts, name
        data = CACHE.joinpath(*PurePosixPath(name).parts).read_bytes()
        expected = self.index[name]
        assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'], name
        self.used[name] = expected
        return data
    def j(self, name):
        return json.loads(self.read(name).decode('utf-8-sig'))
    def z(self, name):
        with np.load(io.BytesIO(self.read(name)), allow_pickle=False) as arrays:
            return {key: arrays[key] for key in arrays.files}
    def resolve(self, original, expected=None):
        name = str(original).replace('\\','/')
        for marker in ('frozen_artifacts/', 'dayahead/'):
            if marker in name:
                relative = marker+name.split(marker,1)[1]
                if relative in self.index:
                    if expected:
                        assert self.index[relative]['sha256'] == expected, relative
                    return relative
        raise ValueError('No archived authority: '+name)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def save(name, value):
    (HERE/name).write_text(dumps(value), encoding='utf-8')


def load_csvs():
    tables = {}
    checks = []
    manifest = json.loads((OUT/'MANIFEST.json').read_text(encoding='utf-8-sig'))
    inventory = {part['filename']: (table,part) for table in manifest['CSV_files'] for part in table['parts']}
    for path in sorted(OUT.glob('[0-9][0-9]_*.csv')):
        data = path.read_bytes()
        text = data.decode('utf-8-sig', errors='strict')
        assert text.encode('utf-8') == data.removeprefix(b'\xef\xbb\xbf')
        reader = csv.DictReader(io.StringIO(text, newline=''))
        rows = list(reader)
        assert len(reader.fieldnames) == len(set(reader.fieldnames))
        assert all(None not in row and all(v is not None for v in row.values()) for row in rows)
        table, part = inventory[path.name]
        digest = hashlib.sha256(data).hexdigest()
        assert digest == part['SHA256'] and len(rows) == part['row_count']
        assert reader.fieldnames == table['columns'] and len(data) <= 500_000_000
        special = collections.Counter(value for row in rows for value in row.values() if value in ('TRUE','FALSE','NOT_AVAILABLE','NaN','nan','','true','false'))
        assert not special['true'] and not special['false']
        tables[path.name[:2]] = rows
        checks.append(dict(file=path.name, rows=len(rows), bytes=len(data), SHA256=digest,
                           schema=reader.fieldnames, UTF8_roundtrip=True, original_manifest_match=True,
                           special_values=dict(special)))
    assert len(tables)==11
    return tables, checks


def span(segments, lo=-math.inf, hi=math.inf):
    """Half-open interval intersection; sum disjoint service, not wall-clock duration."""
    ordered = sorted((float(segment['start']),float(segment['end'])) for segment in segments)
    assert all(end >= start for start,end in ordered)
    assert all(a[1] <= b[0] for a,b in zip(ordered,ordered[1:])), 'Overlapping service segments'
    return math.fsum(max(0.,min(end,hi)-max(start,lo)) for start,end in ordered)


def terminal_audit(archive, tables):
    final = archive.j('FINAL_RESULT_INDEX.json')
    audit = archive.j(REV+'/FINAL_AUDIT.json')
    assert audit['counts']['total_accepted']==124 and len(audit['pending'])==0
    assert len(final)==len({(x['day'],x['policy']) for x in final})==124
    source_map = []
    refs = {}
    records=[]
    units=[]
    cases=[]
    csvjobs={(r['day'],r['policy'],r['job_uid']):r for r in tables['06']}
    count=0
    for entry in sorted(final,key=lambda x:(x['day'],x['policy'])):
        day,policy=entry['day'],entry['policy']
        da=f'{RUN}/{day}/{policy}/dayahead'
        acceptance=archive.j(entry['acceptance'])
        assert acceptance['status']=='PASS'
        joint=archive.resolve(acceptance['new_joint']['path'],acceptance['new_joint']['sha256'])
        frozen=archive.j(joint)
        decision=frozen['decision']
        jobs=decision['AIDC_decision']
        if day not in refs:
            reference=archive.j(f'{RUN}/{day}/B0/dayahead/FROZEN_JOINT_DECISION.json')['decision']['AIDC_decision']
            refs[day]={str(job['job_uid']):job for job in reference}
        reference=refs[day]
        assert len(jobs)==len(reference)==len({str(j['job_uid']) for j in jobs})
        local=[]
        total_selected=total_migrations=shifted=initial_changed=final_changed=0
        for job in jobs:
            uid=str(job['job_uid']); ref=reference[uid]
            old,new=ref['compute_segments'],job['compute_segments']
            totals=[span(old),span(new)]
            inside=[span(old,24,120),span(new,24,120)]
            after=[span(old,120),span(new,120)]
            before=[span(old,hi=24),span(new,hi=24)]
            selected=job['AIDC_site']!='UNASSIGNED'
            migrated=bool(job.get('migration_selected',False))
            total_selected+=selected;total_migrations+=migrated
            shifted+=job['start_slot']!=ref['start_slot']
            initial_changed+=job.get('initial_AIDC',job['AIDC_site'])!=ref.get('initial_AIDC',ref['AIDC_site'])
            final_changed+=job['AIDC_site']!=ref['AIDC_site']
            csvrow=csvjobs[day,policy,uid];count+=1
            expected={'reference_terminal_remaining_slots':after[0],'optimized_terminal_remaining_slots':after[1],
                      'terminal_residual_delta_slots':after[1]-after[0],'reference_start_slot':float(ref['start_slot'])-24,
                      'optimized_start_slot':float(job['start_slot'])-24,'safe_duration_slots':job['safe_duration_slots']}
            for field,value in expected.items():
                assert float(csvrow[field])==value,(day,policy,uid,field)
            assert (csvrow['terminal_invariant_pass']=='TRUE')==(after[1]<=after[0]+1e-9)
            assert (csvrow['checkpoint_migrated']=='TRUE')==migrated
            if after[1]-after[0]>1e-9:
                row=dict(day=day,policy=policy,job_uid=uid,state_at_issue=job['state_at_issue'],requested_GPU=job['requested_GPU'],
                         reference_start=ref['start_slot'],optimized_start=job['start_slot'],safe_duration_slots=job['safe_duration_slots'],
                         checkpoint_migrated=migrated,migration_selected=migrated,reference_compute_segments=old,optimized_compute_segments=new,
                         reference_total_compute_service_slots=totals[0],optimized_total_compute_service_slots=totals[1],
                         reference_pre_day_service_slots=before[0],optimized_pre_day_service_slots=before[1],
                         reference_in_day_service_slots=inside[0],optimized_in_day_service_slots=inside[1],
                         reference_post_day_service_slots=after[0],optimized_post_day_service_slots=after[1],
                         delta_post_day_slots=after[1]-after[0],delta_post_day_GPUh=(after[1]-after[0])*float(job['requested_GPU'])/4,
                         D_day_service_reduction_GPUh=(inside[0]-inside[1])*float(job['requested_GPU'])/4,
                         reference_end=ref['end_slot'],optimized_end=job['end_slot'],
                         source_inside_archive=joint,source_SHA256=archive.index[joint]['sha256'])
                for field in ('migration_checkpoint_slot','transfer_start_slot','transfer_end_slot','restart_complete_slot'):
                    row[field]=job.get(field,NA)
                local.append(row);records.append(row)
                if len(cases)<3:cases.append(dict(reference=ref,optimized=job))
        unit=dict(day=day,policy=policy,affected_jobs=len(local),affected_GPUh=math.fsum(r['delta_post_day_GPUh'] for r in local),
                  terminal_residual_extra_GPU_slots=math.fsum(r['delta_post_day_GPUh']*4 for r in local),
                  D_day_service_reduction_GPUh=math.fsum(r['D_day_service_reduction_GPUh'] for r in local),
                  total_selected_jobs=total_selected,total_migrations=total_migrations,temporal_shift_count=shifted,
                  spatial_relocation_count=initial_changed,final_site_change_count=final_changed)
        units.append(unit)
        ac=entry['final_actual'];acroot=ac.split('/replays/')[0]
        fresh=entry['acceptance'].rsplit('/',1)[0]+'/accepted_fresh' if acceptance['old_primary_fresh']=='FAIL' else da+'/fresh'
        control=policy in ('B0','B1')
        post=ac+('/CONTROL_COMMON_BINDING' if control else '/ETA95_QSAFE_ACTUAL')
        source_map.append(dict(day=day,policy=policy,da=da,joint=joint,fresh=fresh,post=post,
                               pre=post if control else ac+'/ETA95_ACTUAL',ac=ac,
                               ci=f'{acroot}/common_inputs/{day}/{policy}',acceptance=entry['acceptance']))
    assert count==len(csvjobs)==188036
    save('terminal_records.json',records);save('terminal_units.json',units);save('sample_jobs.json',cases)
    save('source_map.json',source_map)
    return records,units,source_map


class Comparisons:
    def __init__(self):
        self.count=0;self.errors=[];self.by_table=collections.Counter();self.max_float_error=0.
    def cell(self,table,key,row,field,expected):
        self.count+=1;self.by_table[table]+=1
        actual=row[field]
        if expected is None: expected=NA
        if isinstance(expected,(bool,np.bool_)):
            okay=actual==('TRUE' if expected else 'FALSE')
        elif isinstance(expected,(int,float,np.number)):
            try:
                value=float(actual)
                if math.isnan(float(expected)):okay=math.isnan(value)
                else:
                    error=abs(value-float(expected));self.max_float_error=max(self.max_float_error,error)
                    okay=math.isclose(value,float(expected),rel_tol=2e-13,abs_tol=1e-10)
            except ValueError:okay=False
        elif isinstance(expected,(list,dict)):
            okay=json.loads(actual)==expected
        else:okay=actual==str(expected)
        if not okay:
            self.errors.append(dict(table=table,key=list(key),field=field,actual=actual,expected=expected))
    def fields(self,table,key,row,expected):
        for field,value in expected.items():self.cell(table,key,row,field,value)


def grid_metrics(archive, folder, tolerance):
    z=archive.z(folder+'/OPENDSS_PHASE_ARRAYS.npz')
    v=z['voltage_pu'];i=z['phase_current_loading_pu'];k=z['transformer_total_kva_loading_pu']
    lines=np.flatnonzero(z['branch_kinds']=='line');transformers=np.flatnonzero(z['branch_kinds']=='transformer')
    assert len(v)==96 and len(lines)>0 and len(transformers)>0
    rows=[]
    for t in range(96):
        il=lines[np.argmax(i[t,lines])];it=transformers[np.argmax(i[t,transformers])];ik=transformers[np.nanargmax(k[t,transformers])]
        imin=int(np.argmin(v[t]));imax=int(np.argmax(v[t]))
        rows.append(dict(rho_line_max=float(i[t,il]),critical_line=str(z['branch_names'][il]),critical_line_phase=str(z['branch_phases'][il]),
                         Vmin_pu=float(v[t,imin]),Vmax_pu=float(v[t,imax]),Vmin_bus=str(z['node_names'][imin]),Vmax_bus=str(z['node_names'][imax]),
                         Vmin_phase=str(z['node_phases'][imin]),Vmax_phase=str(z['node_phases'][imax]),
                         tx_current_max_pu=float(i[t,it]),tx_current_asset=str(z['branch_names'][it]),tx_current_phase=str(z['branch_phases'][it]),
                         tx_kVA_max_pu=float(k[t,ik]),tx_kVA_asset=str(z['branch_names'][ik]),tx_kVA_phase='TOTAL_ASSET',
                         voltage_violation_count=int(np.count_nonzero((v[t]<.95-tolerance)|(v[t]>1.05+tolerance))),
                         line_violation_count=int(np.count_nonzero(i[t,lines]>1+tolerance)),
                         tx_current_violation_count=int(np.count_nonzero(i[t,transformers]>1+tolerance)),
                         tx_kVA_violation_count=int(np.count_nonzero(k[t,transformers]>1+tolerance)),converged=bool(z['convergence'][t]),
                         regulator_taps=z['regulator_taps'][t].tolist(),capacitor_states=z['capacitor_states'][t].tolist()))
    metrics=dict(rho_max=max(r['rho_line_max'] for r in rows),Vmin_pu=min(r['Vmin_pu'] for r in rows),Vmax_pu=max(r['Vmax_pu'] for r in rows),
                 tx_current_max_pu=max(r['tx_current_max_pu'] for r in rows),tx_kVA_max_pu=max(r['tx_kVA_max_pu'] for r in rows),
                 converged_slots=sum(r['converged'] for r in rows))
    for name in ('voltage','line','tx_current','tx_kVA'):metrics[name+'_violation_cells']=sum(r[name+'_violation_count'] for r in rows)
    metrics['physically_feasible']=not any(metrics[name+'_violation_cells'] for name in ('voltage','line','tx_current','tx_kVA'))
    return metrics,rows,z


def crosscheck(archive,tables,units,sources):
    check=Comparisons()
    lookup={name:{(r['day'],r['policy']):r for r in tables[name]} for name in ('01','02','03','10')}
    glookup={(r['day'],r['policy'],r['trajectory'],int(r['slot'])):r for r in tables['05']}
    mlookup={(r['day'],r['policy'],int(r['slot']),r['mess_id']):r for r in tables['04']}
    umap={(u['day'],u['policy']):u for u in units}
    rule=archive.j(REV+'/RULE_FREEZE.json')
    method=archive.j(archive.resolve(rule['actual_method']['path'],rule['actual_method']['sha256']))
    touched_grid=set()
    for source in sources:
        day,policy=source['day'],source['policy'];key=(day,policy);unit=umap[key]
        da,ar,qr,ur=[lookup[n][key] for n in ('01','02','03','10')]
        frozen=archive.j(source['joint']);decision=frozen['decision']
        acceptance=archive.j(source['acceptance'])
        done=archive.j(source['ac']+'/COMPLETE.json')
        receipt=archive.j(source['ac']+'/CANDIDATE_RECEIPT.json')
        assert receipt['method_SHA']==rule['actual_method']['sha256']
        assert done['status']=='PASS' and receipt['status']=='COMPLETE'
        for label,prefix,folder,table,row in [('DAYAHEAD_FRESH','DA_',source['fresh'],'01',da),('ETA95_QSAFE_ACTUAL','Actual_',source['post'],'02',ar),('ETA95_ACTUAL','preQ_',source['pre'],'03',qr)]:
            metrics,slots,z=grid_metrics(archive,folder,method['inherited_hard_comparison_tolerance'])
            mapped={prefix+name:value for name,value in metrics.items()}
            if prefix=='DA_':
                mapped={k.replace('_cells','_count'):v for k,v in mapped.items() if not k.endswith('physically_feasible')}
                mapped['DA_physical_outcome']='PASS' if metrics['physically_feasible'] else 'FAIL'
            check.fields(table,key,row,mapped)
            for t,slot in enumerate(slots):
                gkey=(day,policy,label,t);check.fields('05',gkey,glookup[gkey],slot);touched_grid.add(gkey)
            if prefix=='DA_':unit.update(P1=None,DA_rho=metrics['rho_max']);fresh_metrics=metrics
            elif prefix=='Actual_':
                unit['Actual_rho']=metrics['rho_max'];actual_metrics=metrics;actual_arrays=z
                check.fields('03',key,qr,{'postQ_'+name:value for name,value in metrics.items()})
                check.fields('02',key,ar,{'Actual_'+name+'_violation_day':metrics[name+'_violation_cells']>0 for name in ('voltage','line','tx_current','tx_kVA')})
            else:pre_metrics=metrics
        original=archive.j(source['ac']+'/ORIGINAL_ACTUAL/REFERENCE.json')
        if original.get('available'):
            try:oldfolder=archive.resolve(original['authoritative_root']+'/OPENDSS_PHASE_ARRAYS.npz').rsplit('/',1)[0]
            except ValueError:
                oldfolder=next((f'{RUN}/{day}/{policy}/actual'+suffix for suffix in ('/grid','') if f'{RUN}/{day}/{policy}/actual'+suffix+'/OPENDSS_PHASE_ARRAYS.npz' in archive.index),None)
            if oldfolder:
                assert archive.index[oldfolder+'/OPENDSS_PHASE_ARRAYS.npz']['sha256']==original['grid_SHA']
                _,slots,_=grid_metrics(archive,oldfolder,method['inherited_hard_comparison_tolerance'])
                for t,slot in enumerate(slots):
                    gkey=(day,policy,'ORIGINAL_ACTUAL',t);check.fields('05',gkey,glookup[gkey],slot);touched_grid.add(gkey)
        ledger=archive.j(source['da']+'/optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
        fields=['P1_rho_planning','P2_H4_shortfall_GPUh','P3_migrations','P4_reference_deviation','P5_stable_tie']
        check.fields('01',key,da,dict(zip(fields,ledger)))
        unit['P1']=ledger[0]
        for field,unitfield in [('AIDC_selected_job_count','total_selected_jobs'),('temporal_shift_count','temporal_shift_count'),('spatial_relocation_count','spatial_relocation_count'),('final_site_change_count','final_site_change_count'),('checkpoint_migration_count','total_migrations'),('terminal_residual_violation_jobs','affected_jobs')]:
            check.cell('01',key,da,field,unit[unitfield])
        check.fields('01',key,da,dict(primary_fresh_status=acceptance['old_primary_fresh'],restoration_status=acceptance['local_restoration'],full_PQ_fallback=acceptance['full_PQ_fallback']))
        post=archive.z(source['post']+'/EXECUTION.npz');pre=archive.z(source['pre']+'/EXECUTION.npz')
        P,Q=post['P_EXEC'],post['Q_EXEC'];delta=Q-pre['Q_EXEC'];changed=np.abs(delta)>1e-9
        P_same=np.array_equal(P,pre['P_EXEC']);E_same=np.array_equal(post['energy_after'],pre['energy_after']) and np.array_equal(post['SoC_after'],pre['SoC_after'])
        acceptance_identity=done['binding']['AIDC_schedule_SHA']==acceptance['new_identity']['AIDC']
        route_same=np.array_equal(post['locations'],pre['locations'])
        if policy in ('B2','B3'):
            qa=archive.j(source['post']+'/C_VERSUS_B_AUDIT.json')
            assert qa['B_binding']['AIDC_schedule_SHA']==qa['C_binding']['AIDC_schedule_SHA']==done['binding']['AIDC_schedule_SHA']
            assert qa['B_binding']['locations_SHA']==qa['C_binding']['locations_SHA']
        norm=np.hypot(P,Q)/method['pcs_kva']
        theta=np.arange(method['pcs_inner_polygon_faces'])*2*np.pi/method['pcs_inner_polygon_faces']
        polygon=np.max(P[:,:,None]*np.cos(theta)+Q[:,:,None]*np.sin(theta),axis=2)/(method['pcs_kva']*np.cos(np.pi/method['pcs_inner_polygon_faces']))
        ev=archive.j(source['post']+'/Q_CONTROL_EVENTS.json') if source['post']+'/Q_CONTROL_EVENTS.json' in archive.index else []
        event_slots=done.get('intervention_slots',int(np.any(changed,axis=1).sum()))
        unresolved=done.get('ROBUST_Q_ONLY_UNRESOLVED_slots',0)
        check.fields('03',key,qr,dict(Q_intervention_slots=event_slots,Q_intervention_rate=event_slots/96,Q_unresolved_slots=unresolved,Q_unresolved_day=unresolved>0,
            sum_abs_delta_Q_kvar=np.abs(delta).sum(),mean_abs_delta_Q_all_vehicle_slots_kvar=np.abs(delta).mean(),
            mean_abs_delta_Q_changed_vehicle_slots_kvar=np.abs(delta)[changed].mean() if changed.any() else math.nan,
            max_abs_delta_Q_kvar=np.abs(delta).max(),changed_Q_vehicle_slots=int(changed.sum()),maximum_PCS_norm_utilization=norm.max(),maximum_PCS_polygon_utilization=polygon.max(),
            P_EXEC_identity=P_same,SoC_energy_identity=E_same,AIDC_decision_identity=acceptance_identity,route_location_identity=route_same,
            Q_delta_rho=actual_metrics['rho_max']-pre_metrics['rho_max'],Q_delta_voltage_cells=actual_metrics['voltage_violation_cells']-pre_metrics['voltage_violation_cells'],
            Q_search_runtime_s=sum(e.get('search_runtime_seconds',0) for e in ev) if ev else NA))
        commands={(int(r['slot']),r['mess_id']):r for r in decision['MESS_trajectory']};ids=sorted({mid for t,mid in commands})
        assert P.shape==(96,4) and len(commands)==384
        actuator={(int(r['slot']),r['mess_id']):r for r in archive.j(source['post']+'/ACTUATOR.json')['trajectory']}
        mess=archive.j(source['ci']+'/ACTUAL_MESS_AUDIT.json')
        assert ids==mess['ids']
        conn=np.array([[bool(actuator[t,mid]['connected']) for mid in ids] for t in range(96)])
        for t in range(96):
            for m,mid in enumerate(ids):
                row=mlookup[day,policy,t,mid];command=commands[t,mid];act=actuator[t,mid]
                check.fields('04',(day,policy,t,mid),row,dict(P_DA_kW=command['p_kw'],Q_DA_kvar=command['q_kvar'],P_Actual_kW=P[t,m],Q_Actual_kvar=Q[t,m],delta_Q_kvar=delta[t,m],
                    SoC_kWh=post['energy_after'][t,m],SoC_pct=post['SoC_after'][t,m]*100,PCS_norm_utilization=norm[t,m],PCS_polygon_utilization=polygon[t,m],Q_intervention=changed[t,m],
                    location_service_id=act['actual_service_id'],connected=bool(act['connected']),regulator_taps_final=actual_arrays['regulator_taps'][t].tolist()))
        planning_P=np.array([[commands[t,mid]['p_kw'] for mid in ids] for t in range(96)])
        departures={(r['mess_id'],r['departure_slot']) for r in commands.values() if r.get('departure_slot') is not None}
        check.fields('01',key,da,dict(MESS_vehicle_count=len(ids),MESS_dispatch_slots=int((np.abs(planning_P)>1e-9).sum()),MESS_move_count=len(departures),MESS_abs_P_energy_kWh=np.abs(planning_P).sum()/4))
        unit.update(MESS_dispatch_slots=int((np.abs(planning_P)>1e-9).sum()),MESS_move_count=len(departures),MESS_abs_P_energy_kWh=float(np.abs(planning_P).sum()/4))
        check.fields('10',key,ur,dict(MESS_nameplate_total_P_kW=len(ids)*method['active_power_limit_kw'],MESS_nameplate_total_S_kVA=len(ids)*method['pcs_kva'],
            MESS_nameplate_total_E_kWh=len(ids)*float(np.nanmedian(post['energy_after']/post['SoC_after'])),max_simultaneous_abs_P_kW=np.abs(P).sum(axis=1).max(),
            max_net_discharge_P_kW=np.maximum(P.sum(axis=1),0).max(),max_net_charge_P_kW=np.maximum(-P.sum(axis=1),0).max(),max_simultaneous_apparent_power_kVA=np.hypot(P,Q).sum(axis=1).max(),
            P_nameplate_utilization_max=np.abs(P).sum(axis=1).max()/(4*method['active_power_limit_kw']),S_nameplate_utilization_max=np.hypot(P,Q).sum(axis=1).max()/(4*method['pcs_kva']),
            mean_connected_MESS=conn.sum(axis=1).mean(),max_connected_MESS=conn.sum(axis=1).max(),total_discharge_energy_kWh=np.maximum(P,0).sum()/4,total_charge_energy_kWh=np.maximum(-P,0).sum()/4,
            absolute_P_energy_kWh=np.abs(P).sum()/4,max_unit_P_utilization=np.abs(P).max()/method['active_power_limit_kw'],max_unit_PCS_utilization=norm.max()))
        h4=archive.j(source['ci']+'/H4_SCORE.json');rate=archive.j(source['ci']+'/ACTUAL_EXECUTION_RATE.json')
        check.fields('02',key,ar,dict(Actual_H4_shortfall_mean_GPUh=np.mean(h4['realized_shortfall_GPUh']),Actual_H4_shortfall_max_GPUh=np.max(h4['realized_shortfall_GPUh']),execution_rate=rate['START_EXECUTION_RATE'],
            decision_SHA=frozen['decision_SHA'],AIDC_decision_SHA=done['binding']['AIDC_schedule_SHA'],Actual_optimizer_calls=done['scheduling_optimizer_calls']))
        unit['Actual_H4_shortfall_mean_GPUh']=float(np.mean(h4['realized_shortfall_GPUh']))
        if policy=='B3':print('CROSSCHECKED',day,flush=True)
    assert touched_grid==set(glookup)
    save('terminal_units.json',units)
    save('crosscheck.json',dict(cells_compared=check.count,by_table=dict(check.by_table),errors=check.errors,max_absolute_float_error=check.max_float_error))
    save('archive_sources_used.json',archive.used)
    return check


if __name__=='__main__':
    archive=Archive()
    tables,checks=load_csvs()
    save('csv_format_checks.json',checks)
    records,units,sources=terminal_audit(archive,tables)
    check=crosscheck(archive,tables,units,sources)
    save('archive_sources_used.json',archive.used)
    print(dumps(dict(flagged=len(records),counts=dict(collections.Counter(r['policy'] for r in records)),
                     affected_units=sum(bool(u['affected_jobs']) for u in units),all_migrated=all(r['checkpoint_migrated'] for r in records),
                     sources_read=len(archive.used))))
