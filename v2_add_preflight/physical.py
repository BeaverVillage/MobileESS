"""V2_add electrical adapter. No optimizer or Production imports."""
from __future__ import annotations
import csv
import math
from pathlib import Path
import time

import numpy as np
import opendssdirect as odd

from .audit import DOC,ROOT,read,save,sha
from .vendor.ieee8500_ac import IEEE8500AC

RUNTIME=ROOT.parent/'V2_add_runtime'


class Physical(IEEE8500AC):
    def __init__(self,tag):
        self.source_dir=DOC/'source/feeder'
        self.output_dir=RUNTIME/'phase2'/tag/'dss'
        self.output_dir.mkdir(parents=True,exist_ok=True)
        self.source_hashes={}  # Existing source-byte certification is reused.
        self.d=odd.NewContext()
        for method in ('AllowChangeDir','AllowForms','AllowEditor','AllowDOScmd'):
            getattr(self.d.Basic,method)(False)
        self.d.Text.Command(f'compile "{self.source_dir/"Master.dss"}"')
        self.d.Text.Command(f'set datapath="{self.output_dir}"')
        self.d.Text.Command('set maxiterations=100 maxcontroliter=100 tolerance=1e-9 mode=snapshot controlmode=off')
        self.d.Solution.Solve()
        self.original_inventory=self._inventory()
        self.pccs={}
        self.mapping=list(csv.DictReader((DOC/'AIDC12_STA12_PCC_MAPPING.csv').open(encoding='utf-8')))
        self.loads=read(DOC/'OFFICIAL_BALANCED_AXES.json')['loads']
        self.load_names=[r['name'] for r in self.loads]
        self.pv_records=read(DOC/'source/PR197_PV_HOT_RECORDS.json')
        ratio=read(DOC/'source/PR197_SCREENING_RULE.json')['PV_ratio']
        self.pv_capacity=np.array([r['kw']*ratio for r in self.pv_records])
        self.pv_weights=self.pv_capacity/math.fsum(self.pv_capacity)
        self.pv_names=[]
        assert self.d.Generators.Count()==0  # No duplicate original injections.
        for i,r in enumerate(self.pv_records):
            name=f'aemo_pv_{i:04d}'
            self.d.Circuit.SetActiveBus(r['buses'][0].split('.')[0])
            assert int(r['buses'][0].split('.')[1]) in self.d.Bus.Nodes()
            assert abs(self.d.Bus.kVBase()-.12)<.001 and r['kv']==.12
            self.d.Text.Command(f'new Generator.{name} phases=1 bus1={r["buses"][0]} conn=wye kv={r["kv"]:.17g} '
                f'kw=0 kvar=0 kva={self.pv_capacity[i]:.17g} model=1 status=fixed '
                f'vminpu={r["vminpu_load_characteristic"]:.17g} vmaxpu={r["vmaxpu_load_characteristic"]:.17g}')
            self.pv_names.append(name)
        design=read(DOC/'source/PR199_MV_DESIGN.json')['transformer']
        self.port_meta=[]
        for r in self.mapping:
            site,bus=r['location_id'],r['candidate_bus']
            self.d.Circuit.SetActiveBus(bus)
            assert set(self.d.Bus.Nodes())=={1,2,3}
            assert abs(self.d.Bus.kVBase()*math.sqrt(3)-12.47)<.01247
            if r['role']=='AIDC':
                self.add_pcc(site,bus,'MV_3PH')
            else:
                name='high_mv_'+site.lower();secondary=name+'_lv'
                self.d.Text.Command(f'new Transformer.{name} phases=3 windings=2 buses=[{bus}.1.2.3 {secondary}.1.2.3.0] '
                    f'conns=[delta wye] kvs=[12.47 .48] kvas=[750 750] %rs=[.5 .5] '
                    f'xhl={design["XHL_pct_calculated_from_Z_and_assumed_R"]:.17g} '
                    f'%noloadloss={design["noloadloss_pct_assumed"]} %imag={design["imag_pct_assumed"]} '
                    'rneut=0 normhkva=750 emerghkva=750')
                self.d.Text.Command(f'new Load.pcc_{site.lower()} phases=3 bus1={secondary}.1.2.3 conn=wye kv=.48 '
                    'kw=0 kvar=0 model=1 status=fixed vminpu=.8 vmaxpu=1.2')
                self.pccs[site]=dict(element='Load.pcc_'+site.lower(),bus=secondary,mode='MV_DEDICATED_480V',mv_bus=bus)
                self.port_meta.append(dict(site=site,mv_bus=bus,secondary_bus=secondary,
                    transformer_kva=750.,interface_kva=600.,interface_current_A=600/(math.sqrt(3)*.48),
                    vehicle_P_limit_kw=300.,vehicle_Q_limit_kvar=250.,vehicle_PCS_kva=400.,occupancy_limit=1,
                    hardware_status='RESEARCH_MODEL_ASSUMPTION_NOT_FIELD_CERTIFIED'))
        self.d.Text.Command('set voltagebases=[115 12.47 .48 .208]')
        self.d.Text.Command('calcvoltagebases')
        self.d.Text.Command('set controlmode=off')
        self.d.Solution.Solve()
        self.inventory=self._inventory()
        self._controlled_transformers={r['transformer'] for r in self.inventory['regcontrols']}
        self._orient_original_lines();self._prepare_array_axes()
        # ALL originals, both terminals, real phase conductors. Disabled switches
        # remain in the axis with their original disabled state and zero current.
        self.all_mask=np.array([r['node']>0 for r in self.line_axes])
        for r,included in zip(self.line_axes,self.all_mask):
            r['legacy_parent_objective_included']=r.get('objective_included')
            r['objective_included']=bool(included)
            r['objective_scope']='V2_add all original real-phase conductors, both terminals; disabled originals retained at zero current'
        self.mv_mask=np.array([r['node']>0 and r['group']=='Primary' for r in self.line_axes])
        self.lv_mask=self.all_mask & ~self.mv_mask
        self.triplex_mask=np.array([r['node']>0 and r['group']=='Triplex' for r in self.line_axes])
        phase_bus={r['buses'][0].split('.')[0].lower():r['primary_phase'] for r in self.pv_records}
        for _ in range(10):
            changed=False
            for r in self.inventory['lines']:
                if r['group']!='Triplex':continue
                a,b=[v.split('.')[0].lower() for v in r['buses']]
                if a in phase_bus and b not in phase_bus:phase_bus[b]=phase_bus[a];changed=True
                if b in phase_bus and a not in phase_bus:phase_bus[a]=phase_bus[b];changed=True
            if not changed:break
        byname={r['element']:r for r in self.inventory['lines']}
        for r in self.line_axes:
            bus=byname[r['element']]['buses'][0].split('.')[0].lower()
            r['physical_phase']=('ABC'[r['node']-1] if r['group']=='Primary' and r['node'] in (1,2,3)
                else f'{phase_bus.get(bus,"UNKNOWN")}/hot{r["node"]}')
        self.d.Vsources.Name('source');self.d.Vsources.PU(1.04)
        for name in self.d.RegControls.AllNames():
            self.d.RegControls.Name(name);self.d.RegControls.ForwardVreg(123.5)
        self.d.Capacitors.Name('capbank3');self.d.Capacitors.States([0])
        self.initial_state=self.control_state()
        self.base_pcc={s:(0.,0.) for s in self.pccs}
        assert self.d.Lines.Count()==3703 and self.d.Transformers.Count()==1202
        assert self.d.Generators.Count()==2354 and len(self.pccs)==24
        self.inputs=np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz',allow_pickle=False)
        self.bg=np.load(DOC/'input/IEEE8500_BG_ALLOCATION_CANDIDATE.npz',allow_pickle=False)
        self.sites=list(map(str,self.inputs['PLANNING_AIDC_site']))
        self.solve_count=0
        self.prepared=False

    def apply(self,role,t,beta,mess=None,aidc_delta=None):
        P=self.bg[role+'_P'][t]*beta;Q=self.bg[role+'_Q'][t]*beta
        self.expected_bg=np.array([math.fsum(P),math.fsum(Q)])
        for name,p,q in zip(self.load_names,P,Q):
            self.d.Loads.Name(name);self.d.Loads.kW(float(p));self.d.Loads.kvar(float(q))
        self.expected_pv_total=math.fsum(self.inputs[role+'_PV_P_kw'][t])
        assert np.max(abs(self.inputs[role+'_PV_Q_kvar'][t]),initial=0)==0
        pv=self.pv_weights*self.expected_pv_total
        pv[int(np.argmax(self.pv_weights))]+=self.expected_pv_total-math.fsum(pv)
        assert np.min(pv)>=-1e-10 and np.max(pv-self.pv_capacity)<=1e-9
        for name,p in zip(self.pv_names,pv):
            self.d.Generators.Name(name);self.d.Generators.kW(float(p));self.d.Generators.kvar(0)
        self.base_pcc={s:(float(self.inputs[role+'_AIDC_P_kw'][t,j]),float(self.inputs[role+'_AIDC_Q_kvar'][t,j])) for j,s in enumerate(self.sites)}
        self.base_pcc.update({s:(0.,0.) for s in self.pccs if s.startswith('STA')})
        for site,delta in (aidc_delta or {}).items():
            a,b=self.base_pcc[site];self.base_pcc[site]=(a+delta[0],b+delta[1])
        self.base_pcc.update(mess or {})
        for site,(p,q) in self.base_pcc.items():
            self.d.Loads.Name(self.pccs[site]['element'].split('.',1)[1]);self.d.Loads.kW(float(p));self.d.Loads.kvar(float(q))
        self.d.Text.Command('set mode=snapshot loadmult=1 controlmode=static')
        self.d.Solution.Hour(t//4);self.d.Solution.Seconds((t%4)*900)

    def measure(self,role,t,beta,*,state=None,fixed=False,accounting=True):
        if state is not None:self.restore_control_state(state)
        self.d.Text.Command('set controlmode=off' if fixed else 'set controlmode=static')
        start=time.perf_counter();self.d.Solution.Solve();self.solve_count+=1
        a=self.measurement_arrays()
        rho=a['line_rho'];idx=int(np.argmax(np.where(self.all_mask,rho,-1)))
        binding=self.line_axes[idx]
        txk=a['transformer_winding_nameplate_kva_rho']
        v=a['node_voltage_pu']
        ports=[]
        for r in self.port_meta:
            self.d.Circuit.SetActiveElement(self.pccs[r['site']]['element'])
            current=np.asarray(self.d.CktElement.Currents()).reshape(-1,2)
            I=np.linalg.norm(current,axis=1)
            pq=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            ports.append(dict(site=r['site'],P_kw=float(pq[0]),Q_kvar=float(pq[1]),
                current_max_A=float(I.max()),current_loading=float(I.max()/r['interface_current_A']),
                apparent_kva=float(np.linalg.norm(pq)),interface_loading=float(np.linalg.norm(pq)/600)))
        row=dict(role=role,slot=t,evaluation_slot=t-(24 if role=='ACTUAL' else 0),beta_BG=beta,
            rho_global=float(rho[self.all_mask].max()),rho_MV=float(rho[self.mv_mask].max()),
            rho_LV=float(rho[self.lv_mask].max()),rho_Triplex=float(rho[self.triplex_mask].max()),
            binding_line=binding['element'],binding_phase=binding['node'],binding_terminal=binding['terminal'],
            binding_physical_phase=binding['physical_phase'],
            binding_class=binding['group'],Vmin=float(v.min()),Vmax=float(v.max()),
            line_violation_cells=int(np.sum((rho>1+1e-8)&self.all_mask)),
            node_voltage_violation_cells=int(np.sum((v<.95-1e-8)|(v>1.05+1e-8))),
            transformer_nameplate_max=float(txk.max()),transformer_current_max=float(a['transformer_current_rho'].max()),
            transformer_violation_cells=int(np.sum(txk>1+1e-8)+np.sum(a['transformer_current_rho']>1+1e-8)),
            port_current_max=float(max(r['current_loading'] for r in ports)),
            port_violation_cells=sum(r['current_loading']>1+1e-8 or r['interface_loading']>1+1e-8 for r in ports),
            converged=a['converged'],controls_done=a['control_actions_done'],control_queue=a['control_queue_size'])
        row['H_MV_LV']=row['rho_MV']-row['rho_LV']
        state=self.control_state()
        if accounting:
            actual_bg=np.zeros(2);actual_pv=np.zeros(2);pcc=np.zeros(2);caps=np.zeros(2)
            for name in self.load_names:
                self.d.Loads.Name(name);actual_bg+=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            for name in self.pv_names:
                self.d.Generators.Name(name);actual_pv-=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            for site in self.pccs:
                self.d.Circuit.SetActiveElement(self.pccs[site]['element']);pcc+=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            for name in self.d.Capacitors.AllNames():
                self.d.Capacitors.Name(name);caps+=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            residual=a['source_kw_kvar']-(actual_bg+pcc-actual_pv+caps+a['loss_kw_kvar'])
            row.update(PV_command_kw=self.expected_pv_total,PV_actual_kw=float(actual_pv[0]),PV_actual_kvar=float(actual_pv[1]),
                PV_total_abs_error_kw=float(abs(actual_pv[0]-self.expected_pv_total)),
                BG_P_actual_kw=float(actual_bg[0]),BG_Q_actual_kvar=float(actual_bg[1]),
                BG_P_abs_error_kw=float(abs(actual_bg[0]-self.expected_bg[0])),BG_Q_abs_error_kvar=float(abs(actual_bg[1]-self.expected_bg[1])),
                balance_P_error_kw=float(residual[0]),balance_Q_error_kvar=float(residual[1]))
        row['elapsed_s']=time.perf_counter()-start
        row['physics_PASS']=bool(row['converged'] and row['controls_done'] and not row['control_queue'] and
            not any(row[k] for k in ('line_violation_cells','node_voltage_violation_cells','transformer_violation_cells','port_violation_cells')) and
            (not accounting or max(abs(row[k]) for k in ['PV_total_abs_error_kw','PV_actual_kvar','BG_P_abs_error_kw','BG_Q_abs_error_kvar','balance_P_error_kw','balance_Q_error_kvar'])<1e-4))
        return row,a,state,ports

    def check_parameters(self):
        for old in self.original_inventory['lines']:
            self.d.Circuit.SetActiveElement(old['element'])
            assert self.d.CktElement.NormalAmps()==old['normal_amps'] and self.d.CktElement.Enabled()==old['enabled']
        for old in self.original_inventory['transformers']:
            self.d.Transformers.Name(old['element'].split('.',1)[1])
            for w in old['windings']:
                self.d.Transformers.Wdg(w['winding']);assert self.d.Transformers.kVA()==w['kva_nameplate']
        for name,capacity,r in zip(self.pv_names,self.pv_capacity,self.pv_records):
            self.d.Generators.Name(name)
            assert self.d.CktElement.BusNames()==r['buses'] and self.d.Generators.kV()==r['kv']
            assert abs(float(self.d.Properties.Value('kVA'))-capacity)<1e-9 and self.d.Generators.Model()==1
        self.d.Vsources.Name('source');assert self.d.Vsources.PU()==1.04
        for name in self.d.RegControls.AllNames():
            self.d.RegControls.Name(name);assert self.d.RegControls.ForwardVreg()==123.5
        return True
