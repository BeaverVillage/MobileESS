"""Only the official customer Load structure changes; PV stays at old hot nodes."""
import math
from collections import defaultdict, deque
import numpy as np
import opendssdirect as odd
from ieee8500_v42.ac import IEEE8500AC
from ieee8500_v42_aemo.engine import StudyEngine
from .common import *


class OriginalCase(IEEE8500AC):
    def __init__(self, tag, balanced=True):
        self.source_dir = SOURCE.resolve()
        self.output_dir = (REPORT/'ac'/tag/'dss').resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.source_hashes = self._hash_source()
        self.d = odd.NewContext()
        for method in ('AllowChangeDir', 'AllowForms', 'AllowEditor', 'AllowDOScmd'):
            getattr(self.d.Basic, method)(False)
        self.master = 'Master.dss' if balanced else 'Master-unbal.dss'
        self.d.Text.Command(f'compile "{self.source_dir/self.master}"')
        self.d.Text.Command(f'set datapath="{self.output_dir}"')
        self.d.Text.Command('set maxiterations=100 maxcontroliter=100 tolerance=1e-9 mode=snapshot controlmode=off')
        self.d.Solution.Solve()
        self.d.Text.Command('set controlmode=static')
        self.pccs = {}; self._last_background_scale = None; self._last_pcc_demand = {}
        self.original_loads = {}
        for name in self.d.Loads.AllNames():
            self.d.Loads.Name(name)
            self.original_loads[name] = (self.d.Loads.kW(), self.d.Loads.kvar())
        self.inventory = self._inventory()
        self._orient_original_lines()
        self._controlled_transformers = {r['transformer'] for r in self.inventory['regcontrols']}
        self._prepare_array_axes()
        self.initial_state = self.control_state()
        self._assert_policy()


def customer_records(e):
    phase = {}; graph = defaultdict(set)
    for r in e.inventory['transformers']:
        if len(r['buses']) == 3 and '.1.0' in r['buses'][1].lower():
            p = int(r['buses'][0].split('.')[1])
            for bus in r['buses'][1:]: phase[bus.split('.')[0].lower()] = 'ABC'[p-1]
    for r in e.inventory['lines']:
        if r['group'] == 'Triplex':
            a,b = [v.split('.')[0].lower() for v in r['buses']]
            graph[a].add(b); graph[b].add(a)
    records = []
    for r in e.inventory['loads']:
        e.d.Loads.Name(r['name'])
        props = {p:e.d.Properties.Value(p) for p in e.d.CktElement.AllPropertyNames()}
        bus = r['buses'][0].split('.')[0].lower()
        queue=deque([bus]); seen={bus}; primary=None
        while queue:
            b=queue.popleft()
            if b in phase: primary=phase[b]; break
            for c in graph[b]-seen: seen.add(c); queue.append(c)
        assert primary in 'ABC'
        records.append(dict(r, status=props['Status'].lower(), enabled=bool(e.d.CktElement.Enabled()),
                            daily=props['Daily'], yearly=props['Yearly'], duty=props['Duty'], primary_phase=primary))
    return records


class BalancedEngine(OriginalCase):
    # These methods do not write into the parent P5 report.
    set_pcc = StudyEngine.set_pcc
    settle = StudyEngine.settle
    state_rows = StudyEngine.state_rows
    verify_parameters = StudyEngine.verify_parameters

    def __init__(self, tag):
        super().__init__(tag, True)
        self.policy='P5'; self.pv_enabled=True
        self.load_records=customer_records(self)
        self.load_names=[r['name'] for r in self.load_records]
        self.base_p=np.array([r['kw'] for r in self.load_records])
        self.base_q=np.array([r['kvar'] for r in self.load_records])
        self.fixed=np.array([r['status']=='fixed' for r in self.load_records])
        assert len(self.load_records)==1177 and self.fixed.sum()==24
        assert all(r['phases']==2 and r['enabled'] and not r['delta'] and r['kv']==.208 for r in self.load_records)
        self.primary_phase_by_customer={r['buses'][0].split('.')[0].lower():r['primary_phase'] for r in self.load_records}
        assert sha(MAPPING)==MAPPING_SHA
        for r in rows(MAPPING):
            self.add_pcc(r['location_id'],r['candidate_bus'],'MV_3PH' if r['role']=='AIDC' else 'LV_SPLIT_240')
        # Lossless existing 2354 per-hot PV installation; do not rebalance or move it.
        self.pv_records=read(REPORT/'UNBALANCED_CUSTOMER_RECORDS.json')
        self.pv_names=[]; self.pv_capacity=[]
        ratio=float(read(DATA/'historical/SCREENING_RULE_PR62.json')['PV_ratio'])
        for i,r in enumerate(self.pv_records):
            capacity=r['kw']*ratio; name=f'aemo_pv_{i:04d}'
            self.d.Text.Command(f'new Generator.{name} phases=1 bus1={r["buses"][0]} conn=wye kv={r["kv"]:.17g} '
                f'kw=0 kvar=0 kva={capacity:.17g} model=1 status=fixed '
                f'vminpu={r["vminpu_load_characteristic"]:.17g} vmaxpu={r["vmaxpu_load_characteristic"]:.17g}')
            self.pv_names.append(name); self.pv_capacity.append(capacity)
        self.pv_capacity=np.array(self.pv_capacity)
        assert self.d.Generators.Count()==2354 and self.d.Loads.Count()==1201
        assert self.d.Circuit.NumNodes()==8531 and self.d.Lines.Count()==3703 and self.d.Transformers.Count()==1190
        self.apply_policy()
        self.expected_p=np.zeros(1177); self.expected_q=np.zeros(1177); self.expected_pv=np.zeros(2354)

    def apply_policy(self):
        self.d.Vsources.Name('source'); self.d.Vsources.PU(1.04)
        for name in self.d.RegControls.AllNames():
            self.d.RegControls.Name(name); self.d.RegControls.ForwardVreg(123.5)
        self.d.Capacitors.Name('capbank3'); self.d.Capacitors.States([0])
        assert self.d.CktElement.Enabled()
        self.initial_state=self.control_state()
        path=REPORT/'overlays/P5.dss'; path.parent.mkdir(parents=True,exist_ok=True)
        text=(OLD/'overlays/P5.dss').read_text(encoding='utf-8')
        if path.exists(): assert path.read_text(encoding='utf-8')==text
        else: path.write_text(text,encoding='utf-8')
        assert sha(path)==sha(OLD/'overlays/P5.dss')

    def apply_inputs(self, slot, gross_factor, pv_factor, aidc_p, aidc_q):
        assert 0<=slot<96 and math.isfinite(gross_factor) and gross_factor>=0 and 0<=pv_factor<=1
        multiplier=np.full(1177,BG_SCALE*float(gross_factor)); multiplier[self.fixed]=BG_SCALE
        self.expected_p=self.base_p*multiplier; self.expected_q=self.base_q*multiplier
        for name,p,q in zip(self.load_names,self.expected_p,self.expected_q):
            self.d.Loads.Name(name); self.d.Loads.kW(float(p)); self.d.Loads.kvar(float(q))
        self.expected_pv=self.pv_capacity*pv_factor
        for name,p in zip(self.pv_names,self.expected_pv):
            self.d.Generators.Name(name); self.d.Generators.kW(float(p)); self.d.Generators.kvar(0)
        self.base_pcc={s:(float(aidc_p[i]),float(aidc_q[i])) for i,s in enumerate(sorted(s for s in self.pccs if s.startswith('AIDC')))}
        self.base_pcc.update({s:(0.,0.) for s in self.pccs if s.startswith('STA')})
        self.set_pcc(self.base_pcc)
        self.d.Text.Command('set mode=snapshot loadmult=1')
        self.d.Solution.Hour(slot//4); self.d.Solution.Seconds((slot%4)*900)

    def load_measurements(self):
        actual=np.zeros((1177,2)); legs=np.zeros((1177,2,2)); error=0.
        for i,r in enumerate(self.load_records):
            self.d.Loads.Name(r['name'])
            error=max(error,abs(self.d.Loads.kW()-self.expected_p[i]),abs(self.d.Loads.kvar()-self.expected_q[i]))
            assert abs(self.d.Loads.PF()-r['pf'])<1e-12
            assert self.d.Properties.Value('Status').lower()==r['status']
            assert self.d.Loads.Model()==r['model'] and self.d.CktElement.BusNames()==r['buses']
            powers=np.asarray(self.d.CktElement.Powers()).reshape(-1,2)
            assert self.d.CktElement.NodeOrder()==[1,2,0]
            legs[i]=powers[:2]; actual[i]=powers.sum(0)
        pv=np.zeros((2354,2))
        for i,name in enumerate(self.pv_names):
            self.d.Generators.Name(name)
            pv[i]=-np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            assert abs(float(self.d.Properties.Value('kVA'))-self.pv_capacity[i])<1e-10
            assert self.d.CktElement.BusNames()==self.pv_records[i]['buses']
        pcc=np.zeros((24,2))
        for i,site in enumerate(sorted(self.pccs)):
            self.d.Loads.Name(self.pccs[site]['element'].split('.',1)[1])
            pcc[i]=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            assert np.max(np.abs(pcc[i]-self.base_pcc[site]))<1e-5
        assert error<1e-10
        cap=np.zeros(2)
        for name in self.d.Capacitors.AllNames():
            self.d.Capacitors.Name(name); cap+=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
        balance=-np.asarray(self.d.Circuit.TotalPower())-(actual.sum(0)+pcc.sum(0)-pv.sum(0)+cap+np.asarray(self.d.Circuit.Losses())/1000)
        self.last_legs=legs; self.last_pcc=pcc; self.last_capacitor_pq=cap
        return actual,pv,error,balance
