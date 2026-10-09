import os,sys,json,hashlib,time
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
import numpy as np
sys.dont_write_bytecode=True
H=Path(__file__).absolute().parent;ROOT=Path(json.loads((H/'CLONE_INPUT_MANIFEST.json').read_text(encoding='utf-8'))['source_paper']).parent.parent;BIND=H;STRESS=ROOT/'IEEE8500_stress_calibration_20260911'
sys.path.insert(0,str(STRESS));sys.path.insert(0,str(BIND))
import stress_common as s
from v41r4_ieee8500_adapter import electrical_port_contract
from dayahead.v28r2.formulation import PF_TAN
NAMES=tuple(r['control_name'] for r in electrical_port_contract()['control_axis'])
assert len(NAMES)==60
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()
def record(p):return dict(path=str(p),sha256=sha(p),bytes=Path(p).stat().st_size)
def frozen_check():
    for name in ['RECONSTRUCTION_FREEZE_MANIFEST.json']:
        for r in read(BIND/name)['files']:assert sha(r['path'])==r['sha256'],r['path']
def remapped_engine(folder):
    import opendssdirect as odd
    folder.mkdir(parents=True,exist_ok=True)
    d=odd.NewContext();d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False);d.Basic.AllowEditor(False);d.Basic.AllowDOScmd(False)
    d.Text.Command(f'Compile "{H / "PCC_Master.dss"}"')
    d.Basic.DataPath(str(folder))
    d.Solution.MaxIterations(100);d.Solution.MaxControlIterations(1000)
    assert d.Circuit.NumBuses()==4912 and d.Circuit.NumNodes()==8639 and d.Solution.ControlMode()==0
    return d

class Engine:
    def __init__(self,folder):
        self.d=d=remapped_engine(Path(folder));self.native=s.old.configs(d)
        self.loads=s.frozen.native_inventory(d);self.ax=s.frozen.measurement_axes(d);self.nodes=np.array(d.Circuit.AllNodeNames())
        self.P=np.array([r['base_kw'] for r in self.loads]);self.Q=np.array([r['base_kvar'] for r in self.loads])
        self.md,self.mpv,self.ratio,self.ap,self.aq,self.inv=s.input_authorities();self.inv=read(H/'PCC_OVERLAY_INVENTORY.json')
        forecast=read(H/'D1_AEMO_VIC1_FORECAST.json');rule=read(H/'SCREENING_RULE.json')
        self.md=np.asarray(forecast['demand_mw_96'])/max(forecast['demand_mw_96']);self.mpv=np.asarray(forecast['pv_mw_96'])/max(forecast['pv_mw_96']);self.ratio=rule['PV_ratio']
        with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:self.ap=z['pcc'].copy();self.aq=z['qcc'].copy()
        d.Text.Command(f'Redirect "{s.overlay_path(1.04,123.5)}"')
        self.adapted=s.old.configs(d);s.allowed_audit(self.native,self.adapted,1.04,123.5)
        resources=s.frozen.add_resources(d,self.loads,self.ratio,self.inv)
        save(Path(folder)/'RESOURCE_BINDING.json',dict(PV_ratio=self.ratio,resource_text_sha256=hashlib.sha256(resources.encode()).hexdigest()))
        self.services=[f'IDC{i:02}' for i in range(1,13)]+[f'STA{i:02}' for i in range(1,13)]
        by={(r['PCC_role'],r['location_id']):r for r in self.inv}
        for sid in self.services:
            location='A'+sid if sid.startswith('IDC') else sid;r=by['MESS',location]
            d.Text.Command(f'New Load.np8500_mess_{sid.lower()} phases=3 bus1={r["PCC_bus"]}.1.2.3 conn=wye kv=0.48 kW=0 kvar=0 Model=1 Vminpu=0.85 Vmaxpu=1.15 Status=Fixed')
        assert d.Circuit.NumBuses()==4912 and d.Circuit.NumNodes()==8639 and d.Transformers.Count()==1226
        self.tolerance=d.Solution.Convergence()
    def inputs(self,t,x=None):
        s.old.inputs(self.d,self.loads,self.P,self.Q,self.ap,self.aq,.552,self.md,self.mpv,self.ratio,t)
        base=np.r_[self.ap[t],np.zeros(48)];self.x=base.copy() if x is None else np.asarray(x).copy()
        self.controls(self.x)
    def controls(self,x):
        d=self.d
        for j in range(12):
            d.Loads.Name(f'op8500_aidc{j+1:02d}');d.Loads.kW(float(x[j]));d.Loads.kvar(float(PF_TAN*x[j]))
        for j,sid in enumerate(self.services):
            d.Loads.Name('np8500_mess_'+sid.lower());d.Loads.kW(float(-x[12+j]));d.Loads.kvar(float(-x[36+j]))
    def solve(self):
        self.d.Solution.SolveSnap();assert self.d.Solution.Converged() and self.d.Error.Number()==0
    def arrays(self):
        d=self.d;ax=self.ax;v=np.asarray(d.Circuit.AllBusMagPu())
        ia=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2);ii=ia[:,0]*np.exp(1j*np.deg2rad(ia[:,1]));pw=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
        line=ii[ax['line_pos']]/ax['line_rating'];tx=ii[ax['tx_pos']]/ax['tx_rating']
        ss=np.bincount(ax['power_group'],weights=pw[ax['power_pos'],0])+1j*np.bincount(ax['power_group'],weights=pw[ax['power_pos'],1])
        return v*v,line,tx,ss
    def state(self,t):return s.control_state(self.d,t,1.04,123.5)
    def hold(self,state):
        d=self.d;d.Solution.ControlMode(-1)
        for r in state['regulators']:d.RegControls.Name(r['name']);d.RegControls.TapNumber(r['tap_number'])
        for c in state['capacitors']:d.Capacitors.Name(c['name']);d.Capacitors.States(c['step_states'])
        d.Solution.Convergence(1e-10)
    def close(self):self.d.Basic.ClearAll()

def baseline():
    frozen_check();out=H/'B0_REPLAY';out.mkdir(exist_ok=False);e=Engine(out/'runtime');rows=[];states=[];values=[];start=time.perf_counter()
    for t in range(96):
        e.inputs(t);e.solve();assert e.d.Solution.ControlActionsDone()
        a=e.arrays();values.append(a);states.append(e.state(t))
        v=np.sqrt(a[0]);li=np.abs(a[1]);tx=np.abs(a[2]);kv=np.abs(a[3])/e.ax['kva_rating']
        rows.append(dict(slot=t,Vmin_pu=float(v.min()),Vmax_pu=float(v.max()),max_phase_line_loading_pu=float(li.max()),max_transformer_phase_current_pu=float(tx.max()),max_transformer_winding_kva_pu=float(kv.max()),Vmin_node=str(e.nodes[v.argmin()]),Vmax_node=str(e.nodes[v.argmax()]),line_witness=str(e.ax['line_label'][li.argmax()]),line_axis=int(li.argmax()),converged=True,controls_settled=True))
    keys=['Vmin_pu','Vmax_pu','max_phase_line_loading_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu']
    summary={k:(min if k=='Vmin_pu' else max)(r[k] for r in rows) for k in keys}
    authority=read(STRESS/'IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json');expected=authority['selected_summary'];diff={k:abs(summary[k]-expected[k]) for k in keys}
    save(out/'SUMMARY.json',dict(status='PASS' if max(diff.values())<=1e-10 else 'FAIL_CLOSE',metrics=summary,authority_metrics={k:expected[k] for k in keys},max_absolute_differences=diff,converged_slots=96,control_settled_slots=96,wall_seconds=time.perf_counter()-start))
    save(out/'SLOTS.json',rows);save(out/'CONTROL_STATES.json',states)
    np.savez_compressed(out/'ANCHORS.npz',control_names=np.array(NAMES),x=np.c_[e.ap,np.zeros((96,48))],v2=np.array([v[0] for v in values]),line=np.array([v[1] for v in values]),tx=np.array([v[2] for v in values]),S=np.array([v[3] for v in values]))
    save(H/'AXES.json',dict(nodes=e.nodes.tolist(),line=e.ax['line_label'].tolist(),tx=e.ax['tx_label'].tolist(),winding=e.ax['kva_label'].tolist(),line_rating_A=e.ax['line_rating'].tolist(),tx_rating_A=e.ax['tx_rating'].tolist(),winding_rating_kVA=e.ax['kva_rating'].tolist(),control_names=list(NAMES),native_secondary_bus_primary_phase={r['bus_connection'].split('.')[0].lower():r['primary_phase'] for r in e.loads}))
    save(H/'ELEMENT_STATIC_ALLOWED_CHANGE_AUDIT.json',s.allowed_audit(e.native,e.adapted,1.04,123.5));e.close();assert max(diff.values())<=1e-10,diff
    print('B0_REPLAY_PASS',json.dumps(summary),flush=True)

def generate_slot(t):
    start=time.perf_counter();folder=H/'coefficients'/f'slot_{t:02}';folder.mkdir(parents=True,exist_ok=False)
    e=Engine(folder/'runtime');states=read(H/'B0_REPLAY/CONTROL_STATES.json')
    with np.load(H/'B0_REPLAY/ANCHORS.npz') as z:base=z['x'][t].copy();anchor=[z[k][t].copy() for k in ['v2','line','tx','S']]
    e.inputs(t);e.hold(states[t]);e.controls(base);e.solve()
    j=[np.empty((60,len(a)),dtype=a.dtype) for a in anchor]
    for k in range(60):
        sides=[]
        for sign in [1,-1]:
            x=base.copy();x[k]+=sign;e.controls(x);e.solve();sides.append(e.arrays())
        for p in range(4):j[p][k]=(sides[0][p]-sides[1][p])/2
    np.savez_compressed(folder/'COEFFICIENTS.npz',x=base,v2=anchor[0],v2_J=j[0],line=anchor[1],line_J=j[1],tx=anchor[2],tx_J=j[2],S=anchor[3],S_J=j[3])
    e.close();r=dict(slot=t,central_signed_solves=120,settled_base_solves=1,wall_seconds=time.perf_counter()-start,artifact=record(folder/'COEFFICIENTS.npz'))
    save(folder/'GENERATION.json',r);return r
