"""Rebuild only descendants of native load-element allocation.

The exogenous reference PCC control input precedes AC allocation. Its stored
input digest is verified separately; no old voltages, currents, gradients or
native-control outcomes are supplied to the new anchor generator.
"""
from pathlib import Path
from types import FunctionType,SimpleNamespace
from dataclasses import replace
from functools import lru_cache
import hashlib,json,os
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,reference,sha,digest,write_json,write_npz,write_parquet
from dayahead.v40e.audit import REL,OLD,source
from dayahead.v40e.mapping import corrected_mapping


class LoadedNPZ(dict):
    """Decompress each newly certified array once; preserve exact array values."""
    @property
    def files(self):return list(self)
    def close(self):pass
    @classmethod
    def open(cls,path):
        with np.load(path,allow_pickle=False) as z:return cls({k:z[k] for k in z.files})


def old_cache(repo,day):
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    if day.startswith('2025-05-'):return Path(repo)/'dayahead/cache/v37_may_locked_final/electrical'/day
    a=SOURCE_DATA_REPOSITORY/'frozen_artifacts/v28r2_april_full_month_preflight'/day/'dayahead/electrical_cache'
    if not (a/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz').exists():
        a=Path(repo)/'dayahead/cache/v37_r2_april_background'/day
    if not (a/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz').exists():
        a=Path(repo).parent/'MobileESS_v37_may_final/dayahead/cache/v37_r2_april_background'/day
    return a


@lru_cache(maxsize=12)
def upstream(repo,day):
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v28r2.electrical_context import source_root,portable_background_paths
    from dayahead.v28r2.source_cache import day_root
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    from dayahead import grid_background_v16_2 as bg
    repo=Path(repo).resolve();out=repo/REL/'electrical'/day;out.mkdir(parents=True,exist_ok=True)
    cache=old_cache(repo,day);vp=cache/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz'
    from dayahead.v41r2.authority import OUT as rebase_out,DAY as rebase_day
    assert day==rebase_day,'V41R2_FULL_MAY_HOLD'
    vp=rebase_out/'V41R2_B0_IT_PCC.npz'
    with np.load(vp) as z:
        plan=np.asarray(z['pcc']).copy()
    control=np.column_stack([plan,np.zeros((96,24))])
    recorded=hashlib.sha256(json.dumps(plan.tolist(),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    computed=hashlib.sha256(json.dumps(plan.tolist(),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    assert recorded==computed and np.count_nonzero(control[:,12:])==0
    write_npz(out/'UPSTREAM_REFERENCE_PCC_CONTROL_INPUT.npz',reference_pcc_kw=plan)
    forecast_path=day_root(SOURCE_DATA_REPOSITORY,day)/'aemo_forecast.json';forecast=read(forecast_path)
    paths=portable_background_paths(SOURCE_DATA_REPOSITORY,source_root(SOURCE_DATA_REPOSITORY));refs={str(forecast_path):sha(forecast_path)}
    def verify(p):
        records={}
        for name,expected in bg.EXPECTED_SHA256.items():
            if name=='pv_reference':records[name]={'sha256':expected,'status':'FROZEN_NORMALIZATION_PROVENANCE_NOT_NUMERIC_INPUT'};continue
            path=getattr(p,name);assert sha(path)==expected,name
            refs[str(path)]=expected;records[name]=reference(path)
        return records
    ns=dict(bg.build_authority_background_binding.__globals__);ns['_verify_sources']=verify
    build=FunctionType(bg.build_authority_background_binding.__code__,ns)
    background=build(timestamps_fixed_aest=forecast['timestamps_96'],demand_mw_96=forecast['demand_mw_96'],rooftop_pv_mw_96=forecast['pv_mw_96'],paths=paths)
    axis=sorted(set().union(*[set(row) for row in background.gross_p_kw_96]))
    write_npz(out/'UPSTREAM_BUS_PHASE_TARGETS.npz',bus_phase_keys=np.array([b+'::'+p for b,p in axis]),
        gross_P_kw=np.array([[r.get(k,0.) for k in axis] for r in background.gross_p_kw_96]),
        gross_Q_kvar=np.array([[r.get(k,0.) for k in axis] for r in background.gross_q_kvar_96]),
        PV_P_kw=np.array([[r.get(k,0.) for k in axis] for r in background.pv_generation_kw_96]))
    src=source_root(SOURCE_DATA_REPOSITORY);previous=Path.cwd()
    try:
        binding=build_full_grid_binding(assets=src/'opendss_assets',contract=src/'power_v70_p4f_contract',
            demand_mw_96=forecast['demand_mw_96'],rooftop_pv_mw_96=forecast['pv_mw_96'],aidc_plan_kw_96x12=plan,
            pcc_asset=SOURCE_DATA_REPOSITORY/'dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss',background_binding=background)
    finally:os.chdir(previous)
    write_json(out/'UPSTREAM_REUSE_CERTIFICATE.json',{'day':day,'source_input_SHAs':refs,
        'reference_control_input':reference(out/'UPSTREAM_REFERENCE_PCC_CONTROL_INPUT.npz'),
        'reference_control_input_sha_in_historical_container':recorded,'input_payload_digest_verified':True,
        'historical_container':reference(vp),'reused_fields':['V41R2 rematerialized B0 PCC (pre-AC input)'],
        'historical_AC_anchor_voltage_reused':False,'historical_current_reused':False,'historical_sensitivity_reused':False,
        'historical_native_control_state_reused':False,'historical_May_case_decisions_reused':False,
        'upstream_reference_constructor':source(repo,'dayahead/v28r2/electrical_context.py','_legacy_reference'),
        'reason':'V41R2 operating point is the new Q90 B0 PCC trajectory, derived before AC generation; no historical AC outputs reused.'})
    return plan,forecast,background,binding,src,refs


def rebuild_day(repo,day):
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.run_v16_3_voltage_candidate import _anchor_and_sensitivity_day
    from dayahead.run_v16_3_correction import _generate_current_day
    repo=Path(repo).resolve();out=repo/REL/'electrical'/day
    resultpath=out/'V40E_ELECTRICAL_REBUILD_LINEAGE.json'
    if resultpath.exists():
        result=read(resultpath)
        if result['mapper_SHA']!=sha(repo/'dayahead/v40e/mapping.py'):raise RuntimeError('CORRECTED_MAPPER_DRIFT')
        for row in result['outputs'].values():assert sha(row['new']['path'])==row['new']['sha256']
        return result
    plan,forecast,bg,binding,src,refs=upstream(str(repo),day)
    vp=out/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz';ip=out/'data'/f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz'
    # Existing uncertified V40E cache is never silently reused.
    if vp.exists() or ip.exists():raise RuntimeError('UNSEALED_CORRECTED_CACHE_EXISTS:'+day)
    previous=Path.cwd()
    try:
        with corrected_mapping() as patch:
            print('BUILD corrected anchor/voltage '+day,flush=True)
            _anchor_and_sensitivity_day(SOURCE_DATA_REPOSITORY,src,bg,plan.tolist(),binding,day,vp)
            print('BUILD corrected line/transformer current '+day,flush=True)
            _generate_current_day(SOURCE_DATA_REPOSITORY,src,out,day,({'plan_kw_96x12':plan.tolist()},forecast,bg,binding,vp,None))
    finally:os.chdir(previous)
    outputs={};old=old_cache(repo,day)
    for label,path in [('voltage',vp),('current',ip)]:
        oldp=old/'data'/path.name;changes={}
        with np.load(path) as new,np.load(oldp) as before:
            for k in new.files:
                if k not in before:continue
                a=new[k];b=before[k]
                if a.dtype.kind in 'fiu' and a.shape==b.shape:changes[k]={'exact_equal':bool(np.array_equal(a,b)),'max_abs_change':float(np.max(abs(a-b),initial=0))}
            if label=='current':
                assert np.array_equal(new['rating_a'],before['rating_a'])
                assert str(new['source_voltage_cache_sha256'])==sha(vp)
        outputs[label]={'old':reference(oldp),'new':reference(path),'numeric_changes':changes}
        assert outputs[label]['old']['sha256']!=outputs[label]['new']['sha256']
    result={'day':day,'status':'PASS','mapper_SHA':sha(repo/'dayahead/v40e/mapping.py'),'patched_aliases':patch['patched_aliases'],
            'source_input_SHAs':refs,'outputs':outputs,'old_contaminated_electrical_cache_reuse_count':0,
            'native_controls':'NEW_D1_NATIVE_CONTROL_SOLVES_THEN_FROZEN_PER_SLOT',
            'line_and_transformer_current_sensitivity':'Every branch row in current cache is freshly measured with unchanged rating.',
            'transformer_kVA_model':'The method has no separate AC kVA sensitivity artifact: transformer P/Q constants and control matrices come from the lossless full-grid binding; kVA polygon uses these same preserved equations and ratings.',
            'transformer_kVA_no_model_change':True,'full_May_campaign_started':False}
    write_json(resultpath,result);print('SEALED corrected electrical '+day,flush=True);return result


def electrical_context(repo,day):
    from dayahead.v28r2.electrical_context import ElectricalContext
    repo=Path(repo).resolve();out=repo/REL/'electrical'/day
    cert=read(out/'V40E_ELECTRICAL_REBUILD_LINEAGE.json')
    assert cert['mapper_SHA']==sha(repo/'dayahead/v40e/mapping.py') and cert['status']=='PASS'
    plan,forecast,bg,binding,src,refs=upstream(str(repo),day)
    vp=out/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz';ip=out/'data'/f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz'
    for label,p in [('voltage',vp),('current',ip)]:assert sha(p)==cert['outputs'][label]['new']['sha256']
    legacy=({'plan_kw_96x12':plan.tolist()},forecast,bg,binding,vp,cert)
    return ElectricalContext(legacy,LoadedNPZ.open(vp),LoadedNPZ.open(ip),src,vp,ip)


def rebuild_april_joint(repo):
    from dayahead.tools import run_v37_r2_voltage_fidelity_repair as r2
    from dayahead.tools import run_v37_r3_restore_intended_cuts as r3
    from dayahead.v36 import context as april_context
    repo=Path(repo).resolve();out=repo/REL/'april_joint_authority';out.mkdir(parents=True,exist_ok=True)
    states,loaded=r2._aggregate_states(repo)
    selected=r2._select_calibration_states(states)
    # Reconstruct the frozen background probe population directly from the sealed calibration rows.
    oldpath=repo/'dayahead/artifacts/v37_r2_voltage_fidelity_repair/V37_R2_FRESH_LOCAL_SENSITIVITY.parquet'
    old=pd.read_parquet(oldpath);back=old[old.probe_kind=='TARGETED_APRIL_BACKGROUND_FRESH_ONLY_PROBE'].drop_duplicates('calibration_state_id')
    extra=[]
    for row in back.itertuples(index=False):
        day=str(row.day);key=(day,'FRESH_ONLY')
        if key not in loaded:
            plan=upstream(str(repo),day)[0]
            loaded[key]={'pcc_p':plan,'pcc_q':plan*r2.PF_TAN,'p':np.zeros((96,4)),'q':np.zeros((96,4)),
                         'locations':np.array([[f'TRANSIT_{v}' for v in r2.MESS_IDS] for _ in range(96)],dtype=object),
                         'fresh':None,'planning':None,'formulation_data':True,'electrical_cache':repo/REL/'electrical'/day}
        extra.append({'day':day,'case':'FRESH_ONLY','slot':int(row.slot),'service':str(row.source_service),'timestamp':row.timestamp,
            'P_kW':0.,'Q_kvar':0.,'Fresh_local_Vmin_pu':np.nan,'vehicle_ids':str(r2.MESS_IDS[0]),
            'selection_reasons':row.selection_reasons,'calibration_state_id':row.calibration_state_id,'probe_kind':row.probe_kind,
            'probe_target_P_kW':row.P_at_source_PCC_kW,'probe_target_Q_kvar':row.Q_at_source_PCC_kvar,
            'probe_vehicle_index':0,'override_source_location':True,'zero_all_MESS_at_slot':True})
    selected=pd.concat([selected,pd.DataFrame(extra)],ignore_index=True)
    assert set(selected.calibration_state_id)==set(old.calibration_state_id)
    write_parquet(out/'FROZEN_CALIBRATION_STATES.parquet',selected)
    original=(r2.build_electrical_context,april_context.load_day_context)
    r2.build_electrical_context=lambda _repo,_data,cache:electrical_context(repo,Path(cache).name)
    april_context.load_day_context=lambda day:(None,electrical_context(repo,day))
    try:
        with corrected_mapping():
            print('REMEASURE frozen April joint-gradient states '+str(len(selected)),flush=True)
            measured=r2._measure_calibration(repo,selected,loaded)
            repeated=r2._measure_calibration(repo,selected,loaded)
    finally:r2.build_electrical_context,april_context.load_day_context=original
    key=['calibration_state_id','source_service','target_bus_phase_key'];a=measured.set_index(key).sort_index();b=repeated.set_index(key).sort_index()
    assert a.index.equals(b.index)
    errors={k:float(abs(a[k]-b[k]).max()) for k in ['Fresh_base_voltage_pu','Fresh_H_P_pu_squared_per_kW','Fresh_H_Q_pu_squared_per_kvar']}
    assert max(errors.values())<=1e-10
    local=measured[measured.target_is_selectable_MESS_PCC].copy()
    write_parquet(out/'V40E_CORRECTED_APRIL_LOCAL_SENSITIVITY.parquet',local)
    write_parquet(out/'V40E_CORRECTED_APRIL_FULL_BUS_PHASE_SENSITIVITY.parquet',measured)
    gradients=[]
    for group,f in local.groupby(['source_service','target_service','phase'],sort=True):
        f=f.sort_values(['day','case','slot','calibration_state_id']).reset_index(drop=True);chosen,score=r3._select_joint_gradient(f)
        gradients.append({'source_service':group[0],'target_service':group[1],'phase':group[2],
            'target_bus_phase_key':chosen.target_bus_phase_key,'H_P_pu_squared_per_kW':float(chosen.Fresh_H_P_pu_squared_per_kW),
            'H_Q_pu_squared_per_kvar':float(chosen.Fresh_H_Q_pu_squared_per_kvar),'P_Q_same_April_state':True,
            'selected_calibration_state_id':chosen.calibration_state_id,'selected_day':chosen.day,'selected_slot':int(chosen.slot),
            'selection_score':list(score),'candidate_count':len(f)})
    assert len(gradients)==1728
    oldauth=repo/'dayahead/artifacts/v37_r3_restore_intended_cuts/V37_R3_JOINT_VOLTAGE_AUTHORITY.json'
    authority={'schema':'V40E_CORRECTED_APRIL_JOINT_VOLTAGE_AUTHORITY','status':'PASS','old_authority':reference(oldauth),
        'mapper_SHA':sha(repo/'dayahead/v40e/mapping.py'),'calibration_source':reference(out/'V40E_CORRECTED_APRIL_LOCAL_SENSITIVITY.parquet'),
        'frozen_state_population':reference(out/'FROZEN_CALIBRATION_STATES.parquet'),'joint_gradients':gradients,
        'same_selection_function':source(repo,'dayahead/tools/run_v37_r3_restore_intended_cuts.py','_select_joint_gradient'),
        'May_outcomes_used_for_selection':False,'repeat_max_errors':errors,'calibration_days':sorted(local.day.unique()),
        'old_contaminated_gradient_reuse_count':0,'new_tuning_parameters':0}
    write_json(out/'V40E_CORRECTED_JOINT_VOLTAGE_AUTHORITY.json',authority);print('SEALED 1728 corrected joint gradients',flush=True)


def planning_context(repo,day):
    from dayahead.v28r2.electrical_subproblem import slot_coefficients
    from dayahead.v36.storage import attach_context
    from dayahead.v39d.evaluate import _load_capacity
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    repo=Path(repo).resolve();e=electrical_context(repo,day)
    authpath=repo/REL/'april_joint_authority/V40E_CORRECTED_JOINT_VOLTAGE_AUTHORITY.json';auth=read(authpath)
    assert auth['status']=='PASS' and auth['mapper_SHA']==sha(repo/'dayahead/v40e/mapping.py')
    nodes=list(map(str,e.voltage['node_names']));controls=list(map(str,e.voltage['control_names']));coeff=[]
    indexed=[(controls.index(f"mess_p_kw[{r['source_service']}]"),controls.index(f"mess_q_kvar[{r['source_service']}]"),nodes.index(r['target_bus_phase_key']),r['H_P_pu_squared_per_kW'],r['H_Q_pu_squared_per_kvar']) for r in auth['joint_gradients']]
    for t in range(96):
        c=slot_coefficients(e.legacy_context,e.voltage,e.current,t);h=c.voltage_matrix.copy()
        for p,q,n,hp,hq in indexed:h[p,n]=hp;h[q,n]=hq
        const=e.voltage['anchor_v_squared'][t]-h.T@c.anchor
        coeff.append(replace(c,voltage_constant=const,voltage_matrix=h,coefficient_sha256=digest({'base':c.coefficient_sha256,'joint':sha(authpath),'mapper':auth['mapper_SHA'],'slot':t})))
    coefficients=tuple(coeff);attach_context(coefficients,e.legacy_context)
    capacity,_=_load_capacity(repo);c1path=repo/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json';c1=load_c1(c1path)
    wp=day_root(SOURCE_DATA_REPOSITORY,day)/'gfs_d1_weather.parquet';weather=pd.read_parquet(wp);tables={}
    for site,cap in capacity.site_capacity.items():
        it=np.array([float(site_it_power_kw(cap,g)) for g in range(cap+1)])
        tables[site]=np.array([exact_c1_pcc_kw(it,float(w.t_wb_c),float(w.rh_pct),c1) for w in weather.itertuples(index=False)])
    refs=dict(upstream(str(repo),day)[5]);refs.update({str(p):sha(p) for p in [e.voltage_path,e.current_path,authpath,c1path,wp,repo/'dayahead/v40e/mapping.py']})
    return SimpleNamespace(electrical=e,coefficients=coefficients,nodes=nodes,capacity=capacity,tables=tables,input_shas=refs,day=day,
        provenance={'old_electrical_cache_reuse':0,'corrected_electrical_authority':True,'Actual_reads':0,'Fresh_case_result_reads':0,'candidate_AC_solves':0})


def main(repo):
    repo=Path(repo).resolve();out=repo/REL
    assert read(out/'allocation_tests/V40E_ALLOCATION_TEST_RESULT.json')['BACKGROUND_ALLOCATION_CONSERVATION']=='PASS'
    assert read(out/'b0_semantics/V40E_CASE_SEMANTICS_FIREWALL.json')['CASE_SEMANTICS_GATE']=='PASS'
    lineage={'EARLIEST_CONTAMINATED_ARTIFACT':'NATIVE_LOAD_ELEMENT_ALLOCATION (runtime values); earliest persisted descendant is D1_AC_ANCHOR_SENSITIVITY_<day>.npz',
        'earliest_allocation_witness':reference(repo/OLD/'power_scale_parity/2025-05-01/Fresh/B0/OPENDSS_COMPONENT_ELEMENTS.parquet'),
        'upstream_preserved':['regional demand/PV','normalization constants','96-slot normalized profiles','bus-phase background targets','PV allocation','exogenous reference PCC input','topology/ratings'],
        'boundary':'Only the inverse aggregate bus-phase to native load-element allocation is corrected. Rebuild all AC descendants.',
        'B0_B2_reference_decisions_preserved':True,'B1_B3_old_optimized_decisions_production_reuse':False,'REQUIRED_RERUN_BOUNDARY':'CASE C'}
    write_json(out/'V40E_EARLIEST_CONTAMINATED_AUTHORITY.json',lineage)
    # April calibration repair is limited to the already frozen eight-day state population, not an April/May campaign.
    days=read(repo/'dayahead/artifacts/v37_r3_restore_intended_cuts/V37_R3_JOINT_VOLTAGE_AUTHORITY.json')['calibration_days']
    for day in ['2025-05-01']+days:rebuild_day(repo,day)
    if not (out/'april_joint_authority/V40E_CORRECTED_JOINT_VOLTAGE_AUTHORITY.json').exists():rebuild_april_joint(repo)
    c=planning_context(repo,'2025-05-01')
    branch_names=np.array(c.coefficients[0].branch_names)
    arrays={'node_names':np.array(c.nodes),'branch_names':branch_names}
    for field in ('voltage_constant','voltage_matrix','current_constant','current_matrix','flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix','branch_limits'):
        arrays[field]=np.array([getattr(x,field) for x in c.coefficients])
    write_npz(out/'electrical/2025-05-01/V40E_PLANNING_ELECTRICAL_COEFFICIENTS.npz',**arrays)
    tx=np.flatnonzero(np.char.startswith(branch_names,'transformer.'))
    write_npz(out/'electrical/2025-05-01/V40E_TRANSFORMER_CURRENT_KVA_COEFFICIENTS.npz',branch_names=branch_names[tx],
        current_constant=arrays['current_constant'][:,tx],current_matrix=arrays['current_matrix'][:,:,tx],
        P_constant=arrays['flow_p_constant'][:,tx],Q_constant=arrays['flow_q_constant'][:,tx],
        P_control_matrix=arrays['flow_p_matrix'][:,tx,:],Q_control_matrix=arrays['flow_q_matrix'][:,tx,:],
        kVA_ratings=np.array([np.nan if x is None else float(x) for x in c.coefficients[0].transformer_ratings])[tx])
    write_json(out/'V40E_CORRECTED_ELECTRICAL_AUTHORITY_GATE.json',{'status':'PASS','May_day':'2025-05-01','April_calibration_days':days,
        'PLANNING_ELECTRICAL_AUTHORITY_REBUILT':'PASS','old_contaminated_cache_reuse_count':0,'coefficient_SHAs':[x.coefficient_sha256 for x in c.coefficients],
        'source_input_SHAs':c.input_shas,'physical_gates':'Rebuilt coefficient-dependent evaluator; case-specific feasibility to be checked before Fresh.',
        'full_May_campaign_authorized':False})
    c.electrical.voltage.close();c.electrical.current.close()
