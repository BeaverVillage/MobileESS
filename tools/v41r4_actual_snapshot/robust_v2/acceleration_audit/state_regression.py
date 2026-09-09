"""Compact isolated exact-state audit. No optimization or authoritative writes."""
import sys,os,time,itertools,gc,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent;PROD=HERE.parent;ROOT=PROD.parents[1]
sys.path.insert(0,str(PROD));from binding import verify_method
verify_method()
import common
common.OUT=HERE
from common import read,save,sha,arrays,digest,protect
protect()
import numpy as np,psutil
from types import SimpleNamespace as NS
from qsafe import PrefixEngine,q_bounds,feasible
from dayahead.v28r2 import opendss_backend as backend
from dayahead.v28r2.opendss_mapping import REGULATORS,CAPACITORS,FeederAssets
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v40e.mapping import corrected_mapping,NativeAllocation
from dayahead.full_ieee123_g11_v16_1 import _oriented_branches
from dayahead.run_v16_3_voltage_candidate import _enable_native_controls
from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY

OLD=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_v1'
RUN=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4'
ASSETS=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
SETTERS=('Hour','Seconds','Year','Frequency','LoadMult','GenMult','MaxIterations','MinIterations','MaxControlIterations','Convergence','Algorithm','LoadModel','StepSize','Number')

def compile_engine():
    cwd=Path.cwd();odd,adapter=backend.compile_clean_engine(ASSETS)
    odd.Basic.AllowChangeDir(False);odd.Basic.DataPath(str(HERE));os.chdir(cwd)
    return odd,adapter

def load_case(day,policy,t,source):
    cp=source/'replays'/day/policy/'ETA95_QSAFE_ACTUAL'
    z=arrays(cp/'EXECUTION.npz');base=arrays(cp/'OPENDSS_PHASE_ARRAYS.npz');events=read(cp/'Q_CONTROL_EVENTS.json')
    bgpath=ROOT/'frozen_artifacts/v41r4_may/audit'/day/'inputs/ORIGINAL_ACTUAL_BACKGROUND.npz';bgz=arrays(bgpath)
    scale=read(ROOT/'frozen_artifacts/v41r4_may/audit/V41R3_BACKGROUND_SCALE_AUTHORITY.json');assert scale['selected_alpha_BG']==1.15
    keys=[tuple(k.split('::')) for k in bgz['bus_phase_keys']]
    bg=NS(gross_p_kw_96=tuple({k:1.15*float(v) for k,v in zip(keys,row)} for row in bgz['gross_P_kw']),gross_q_kvar_96=tuple({k:1.15*float(v) for k,v in zip(keys,row)} for row in bgz['gross_Q_kvar']),pv_generation_kw_96=tuple({k:float(v) for k,v in zip(keys,row)} for row in bgz['PV_P_kw']))
    odd,adapter=compile_engine()
    branches,_=_oriented_branches(odd);odd.Basic.ClearAll();del odd;gc.collect()
    assert tuple(b.branch_id for b in branches)==tuple(base['branch_names'])
    context=NS(legacy_context=(None,None,bg,NS(factories=[NS(data=NS(branches=branches))]),None,None))
    voltage=dict(node_names=base['node_names'],regulator_taps=base['regulator_taps'].copy(),capacitor_states=base['capacitor_states'].copy())
    voltage['regulator_taps'][0]=events[0]['start_taps']
    rows=read(cp/'ACTUATOR.json')['trajectory'];ids=sorted({r['mess_id'] for r in rows})
    connected=np.array([next(r['connected'] for r in rows if r['slot']==t and r['mess_id']==mid) for mid in ids])
    trajectory=FrozenTrajectory(day,'ACTUAL',policy,z['PCC_P'].copy(),z['PCC_Q'].copy(),z['P_EXEC'].copy(),z['Q_EXEC'].copy(),tuple(ids),z['locations'].copy(),read(cp/'OPENDSS_SUMMARY.json')['schedule_sha256'])
    engine=PrefixEngine(context,voltage,trajectory,HERE);engine.accepted_taps=base['regulator_taps'][:t].tolist()
    lower,upper=q_bounds(z['P_EXEC'][t],connected,NS(pcs_kva=400.,pcs_polygon_faces=16,active_power_limit_kw=300.))
    return NS(day=day,policy=policy,t=t,cp=cp,z=z,base=base,events=events,engine=engine,context=context,voltage=voltage,trajectory=trajectory,adapter=adapter,lower=lower,upper=upper,bgpath=bgpath)

def apply(c,odd,adapter,q):
    prior=c.trajectory.mess_q_kvar[c.t].copy();c.trajectory.mess_q_kvar[c.t]=q
    try:backend.apply_trajectory_slot(odd,adapter,c.context,c.trajectory,c.t)
    finally:c.trajectory.mess_q_kvar[c.t]=prior

def prepare_prefix(c):
    odd,adapter=compile_engine()
    for s in range(c.t):
        backend.apply_trajectory_slot(odd,adapter,c.context,c.trajectory,s)
        if s==0:backend.apply_frozen_native_state(odd,c.voltage,0)
        _enable_native_controls(odd);odd.Solution.SolveSnap();assert odd.Solution.Converged()
        assert backend._native_state(odd)[0]==c.engine.accepted_taps[s]
    apply(c,odd,adapter,c.z['Q_EXEC'][c.t])
    if c.t==0:backend.apply_frozen_native_state(odd,c.voltage,0)
    return odd,adapter

def capture(c,odd):
    taps,caps=backend._native_state(odd)
    controls=[]
    for name in odd.RegControls.AllNames():
        odd.RegControls.Name(name)
        controls.append(dict(name=name,tap_number=odd.RegControls.TapNumber(),is_reversible=odd.RegControls.IsReversible(),delay=odd.RegControls.Delay(),tap_delay=odd.RegControls.TapDelay(),forward_vreg=odd.RegControls.ForwardVreg(),forward_band=odd.RegControls.ForwardBand(),reverse_vreg=odd.RegControls.ReverseVreg(),max_tap_change=odd.RegControls.MaxTapChange()))
    loads=[];generators=[]
    for name in odd.Loads.AllNames():
        odd.Loads.Name(name);loads.append([name,odd.Loads.kW(),odd.Loads.kvar()])
    for name in odd.Generators.AllNames():
        odd.Generators.Name(name);generators.append([name,odd.Generators.kW(),odd.Generators.kvar()])
    return dict(slot=c.t,physical_timestamp_local=f'{c.day}T{c.t//4:02}:{c.t%4*15:02}:00+10:00',native_solution_mode=int(odd.Solution.Mode()),native_control_mode=int(odd.Solution.ControlMode()),solution={k:getattr(odd.Solution,k)() for k in SETTERS},DblHour=odd.Solution.DblHour(),ControlActionsDone=odd.Solution.ControlActionsDone(),ControlIterations=odd.Solution.ControlIterations(),taps=taps,capacitors=caps,regcontrols=controls,queue_size=odd.CtrlQueue.QueueSize(),queue=odd.CtrlQueue.Queue(),action_count=odd.CtrlQueue.NumActions(),Y_system_changed=odd.YMatrix.SystemYChanged(),Y_loads_need_update=odd.YMatrix.LoadsNeedUpdating(),Y_solution_initialized=odd.YMatrix.SolutionInitialized(),Y_iteration=odd.YMatrix.Iteration(),node_voltage_vector=odd.YMatrix.getV(),node_current_vector=odd.YMatrix.getI(),node_order=odd.Circuit.YNodeOrder(),loads=loads,generators=generators,AIDC_P=c.z['PCC_P'][c.t].tolist(),AIDC_Q=c.z['PCC_Q'][c.t].tolist(),MESS_P=c.z['P_EXEC'][c.t].tolist(),MESS_locations=c.z['locations'][c.t].tolist(),background_source_SHA=sha(c.bgpath),alpha_BG=1.15)

def restore(c,odd,adapter,state,q,warm):
    # Nonempty queued/delayed controls cannot be safely reconstructed by guessing.
    assert state['queue_size']==0 and state['action_count']==0,'UNRESTORABLE_CONTROL_QUEUE'
    odd.CtrlQueue.ClearQueue();odd.CtrlQueue.ClearActions()
    for name in odd.RegControls.AllNames():odd.RegControls.Name(name);odd.RegControls.Reset()
    for name,tap in zip(REGULATORS,state['taps']):odd.Transformers.Name(name);odd.Transformers.Wdg(2);odd.Transformers.Tap(tap)
    for name,cap in zip(CAPACITORS,state['capacitors']):odd.Capacitors.Name(name);odd.Capacitors.States([cap])
    for key,value in state['solution'].items():getattr(odd.Solution,key)(value)
    odd.Solution.ControlMode(state['native_control_mode'])
    apply(c,odd,adapter,q)
    if warm:
        odd.Solution.BuildYMatrix(2,True)
        assert odd.Circuit.YNodeOrder()==state['node_order']
        for i,value in enumerate(state['node_voltage_vector']):odd.YMatrix.VVector()[i]=value
        for i,value in enumerate(state['node_current_vector']):odd.YMatrix.IVector()[i]=value
        odd.YMatrix.SolutionInitialized(state['Y_solution_initialized'])
        odd.YMatrix.LoadsNeedUpdating(state['Y_loads_need_update'])
        odd.YMatrix.Iteration(state['Y_iteration'])
    odd.Solution.ControlActionsDone(state['ControlActionsDone']);odd.Solution.ControlIterations(state['ControlIterations'])
    assert backend._native_state(odd)==(state['taps'],state['capacitors'])
    _enable_native_controls(odd);odd.Solution.SolveSnap()

def measure(c,odd):
    m=np.asarray([backend._branch_measurement(odd,b) for b in c.engine.branches]);taps,caps=backend._native_state(odd)
    return dict(v=backend._voltage_vector(odd,c.engine.nodes),ia=m[:,0],ipu=m[:,1],kva=m[:,2],losses=np.asarray(odd.Circuit.Losses())[:2]/1000,taps=taps,caps=caps,converged=bool(odd.Solution.Converged()))

def compare(a,b):
    diff={k:float(np.nanmax(np.abs(a[k]-b[k]))) for k in ('v','ia','ipu','kva','losses')}
    bits={k:bool(np.array_equal(a[k],b[k],equal_nan=True)) for k in diff}
    return dict(max_absolute_difference=diff,bit_identical=bits,final_taps_identical=a['taps']==b['taps'],capacitors_identical=a['caps']==b['caps'],convergence_identical=a['converged']==b['converged'],violation_classification_identical=feasible(a)==feasible(b),numerical_pass=diff['v']<=1e-10 and diff['ia']<=1e-8 and diff['ipu']<=1e-10 and diff['kva']<=1e-10 and a['taps']==b['taps'] and feasible(a)==feasible(b),all_bit_identical=all(bits.values()) and a['taps']==b['taps'] and a['caps']==b['caps'] and a['converged']==b['converged'])

def main():
    started=time.time();records=[];states=[];baselines=[]
    plan=[('2025-05-12','B3',30,OLD),('2025-05-01','B2',6,PROD),('2025-05-12','B3',80,OLD)]
    save(HERE/'REGRESSION_PLAN.json',dict(cases=[(d,p,t,str(s)) for d,p,t,s in plan],Q_trials='original, full absorption, full injection, zero, 16 domain corners, May12 witness; no search algorithm edits',numerical_tolerances=dict(voltage=1e-10,current_A=1e-8,current_loading=1e-10,transformer_kVA_loading=1e-10),adoption_requires_no_accepted_Q_or_search_order_change=True,hidden_state_fail_closed=True,max_RSS_GB=.75))
    original_allocate=NativeAllocation.allocate;cache={}
    def allocation(self,p,q):
        key=(id(p),id(q))
        if key not in cache:cache[key]=(p,q,original_allocate(self,p,q))
        return cache[key][2]
    NativeAllocation.allocate=allocation
    with corrected_mapping():
        for day,policy,t,source in plan:
            c=load_case(day,policy,t,source);caseid=f'{day}_{policy}_{t}';print('CASE',caseid,flush=True)
            q0=c.z['Q_EXEC'][t];tic=time.perf_counter();original=c.engine.evaluate(t,q0);baseline_seconds=time.perf_counter()-tic
            assert np.array_equal(original['v'],c.base['voltage_pu'][t]) and np.array_equal(original['ipu'],c.base['phase_current_loading_pu'][t]),'COMPACT_INPUT_BINDING_NOT_AUTHORITATIVE'
            baseline=dict(case=caseid,voltage_bit_identical=True,current_bit_identical=True,seconds=baseline_seconds);baselines.append(baseline)
            reused,adapter=prepare_prefix(c);state=capture(c,reused);states.append(dict(case=caseid,state=state));save(HERE/(caseid+'_SLOT_START.json'),state)
            points=[q0,c.lower,c.upper,np.clip(np.zeros(4),c.lower,c.upper)]+[np.array(x) for x in itertools.product(*zip(c.lower,c.upper))]
            if day=='2025-05-12' and t==30:
                witness=read(PROD/'historical_evidence/MAY12_B3_SLOT30_FORENSIC/FINAL_AUDIT.json')['witness']['Q_kvar'];points.append(np.array(witness))
            unique=[]
            for q in points:
                if not any(np.array_equal(q,x) for x in unique):unique.append(q.copy())
            authoritative=[]
            for i,q in enumerate(unique):
                tic=time.perf_counter();a=c.engine.evaluate(t,q);seconds=time.perf_counter()-tic;authoritative.append(a)
                for mode,warm in [('B_TAPS_ONLY',False),('B_VISIBLE_STATE_WITH_WARMSTART',True),('C_REUSED_ENGINE_WITH_WARMSTART',True)]:
                    odd,ad=(reused,adapter) if mode.startswith('C') else compile_engine();tic=time.perf_counter()
                    try:
                        restore(c,odd,ad,state,q,warm);b=measure(c,odd);r=dict(case=caseid,trial=i,mode=mode,Q=q.tolist(),authoritative_seconds=seconds,restore_solve_measure_seconds=time.perf_counter()-tic,**compare(a,b))
                    except Exception as exc:r=dict(case=caseid,trial=i,mode=mode,error=repr(exc),all_bit_identical=False,numerical_pass=False)
                    records.append(r)
                    if not mode.startswith('C'):odd.Basic.ClearAll();del odd
                if i%4==0:
                    gc.collect();rss=psutil.Process().memory_info().rss/1024**3;assert rss<.75,('AUDIT_RSS_LIMIT',rss)
                    save(HERE/'PROGRESS.json',dict(status='RUNNING',case=caseid,trials=i+1,comparisons=len(records),RSS_GB=rss,elapsed_seconds=time.time()-started));print('TRIAL',i+1,'comparisons',len(records),flush=True)
            # Reversal exposes state carried over from a different candidate history.
            for i in reversed(range(len(unique))):
                tic=time.perf_counter()
                try:restore(c,reused,adapter,state,unique[i],True);b=measure(c,reused);r=dict(case=caseid,trial=i,mode='C_REVERSE_ORDER',restore_solve_measure_seconds=time.perf_counter()-tic,**compare(authoritative[i],b))
                except Exception as exc:r=dict(case=caseid,trial=i,mode='C_REVERSE_ORDER',error=repr(exc),all_bit_identical=False,numerical_pass=False)
                records.append(r)
            reused.Basic.ClearAll();del reused,c;cache.clear();gc.collect();save(HERE/'TRIAL_COMPARISONS.json',records)
    grouped={m:dict(comparisons=sum(r['mode']==m for r in records),all_bit_identical=all(r['all_bit_identical'] for r in records if r['mode']==m),all_numerical_pass=all(r['numerical_pass'] for r in records if r['mode']==m),classification_mismatches=sum(not r.get('violation_classification_identical',False) for r in records if r['mode']==m),tap_mismatches=sum(not r.get('final_taps_identical',False) for r in records if r['mode']==m)) for m in sorted({r['mode'] for r in records})}
    save(HERE/'RESULT.json',dict(status='COMPLETE',regression=grouped,baselines=baselines,elapsed_seconds=time.time()-started,production_method_changed=False,adopted=False,next_step='Fail closed on any non-equivalence; otherwise expanded exact search-order/accepted-Q and 96-slot regression required before adoption'))
    print('AUDIT_COMPLETE',grouped,flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as e:save(HERE/'TECHNICAL_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
