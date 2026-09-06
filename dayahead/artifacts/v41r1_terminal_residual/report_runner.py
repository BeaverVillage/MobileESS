"""Observational May01 report; never changes a decision or calls an optimizer."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.persistence import table,verify_table
from dayahead.v41.scientific_archive import native,verify_manifest
from dayahead.v41.execution import science

OLD=ROOT.parent/'MobileESS_v41_final_ml_interface_may_campaign/frozen_artifacts/v41_may_campaign'
DAY='2025-05-01'


def location(row):
    result={k:native(row[k]) for k in ('slot','node','bus','phase','line_id','branch_phase') if k in row}
    if 'timestamp' in row:result['AEST']=pd.Timestamp(row.timestamp).tz_convert('Australia/Brisbane').isoformat()
    if 'node' in result and 'bus' not in result:
        result['bus'],phase=result['node'].rsplit('.',1)
        result['phase']={'1':'A','2':'B','3':'C'}.get(phase,phase)
    return result


def electrical(folder,planning=False):
    if planning:
        v=pd.read_parquet(folder/'PLANNING_BUS_PHASES.parquet')
        b=pd.read_parquet(folder/'PLANNING_BRANCH_PHASES.parquet')
        b=b[b.branch_phase.str.startswith('line.')&b.active_current_constraint]
        field='polygon_loading_pu'
        at18=b[(b.slot==72)&(b.branch_phase=='line.l10::A')]
    else:
        v=pd.read_parquet(folder/'BUS_PHASE_VOLTAGES.parquet')
        b=pd.read_parquet(folder/'BRANCH_PHASE_CURRENTS.parquet')
        b=b[b.kind=='line'];field='loading_pu'
        at18=b[(b.slot==72)&(b.line_id=='line.l10')&(b.phase=='A')]
    vr=v.loc[v.voltage_pu.idxmax()];vl=v.loc[v.voltage_pu.idxmin()];br=b.loc[b[field].idxmax()]
    violations=v[(v.voltage_pu<.95)|(v.voltage_pu>1.05)]
    assert len(at18)==1
    return dict(Vmin=float(v.voltage_pu.min()),Vmax=float(v.voltage_pu.max()),
        raw_voltage_violation_count=len(violations),
        validation_voltage_violation_count=int(((v.voltage_pu<.95-1e-9)|(v.voltage_pu>1.05+1e-9)).sum()),
        maximum_voltage_location=location(vr),minimum_voltage_location=location(vl),
        voltage_violations=[dict(**location(row),voltage_pu=float(row.voltage_pu)) for _,row in violations.iterrows()],
        rho_max=float(br[field]),critical_line_location=location(br),
        critical_line_P_kW=float(br.P_flow_kW),critical_line_Q_kvar=float(br.Q_flow_kvar),
        line_current_violation_count=int((b[field]>1+1e-9).sum()),
        critical_18h_line_l10_A=dict(P_kW=float(at18.P_flow_kW.iloc[0]),Q_kvar=float(at18.Q_flow_kvar.iloc[0]),
            rho=float(at18[field].iloc[0])),post_H_grid_rows=int((v.slot>=96).sum()),voltage_rows=len(v))


def changes(reference,chosen):
    ref={r['job_uid']:r for r in reference};rows=[]
    def at(row,t=96):
        parts=row.get('compute_segments',[dict(site=row['AIDC_site'],start=row['start_slot'],end=row['end_slot'])])
        return row['requested_GPU']*sum(p['site']!='UNASSIGNED' and p['start']<=t<p['end'] for p in parts)
    for row in chosen:
        old=ref[row['job_uid']]
        time=row['start_slot']!=old['start_slot'];site=row['AIDC_site']!=old['AIDC_site']
        migration=bool(row.get('migration_selected'))
        cross=old['state_at_issue']=='PENDING' and old['AIDC_site']!='UNASSIGNED' and old['start_slot']>=24 and old['end_slot']>120
        category='migration' if migration else 'time_and_site' if time and site else 'time_only' if time else 'site_only' if site else 'unchanged'
        rows.append(dict(job_id=row['job_uid'],state=old['state_at_issue'],start_changed=time,site_changed=site,
            migration=migration,category=category,reference_start_day=old['start_slot']-24,selected_start_day=row['start_slot']-24,
            reference_site=old['AIDC_site'],selected_site=row['AIDC_site'],reference_cross_midnight=cross,
            fixed_pre_D00_PENDING=old['state_at_issue']=='PENDING' and old['start_slot']<24,
            GPU_at_18_reference=at(old),GPU_at_18_selected=at(row),GPU_at_18_delta=at(row)-at(old)))
    f=pd.DataFrame(rows)
    return f,dict(start_changes=int(f.start_changed.sum()),site_changes=int(f.site_changed.sum()),migrations=int(f.migration.sum()),
        cross_midnight_start_changes=int((f.reference_cross_midnight&f.start_changed).sum()),
        cross_midnight_site_changes=int((f.reference_cross_midnight&f.site_changed).sum()),
        pre_D00_PENDING_start_or_site_changes=int((f.fixed_pre_D00_PENDING&(f.start_changed|f.site_changed)).sum()),
        mutually_exclusive_categories=f.groupby('category').agg(jobs=('job_id','size'),GPU_at_18_delta=('GPU_at_18_delta','sum')).reset_index().to_dict('records'),
        restored_cross_midnight_cohort_GPU_at_18_delta=int(f.loc[f.reference_cross_midnight,'GPU_at_18_delta'].sum()))


def policy(root,policy,reference,new):
    unit=root/'pilot'/DAY/policy;da=unit/'dayahead';ac=unit/'actual'
    decision=read(da/'FROZEN_JOINT_DECISION.json')['decision']
    vector=read(da/'optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
    values={stage:electrical(path,stage=='DayAhead') for stage,path in (
        ('DayAhead',da/'optimization/stages/JOINT_FREEZE'),('Fresh',da/'grid'),('Actual',ac/'grid'))}
    h4=pd.read_parquet(ac/'H4_OPTIMIZER_WINDOWS.parquet')
    actual_vector=[values['Actual']['rho_max'],float(h4.reserve_shortfall_xi_GPUh.mean()),*vector[2:]]
    frame,delta=changes(reference,decision['AIDC_decision'])
    delta_ref=table(OUT/'comparison'/f'{"NEW" if new else "OLD"}_{policy}_DECISION_DELTAS.parquet',frame)
    with np.load(da/'FROZEN_AIDC_POWER.npz',allow_pickle=False) as arrays:
        gpu=arrays['gpu'];pcc=arrays['pcc']
        occupancy=dict(critical_18h_GPU=int(gpu[72].sum()),whole_day_max_GPU=int(gpu.sum(axis=1).max()),
            critical_18h_AIDC_PCC_kW=float(pcc[72].sum()),critical_18h_PCC_by_site=pcc[72].tolist(),
            whole_day_GPUh=float(gpu.sum()/4),whole_day_AIDC_PCC_kWh=float(pcc.sum()/4))
    outcome=read(ac/'ACTUAL_RESULT.json')
    result=dict(DayAhead_objective_vector=vector,Actual_evaluated_objective_vector=actual_vector,
        Actual_vector_authority='P1 measured line rho; P2 frozen scalar H4 reserve minus realized available headroom; P3-P5 frozen DayAhead decision components. No Actual optimization.',
        electrical=values,occupancy=occupancy,decision_changes=delta,decision_delta_table=delta_ref,
        Actual_execution_delay_KPIs=outcome['execution_delay_KPIs'],Actual_execution_rate=outcome['execution_rate'],
        Actual_GPU_feasibility=outcome['final_execution_feasibility'],Actual_optimizer_calls=outcome['Actual_optimizer_calls'],
        Actual_physical_violation=outcome['summary']['physical_violation'],
        raw_and_capped_H4_coverage=outcome['H4_raw_vs_actionable_coverage'])
    if new:
        result['terminal']=read(da/'terminal/TERMINAL_NO_DUMPING_AUDIT.json')
        result['independent_day']=read(da/'terminal/INDEPENDENT_DAY_TERMINAL_BOUNDARY_AUDIT.json')
        verify_table(result['terminal']['table'])
    return result


def main():
    frozen=read(RUNTIME/'V41R1_SCIENTIFIC_REVISION_FREEZE.json');assert frozen['science']==science()
    reference=read(OLD/'inputs'/DAY/'common/COMMON_B0_REFERENCE_JOBS.json')
    results={label:{p:policy(root,p,reference,label=='NEW') for p in ('B0','B1')} for label,root in [('OLD',OLD),('NEW',RUNTIME)]}
    receipts=[];files={}
    for p in ('B0','B1'):
        unit=RUNTIME/'pilot'/DAY/p
        manifest=verify_manifest(unit/'UNIT_SCIENTIFIC_MANIFEST.json')
        files[p]=[dict(path=str(unit/r['relative_path']),rows=r['row_count'],sha256=r['sha256']) for r in manifest['artifacts']]
        for phase in ('dayahead','actual'):
            path=unit/phase/(phase.upper()+'_RECEIPT.json');r=read(path)
            assert r['science']==frozen['science'] and r['scientific_commit']==frozen['scientific_commit']
            receipts.append(dict(policy=p,phase=phase,**record(path)))
    prep=read(RUNTIME/'inputs'/DAY/'PRE_SOLVE_PERSISTENCE_AUDIT.json')
    for entry in prep['tables'].values():verify_table(entry)
    assert prep['snapshot_count']==1 and prep['tables']['runtime_predictions']['rows']==1395 and prep['tables']['h4_windows']['rows']==81
    from dayahead.v41.scalars import project
    old_snapshot=read(OLD/'inputs'/DAY/f'V41_ML_SNAPSHOT_{DAY}.json')
    snapshot=read(prep['snapshot']['path'])
    assert project(old_snapshot).sha256==project(snapshot).sha256
    from dayahead.v41r1.audit import old_files
    original=read(ROOT/'dayahead/artifacts/v41r1_premay_voltage_security_margin/V41_EXPOSED_PRE_MARGIN_PILOT_PRESERVATION.json')['files']
    assert old_files()==original
    p0=read(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json');assert p0['PASS']==7 and p0['FAIL']==0
    nesting=read(OUT/'V41_MAY01_B0_IN_B1_FEASIBILITY.json');assert nesting['status']=='PASS'
    gains={}
    for label,policies in results.items():
        gains[label]={}
        for stage,field in [('DayAhead','DayAhead_objective_vector'),('Actual','Actual_evaluated_objective_vector')]:
            a=policies['B0'][field][0];b=policies['B1'][field][0]
            gains[label][stage]=dict(B0=a,B1=b,B0_minus_B1=a-b,B1_reduction_percent=100*(a-b)/a)
    failures=[]
    for p,value in results['NEW'].items():
        if value['Actual_physical_violation']:failures.append(p+'_ACTUAL_PHYSICAL_VALIDATION_FAIL')
        for stage,grid in value['electrical'].items():
            if grid['raw_voltage_violation_count'] or grid['line_current_violation_count']:failures.append(p+'_'+stage+'_PHYSICAL_ELECTRICAL_VIOLATION')
        assert value['terminal']['TERMINAL_CONSTRAINT_VIOLATIONS']==0
        assert not value['independent_day']['previous_policy_day_terminal_state_used']
    report=dict(status='COMPLETE_RAW_OUTCOMES_REPORTED',scientific_commit=frozen['scientific_commit'],
        full_May_launch_gate='FAIL' if failures else 'PASS',full_May_blocking_reasons=failures,full_May_launched=False,
        voltage_margin='CANCELLED_BY_USER',EPSILON_V_UP='NOT_INTRODUCED',NEW_VOLTAGE_MARGIN='NONE',
        results=results,primary_gains=gains,all_four_phases_same_scientific_commit=True,receipts=receipts,
        ML_snapshot_count=1,PENDING_runtime_rows=1395,H4_rows=81,unchanged_old_vs_new_scalar_outputs=True,
        scalar_SHA=project(snapshot).sha256,pre_solve_persistence=record(RUNTIME/'inputs'/DAY/'PRE_SOLVE_PERSISTENCE_AUDIT.json'),
        preserved_old_May01_files=len(original),P0=record(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json'),
        B0_in_B1=record(OUT/'V41_MAY01_B0_IN_B1_FEASIBILITY.json'),
        attribution_limit='Saved job deltas exactly decompose decisions and 18h GPU occupancy. Joint nonlinear rho gains are not additively attributed without controlled ablations; pre-D00 freeze is a separate changed boundary.',
        generator=record(__file__))
    write_json(OUT/'V41R1_MAY01_OLD_VS_NEW_RESULTS.json',native(report))
    write_json(OUT/'V41R1_COMPLETE_PERSISTENCE_AUDIT.json',dict(status='PASS',policy_files=files,phase_receipts=receipts,
        all_manifest_leaves_reopened=True,ML_tables_reopened=True,terminal_tables_reopened=True,
        source_and_commits_identical=True,old_files_unchanged=len(original)))
    flat=[]
    for label,policies in results.items():
        for p,value in policies.items():
            for stage,metrics in value['electrical'].items():
                flat.append(dict(revision=label,policy=p,stage=stage,**{k:metrics[k] for k in ('Vmin','Vmax','rho_max','raw_voltage_violation_count')},
                    maximum_voltage_location=str(metrics['maximum_voltage_location']),critical_line_location=str(metrics['critical_line_location'])))
    pd.DataFrame(flat).to_csv(OUT/'V41R1_MAY01_RAW_ELECTRICAL_RESULTS.csv',index=False)
    print(native(dict(primary_gains=gains,NEW={p:{k:v[k] for k in ('DayAhead_objective_vector','Actual_evaluated_objective_vector','electrical','occupancy','decision_changes')} for p,v in results['NEW'].items()},full_May_launch_gate=report['full_May_launch_gate'])))


if __name__=='__main__':main()
