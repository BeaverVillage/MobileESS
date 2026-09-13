"""Use installed PyArrow solely to read archived Parquet (bundled runtime lacks it)."""
import datetime as dt
import io
import json
import hashlib
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from reaudit import Archive,Comparisons,HERE,OUT,RUN,REV,NA,load_csvs,save

PR=HERE.parent/'v41r4_final_results_pr'
COMMIT='33a86d31c27051aedbdb93d60b844216533a45a9'


def main():
    archive=Archive();tables,_=load_csvs();check=Comparisons()
    sources=json.loads((HERE/'source_map.json').read_text())
    final_units=json.loads((HERE/'terminal_units.json').read_text())
    rule=archive.j(REV+'/RULE_FREEZE.json');method=archive.j(archive.resolve(rule['actual_method']['path'],rule['actual_method']['sha256']))
    authority=archive.j(f'{RUN}/audit/2025-05-01/domain/DAILY_DOMAIN_AUTHORITY.json')
    evidence=[]
    for item in authority['sources']:
        if '/dayahead/' not in item['path'].replace('\\','/'):continue
        relative='dayahead/'+item['path'].replace('\\','/').split('/dayahead/')[1]
        data=subprocess.check_output(['git','show',COMMIT+':'+relative],cwd=PR)
        assert hashlib.sha256(data).hexdigest()==item['sha256']
        evidence.append(dict(PR_commit=COMMIT,path=relative,sha256=item['sha256'],archive_binding=f'{RUN}/audit/2025-05-01/domain/DAILY_DOMAIN_AUTHORITY.json',byte_identical=True))
    first=sources[0];ml=archive.j(first['da']+'/ml/ML_SNAPSHOT.json');cap=np.array(ml['future_service_capacity_gpu'])
    a=tables['00'][0]
    check.fields('00',(),a,dict(campaign_version='V41R4',evaluation_month='2025-05',expected_days=31,expected_policies=4,expected_policy_days=124,completed_policy_days=124,
        alpha_BG=method['alpha_BG'],AIDC_equivalent_GPU=int(cap.sum(axis=1)[0]),AIDC_site_count=cap.shape[1],MESS_count=4,MESS_Pmax_kW_per_unit=method['active_power_limit_kw'],
        MESS_Smax_kVA_per_unit=method['pcs_kva'],eta_charge=method['eta_charge'],eta_discharge=method['eta_discharge'],PCS_polygon_faces=method['pcs_inner_polygon_faces'],
        voltage_lower_pu=method['hard_limits']['Vmin'],voltage_upper_pu=method['hard_limits']['Vmax'],grid_slots_per_day=96,grid_interval_min=15,
        source_archive_filename=Path(archive.verification['archive']).name,source_archive_size_bytes=archive.verification['size_bytes'],source_archive_SHA256=archive.verification['sha256'],
        runtime_model_id=ml['runtime_model_id'],H4_model_id=ml['H4_model_id'],method_SHA=rule['actual_method']['sha256']))
    timezone_rows=[];occupancy_checks=0;power_equal=0;event_counts=[];negative=[];feeder={}
    csv4={};csv5={}
    for row in tables['04']:csv4.setdefault((row['day'],row['policy']),[]).append(row)
    for row in tables['05']:csv5.setdefault((row['day'],row['policy']),[]).append(row)
    for source in sources:
        day,policy=source['day'],source['policy'];key=(day,policy)
        field=archive.j(source['da']+'/aidc/AIDC_FIELD_AUTHORITY.json')
        assert 'issue-time origin' in field['slot_origin']
        site_path=source['da']+'/aidc/SITE_TRAJECTORIES_96.parquet'
        frame=pd.read_parquet(io.BytesIO(archive.read(site_path))) if site_path in archive.index else None
        axis_path=source['da']+'/grid/FEEDER_SYSTEM_96.parquet'
        if axis_path in archive.index:
            axis=pd.read_parquet(io.BytesIO(archive.read(axis_path)))
            clock=list(axis['timestamp'].sort_values())
        else:
            authority=archive.j(source['da']+'/authority/AUTHORITY_MANIFEST.json')
            origin=pd.Timestamp(authority['issue_time'])+pd.Timedelta(hours=6)
            clock=[origin+pd.Timedelta(minutes=15*t) for t in range(96)]
        assert len(clock)==96 and all((b-a).total_seconds()==900 for a,b in zip(clock,clock[1:]))
        for row in csv4[key]+csv5[key]:
            assert pd.Timestamp(row['timestamp'])==clock[int(row['slot'])]
        timezone_rows.append(dict(day=day,policy=policy,first_archived_timestamp=clock[0].isoformat(),CSV_first_timestamp=csv4[key][0]['timestamp'],same_instant=True))
        power=archive.z(source['da']+'/FROZEN_AIDC_POWER.npz')
        if frame is not None:
            for col,name in [('known_scheduled_GPU','gpu'),('IT_load_kW','it'),('PCC_P_kW','pcc'),('PCC_Q_kvar','qcc')]:
                arr=frame.pivot(index='slot',columns='IDC_id',values=col).sort_index(axis=1).to_numpy()
                assert np.array_equal(arr,power[name]),(key,col);power_equal+=arr.size
            occupancy=pd.read_parquet(io.BytesIO(archive.read(source['da']+'/aidc/JOB_SLOT_OCCUPANCY.parquet')))
            assert not occupancy.duplicated(['job_uid','site_id','slot']).any()
            scheduled=occupancy.groupby(['slot','site_id']).GPU.sum().unstack(fill_value=0).reindex(index=range(96),columns=[f'AIDC{i:02d}' for i in range(1,13)],fill_value=0).to_numpy()
            assert np.array_equal(scheduled,power['gpu']);occupancy_checks+=len(occupancy)
        post=archive.z(source['post']+'/EXECUTION.npz');pre=archive.z(source['pre']+'/EXECUTION.npz')
        changed=(np.abs(post['Q_EXEC']-pre['Q_EXEC'])>1e-9).any(axis=1).sum()
        done=archive.j(source['ac']+'/COMPLETE.json')
        assert int(changed)==done.get('intervention_slots',0)
        events=archive.j(source['post']+'/Q_CONTROL_EVENTS.json') if source['post']+'/Q_CONTROL_EVENTS.json' in archive.index else []
        event_counts.append(dict(day=day,policy=policy,array_changed_slots=int(changed),reported_intervention_slots=done.get('intervention_slots',0),events=len(events)))
        if policy=='B0':
            n=f'{RUN}/{day}/B0/actual/grid/FEEDER_SYSTEM_96.parquet'
            if n in archive.index:
                f=pd.read_parquet(io.BytesIO(archive.read(n)));z=archive.z(source['post']+'/OPENDSS_PHASE_ARRAYS.npz')
                line=z['branch_kinds']=='line'
                if len(f)==96 and np.allclose(f['rho_max'],z['phase_current_loading_pu'][:,line].max(axis=1),rtol=0,atol=1e-10) and np.allclose(f['Vmax_pu'],z['voltage_pu'].max(axis=1),rtol=0,atol=1e-10):feeder[day]=float(f['feeder_import_P_kW'].max())
    for row in tables['10']:
        key=(row['day'],row['policy']);peak=feeder.get(row['day'],NA)
        check.cell('10',key,row,'B0_feeder_peak_kW',peak)
        check.cell('10',key,row,'MESS_nameplate_to_B0_peak_ratio',1200/peak if peak!=NA else NA)
        check.cell('10',key,row,'MESS_actual_max_P_to_B0_peak_ratio',float(row['max_simultaneous_abs_P_kW'])/peak if peak!=NA else NA)
    for row in tables['08']:
        policy=row['policy'];actual=[r for r in tables['02'] if r['policy']==policy]
        # 02 scalar values were already independently checked against every NPZ cell maximum.
        check.fields('08',(policy,),row,dict(Vmin_global=min(float(r['Actual_Vmin_pu']) for r in actual),Vmax_global=max(float(r['Actual_Vmax_pu']) for r in actual),
            voltage_violation_days=sum(r['Actual_voltage_violation_day']=='TRUE' for r in actual),thermal_violation_days=sum(any(r['Actual_'+q+'_violation_day']=='TRUE' for q in ('line','tx_current','tx_kVA')) for r in actual)))
    for row in tables['09']:
        for name,value in row.items():
            if 'improvement' in name and float(value)<0:negative.append(dict(day=row['day'],metric=name,value=float(value)))
    save('method_source_evidence.json',evidence)
    save('metadata_crosscheck.json',dict(cells_compared=check.count,by_table=dict(check.by_table),errors=check.errors,occupancy_rows_verified=occupancy_checks,
        AIDC_power_cells_verified=power_equal,timestamp_rows_verified=sum(len(tables[n]) for n in ('04','05')),timezones=timezone_rows,Q_count_checks=event_counts,
        negative_improvement_cells=negative,feeder_available_days=sorted(feeder),frozen_IT_power_model_packaged=any(n.endswith('V24T_C1_QUASISTATIC_MODEL.json') for n in archive.index)))
    save('metadata_sources_used.json',archive.used)
    print(json.dumps(dict(errors=check.errors,occupancy_rows_verified=occupancy_checks,AIDC_power_cells_verified=power_equal,negative_improvement_cells=len(negative),feeder_available_days=len(feeder)),indent=2))


if __name__=='__main__':main()
