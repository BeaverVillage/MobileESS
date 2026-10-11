"""Native bitwise equality and exact setter-order evidence for a detached candidate."""
from pathlib import Path
import sys,time,json,hashlib
from unittest.mock import patch
import numpy as np
OUT=Path(__file__).resolve().parent;SOURCE=Path(r'D:\v42_svr11_epoch12_20261011')
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,atomic,record
from v42_svr11.authority import scope
from v42_svr11.model import _forecast_native_totals,_apply_forecast_native,FIELDS
from v42_svr11.context_lifecycle import retire_completed_probe,flush_completed_probes
from v42_svr11.ldc_interval import descriptors,project
from exact_fastpath import forecast_setter_schedule,apply_schedule,terminal_layout,terminal_values
R=Path(r'D:\v42_svr11_may_20261011_12')
def array_sha(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def run():
 with scope(R/'CAMPAIGN_MANIFEST.json') as m:
  from v42_voltage_control.bindings import original_bindings
  authority,*_=original_bindings()
  from dayahead import run_v16_3_voltage_candidate as original
  from dayahead.v28r2 import opendss_mapping as mapping
  from dayahead.v28r2.opendss_backend import _voltage_vector
  from v42_regcontrol.runner import background
  from v42_voltage_control.svr import install
  from v42_voltage_control.b0_new import build_planning
  from v42_voltage_control.timecontrol import CommonClock,queue,seconds
  from v42_thermal.authority import current_authority
  scenario=read(m['scenario']['path']);native_results=read(OUT/'VALIDATION_PROGRESS.json')['native'] if (OUT/'VALIDATION_PROGRESS.json').exists() else [];setter_results=[]
  for number in range(1,32):
   day=f'2025-05-{number:02d}';folder=R/'raw'/day
   f=read(read(folder/'SOURCE_PROVENANCE.json')['daily_sources']['aemo_forecast.json']['path'])
   bg=background(f['timestamps_96'],f['demand_mw_96'],f['pv_mw_96'])
   planpath=R/'models'/day/'FORECAST_ANCHOR/PLANNING_PHYSICAL.npz'
   if not planpath.exists():
    dest=OUT/'anchors'/day
    if not (dest/'PLANNING_PHYSICAL.npz').exists():build_planning(day,folder,dest)
    planpath=dest/'PLANNING_PHYSICAL.npz'
   with np.load(planpath) as z:p=z['PCC_P_kw'].copy()
   e,ad,_=authority.compile_verified()
   try:
    install(e,scenario['svr']);branches,_=authority.source()['oriented_branches'](e)
    nodes=tuple(sorted(n.lower() for n in e.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in ('1','2','3')))
    controls=original._control_axis(e);native=authority.source()['NativeAllocation'].from_adapter(ad)
    ldc=descriptors(e,branches,nodes,authority.source()['inventory'](e),current_authority())
    load_names=tuple(e.Loads.AllNames());generator_names=tuple(e.Generators.AllNames());layout=terminal_layout(e,branches)
    names=tuple(f'{b.branch_id}::{b.phase}' for b in branches);thermal=current_authority();rows={r['branch_phase'].lower():r for r in thermal['rows']+thermal['lines']};ratings=np.array([rows[n.lower()]['NormalAmps'] for n in names]);limits=np.array([b.ampacity_a_u080 for b in branches])
   finally:retire_completed_probe(e)
   del e;flush_completed_probes();totals=_forecast_native_totals(native,bg)
   schedules=forecast_setter_schedule(native,totals,bg,p,ad,load_names,generator_names,original.PF_TAN)
   class Collection:
    def __init__(self,names):self.names=names
    def AllNames(self):return self.names
   class Recorder:
    Loads=Collection(load_names);Generators=Collection(generator_names)
   def stream(fast,t):
    calls=[]
    def load(e,n,p,q):calls.append(('load',str(n),float(p).hex(),float(q).hex()))
    def gen(e,n,p,q=0):calls.append(('generator',str(n),float(p).hex(),float(q).hex()))
    with patch.object(mapping,'_set_load',load),patch.object(original,'_set_load',load),patch.object(original,'_set_generator',gen):
     if fast:apply_schedule(Recorder(),schedules[t])
     else:_apply_forecast_native(Recorder(),native,totals,t);original._set_slot(Recorder(),{**ad,'loads':[]},bg,p,t)
    return calls
   h=hashlib.sha256();setter_calls=0
   for t in range(96):
    a=stream(False,t);b=stream(True,t);assert a==b,(day,t);setter_calls+=len(a);h.update(json.dumps(a).encode())
   setter_results.append(dict(day=day,slots=96,ordered_setter_calls=setter_calls,bitwise_IEEE_values=True,SHA=h.hexdigest()))
   print('SETTERS',day,'96 PASS',flush=True)
   targets={1:(0,47,95),16:(47,),18:(51,)}.get(number,())
   for target in targets:
    if any(v['day']==day and v['slot']==target for v in native_results):continue
    results=[]
    for fast in (False,True):
     began=time.perf_counter();compile_count=physical_solves=0;states=[]
     def probe(j=None,sign=0):
      nonlocal compile_count,physical_solves
      e,adapter,_=authority.compile_verified();compile_count+=1
      try:
       clock=CommonClock('DAYAHEAD',day);clock.bind(e);install(e,scenario['svr'])
       assert tuple(e.Loads.AllNames())==load_names and tuple(e.Generators.AllNames())==generator_names
       for t in range(target+1):
        if fast:apply_schedule(e,schedules[t])
        else:_apply_forecast_native(e,native,totals,t);original._set_slot(e,{**adapter,'loads':[]},bg,p,t)
        if t==target and j is not None:
         anchor=float(p[t,j]) if j<12 else 0.;delta=original._perturbation(controls[j],anchor);original._apply_control(e,controls[j],anchor+sign*delta,p[t])
        clock.settle_slot(e,t,capture_events=False)
       physical_solves+=clock.total_physical_solve_count
       v=_voltage_vector(e,nodes)**2
       pq=terminal_values(e,layout,len(branches)) if fast else np.asarray([original._terminal_phase(e,b.branch_id,b.parent_bus,b.phase) for b in branches])
       taps=[]
       for reg in e.RegControls.AllNames():e.RegControls.Name(reg);taps.append((reg,e.RegControls.TapNumber()))
       states.append(dict(taps=taps,queue=queue(e),seconds=seconds(e),physical_solves=clock.total_physical_solve_count))
       return v,pq[:,2]/ratings,pq[:,0],pq[:,1]
      finally:retire_completed_probe(e)
     base=probe();mat=[np.empty((60,len(x))) for x in base];anchor=np.zeros(60);anchor[:12]=p[target]
     responses=[base]
     for j,control in enumerate(controls):
      plus=probe(j,1);minus=probe(j,-1);responses.extend((plus,minus));d=original._perturbation(control,anchor[j])
      for k in range(4):mat[k][j]=(plus[k]-minus[k])/(2*d)
     row={}
     for k,family in enumerate(('voltage','current','flow_p','flow_q')):row[family+'_constant']=base[k]-anchor@mat[k];row[family+'_matrix']=mat[k] if k<2 else mat[k].T
     row['branch_limits']=limits;row=project(row,ldc);flush_completed_probes()
     results.append(dict(row=row,responses=responses,states=states,seconds=time.perf_counter()-began,compiles=compile_count,solves=physical_solves))
     print('NATIVE',day,target,'FAST' if fast else 'BASE',results[-1]['seconds'],flush=True)
    a,b=results;assert a['compiles']==b['compiles']==121 and a['solves']==b['solves'] and a['states']==b['states']
    for i,(x,y) in enumerate(zip(a['responses'],b['responses'])):
     for k,(u,v) in enumerate(zip(x,y)):assert u.tobytes()==v.tobytes(),(day,target,i,k)
    for f in FIELDS:assert a['row'][f].tobytes()==b['row'][f].tobytes(),(day,target,f)
    np.savez_compressed(OUT/f'{day}_SLOT_{target:02d}_EXACT.npz',**b['row'])
    r=dict(day=day,slot=target,all121responses_bitwise_equal=True,all9coefficient_fields_bitwise_equal=True,controller_taps_queue_clock_and_solve_counts_equal=True,compiles=121,physical_solves=a['solves'],baseline_seconds=a['seconds'],candidate_seconds=b['seconds'],speedup=a['seconds']/b['seconds'],fields={f:array_sha(b['row'][f]) for f in FIELDS})
    native_results.append(r);atomic(OUT/'VALIDATION_PROGRESS.json',dict(setters=setter_results,native=native_results));print(json.dumps(r),flush=True)
  atomic(OUT/'VALIDATION.json',dict(PASS=True,source_SHA=m['execution_SHA'],candidate=record(OUT/'exact_fastpath.py'),setters=setter_results,native=native_results,Actual_inputs_used=0,tap_settings_changes=0,independent_context_reuse=0,solves_skipped=0,official_workers_modified=0))
if __name__=='__main__':run()
