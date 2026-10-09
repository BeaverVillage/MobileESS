"""Original full IEEE8500 plus explicit operating, customer-PV and PCC overlays."""
import math
from collections import Counter, defaultdict, deque
import numpy as np
from ieee8500_v42.ac import IEEE8500AC
from .common import *

POLICIES = {"P0": (1.05,126.5,True), "P1": (1.04,126.5,True),
            "P2": (1.04,123.5,True), "P3": (1.04,123.5,False),
            "P4": (1.04,123.5,False), "P5": (1.04,123.5,False)}


def target_vreg(policy,name):
    if name.lower().startswith('feeder_reg'):return POLICIES[policy][1]
    if policy=='P5' or (policy=='P4' and name.lower().startswith('vreg3_')):return 123.5
    return 125.


class StudyEngine(IEEE8500AC):
    def __init__(self, tag, policy="P0", pv=False):
        super().__init__(output_dir=REPORT/"ac"/tag/"dss")
        assert policy in POLICIES
        self.policy = policy
        self.pv_enabled = pv
        self.load_records = []
        phase = {}
        graph = defaultdict(set)
        for meta in self.inventory["transformers"]:
            if len(meta["buses"]) == 3 and ".1.0" in meta["buses"][1].lower():
                primary = int(meta["buses"][0].split(".")[1])
                for bus in meta["buses"][1:]:
                    phase[bus.split(".")[0].lower()] = "ABC"[primary-1]
        for meta in self.inventory["lines"]:
            if meta["group"] == "Triplex":
                a,b = [bus.split(".")[0].lower() for bus in meta["buses"]]
                graph[a].add(b); graph[b].add(a)
        for meta in self.inventory["loads"]:
            self.d.Loads.Name(meta["name"])
            props = {p:self.d.Properties.Value(p) for p in self.d.CktElement.AllPropertyNames()}
            bus = meta["buses"][0].split(".")[0].lower()
            queue=deque([bus]);seen={bus}; primary=None
            while queue:
                b=queue.popleft()
                if b in phase:
                    primary=phase[b];break
                for c in graph[b]-seen:
                    seen.add(c);queue.append(c)
            assert primary in "ABC", "SOURCE_SERVICE_PRIMARY_PHASE_MISSING"
            record=dict(meta,status=props["Status"].lower(),enabled=bool(self.d.CktElement.Enabled()),
                        daily=props["Daily"],yearly=props["Yearly"],duty=props["Duty"],
                        primary_phase=primary)
            assert record["status"] in ("fixed","variable") and meta["phases"]==1
            self.load_records.append(record)
        self.load_names = [r["name"] for r in self.load_records]
        self.base_p=np.array([r["kw"] for r in self.load_records])
        self.base_q=np.array([r["kvar"] for r in self.load_records])
        self.fixed=np.array([r["status"]=="fixed" for r in self.load_records])
        assert len(self.load_records)==2354 and self.fixed.sum()==48
        assert all(r["enabled"] for r in self.load_records)
        self.primary_phase_by_customer={r["buses"][0].split(".")[0].lower():r["primary_phase"] for r in self.load_records}
        assert sha(MAPPING)==MAPPING_SHA
        for row in rows(MAPPING):
            self.add_pcc(row["location_id"],row["candidate_bus"],
                         "MV_3PH" if row["role"]=="AIDC" else "LV_SPLIT_240")
        self.pv_capacity=np.zeros(2354)
        self.pv_names=[]
        if pv:
            ratio=float(read(DATA/"historical/SCREENING_RULE_PR62.json")["PV_ratio"])
            for index,r in enumerate(self.load_records):
                capacity=ratio*r["kw"]
                name=f"aemo_pv_{index:04d}"
                command=(f'new Generator.{name} phases=1 bus1={r["buses"][0]} '
                    f'conn={"delta" if r["delta"] else "wye"} kv={r["kv"]:.17g} '
                    f'kw=0 kvar=0 kva={capacity:.17g} model=1 status=fixed '
                    f'vminpu={r["vminpu_load_characteristic"]:.17g} '
                    f'vmaxpu={r["vmaxpu_load_characteristic"]:.17g}')
                self.d.Text.Command(command)
                self.pv_names.append(name);self.pv_capacity[index]=capacity
            assert self.d.Generators.Count()==2354
        assert self.d.Circuit.NumNodes()==8531 and self.d.Transformers.Count()==1190
        assert self.d.Lines.Count()==3703 and self.d.Loads.Count()==2378
        self.apply_policy(policy)
        self.expected_p=np.zeros(2354);self.expected_q=np.zeros(2354);self.expected_pv=np.zeros(2354)

    def apply_policy(self, policy):
        source,feeder,cap3=POLICIES[policy]
        self.d.Vsources.Name("source");self.d.Vsources.PU(source)
        for name in self.d.RegControls.AllNames():
            self.d.RegControls.Name(name)
            if name.lower().startswith("feeder_reg"):
                self.d.RegControls.ForwardVreg(feeder)
            else:
                assert self.d.RegControls.ForwardVreg()==125.0
                self.d.RegControls.ForwardVreg(target_vreg(policy,name))
        controlled=set()
        for name in self.d.CapControls.AllNames():
            self.d.CapControls.Name(name);controlled.add(self.d.CapControls.Capacitor().lower())
        assert len(controlled)==9 and "capbank3" not in controlled
        self.d.Capacitors.Name("capbank3");self.d.Capacitors.States([1 if cap3 else 0])
        # Ten original enabled objects; cap3 OFF is its zero switched step.
        assert self.d.CktElement.Enabled()
        self.initial_state=self.control_state()
        commands=["! User-authorized operating overlay; source files unchanged.",
                  f"Edit Vsource.source pu={source}"]
        commands += [f"Edit RegControl.{name} Vreg={feeder}"
                     for name in self.d.RegControls.AllNames() if name.lower().startswith("feeder_reg")]
        commands += [f"Edit RegControl.{name} Vreg=123.5" for name in self.d.RegControls.AllNames()
                     if not name.lower().startswith('feeder_reg') and target_vreg(policy,name)==123.5]
        if not cap3:commands.append("Edit Capacitor.CAPBank3 states=[0]")
        path=REPORT/"overlays"/f"{policy}.dss";path.parent.mkdir(parents=True,exist_ok=True)
        text="\n".join(commands)+"\n"
        if path.exists():assert path.read_text(encoding="utf-8")==text
        else:path.write_text(text,encoding="utf-8")

    def apply_inputs(self, slot, gross_factor, pv_factor, aidc_p, aidc_q, *, static=False, pv_on=True):
        assert 0<=slot<96 and math.isfinite(gross_factor) and gross_factor>=0
        assert 0<=pv_factor<=1, "PV_NAMEPLATE_EXCEEDED_NO_CLIPPING"
        multipliers=np.full(2354,BG_SCALE*float(gross_factor))
        if static:multipliers[:]=BG_SCALE
        else:multipliers[self.fixed]=BG_SCALE
        self.expected_p=self.base_p*multipliers
        self.expected_q=self.base_q*multipliers
        for name,p,q in zip(self.load_names,self.expected_p,self.expected_q):
            self.d.Loads.Name(name);self.d.Loads.kW(float(p));self.d.Loads.kvar(float(q))
        self.expected_pv=self.pv_capacity*(pv_factor if pv_on else 0)
        for name,p in zip(self.pv_names,self.expected_pv):
            self.d.Generators.Name(name);self.d.Generators.kW(float(p));self.d.Generators.kvar(0)
        self.base_pcc={}
        for i,site in enumerate(sorted(s for s in self.pccs if s.startswith("AIDC"))):
            self.base_pcc[site]=(float(aidc_p[i]),float(aidc_q[i]))
        for site in self.pccs:
            if site.startswith("STA"):self.base_pcc[site]=(0.,0.)
        self.set_pcc(self.base_pcc)
        self.d.Text.Command("set mode=snapshot loadmult=1")
        self.d.Solution.Hour(slot//4);self.d.Solution.Seconds((slot%4)*900)

    def set_pcc(self, demands):
        for site in self.pccs:
            p,q=demands.get(site,(0.,0.))
            assert np.isfinite([p,q]).all()
            self.d.Loads.Name(self.pccs[site]["element"].split(".",1)[1])
            self.d.Loads.kW(float(p));self.d.Loads.kvar(float(q))

    def settle(self, mode="auto", state=None):
        if state is not None:self.restore_control_state(state)
        self.d.Text.Command("set controlmode=static" if mode=="auto" else "set controlmode=off")
        self.d.Solution.Solve()
        assert self.d.Solution.Converged(), "AC_NONCONVERGENCE"
        if mode=="auto":
            assert self.d.Solution.ControlActionsDone() and self.d.CtrlQueue.QueueSize()==0, "UNSETTLED_CONTROLS"
        return self.measurement_arrays()

    def load_measurements(self):
        actual=np.zeros((2354,2));error=0.
        for i,r in enumerate(self.load_records):
            self.d.Loads.Name(r["name"])
            error=max(error,abs(self.d.Loads.kW()-self.expected_p[i]),abs(self.d.Loads.kvar()-self.expected_q[i]))
            assert abs(self.d.Loads.PF()-r["pf"])<1e-12
            assert self.d.Properties.Value("Status").lower()==r["status"]
            assert self.d.Loads.Model()==r["model"] and self.d.CktElement.BusNames()==r["buses"]
            actual[i]=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
        pv=np.zeros((2354,2))
        for i,name in enumerate(self.pv_names):
            self.d.Generators.Name(name)
            pv[i]=-np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            assert abs(float(self.d.Properties.Value("kVA"))-self.pv_capacity[i])<1e-10
        pcc=np.zeros(2)
        for site,pair in self.base_pcc.items():
            self.d.Loads.Name(self.pccs[site]["element"].split(".",1)[1])
            value=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            assert np.max(np.abs(value-np.asarray(pair)))<1e-5
            pcc+=value
        assert error<1e-10
        capacitor_pq=np.zeros(2)
        for name in self.d.Capacitors.AllNames():
            self.d.Capacitors.Name(name)
            capacitor_pq+=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
        self.last_capacitor_pq=capacitor_pq
        balance=-np.asarray(self.d.Circuit.TotalPower())-(actual.sum(0)+pcc-pv.sum(0)
            +capacitor_pq+np.asarray(self.d.Circuit.Losses())/1000)
        return actual,pv,error,balance

    def state_rows(self, stage, slot):
        output=[]
        for name in self.d.RegControls.AllNames():
            self.d.RegControls.Name(name);transformer=self.d.RegControls.Transformer()
            vreg=self.d.RegControls.ForwardVreg()
            self.d.Transformers.Name(transformer);self.d.Transformers.Wdg(2)
            tap=self.d.Transformers.Tap();lo=self.d.Transformers.MinTap();hi=self.d.Transformers.MaxTap()
            output.append(dict(stage=stage,slot=slot,kind="RegControl",name=name,
                enabled=self.d.CktElement.Enabled(),tap_number=self.d.RegControls.TapNumber(),
                tap_ratio=tap,min_tap=lo,max_tap=hi,at_lower_limit=abs(tap-lo)<1e-10,
                at_upper_limit=abs(tap-hi)<1e-10,Vreg=vreg,states="",energized="",
                delay_seconds=self.inventory["regcontrols"][[r["name"] for r in self.inventory["regcontrols"]].index(name)]["properties"]["Delay"]))
        for name in self.d.Capacitors.AllNames():
            self.d.Capacitors.Name(name);states=self.d.Capacitors.States()
            enabled=bool(self.d.CktElement.Enabled())
            output.append(dict(stage=stage,slot=slot,kind="Capacitor",name=name,enabled=enabled,
                tap_number="",tap_ratio="",min_tap="",max_tap="",at_lower_limit="",at_upper_limit="",
                Vreg="",states=json.dumps(states),energized=enabled and any(states),delay_seconds=""))
        for name in self.d.CapControls.AllNames():
            self.d.CapControls.Name(name)
            output.append(dict(stage=stage,slot=slot,kind="CapControl",name=name,
                enabled=bool(self.d.CktElement.Enabled()),tap_number="",tap_ratio="",min_tap="",max_tap="",
                at_lower_limit="",at_upper_limit="",Vreg="",states="",energized="",
                delay_seconds=self.d.Properties.Value("Delay"),delay_off_seconds=self.d.Properties.Value("DelayOff")))
        return output

    def verify_parameters(self):
        assert self.verify_source_unchanged()
        source,feeder,_=POLICIES[self.policy]
        self.d.Vsources.Name("source");assert self.d.Vsources.PU()==source
        for r in self.inventory["regcontrols"]:
            self.d.RegControls.Name(r["name"])
            self.d.Circuit.SetActiveElement("RegControl."+r["name"])
            assert self.d.CktElement.Enabled()
            for k,v in r["properties"].items():
                if k.lower()=="tapnum":continue
                expected=str(target_vreg(self.policy,r['name'])) if k.lower()=="vreg" else v
                actual=self.d.Properties.Value(k)
                if k.lower()=="vreg":assert float(actual)==float(expected)
                else:assert actual==expected, ("REGCONTROL_PARAMETER_DRIFT",r["name"],k,actual,expected)
        for r in self.inventory["capcontrols"]:
            self.d.Circuit.SetActiveElement("CapControl."+r["name"])
            assert self.d.CktElement.Enabled()
            for k,v in r["properties"].items():
                assert self.d.Properties.Value(k)==v,("CAPCONTROL_PARAMETER_DRIFT",r["name"],k)
        for r in self.inventory["lines"]:
            self.d.Lines.Name(r["element"].split(".",1)[1])
            assert self.d.CktElement.NormalAmps()==r["normal_amps"]
            assert self.d.CktElement.BusNames()==r["buses"]
        for r in self.inventory["transformers"]:
            self.d.Transformers.Name(r["element"].split(".",1)[1])
            for w in r["windings"]:
                self.d.Transformers.Wdg(w["winding"])
                assert self.d.Transformers.kVA()==w["kva_nameplate"]
        return dict(PASS=True,original_DSS_byte_identity=True,all_original_ratings=True,
                    original_RegControls=12,original_CapControls=9,
                    downstream_Vreg_unchanged=self.policy in ('P0','P1','P2','P3'),
                    actual_Vreg_targets={r['name']:target_vreg(self.policy,r['name']) for r in self.inventory['regcontrols']},
                    original_CapControl_properties_delays_unchanged=True)
