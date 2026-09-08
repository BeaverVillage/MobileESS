"""Solver-free May-wide B0 screen. Existing authorities are read-only.

Independent spawn processes, one clean DSS context per trajectory, no electrical
coefficient generation. The strict screen summary is authoritative; inherited
OpenDSS summaries retain their historical reporting tolerance only.
"""
from pathlib import Path
from types import SimpleNamespace, FunctionType
from contextlib import contextmanager
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import hashlib, json, os, sys, time, subprocess
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'dayahead/artifacts/v41r4_may_alpha_screen'
MAY = ROOT/'dayahead/artifacts/v41r3_fast_power_scale_freeze/may_campaign'
RUN = ROOT/'frozen_artifacts/v41r3_may'
SCALE_RUN = ROOT/'frozen_artifacts/v41r3_scale'
ALPHAS = (1.35, 1.40, 1.45, 1.50)
DAYS = tuple(f'2025-05-{n:02}' for n in range(1,32))
VECTOR = (80,40,80,40,100,80,40,80,40,80,40,80)
SITES = tuple(f'AIDC{n:02}' for n in range(1,13))

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def rec(p):
    p=Path(p).resolve()
    with p.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p),sha256=h,bytes=p.stat().st_size)
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f: json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False)
def atomic(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_suffix('.tmp');q.write_text(json.dumps(v,indent=2,allow_nan=False),encoding='utf-8');os.replace(q,p)
def npz(p,**a):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists()
    np.savez_compressed(p,**a)
    with np.load(p) as z: assert all(np.array_equal(z[k],v,equal_nan=True) if np.asarray(v).dtype.kind=='f' else np.array_equal(z[k],v) for k,v in a.items())
    return rec(p)
def arrays(p):
    with np.load(p) as z: return {k:z[k].copy() for k in z.files}
def input_folder(day): return (SCALE_RUN if day=='2025-05-04' else RUN)/'inputs'/day
def power_path(day):
    if day=='2025-05-04': return SCALE_RUN/day/'B0/dayahead/FROZEN_AIDC_POWER.npz'
    return MAY/day/'V41R2_B0_IT_PCC.npz'

def background_builder():
    from dayahead import grid_background_v16_2 as bg
    from dayahead.v28r2.electrical_context import portable_background_paths,source_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    paths=portable_background_paths(SOURCE_DATA_REPOSITORY,source_root(SOURCE_DATA_REPOSITORY))
    # Same source-verification rule as authoritative v40e.electrical.upstream:
    # pv_reference is historical normalization provenance, not a numeric input.
    records={}
    for name,h in bg.EXPECTED_SHA256.items():
        if name=='pv_reference':
            records[name]=dict(sha256=h,status='FROZEN_NORMALIZATION_PROVENANCE_NOT_NUMERIC_INPUT');continue
        r=rec(getattr(paths,name));assert r['sha256']==h,(name,r);records[name]=r
    namespace=dict(bg.build_authority_background_binding.__globals__)
    namespace['_verify_sources']=lambda p:records
    build=FunctionType(bg.build_authority_background_binding.__code__,namespace)
    return lambda timestamps,demand,pv:build(timestamps_fixed_aest=timestamps,demand_mw_96=demand,rooftop_pv_mw_96=pv,paths=paths),records

def background_arrays(bg):
    keys=sorted(set().union(*(set(r) for rows in (bg.gross_p_kw_96,bg.gross_q_kvar_96,bg.pv_generation_kw_96) for r in rows)))
    return dict(bus_phase_keys=np.array(['::'.join(k) for k in keys]),
        **{name:np.array([[r.get(k,0.) for k in keys] for r in rows]) for name,rows in [('gross_P_kw',bg.gross_p_kw_96),('gross_Q_kvar',bg.gross_q_kvar_96),('PV_P_kw',bg.pv_generation_kw_96)]})

def background(day,stage,alpha):
    from dayahead.grid_background_v16_2 import AuthorityBackgroundBinding
    a=arrays(OUT/'inputs'/day/f'{stage}_BACKGROUND.npz');keys=[tuple(k.split('::')) for k in a['bus_phase_keys']]
    rows=lambda x:tuple(dict(zip(keys,map(float,row))) for row in x)
    p=alpha*a['gross_P_kw'];q=alpha*a['gross_Q_kvar'];pv=a['PV_P_kw']
    return AuthorityBackgroundBinding(rows(p-pv),rows(q),rows(p),rows(pv),dict(alpha_BG=alpha,PV_scaled=False,stage=stage))

def prepare():
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY,PF_TAN
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v41r2.authority import CAP,RACK
    from dayahead.v40g_segments.canonical import occupancy,import_frozen
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v28r2.opendss_mapping import FeederAssets,compile_clean_engine
    from dayahead.full_ieee123_g11_v16_1 import _oriented_branches
    from native_forensic import settings
    assert tuple(read(CAP)['new_vector'])==VECTOR and sum(VECTOR)==780
    protocol=dict(schema='V41R4_PREDECLARED_MAY_ALPHA_SCREEN_V1',candidate_alphas=list(ALPHAS),days=list(DAYS),
        selection_rule='LARGEST_ALPHA_AMONG_ALL_31_DAYAHEAD_B0_DAYS_PASS; else FAIL_CLOSE; no additional alphas',
        hard_limits=dict(Vmin_inclusive=.95,Vmax_inclusive=1.05,line_strict_upper=1.,transformer_current_strict_upper=1.,transformer_kVA_strict_upper=1.),
        B1_B2_B3_RESULTS_USED=False,Actual_results_used_for_selection=False,MESS_OFF=True,coefficient_generation_calls=0,
        optimization_calls=0,ROBUST_B1_executed=False,FULL_MAY_policy_optimization='HOLD',workers=4,
        parallelism='spawn processes; each trajectory owns a NewContext; no shared engine',
        created_UTC=pd.Timestamp.now(tz='UTC').isoformat(),runner=rec(__file__))
    save(OUT/'PREDECLARED_PROTOCOL.json',protocol)
    build,bgrefs=background_builder();assets=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
    previous=Path.cwd()
    try:
        odd,_=compile_clean_engine(assets);branches,topology=_oriented_branches(odd);conf=settings(odd)
        assert odd.CapControls.Count()==0
        odd.Basic.ClearAll()
    finally: os.chdir(previous)
    # Read the invariant node axis only, never a coefficient or old tap decision.
    node_source=ROOT/'dayahead/artifacts/v41r3_scale_rebalance/screen/alpha_1.600/DAYAHEAD/physics/OPENDSS_PHASE_ARRAYS.npz'
    with np.load(node_source) as z:
        nodes=z['node_names'].copy()
        assert z['branch_names'].tolist()==[b.branch_id for b in branches]
        assert z['branch_phases'].tolist()==[b.phase for b in branches]
    npz(OUT/'NODE_AXIS.npz',node_names=nodes)
    save(OUT/'TOPOLOGY_AND_CONTROLS.json',dict(branches=[vars(b) for b in branches],topology=topology,settings=conf,
        source_assets=assets.sha256,node_axis_source=rec(node_source),node_axis_only=True,old_sensitivities_loaded=False))
    c1path=ROOT/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json';c1=load_c1(c1path)
    protected={str(p.resolve()):rec(p) for folder in ('dayahead/v41','dayahead/v41r1','dayahead/v41r2','dayahead/v41r3','dayahead/v39a','dayahead/v39d','dayahead/v28r2','dayahead/v40e') for p in (ROOT/folder).glob('*.py')}
    protected.update({str(p.resolve()):rec(p) for p in [CAP,RACK,c1path,ROOT/'dayahead/mess_physics.py',ROOT/'dayahead/grid_background_v16_2.py',ROOT/'dayahead/full_ieee123_g11_v16_1.py',ROOT/'dayahead/run_v16_3_voltage_candidate.py']})
    for p in (ROOT/'dayahead/artifacts/v41r3_fast_power_scale_freeze').glob('*AUTHORITY.json'):protected[str(p.resolve())]=rec(p)
    daily=[]
    for day in DAYS:
        folder=input_folder(day);snap=folder/f'V41_ML_SNAPSHOT_{day}.json';seal=read(folder/'common_q90_v3/COMMON_INPUT_RECEIPT.json')
        assert seal['status']=='PASS' and seal['capacity_authority']==rec(CAP) and seal['snapshot']==rec(snap)
        for r in seal['files'].values():assert rec(r['path'])==r
        s=read(snap);assert np.all(np.asarray(s['H4_CAP_PHYS'])==3120)
        assert np.array_equal(s['future_service_capacity_gpu'],np.tile(VECTOR,(96,1)))
        for k in ('model','preprocessing'):
            r=s[k]
            if r['path'] not in protected:assert rec(r['path'])==r;protected[r['path']]=r
        jobs_path=folder/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json';jobs=read(jobs_path)
        assert not any(j.get('migration_selected') for j in jobs)
        gpu,_=occupancy(import_frozen(jobs),SITES);p=arrays(power_path(day))
        assert np.array_equal(gpu,p['gpu']) and np.all(gpu<=np.array(VECTOR))
        wp=day_root(SOURCE_DATA_REPOSITORY,day)/'gfs_d1_weather.parquet';weather=pd.read_parquet(wp)
        it=np.array([[float(site_it_power_kw(VECTOR[i],int(gpu[t,i]))) for i in range(12)] for t in range(96)])
        pcc=np.array([exact_c1_pcc_kw(it[t],float(w.t_wb_c),float(w.rh_pct),c1) for t,w in enumerate(weather.itertuples())])
        assert np.array_equal(it,p['it']) and np.array_equal(pcc,p['pcc']) and np.array_equal(pcc*PF_TAN,p['qcc'])
        fp=day_root(SOURCE_DATA_REPOSITORY,day)/'aemo_forecast.json';f=read(fp)
        bg=build(f['timestamps_96'],f['demand_mw_96'],f['pv_mw_96']);a=background_arrays(bg)
        old_bg=(ROOT/'dayahead/artifacts/v41r3_scale_rebalance' if day=='2025-05-04' else MAY/day)/'inputs/ORIGINAL_DAYAHEAD_BACKGROUND.npz'
        old_equal=None
        if old_bg.exists():
            old=arrays(old_bg);ix=[a['bus_phase_keys'].tolist().index(k) for k in old['bus_phase_keys']]
            assert all(np.array_equal(a[k][:,ix],old[k]) for k in ('gross_P_kw','gross_Q_kvar','PV_P_kw'));old_equal=True
        sources=dict(jobs=rec(jobs_path),common_receipt=rec(folder/'common_q90_v3/COMMON_INPUT_RECEIPT.json'),snapshot=rec(snap),power=rec(power_path(day)),forecast=rec(fp),weather=rec(wp))
        protected.update({r['path']:r for r in sources.values()})
        br=npz(OUT/'inputs'/day/'DAYAHEAD_BACKGROUND.npz',**a)
        pr=npz(OUT/'inputs'/day/'DAYAHEAD_POWER.npz',pcc=p['pcc'],qcc=p['qcc'],gpu=gpu,it=it)
        r=dict(day=day,sources=sources,background=br,power=pr,old_background_bit_exact=old_equal,B0_power_recomputed_bit_exact=True,AIDC_total_GPU=780,H4_cap_GPUh=3120)
        save(OUT/'inputs'/day/'DAYAHEAD_INPUT_RECEIPT.json',r);daily.append(r)
    save(OUT/'PROTECTED_INPUTS_AND_SOURCES.json',dict(records=list(protected.values()),background_sources=bgrefs,daily=daily,git_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),AIDC_authority=rec(CAP),AIDC_vector=list(VECTOR)))
    print('INPUTS_READY',len(daily),'days; 780GPU exact B0 power; coefficients=0',flush=True)

@contextmanager
def capture(stage,folder):
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.run_v16_3_voltage_candidate import _enable_native_controls
    from native_forensic import settings
    conf=read(OUT/'TOPOLOGY_AND_CONTROLS.json')['settings'];roots=[]
    original=backend._voltage_vector;old_apply=backend.apply_frozen_native_state
    def measure(odd,nodes):
        vals=original(odd,nodes);roots.append([-float(v) for v in odd.Circuit.TotalPower()[:2]])
        assert settings(odd)==conf,'NATIVE_CONTROL_SETTINGS_CHANGED'
        return vals
    backend._voltage_vector=measure
    if stage=='DAYAHEAD':backend.apply_frozen_native_state=lambda odd,v,t:_enable_native_controls(odd)
    try:yield roots
    finally:backend._voltage_vector=original;backend.apply_frozen_native_state=old_apply

def strict_summary(result,roots,alpha,stage):
    v=result.voltage_pu;c=result.phase_current_loading_pu;k=result.transformer_total_kva_loading_pu
    line=np.array(result.branch_kinds)=='line';tx=~line
    def extremum(a,names,phases,kind,maximum=True):
        flat=np.nanargmax(a) if maximum else np.nanargmin(a);t,i=np.unravel_index(flat,a.shape)
        return dict(kind=kind,asset=str(names[i]),phase=str(phases[i]),slot=int(t),value=float(a[t,i]))
    names=np.array(result.branch_names);phases=np.array(result.branch_phases)
    worsts=dict(voltage_low=extremum(v,result.node_names,result.node_phases,'VOLTAGE_LOW',False),voltage_high=extremum(v,result.node_names,result.node_phases,'VOLTAGE_HIGH'),
        line=extremum(c[:,line],names[line],phases[line],'LINE_CURRENT'),transformer_current=extremum(c[:,tx],names[tx],phases[tx],'TRANSFORMER_CURRENT'),transformer_kVA=extremum(k[:,tx],names[tx],phases[tx],'TRANSFORMER_TOTAL_KVA'))
    # Total kVA is a transformer-terminal quantity, count once per device/slot.
    unique_tx=list(dict.fromkeys(names[tx]));unique_indices=[list(names).index(n) for n in unique_tx]
    masks=dict(voltage=(v<.95)|(v>1.05),line_current=c[:,line]>=1.,transformer_current=c[:,tx]>=1.,transformer_kVA=k[:,unique_indices]>=1.)
    counts={name:int(mask.sum()) for name,mask in masks.items()}
    gates=dict(convergence=int(result.convergence.sum())==96,voltage=counts['voltage']==0,line=counts['line_current']==0,transformer_current=counts['transformer_current']==0,transformer_kVA=counts['transformer_kVA']==0)
    failures=[w for name,w in worsts.items() if ((name=='voltage_low' and w['value']<.95) or (name=='voltage_high' and w['value']>1.05) or (name not in ('voltage_low','voltage_high') and w['value']>=1.))]
    reg=next(i for i,(n,p) in enumerate(zip(names,phases)) if n=='transformer.reg1a' and p=='A')
    bus=list(result.node_names).index('83.2')
    s=dict(day=result.day,alpha_BG=alpha,stage=stage,PASS=all(gates.values()),physical_gates=gates,convergence_count=int(result.convergence.sum()),
        Vmin=float(v.min()),Vmax=float(v.max()),rho_max=float(c[:,line].max()),p95_line_loading=float(np.percentile(c[:,line],95)),p99_line_loading=float(np.percentile(c[:,line],99)),
        transformer_current=float(c[:,tx].max()),transformer_kVA=float(k[:,tx].max()),worsts=worsts,limiting_constraints=failures,
        violation_counts=counts,violation_slot_counts={name:int(mask.any(axis=1).sum()) for name,mask in masks.items()},
        transformer_kVA_phase_row_count=int((k[:,tx]>=1).sum()),strict_tolerance=0.,thermal_equality_is_violation=True,
        root_P_kW=[float(r[0]) for r in roots],root_Q_kvar=[float(r[1]) for r in roots],losses_kWh=float(result.losses_kw_kvar[:,0].sum()*.25),losses_kvarh=float(result.losses_kw_kvar[:,1].sum()*.25),
        reg1a_A_current=float(c[:,reg].max()),reg1a_A_kVA=float(k[:,reg].max()),Bus83_B_Vmin=float(v[:,bus].min()),Bus83_B_Vmax=float(v[:,bus].max()),
        Bus83_B_voltage=v[:,bus].tolist(),reg1a_A_current_slot=int(c[:,reg].argmax()),reg1a_A_kVA_slot=int(k[:,reg].argmax()),
        MESS_OFF=True,optimization_calls=0,coefficient_generation_calls=0,clean_engine_count=1,worker_PID=os.getpid(),opendss_version=result.opendss_version,elapsed_seconds=result.elapsed_seconds)
    return s

def replay(task):
    day,alpha,stage=task;assert day in DAYS and alpha in ALPHAS and stage in ('DAYAHEAD','ACTUAL')
    folder=OUT/'replays'/stage/f'alpha_{alpha:.2f}'/day
    if (folder/'STRICT_SUMMARY.json').exists():return read(folder/'STRICT_SUMMARY.json')
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead.v41r3.native_actual import native_actual
    branches=[SimpleNamespace(**b) for b in read(OUT/'TOPOLOGY_AND_CONTROLS.json')['branches']]
    binding=SimpleNamespace(factories=[SimpleNamespace(data=SimpleNamespace(branches=branches))])
    context=SimpleNamespace(legacy_context=({},None,background(day,stage,alpha),binding,None,None))
    ppath=OUT/'inputs'/day/f'{stage}_POWER.npz';p=arrays(ppath)
    ids=tuple(f'MESS{i:02}' for i in range(1,5));locs=np.array([[f'TRANSIT_{i}' for i in ids]]*96)
    decision=read(OUT/'inputs'/day/'DAYAHEAD_INPUT_RECEIPT.json')['sources']['jobs']
    trajectory=FrozenTrajectory(day,stage,'B0',p['pcc'],p['qcc'],np.zeros((96,4)),np.zeros((96,4)),ids,locs,decision['sha256'])
    voltage=arrays(OUT/'NODE_AXIS.npz')
    if stage=='ACTUAL':
        state=OUT/'replays/DAYAHEAD'/f'alpha_{alpha:.2f}'/day/'physics/OPENDSS_PHASE_ARRAYS.npz'
        with np.load(state) as z:voltage.update({k:z[k].copy() for k in ('regulator_taps','capacitor_states')})
    from contextlib import nullcontext
    before=trajectory.immutable_sha256;previous=Path.cwd()
    try:
        with corrected_mapping(),capture(stage,folder) as roots,(native_actual(folder) if stage=='ACTUAL' else nullcontext()):
            result=backend.run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=context,voltage=voltage,trajectory=trajectory,output=folder/'physics')
    finally:os.chdir(previous)
    assert before==trajectory.immutable_sha256
    s=strict_summary(result,roots,alpha,stage)
    s.update(power_source=rec(ppath),B0_frozen_decision=decision,trajectory_SHA=before,arrays=rec(folder/'physics/OPENDSS_PHASE_ARRAYS.npz'))
    npz(folder/'ROOT_POWER_AND_BUS83.npz',root_PQ_kw_kvar=np.array(roots),Bus83_B_voltage=np.array(s['Bus83_B_voltage']))
    save(folder/'STRICT_SUMMARY.json',s)
    return s

def distribution(rows):
    rho=np.array([r['rho_max'] for r in rows]);q=np.percentile(rho,[0,50,75,90,100])
    return dict(zip(['min','median','P75','P90','max'],map(float,q)),days_ge={f'{x:.2f}':int((rho>=x).sum()) for x in (.70,.75,.80,.85,.90,.95)})

def aggregate(rows):
    ans=[]
    for alpha in ALPHAS:
        rr=sorted([r for r in rows if r['alpha_BG']==alpha],key=lambda r:r['day']);assert [r['day'] for r in rr]==list(DAYS)
        failed=[r for r in rr if not r['PASS']]
        w=max(rr,key=lambda r:max(r['transformer_current'],r['transformer_kVA'],r['rho_max'],r['Vmax']/1.05,.95/r['Vmin']))
        ans.append(dict(alpha_BG=alpha,eligible=not failed,PASS_days=len(rr)-len(failed),FAIL_days=len(failed),first_failing_day=failed[0]['day'] if failed else None,
            first_failing_constraints=failed[0]['limiting_constraints'] if failed else [],worst_day=w['day'],
            **{name:(min(r[name] for r in rr) if name=='Vmin' else max(r[name] for r in rr)) for name in ('rho_max','Vmin','Vmax','transformer_current','transformer_kVA')},
            worst_metric_days={name:(min(rr,key=lambda r:r[name]) if name=='Vmin' else max(rr,key=lambda r:r[name]))['day'] for name in ('rho_max','Vmin','Vmax','transformer_current','transformer_kVA')},
            stress_distribution=distribution(rr),May02=next(r for r in rr if r['day']=='2025-05-02')))
    return ans

def execute(stage,tasks):
    rows=[];started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn')) as pool:
        futures={pool.submit(replay,t):t for t in tasks}
        for f in as_completed(futures):
            try:r=f.result()
            except BaseException as e:
                atomic(OUT/f'{stage}_ERROR.json',dict(task=futures[f],error=repr(e)));raise
            rows.append(r)
            atomic(OUT/f'{stage}_PROGRESS.json',dict(completed=len(rows),total=len(tasks),elapsed_seconds=time.perf_counter()-started,last=dict(day=r['day'],alpha=r['alpha_BG'],PASS=r['PASS'])))
            print(stage,len(rows),'/',len(tasks),r['day'],r['alpha_BG'],'PASS' if r['PASS'] else 'FAIL','rho',round(r['rho_max'],6),'tx',round(r['transformer_current'],6),flush=True)
    return sorted(rows,key=lambda r:(r['alpha_BG'],r['day']))

def select(rows):
    groups=aggregate(rows);eligible=[r['alpha_BG'] for r in groups if r['eligible']];selected=max(eligible) if eligible else None
    status='FROZEN_DAYAHEAD_ELIGIBLE_ACTUAL_PENDING' if selected else 'FAIL_CLOSE_NO_MAY_WIDE_ELIGIBLE_ALPHA'
    authority=dict(schema='V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY_V1',status=status,candidate_alphas=list(ALPHAS),selected_alpha_BG=selected,
        deterministic_selection_rule=read(OUT/'PREDECLARED_PROTOCOL.json')['selection_rule'],all_day_alpha_results=rows,eligibility_results=groups,
        AIDC_authority=read(OUT/'PROTECTED_INPUTS_AND_SOURCES.json')['AIDC_authority'],AIDC_vector=list(VECTOR),AIDC_total_GPU=780,
        source_SHAs=rec(OUT/'PROTECTED_INPUTS_AND_SOURCES.json'),protocol=rec(OUT/'PREDECLARED_PROTOCOL.json'),runner=rec(__file__),
        B1_B2_B3_RESULTS_USED=False,Actual_results_used_for_selection=False,ROBUST_B1_executed=False,FULL_MAY_policy_optimization='HOLD',
        previous_alpha_1_60_status='DEVELOPMENT_HISTORICAL_ONLY',previous_evidence_deleted=False,
        downstream_execution_allowed=False,frozen_UTC=pd.Timestamp.now(tz='UTC').isoformat())
    save(OUT/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json',authority)
    save(OUT/'V41R3_ALPHA_1_60_HISTORICAL_STATUS.json',dict(alpha_BG=1.6,status='DEVELOPMENT_HISTORICAL_ONLY',old_authority=rec(ROOT/'dayahead/artifacts/v41r3_fast_power_scale_freeze/V41R3_BACKGROUND_SCALE_AUTHORITY.json'),superseding_authority=rec(OUT/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json'),old_file_preserved=True))
    save(OUT/'DAYAHEAD_SCREEN_COMPLETE.json',dict(status=status,selected_alpha_BG=selected,groups=groups,rows=rows))
    print('DAYAHEAD_SELECTION',selected,status,flush=True)

def main():
    command=sys.argv[1]
    if command=='prepare':prepare()
    elif command=='dayahead':select(execute('DAYAHEAD',[(d,a,'DAYAHEAD') for d in DAYS for a in ALPHAS]))
    else:raise ValueError(command)

if __name__=='__main__':main()
