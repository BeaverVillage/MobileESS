"""Instrumented, isolated native TIME S0/S1 AC only; no solver optimization."""
import ast,csv,json,math,re,sys,types
from pathlib import Path
import numpy as np
from .audit import ROOT,DOC,read,sha
from . import correction as c
from .correction_svr import SV,RUN,BETAS,save,table,regulator_readback,graph
from .correction_time100 import clock_class

def seal_s0():
    """One-way seal made before the first S1 operating AC solve."""
    seal=SV/'S0_DIAGNOSIS_SEAL.json'
    if seal.exists():
        v=read(seal);assert all(sha(Path(p).read_bytes())==h for p,h in v['files'].items());return
    from .correction_projection import project
    rows=[];receipts=[]
    for b in BETAS:
        for role in ('PLANNING','ACTUAL'):
            for fresh in (False,True):
                p=RUNTIME_BASE/'correction_time100'/(f'TIME_{b:.2f}_{role}_B0'+('_FRESH' if fresh else ''))
                r,_,_,_=project(p/'RECEIPT.json');rows.append(r);receipts.append(p/'RECEIPT.json')
    table('S0_PRE_SVR_CANONICAL_DIAGNOSIS.csv',rows)
    (SV/'S0_SEALED_FINDINGS_KO.md').write_text('''# S0 진단 봉인 — 추가 SVR 평가 이전

원본 r043과 같은 목적함수는 각 슬롯의 TIME 제어 처리 후 최종 상태에서
source-rooted parent terminal 전류 / 원본 NormalAmps를 측정한 평가96 최대값이다.
모든 이벤트의 극값과 Prefix24 안전은 별도이다. 이전 correction 루트 TIME CSV는
이벤트 envelope 중간 자료이며 canonical/ 및 본 S0 CSV가 최종상태 목적함수이다.

β2.00 Actual: 75.3595439519%, 최소0.9465536641pu.
β2.10 Actual: 78.9655574355%, 최소0.9436775897pu.
이 S0 결과만으로 추가 SVR 장비 후보를 탈락시키거나 Primary를 최종 판정하지 않는다.
IEEE123의 전기 반복15는 β1.50 Actual 초기에서 비수렴했다. IEEE8500의 기존
전기 반복100을 쓰면 원본 TIME 지연을 유지하면서 수렴한다. 제어 반복한도100은 동일하다.
이는 수치 예산 차이이며 Tap/Delay/Source의 사후 조정이 아니다.

기존12 제어기 static 계약과 저전압 노드/경로, 슬롯말 Tap 포화를 봉인한다.
기존 archive에는 이벤트별 RegControl TapNumber가 없으므로 그 검증은
독립 S0 재생 및 S1에서 새로 계측하며 기존 기록에 소급하여 PASS를 부여하지 않는다.
''',encoding='utf-8')
    files=[p for p in SV.iterdir() if p.is_file()]
    files+=receipts
    files += [ROOT/'v2_add_preflight'/n for n in ('correction.py','correction_time100.py','correction_projection.py','correction_svr.py')]
    for name in ('STRICT15_TIME_FAILURE.json','OBJECTIVE_CERTIFICATION.json','CONTROL_PROPERTY_AUDIT.json','PRESERVATION_BASELINE.json'):
        files.append(c.OUT/name)
    save('S0_DIAGNOSIS_SEAL.json',dict(status='SEALED_BEFORE_NEW_SVR_OPERATING_AC',files={str(p):sha(p.read_bytes()) for p in files},
        immutable_historical_evidence=True,SVR_operating_solves_before_seal=0,native_optimizer_calls=0))

RUNTIME_BASE=c.RUNTIME

def source_svr():
    p=ROOT/'v44/svr11_frozen/v42_voltage_control/svr.py'
    m=types.ModuleType('v2_add_ieee8500_series_svr');exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__)
    # Only names/identifier syntax adapt to the IEEE8500 inventory. Electrical
    # equations, finite limits, native control, installation and loss model stay
    # verbatim. IEEE123 original-seven names are never forced on IEEE8500.
    m.ORIGINAL_REGCONTROLS=tuple(r['regcontrol'] for r in read(SV/'EXISTING_REGULATOR_FULL_STATIC_AUDIT.json')['initial_readbacks'])
    m._NAME=re.compile(r'^[a-zA-Z][a-zA-Z0-9_\-]*$')
    return m

class Instrumented(c.CorrectedPhysical):
    configuration='S0'
    def __init__(self,tag,role,mode='TIME'):
        self.capture=False;self.trace=[];self.configuration=type(self).configuration
        super().__init__(tag,role,mode)
        self.outfolder=RUN/tag;self.outfolder.mkdir(parents=True,exist_ok=True)
        self.bank=None;self.original12=tuple(self.d.RegControls.AllNames())
        self.original_line_static={r['element']:self._line_static(r['element']) for r in self.inventory['lines']}
        self.old_node_names=list(self.node_axes);old_phases={ (r['element'],r['terminal'],r['conductor']):r['physical_phase'] for r in self.line_axes}
        if self.configuration!='S0':
            contract=read(SV/'SVR_CANDIDATE_PREREGISTRATION.json')['contracts'][self.configuration]
            self.bank=source_svr().install(self.d,contract)
            before=self.control_state()
            # Energize newly created nodes with AUTO disabled, just as base
            # Physical initializes its model. This is not a TIME event and
            # cannot change taps/caps/clock/queue. Initial controls remain1.0.
            self.d.Solution.ControlMode(-1);self.d.Solution.Solve()
            self.d.Solution.ControlMode(2)
            self.inventory=self._inventory();self._controlled_transformers={r['transformer'] for r in self.inventory['regcontrols']}
            self._orient_original_lines();self._prepare_array_axes()
            self.orientation=c.independent_orientation(self)
            self.canonical,self.security,self.cmv,self.clv=c.masks(self.line_axes,self.orientation)
            self.all_mask=self.canonical;self.mv_mask=self.cmv;self.lv_mask=self.clv
            self.triplex_mask=self.clv & np.array([r['group']=='Triplex' for r in self.line_axes])
            for r,flag in zip(self.line_axes,self.canonical):
                r.update(physical_phase=old_phases[r['element'],r['terminal'],r['conductor']],objective_included=bool(flag),objective_scope='V44_CANONICAL_OBJECTIVE')
            assert all(self._line_static(el)==props for el,props in self.original_line_static.items())
            assert all(self.control_state()['taps'][n]==before['taps'][n] for n in before['taps'])
            assert self.control_state()['capacitors']==before['capacitors'] and not self.queue(self.d)
            assert self.d.Solution.Hour()==self.d.Solution.Seconds()==0
            self.initial_state=self.control_state()
            self.bank.measure() # Static model/readback checks, not new solve.
            (self.outfolder/'SERIES_INSTALLATION.json').write_text(json.dumps(self.bank.installation_receipt),encoding='utf-8')
        self.initial_audit=regulator_readback(self)
        self.capture=True

    def _line_static(self,name):
        self.d.Circuit.SetActiveElement(name)
        return {p:self.d.Properties.Value(p) for p in self.d.CktElement.AllPropertyNames() if p.lower() not in ('bus1','bus2')}

    def measurement_arrays(self):
        a=super().measurement_arrays()
        if self.capture:
            controls=regulator_readback(self);assert all(v['tap_number_readback_PASS'] for v in controls)
            cuts=[]
            if self.bank:
                for u in self.bank.contract['units']:
                    self.d.Circuit.SetActiveElement(u['cut_element']);powers=np.array(self.d.CktElement.Powers()).reshape(-1,2)
                    cuts.append(dict(bank=u['id'],cut_element=u['cut_element'],parent_terminal_P_kw=float(powers[:self.d.CktElement.NumConductors(),0].sum()),
                        parent_terminal_Q_kvar=float(powers[:self.d.CktElement.NumConductors(),1].sum())))
            self.trace.append(dict(physical_seconds=self.d.Solution.Hour()*3600+self.d.Solution.Seconds(),
                controls=controls,capacitors=self.control_state()['capacitors'],queue=self.queue(self.d),cut_flows=cuts,
                losses_kw=float(a['loss_kw_kvar'][0]),transformer_current_max=float(a['transformer_current_rho'].max()),
                transformer_kva_max=float(a['transformer_winding_nameplate_kva_rho'].max())))
        return a

    def check_parameters(self):
        assert all(self._line_static(el)==props for el,props in self.original_line_static.items())
        assert len(self.inventory['lines'])==3703 and sum(r['group']=='Triplex' for r in self.inventory['lines'])==1177
        self.d.Vsources.Name('source');assert self.d.Vsources.PU()==1.04
        for name in self.original12:
            self.d.RegControls.Name(name);assert self.d.RegControls.ForwardVreg()==123.5
        for old in self.original_inventory['transformers']:
            self.d.Transformers.Name(old['element'].split('.',1)[1])
            for w in old['windings']:
                self.d.Transformers.Wdg(w['winding']);assert self.d.Transformers.kVA()==w['kva_nameplate']
        if self.bank:self.bank.measure()
        (self.outfolder/'TAP_QUEUE_EVENT_READBACK.json').write_text(json.dumps(dict(initial=self.initial_audit,events=self.trace)),encoding='utf-8')
        (self.outfolder/'TRANSFORMER_AXES.json').write_text(json.dumps(dict(current=self.transformer_axes,winding=self.transformer_winding_axes)),encoding='utf-8')
        (self.outfolder/'LINE_PRESERVATION.json').write_text(json.dumps(dict(PASS=True,original_lines=3703,original_Triplex=1177,
            original_impedance_and_rating_all_properties_unchanged=True,only_declared_terminal_bus_split=self.configuration!='S0',
            original_objective_parent_terminal_count=int(self.canonical.sum()),original_source_and_original12_controls_unchanged=True,
            new_bank_count=0 if not self.bank else len(self.bank.contract['units']))),encoding='utf-8')
        return True

def install(config):
    original=c.fingerprint
    Instrumented.configuration=config;c.CorrectedPhysical=Instrumented;c.clock_class=clock_class;c.RUN=RUN
    def fingerprint():
        result=original()
        for p in (Path(__file__),ROOT/'v2_add_preflight/correction_svr.py',SV/'SVR_CANDIDATE_PREREGISTRATION.json',SV/'S0_DIAGNOSIS_SEAL.json',ROOT/'v44/svr11_frozen/v42_voltage_control/svr.py'):
            result[str(p)]=sha(p.read_bytes())
        result['configuration']=config
        return result
    c.fingerprint=fingerprint

def main(config):
    c.priority()
    import psutil
    proc=psutil.Process();proc.cpu_affinity([13])
    seal_s0();RUN.mkdir(exist_ok=True);install(config)
    # Names are distinct immutable evidence tags; same version V2_add.
    schedule=dict(name=config,discharge_begin=[68]*8,duration=8)
    # B0 has NO MESS injection: zero trajectory, not the default charge cycle.
    c.trajectory=lambda schedule:(np.zeros((96,8)),np.zeros((96,8)),np.full((97,8),760.))
    for b in BETAS:
        for fresh in (False,True):
            try:c.run_case(b,'ACTUAL',schedule=schedule,fresh=fresh)
            except Exception as exc:
                save(f'FAILURE_{config}_{b:.2f}'+('_FRESH' if fresh else '')+'.json',dict(configuration=config,beta=b,error=repr(exc),certified=False))
                raise

if __name__=='__main__':main(sys.argv[1])
