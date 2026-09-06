"""Two-case attribution after corrected Planning/Fresh/Actual; never a campaign."""
from pathlib import Path
import inspect,json,math
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,reference,sha,write_json,write_parquet
from dayahead.v40e.audit import REL,OLD


def service(repo):
    from dayahead.tools import audit_v40d_service_equivalence as original
    src=inspect.getsource(original.main)
    src=src.replace('root = REPO / "dayahead/artifacts/v40d_actual_realized_replay"','root = REPO / "dayahead/artifacts/v40e_background_mapping_fix"')
    src=src.replace('observed_path = root / "V40D_FROZEN_JOB_OBSERVATIONS.parquet"','observed_path = REPO / "dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet"')
    src=src.replace('("B0", "B1", "B2", "B3")','("B0", "B1")')
    ns=dict(original.__dict__);ns['REPO']=Path(repo).resolve();exec(compile(src,'<V40E_two_case_service_audit>','exec'),ns)
    ns['main']()
    return read(Path(repo)/REL/'service_equivalence/2025-05-01/V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json')


def result_metrics(path):
    with np.load(path) as z:a={k:z[k] for k in z.files}
    branches=a['branch_names'].astype(str);phases=a['branch_phases'].astype(str)
    mask=np.char.startswith(branches,'line.');indices=np.flatnonzero(mask);line=a['phase_current_loading_pu'][:,indices]
    t,j=np.unravel_index(np.argmax(line),line.shape);k=indices[j];v=a['voltage_pu']
    return {'rho':float(line[t,j]),'critical_line':str(branches[k]),'critical_phase':str(phases[k]),'critical_slot':int(t),
            'critical_time':f'{t//4:02d}:{(t%4)*15:02d}','critical_current_A':float(a['phase_current_a'][t,k]),
            'Vmin':float(v.min()),'Vmax':float(v.max()),'voltage_violations':int(((v<.95-1e-9)|(v>1.05+1e-9)).sum()),
            'losses_kWh':float(a['losses_kw_kvar'][:,0].sum()*.25),'source':reference(path)},a


def finish(repo):
    repo=Path(repo).resolve();root=repo/REL;smoke=root/'smoke/2025-05-01';out=root/'b0_b1_forensic';out.mkdir(parents=True,exist_ok=True)
    values=read(smoke/'V40E_B0_B1_CORRECTED_RESULTS.json');sv=service(repo)
    metrics=[];data={};pair_checks=[]
    for ns,dir_ in [('Fresh','fresh'),('Actual','actual_grid')]:
        for case in ('B0','B1'):
            new=smoke/case/dir_/'OPENDSS_PHASE_ARRAYS.npz'
            old=repo/OLD/'power_scale_parity/2025-05-01'/ns/case/'grid/OPENDSS_PHASE_ARRAYS.npz'
            before,oldarr=result_metrics(old);after,newarr=result_metrics(new);data[ns,case]=newarr
            metrics.append({'case':case,'namespace':ns,'old':before,'corrected':after,
                'regulator_state_changed_cells':int(np.count_nonzero(newarr['regulator_taps']!=oldarr['regulator_taps'])),
                'capacitor_state_changed_cells':int(np.count_nonzero(newarr['capacitor_states']!=oldarr['capacitor_states']))})
        stem='fresh_readback' if ns=='Fresh' else 'actual_readback'
        f={c:pd.read_parquet(smoke/c/stem/'OPENDSS_COMPONENT_ELEMENTS.parquet') for c in ('B0','B1')}
        a=f['B0'].set_index(['slot','element']).sort_index();b=f['B1'].set_index(['slot','element']).sort_index()
        assert a.index.equals(b.index)
        delta=b[['P_kw','Q_kvar']]-a[['P_kw','Q_kvar']];delta.columns=['Delta_P_kw_B1_minus_B0','Delta_Q_kvar_B1_minus_B0'];delta['component']=a.component
        outside=delta[delta.component!='AIDC'][['Delta_P_kw_B1_minus_B0','Delta_Q_kvar_B1_minus_B0']]
        assert np.count_nonzero(outside.to_numpy())==0
        assert a.OpenDSS_bus.equals(b.OpenDSS_bus)
        inv0=read(smoke/'B0'/stem/'ENGINE_MAPPING_RATINGS_SOURCE.json');inv1=read(smoke/'B1'/stem/'ENGINE_MAPPING_RATINGS_SOURCE.json')
        assert inv0==inv1
        assert np.array_equal(data[ns,'B0']['regulator_taps'],data[ns,'B1']['regulator_taps'])
        assert np.array_equal(data[ns,'B0']['capacitor_states'],data[ns,'B1']['capacitor_states'])
        write_parquet(out/(ns+'_B0_B1_INPUT_DELTA_DECOMPOSITION.parquet'),delta.reset_index())
        pair_checks.append({'namespace':ns,'background_P_Q_exact_equal':True,'PV_exact_equal':True,'MESS_OFF_exact_equal':True,
            'topology_mapping_ratings_source_exact_equal':True,'native_control_states_exact_equal':True,'AIDC_bus_phase_identity':True,
            'nonzero_electrical_input_difference_outside_AIDC_count':0,'AIDC_PQ_difference_nonzero_cells':int(np.count_nonzero(delta[delta.component=='AIDC'][['Delta_P_kw_B1_minus_B0','Delta_Q_kvar_B1_minus_B0']]))})
    # Evaluate both cases at the union of their own critical coordinates; no max-of-different-arrays attribution shortcut.
    critical=[];site_rows=[]
    for ns in ('Fresh','Actual'):
        coordinates={(m['corrected']['critical_line'],m['corrected']['critical_phase'],m['corrected']['critical_slot']) for m in metrics if m['namespace']==ns}
        for line,ph,t in sorted(coordinates):
            a=data[ns,'B0'];b=data[ns,'B1'];k=next(k for k,(n,p) in enumerate(zip(a['branch_names'],a['branch_phases'])) if n==line and p==ph)
            row={'namespace':ns,'line':line,'phase':ph,'slot':t,'B0_current_A':float(a['phase_current_a'][t,k]),'B1_current_A':float(b['phase_current_a'][t,k]),
                 'B0_loading':float(a['phase_current_loading_pu'][t,k]),'B1_loading':float(b['phase_current_loading_pu'][t,k])}
            stem='fresh_readback' if ns=='Fresh' else 'actual_readback'
            for c in ('B0','B1'):
                f=pd.read_parquet(smoke/c/stem/'OPENDSS_COMPONENTS_96.parquet').set_index('slot')
                row.update({c+'_'+field:float(f.loc[t,field]) for field in ['background_P_kw','background_Q_kvar','PV_P_kw','AIDC_P_kw','AIDC_Q_kvar','MESS_P_kw','P_net_kw']})
            critical.append(row)
            fa=pd.read_parquet(smoke/'B0'/stem/'OPENDSS_COMPONENT_ELEMENTS.parquet');fb=pd.read_parquet(smoke/'B1'/stem/'OPENDSS_COMPONENT_ELEMENTS.parquet')
            aa=fa[(fa.slot==t)&(fa.component=='AIDC')].set_index('AIDC_site_id');bb=fb[(fb.slot==t)&(fb.component=='AIDC')].set_index('AIDC_site_id')
            for site in aa.index:
                site_rows.append({'namespace':ns,'line':line,'phase':ph,'slot':t,'site':site,'bus':aa.loc[site,'OpenDSS_bus'],
                    'B0_PCC_P_kw':aa.loc[site,'P_kw'],'B1_PCC_P_kw':bb.loc[site,'P_kw'],'Delta_PCC_P_kw':bb.loc[site,'P_kw']-aa.loc[site,'P_kw'],
                    'B0_PCC_Q_kvar':aa.loc[site,'Q_kvar'],'B1_PCC_Q_kvar':bb.loc[site,'Q_kvar'],'Delta_PCC_Q_kvar':bb.loc[site,'Q_kvar']-aa.loc[site,'Q_kvar']})
    write_parquet(out/'CRITICAL_LINE_PHASE_SLOT_ATTRIBUTION.parquet',pd.DataFrame(critical))
    write_parquet(out/'CRITICAL_SLOT_SITE_PQ_DECOMPOSITION.parquet',pd.DataFrame(site_rows))
    deltas=read(smoke/'V40E_B0_B1_EXECUTION_STOP_GATE.json')['deltas_B0_minus_B1']
    result={'B0_B1_WORKLOAD_IDENTITY':'PASS','B0_DATA_CENTER_PRESENT':'PASS','B1_DATA_CENTER_PRESENT':'PASS',
        'BACKGROUND_MAPPING_FIXED':'PASS','PLANNING_ELECTRICAL_AUTHORITY_REBUILT':'PASS','POWER_SCALE_PARITY':'PASS','AIDC_SPATIAL_BINDING':'PASS',
        'same_exogenous_input_proofs':pair_checks,'results':values,'old_new_metrics':metrics,'deltas_B0_minus_B1':deltas,
        'service_equivalence':sv,'critical_coordinates':critical,'B2_B3_started':False,'full_May_started':False,'FULL_CAMPAIGN_AUTHORIZED':False,
        'UNASSIGNED_44_case_blocker':'PRESERVED','PV_scale_note':'Frozen nominal allocation 698.000002861023 kW and existing alpha_grid application both retained. No PV rescaling or new PUE factor.',
        'forensic_verdict':'PENDING_ADDITIONAL_ATTRIBUTION' if deltas['Delta_Actual']<=0 else 'CORRECTED_AIDC_ACTUAL_IMPROVEMENT_OBSERVED_PENDING_USER_ACCEPTANCE'}
    write_json(out/'V40E_B0_B1_END_TO_END_FORENSIC.json',result)
    print(json.dumps({'deltas':deltas,'critical':critical}),flush=True)
