import sys,time,json,hashlib
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;ROOT=H.parent;STRESS=ROOT/'IEEE8500_stress_calibration_20260911'
sys.path.insert(0,str(STRESS))
import stress_common as s
from independent_stress_replay import scalar_plan,scalar_measure
save,read,sha,record,table=s.save,s.read,s.sha,s.record,s.table
SITES=[f'AIDC{i:02d}' for i in range(1,13)];SERVICES=SITES+[f'STA{i:02d}' for i in range(1,13)]
KEYS=s.KEYS
def binding():
    inv=read(s.PCC/'PCC_OVERLAY_INVENTORY.json');by={(r['PCC_role'],r['location_id']):r for r in inv};assert len(by)==36
    return by
def channels():
    return [dict(role=role,site=site,component=component,sign='positive_consumption' if role=='AIDC' else 'positive_injection') for role,sites in [('AIDC',SITES),('MESS',SERVICES)] for site in sites for component in ['P','Q']]
class Engine:
    def __init__(self,folder,independent=False):
        self.d=s.frozen.engine(Path(folder));d=self.d;self.native=s.old.configs(d);self.loads=s.frozen.native_inventory(d);self.ax=s.frozen.measurement_axes(d);self.nodes=np.array(d.Circuit.AllNodeNames());self.plan=scalar_plan(d) if independent else None
        self.md,self.mpv,self.ratio,self.ap,self.aq,self.inv=s.input_authorities();self.P=np.array([r['base_kw'] for r in self.loads]);self.Q=np.array([r['base_kvar'] for r in self.loads]);self.by=binding()
        d.Text.Command(f'Redirect "{s.overlay_path(1.04,123.5)}"');self.adapted=s.old.configs(d);s.allowed_audit(self.native,self.adapted,1.04,123.5)
        assert s.frozen.add_resources(d,self.loads,self.ratio,self.inv)==(s.OLD/'B0_RESOURCE_OBJECTS.dss').read_text(encoding='utf-8')
        for site in SERVICES:
            bus=self.by['MESS',site]['PCC_bus'];d.Text.Command(f'New Load.prod8500_mess_{site.lower()} phases=3 bus1={bus}.1.2.3 conn=wye kv=0.48 kW=0 kvar=0 Model=1 Vminpu=0.85 Vmaxpu=1.15 Status=Fixed')
        assert d.Circuit.NumBuses()==4912 and d.Circuit.NumNodes()==8639 and d.Transformers.Count()==1226
    def set_slot(self,t,aidc_p=None,aidc_q=None,mess_p=None,mess_q=None):
        d=self.d;s.old.inputs(d,self.loads,self.P,self.Q,self.ap,self.aq,.5,self.md,self.mpv,self.ratio,t)
        for i,site in enumerate(SITES):
            d.Loads.Name(f'op8500_{site.lower()}');d.Loads.kW(float(self.ap[t,i] if aidc_p is None else aidc_p[t,i]));d.Loads.kvar(float(self.aq[t,i] if aidc_q is None else aidc_q[t,i]))
        for i,site in enumerate(SERVICES):
            d.Loads.Name('prod8500_mess_'+site.lower());d.Loads.kW(float(0 if mess_p is None else -mess_p[t,i]));d.Loads.kvar(float(0 if mess_q is None else -mess_q[t,i]))
    def values(self):return scalar_measure(self.d,self.plan) if self.plan else s.old.measure(self.d,self.ax)
    def controls(self,t):return s.control_state(self.d,t,1.04,123.5)
    def restore(self,state):
        d=self.d
        for r in state['regulators']:d.Transformers.Name(r['transformer']);d.RegControls.Name(r['name']);d.Transformers.Wdg(d.RegControls.TapWinding());d.Transformers.Tap(r['tap_pu'])
        for c in state['capacitors']:d.Capacitors.Name(c['name']);d.Capacitors.States(c['step_states'])
    def perturb(self,ch,amount):
        name=('op8500_' if ch['role']=='AIDC' else 'prod8500_mess_')+ch['site'].lower();self.d.Loads.Name(name);sign=1 if ch['role']=='AIDC' else -1
        if ch['component']=='P':
            q=self.d.Loads.kvar();self.d.Loads.kW(self.d.Loads.kW()+sign*amount);self.d.Loads.kvar(q)
        else:self.d.Loads.kvar(self.d.Loads.kvar()+sign*amount)
    def close(self):self.d.Basic.ClearAll()
def replay(folder,aidc_p=None,aidc_q=None,mess_p=None,mess_q=None,independent=True):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);e=Engine(folder/'runtime',independent);d=e.d;rows=[];values=[[],[],[],[]];states=[];start=time.perf_counter()
    for t in range(96):
        e.set_slot(t,aidc_p,aidc_q,mess_p,mess_q);err=None
        try:d.Solution.SolveSnap()
        except Exception as ex:
            if '#485' not in str(ex):raise
            err=str(ex)
        arrays=e.values();rows.append(s.extrema_row(1.04,.5,t,d.Solution.Converged(),d.Solution.ControlActionsDone(),err,arrays,e.nodes,e.ax,{}));rows[-1]['vreg_V']=123.5;states.append(e.controls(t))
        for target,v in zip(values,arrays):target.append(v)
    summary=s.summarize(1.04,.5,rows,time.perf_counter()-start);save(folder/'AC_SUMMARY.json',summary);table(folder/'AC_96_SLOT_EXTREMA.csv',rows);save(folder/'CONTROL_STATES_96.json',states)
    np.savez_compressed(folder/'AC_PHASE_ARRAYS.npz',node_names=e.nodes,line_phase_axes=e.ax['line_label'],transformer_current_axes=e.ax['tx_label'],transformer_kva_axes=e.ax['kva_label'],**{k:np.array(v) for k,v in zip(KEYS,values)})
    e.close();return summary
