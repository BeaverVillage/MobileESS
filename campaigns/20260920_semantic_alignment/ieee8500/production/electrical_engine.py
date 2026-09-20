"""Production 60-control adapter, legal_mixed_M1 plus 18 inherited ports."""
import os,sys,json,hashlib,time
from pathlib import Path
sys.dont_write_bytecode=True
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import numpy as np
import opendssdirect as odd
H=Path(__file__).absolute().parent;ROOT=H.parent.parent;BIND=H;STRESS=ROOT/'IEEE8500_stress_calibration_20260911'
sys.path.insert(0,str(STRESS));sys.path.insert(0,'C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
import stress_common as s
from dayahead.v28r2.formulation import PF_TAN
SERVICES=[f'IDC{i:02}' for i in range(1,13)]+[f'STA{i:02}' for i in range(1,13)]
NAMES=tuple([f'aidc_load_kw[AIDC{i:02}]' for i in range(1,13)]+[f'mess_{q}[{sid}]' for q in ('p_kw','q_kvar') for sid in SERVICES])
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item() if isinstance(x,np.generic) else str(x)),encoding='utf-8')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record(p):return dict(path=str(p),sha256=sha(p),bytes=Path(p).stat().st_size)
class Engine:
 def __init__(self,folder):
  folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);self.d=d=odd.NewContext()
  d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False);d.Basic.AllowEditor(False);d.Basic.AllowDOScmd(False);d.Basic.DataPath(str(folder))
  d.Text.Command(f'Compile "{ROOT/"IEEE8500_scalability_20260910/source/Master-unbal.dss"}"');d.Basic.DataPath(str(folder))
  self.native=s.old.configs(d);self.loads=s.frozen.native_inventory(d);self.P=np.array([r['base_kw'] for r in self.loads]);self.Q=np.array([r['base_kvar'] for r in self.loads])
  d.Text.Command(f'Redirect "{H/"PCC_OVERLAY.dss"}"');d.Text.Command(f'Redirect "{s.overlay_path(1.04,123.5)}"')
  self.inv=read(H/'PCC_OVERLAY_INVENTORY.json');rule=read(H/'SCREENING_RULE.json');fc=read(H/'D1_AEMO_VIC1_FORECAST.json');self.ratio=rule['PV_ratio']
  self.md=np.array(fc['demand_mw_96'])/max(fc['demand_mw_96']);self.mpv=np.array(fc['pv_mw_96'])/max(fc['pv_mw_96'])
  with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:self.ap=z['pcc'].copy();self.aq=z['qcc'].copy()
  s.frozen.add_resources(d,self.loads,self.ratio,self.inv);self.services=SERVICES
  by={(r['PCC_role'],r['location_id']):r for r in self.inv}
  for sid in self.services:
   r=by['MESS','A'+sid if sid.startswith('IDC') else sid]
   d.Text.Command(f'New Load.np8500_mess_{sid.lower()} phases={r["phases"]} bus1={r["PCC_bus"]}{r["connection"]} conn=wye kv=.48 kw=0 kvar=0 Model=1 Vminpu=.85 Vmaxpu=1.15 Status=Fixed')
  self.ax=s.frozen.measurement_axes(d);self.nodes=np.array(d.Circuit.AllNodeNames())
  d.Solution.MaxIterations(100);d.Solution.MaxControlIterations(1000);d.Solution.Convergence(1e-10);self.tolerance=1e-10
 def inputs(self,t,x=None):
  d=self.d;s.old.inputs(d,self.loads,self.P,self.Q,self.ap,self.aq,.45,self.md,self.mpv,self.ratio,t)
  for i,r in enumerate(self.loads):
   d.Generators.Name(f'op8500_pv_{i:04d}');p=float(.5*self.ratio*self.P[i]*self.mpv[t]);d.CktElement.Enabled(p>0)
   if p>0:d.Generators.kW(p);d.Generators.kvar(0.)
  self.x=np.r_[self.ap[t],np.zeros(48)] if x is None else np.asarray(x).copy();self.controls(self.x)
 def controls(self,x):
  for j in range(12):
   self.d.Loads.Name(f'op8500_aidc{j+1:02}');self.d.Loads.kW(float(x[j]));self.d.Loads.kvar(float(PF_TAN*x[j]))
  for j,sid in enumerate(self.services):
   self.d.Loads.Name('np8500_mess_'+sid.lower());self.d.Loads.kW(float(-x[12+j]));self.d.Loads.kvar(float(-x[36+j]))
 def solve(self):
  self.d.Solution.SolveSnap();assert self.d.Solution.Converged() and self.d.Error.Number()==0
 def arrays(self):
  d=self.d;ax=self.ax;v=np.asarray(d.Circuit.AllBusMagPu());ia=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2);ii=ia[:,0]*np.exp(1j*np.deg2rad(ia[:,1]));pw=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
  ss=np.bincount(ax['power_group'],weights=pw[ax['power_pos'],0])+1j*np.bincount(ax['power_group'],weights=pw[ax['power_pos'],1])
  return v*v,ii[ax['line_pos']]/ax['line_rating'],ii[ax['tx_pos']]/ax['tx_rating'],ss
 def state(self,t):return s.control_state(self.d,t,1.04,123.5)
 def hold(self,st):
  d=self.d;d.Solution.ControlMode(-1)
  for r in st['regulators']:d.RegControls.Name(r['name']);d.RegControls.TapNumber(r['tap_number'])
  for r in st['capacitors']:d.Capacitors.Name(r['name']);d.Capacitors.States(r['step_states'])
 def close(self):self.d.Basic.ClearAll()
def baseline():
 start=time.perf_counter();e=Engine(H/'B0_REPLAY/runtime');rows=[];states=[];values=[]
 try:
  for t in range(96):
   e.inputs(t);e.solve();a=e.arrays();values.append(a);states.append(e.state(t));v=np.sqrt(a[0]);li=np.abs(a[1]);tx=np.abs(a[2]);kv=np.abs(a[3])/e.ax['kva_rating']
   r=dict(slot=t,Vmin_pu=float(v.min()),Vmax_pu=float(v.max()),max_phase_line_loading_pu=float(li.max()),max_transformer_phase_current_pu=float(tx.max()),max_transformer_winding_kva_pu=float(kv.max()),converged=True,controls_settled=bool(e.d.Solution.ControlActionsDone()),line_witness=str(e.ax['line_label'][li.argmax()]))
   r['feasible']=r['controls_settled'] and r['Vmin_pu']>=.95 and r['Vmax_pu']<=1.05 and max(li.max(),tx.max(),kv.max())<=1;rows.append(r)
  keys=['Vmin_pu','Vmax_pu','max_phase_line_loading_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu'];metrics={k:(min if k=='Vmin_pu' else max)(r[k] for r in rows) for k in keys}
  save(H/'B0_REPLAY/AC_VALIDATION.json',dict(status='PASS' if all(r['feasible'] for r in rows) else 'FAIL',metrics=metrics,slots=rows,wall_seconds=time.perf_counter()-start));save(H/'B0_REPLAY/CONTROL_STATES.json',states)
  np.savez_compressed(H/'B0_REPLAY/ANCHORS.npz',x=np.c_[e.ap,np.zeros((96,48))],v2=np.array([v[0] for v in values]),line=np.array([v[1] for v in values]),tx=np.array([v[2] for v in values]),S=np.array([v[3] for v in values]))
  save(H/'AXES.json',dict(nodes=e.nodes.tolist(),line=e.ax['line_label'].tolist(),tx=e.ax['tx_label'].tolist(),winding=e.ax['kva_label'].tolist(),line_rating_A=e.ax['line_rating'].tolist(),tx_rating_A=e.ax['tx_rating'].tolist(),winding_rating_kVA=e.ax['kva_rating'].tolist(),control_names=list(NAMES),native_secondary_bus_primary_phase={r['bus_connection'].split('.')[0].lower():r['primary_phase'] for r in e.loads}))
  assert all(r['feasible'] for r in rows),metrics
 finally:e.close()
 print('FULL_INFRASTRUCTURE_B0',metrics,flush=True)
def generate_slot(t):
 start=time.perf_counter();folder=H/'coefficients'/f'slot_{t:02}';folder.mkdir(parents=True,exist_ok=False);e=Engine(folder/'runtime');st=read(H/'B0_REPLAY/CONTROL_STATES.json')[t]
 try:
  with np.load(H/'B0_REPLAY/ANCHORS.npz') as z:base=z['x'][t].copy();anchor=[z[k][t].copy() for k in ['v2','line','tx','S']]
  e.inputs(t);e.hold(st);e.controls(base);e.solve();j=[np.empty((60,len(a)),dtype=a.dtype) for a in anchor]
  for k in range(60):
   sides=[]
   for sign in [1,-1]:
    x=base.copy();x[k]+=sign;e.controls(x);e.solve();sides.append(e.arrays())
   for n in range(4):j[n][k]=(sides[0][n]-sides[1][n])/2
  np.savez_compressed(folder/'COEFFICIENTS.npz',x=base,v2=anchor[0],v2_J=j[0],line=anchor[1],line_J=j[1],tx=anchor[2],tx_J=j[2],S=anchor[3],S_J=j[3])
 finally:e.close()
 return dict(slot=t,wall_seconds=time.perf_counter()-start,central_signed_solves=120,artifact=record(folder/'COEFFICIENTS.npz'))
