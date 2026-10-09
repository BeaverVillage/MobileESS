"""Unchanged original Balanced feeder with explicit scenario BG/port overlays."""
import numpy as np
import opendssdirect as odd
from ieee8500_v42.ac import IEEE8500AC
from ieee8500_v42_balanced.engine import BalancedEngine
from .common import *


class HighEngine(IEEE8500AC):
    set_pcc=BalancedEngine.set_pcc
    settle=BalancedEngine.settle
    state_rows=BalancedEngine.state_rows
    load_measurements=BalancedEngine.load_measurements
    verify_parameters=BalancedEngine.verify_parameters

    def __init__(self,tag,bg=.552,layout='L0',mapping_path=None,report_dir=None):
        from ieee8500_v42_original.hold import require_execution_approval
        require_execution_approval('OPENDSS:HighEngine')
        self.report_dir=Path(report_dir) if report_dir else REPORT
        self.source_dir=SOURCE.resolve();self.output_dir=(self.report_dir/'ac'/tag/'dss').resolve()
        self.output_dir.mkdir(parents=True,exist_ok=True);self.source_hashes=self._hash_source()
        self.d=odd.NewContext()
        for method in ('AllowChangeDir','AllowForms','AllowEditor','AllowDOScmd'):getattr(self.d.Basic,method)(False)
        self.d.Text.Command(f'compile "{SOURCE/"Master.dss"}"')
        self.d.Text.Command(f'set datapath="{self.output_dir}"')
        self.d.Text.Command('set maxiterations=100 maxcontroliter=100 tolerance=1e-9 mode=snapshot controlmode=off')
        self.d.Solution.Solve();self.d.Text.Command('set controlmode=static')
        self.pccs={};self._last_background_scale=None;self._last_pcc_demand={}
        self.original_loads={}
        for name in self.d.Loads.AllNames():
            self.d.Loads.Name(name);self.original_loads[name]=(self.d.Loads.kW(),self.d.Loads.kvar())
        self.inventory=self._inventory();self._orient_original_lines()
        self._controlled_transformers={r['transformer'] for r in self.inventory['regcontrols']}
        self._prepare_array_axes();self._assert_policy()
        self.original_inventory=read(PR193/'ORIGINAL_FEEDER_INVENTORY.json')
        self.policy='P5';self.pv_enabled=True;self.bg=float(bg);self.layout=layout;self.master='Master.dss'
        if layout!='L0' and mapping_path is None:
            raise ValueError('MV_PORT_GEOMETRY_INFEASIBLE_FIXED_AIDC; explicit audited joint mapping required')
        self.load_records=read(BALANCED_REPORT/'BALANCED_CUSTOMER_RECORDS.json')
        self.load_names=[r['name'] for r in self.load_records];self.base_p=np.array([r['kw'] for r in self.load_records]);self.base_q=np.array([r['kvar'] for r in self.load_records])
        self.fixed=np.array([r['status']=='fixed' for r in self.load_records])
        self.primary_phase_by_customer={r['buses'][0].split('.')[0]:r['primary_phase'] for r in self.load_records}
        self.mapping_path=Path(mapping_path) if mapping_path else MAPPING
        self.mapping=rows(self.mapping_path)
        for r in self.mapping:
            self.d.Circuit.SetActiveBus(r['candidate_bus'])
            low_voltage=self.d.Bus.kVBase()<1
            if r['role']=='AIDC' or layout=='L0' or low_voltage:
                self.add_pcc(r['location_id'],r['candidate_bus'],'MV_3PH' if r['role']=='AIDC' else 'LV_SPLIT_240')
        self.pv_records=read(BALANCED_REPORT/'UNBALANCED_CUSTOMER_RECORDS.json');self.pv_names=[];self.pv_capacity=[]
        ratio=float(read(DATA/'historical/SCREENING_RULE_PR62.json')['PV_ratio'])
        for i,r in enumerate(self.pv_records):
            name=f'aemo_pv_{i:04d}';cap=r['kw']*ratio
            self.d.Text.Command(f'new Generator.{name} phases=1 bus1={r["buses"][0]} conn=wye kv=.12 kw=0 kvar=0 kva={cap:.17g} model=1 status=fixed vminpu=.88 vmaxpu=1.05')
            self.pv_names.append(name);self.pv_capacity.append(cap)
        self.pv_capacity=np.array(self.pv_capacity)
        self.d.Vsources.Name('source');self.d.Vsources.PU(1.04)
        for name in self.d.RegControls.AllNames():self.d.RegControls.Name(name);self.d.RegControls.ForwardVreg(123.5)
        self.d.Capacitors.Name('capbank3');self.d.Capacitors.States([0])
        self.mv_port_meta=[]
        if layout!='L0':self.add_mv_ports()
        self.initial_state=self.control_state()
        overlay=self.report_dir/'overlays/P5.dss';overlay.parent.mkdir(parents=True,exist_ok=True)
        text=(AEMO_REPORT/'overlays/P5.dss').read_text(encoding='utf-8')
        if not overlay.exists():overlay.write_text(text,encoding='utf-8')
        assert sha(overlay)==sha(AEMO_REPORT/'overlays/P5.dss')
        assert self.d.Lines.Count()==3703 and self.d.Loads.Count()==1201 and self.d.Generators.Count()==2354
        self.expected_p=np.zeros(1177);self.expected_q=np.zeros(1177);self.expected_pv=np.zeros(2354)

    def add_mv_ports(self):
        design=read(REPORT/'ENGINEERING_MV_DESIGN.json')
        self.mv_mapping=[r for r in self.mapping if r['location_id'].startswith('STA') and r['location_id'] not in self.pccs]
        assert 0<len(self.mv_mapping)<=12
        self.mv_commands=[]
        for r in self.mv_mapping:
            site=r['location_id'];bus=r.get('candidate_bus',r.get('mv_bus'))
            self.d.Circuit.SetActiveBus(bus);assert self.d.Bus.Nodes()==[1,2,3]
            assert abs(self.d.Bus.kVBase()*np.sqrt(3)-12.47)<.01247
            name='high_mv_'+site.lower();secondary=name+'_lv'
            # D-Yg, grounded 480V neutral; exact research impedance is separately disclosed.
            tx=design['transformer'];xhl=tx['XHL_pct_calculated_from_Z_and_assumed_R']
            cmd=(f'new Transformer.{name} phases=3 windings=2 buses=[{bus}.1.2.3 {secondary}.1.2.3.0] '
                 f'conns=[delta wye] kvs=[12.47 .48] kvas=[750 750] %rs=[.5 .5] xhl={xhl:.17g} '
                 f'%noloadloss={tx["noloadloss_pct_assumed"]} %imag={tx["imag_pct_assumed"]} rneut=0 normhkva=750 emerghkva=750')
            self.d.Text.Command(cmd);self.mv_commands.append(cmd)
            self.d.Text.Command(f'new Load.pcc_{site.lower()} phases=3 bus1={secondary}.1.2.3 conn=wye kv=.48 kw=0 kvar=0 model=1 status=fixed vminpu=.8 vmaxpu=1.2')
            self.pccs[site]=dict(element='Load.pcc_'+site.lower(),bus=secondary,mode='MV_DEDICATED_480V',mv_bus=bus)
        self.d.Text.Command('set voltagebases=[115 12.47 .48 .208]');self.d.Text.Command('calcvoltagebases')
        self.d.Text.Command('set controlmode=off');self.d.Solution.Solve();self.d.Text.Command('set controlmode=static')
        fresh=self._inventory();added=[r for r in fresh['transformers'] if r['element'].lower().startswith('transformer.high_mv_')]
        assert len(added)==len(self.mv_mapping)
        self.inventory['transformers'].extend(added);self.inventory['counts']=fresh['counts'];self.mv_port_meta=added
        self._prepare_array_axes()
        p=self.report_dir/'overlays'/f'MV_{sha(self.mapping_path)[:12]}_750KVA.dss'
        p.parent.mkdir(parents=True,exist_ok=True)
        text='! ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED; original DSS unchanged\n'+'\n'.join(self.mv_commands)+'\n'
        if p.exists():assert p.read_text(encoding='utf-8')==text
        else:p.write_text(text,encoding='utf-8')

    def apply_inputs(self,t,data,mess=None,aidc_delta=None):
        mult=np.full(1177,self.bg*float(data['gross_factor'][t]));mult[self.fixed]=self.bg
        self.expected_p=self.base_p*mult;self.expected_q=self.base_q*mult
        for n,p,q in zip(self.load_names,self.expected_p,self.expected_q):self.d.Loads.Name(n);self.d.Loads.kW(float(p));self.d.Loads.kvar(float(q))
        self.expected_pv=self.pv_capacity*float(data['pv_factor'][t])
        for n,p in zip(self.pv_names,self.expected_pv):self.d.Generators.Name(n);self.d.Generators.kW(float(p));self.d.Generators.kvar(0)
        self.base_pcc={s:(float(data['PCC_P_kw'][t,i]),float(data['PCC_Q_kvar'][t,i])) for i,s in enumerate(sorted(s for s in self.pccs if s.startswith('AIDC')))}
        self.base_pcc.update({s:(0.,0.) for s in self.pccs if s.startswith('STA')})
        for s,x in (aidc_delta or {}).items():
            p,q=self.base_pcc[s];self.base_pcc[s]=(p+x[0],q+x[1])
        self.base_pcc.update(mess or {})
        self.set_pcc(self.base_pcc);self.d.Text.Command('set mode=snapshot loadmult=1')
        self.d.Solution.Hour(t//4);self.d.Solution.Seconds((t%4)*900)

    def port_measurements(self):
        result=[]
        for site in sorted(s for s in self.pccs if s.startswith('STA')):
            self.d.Circuit.SetActiveElement(self.pccs[site]['element'])
            from ieee8500_v42.ac import _complex
            current=np.abs(_complex(self.d.CktElement.Currents()));powers=np.asarray(self.d.CktElement.Powers()).reshape(-1,2)
            volts=_complex(self.d.CktElement.Voltages())
            pq=powers.sum(0)
            result.append(dict(site=site,P_kw=float(pq[0]),Q_kvar=float(pq[1]),S_kva=float(np.linalg.norm(pq)),
                I_max_A=float(current.max()),per_conductor_A=current.tolist(),per_conductor_PQ=powers.tolist(),
                per_conductor_voltage_V=np.abs(volts).tolist(),line_line_V=float(abs(volts[0]-volts[1])),layout=self.layout,
                port_mode=self.pccs[site]['mode']))
        return result
