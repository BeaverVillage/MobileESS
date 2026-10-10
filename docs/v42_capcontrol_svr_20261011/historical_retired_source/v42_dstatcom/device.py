"""Grounded independent-phase converter hardware at an existing audited PCC."""
from dataclasses import asdict, dataclass, field
import hashlib
import math
from pathlib import Path
import re

from .settings import ControllerSettings

VERSION = 'V42_DSTATCOM_GROUNDED_PHASE_DEVICE_V1'


def _require(value, label):
    if not value:
        raise ValueError(label)


def _finite(values):
    return all(math.isfinite(float(v)) for v in values)


def _command(engine, value):
    engine.Text.Command(value)
    if int(engine.Error.Number()):
        raise ValueError('DSTATCOM_DSS_COMMAND_FAILED:' + value + ':' + engine.Error.Description())


def bus_voltages(engine, bus, phases, nominal_kv_ln):
    _require(engine.Circuit.SetActiveBus(bus) >= 0, 'DSTATCOM_BUS_NOT_FOUND:' + bus)
    nodes = list(map(int, engine.Bus.Nodes()))
    magnitudes = list(map(float, engine.Bus.VMagAngle()))[::2]
    by_node = dict(zip(nodes, magnitudes))
    _require(all(p in by_node for p in phases), 'DSTATCOM_PHASE_NOT_FOUND:' + bus)
    result = [by_node[p] / (1000 * nominal_kv_ln) for p in phases]
    _require(_finite(result) and min(result) > 0, 'DSTATCOM_FINITE_ENERGIZED_PHASES_REQUIRED')
    return result


def _element(engine, name):
    engine.Circuit.SetActiveElement(name)
    _require(str(engine.CktElement.Name()).lower() == name.lower(), 'DSTATCOM_ELEMENT_NOT_FOUND:' + name)
    return dict(name=str(engine.CktElement.Name()), phases=int(engine.CktElement.NumPhases()),
        conductors=int(engine.CktElement.NumConductors()), terminals=int(engine.CktElement.NumTerminals()),
        nodes=list(map(int,engine.CktElement.NodeOrder())), buses=list(map(str,engine.CktElement.BusNames())),
        powers=list(map(float,engine.CktElement.Powers())), currents=list(map(float,engine.CktElement.Currents())),
        current_mag_angle=list(map(float,engine.CktElement.CurrentsMagAng())), losses=list(map(float,engine.CktElement.Losses())),
        normal_amps=float(engine.Properties.Value('NormAmps')) if name.lower().startswith(('transformer.','line.')) else None)


def _phase_current(element, phase, terminal=0):
    n = element['conductors']
    positions = [terminal*n+j for j in range(n) if element['nodes'][terminal*n+j] == phase]
    _require(len(positions)==1, 'DSTATCOM_SINGLE_PHASE_CURRENT_AXIS')
    j=positions[0]
    return complex(element['currents'][2*j], element['currents'][2*j+1])


def _terminal_power(element, terminal=0):
    n=element['conductors'];values=element['powers'][2*terminal*n:2*(terminal+1)*n]
    return complex(sum(values[::2]), sum(values[1::2]))


@dataclass(frozen=True)
class SiteSpec:
    site_id: str
    pcc_bus: str
    phases: tuple
    nominal_kv_ln: float
    rating_kvar: float
    service_transformers: tuple = ()
    service_transformer_kva: float | None = None
    mv_parent_bus: str | None = None
    source_receipts: tuple = field(default_factory=tuple)
    endpoint_id: str = 'PCC'

    def __post_init__(self):
        object.__setattr__(self,'phases',tuple(self.phases))
        object.__setattr__(self,'service_transformers',tuple(self.service_transformers))
        object.__setattr__(self,'source_receipts',tuple(self.source_receipts))
        _require(re.fullmatch(r'(STA|IDC)\d{2}', self.site_id) is not None, 'DSTATCOM_KNOWN_SITE_ID_REQUIRED')
        _require(re.fullmatch(r'[A-Za-z0-9_]+', self.endpoint_id) is not None, 'DSTATCOM_VALID_PHYSICAL_ENDPOINT_ID_REQUIRED')
        _require(re.fullmatch(r'[A-Za-z0-9_]+', self.pcc_bus) is not None, 'DSTATCOM_EXPLICIT_EXISTING_PCC_BUS_REQUIRED')
        _require(self.phases==(1,2,3), 'DSTATCOM_THREE_EXISTING_PHASES_AND_INDEPENDENT_MODULES_REQUIRED')
        _require(_finite([self.nominal_kv_ln,self.rating_kvar]) and self.nominal_kv_ln>0 and self.rating_kvar>0,
            'DSTATCOM_POSITIVE_VOLTAGE_AND_RATING_REQUIRED')
        _require(self.rating_kvar%750==0, 'DSTATCOM_RATING_IN_750_KVAR_MODULES_REQUIRED')
        _require(self.service_transformer_kva is None or math.isfinite(self.service_transformer_kva)
            and self.service_transformer_kva>0, 'DSTATCOM_VALID_SERVICE_RATING_REQUIRED')

    @property
    def device_id(self):
        return self.site_id+'_'+self.endpoint_id

    @classmethod
    def from_dict(cls, value):
        value=dict(value)
        if 'rating_kvar' not in value and 'initial_design_rating_kvar' in value:
            value['rating_kvar']=value['initial_design_rating_kvar']
        keys=cls.__dataclass_fields__
        return cls(**{k:value[k] for k in keys if k in value})

    def to_dict(self):
        return asdict(self)


class DStatcomDevice:
    def __init__(self, engine, spec, settings):
        self.engine=engine;self.spec=spec;self.settings=settings
        self.prefix='dstat_'+spec.site_id.lower()+'_'+spec.endpoint_id.lower()
        self.primary_bus=self.prefix+'_coupling'
        self.converter_bus=self.prefix+'_converter'
        self.phase_rating_kva=spec.rating_kvar/3
        self.q_state=[0.,0.,0.]
        self.last_limit_receipt=None
        self.command_history=[]
        self.installation_receipt=self._install()

    def _install(self):
        e,s=self.engine,self.spec
        original_nodes=set(map(str,e.Circuit.AllNodeNames()))
        original_elements=set(map(str,e.Circuit.AllElementNames()))
        _require(not any(n.lower().startswith(('transformer.'+self.prefix,'generator.'+self.prefix,'load.'+self.prefix))
            for n in original_elements), 'DSTATCOM_EXISTING_HARDWARE_NEVER_OVERWRITTEN')
        bus_voltages(e,s.pcc_bus,s.phases,s.nominal_kv_ln)
        actual_base=float(e.Bus.kVBase())
        _require(abs(actual_base-s.nominal_kv_ln)<=1e-9, 'DSTATCOM_NOMINAL_LN_BASE_MISMATCH')
        service=[]
        for name in s.service_transformers:
            e.Transformers.Name(name)
            _require(str(e.Transformers.Name()).lower()==name.lower(), 'DSTATCOM_ORIGINAL_SERVICE_TRANSFORMER_REQUIRED')
            element=_element(e,'Transformer.'+name)
            _require(any(bus.split('.')[0].lower()==s.pcc_bus.lower() for bus in element['buses']),
                'DSTATCOM_SERVICE_TRANSFORMER_NOT_CONNECTED_TO_PCC')
            e.Transformers.Wdg(1);kva=float(e.Transformers.kVA())
            _require(s.service_transformer_kva is None or kva==s.service_transformer_kva,
                'DSTATCOM_ORIGINAL_SERVICE_RATING_DRIFT')
            windings=[]
            for winding in range(1,element['terminals']+1):
                e.Transformers.Wdg(winding)
                windings.append(dict(winding=winding,kVA=float(e.Transformers.kVA()),kV=float(e.Transformers.kV())))
            service.append(dict(name=name,kVA=kva,buses=element['buses'],windings=windings,existing_service_retained=True))
        for expected in s.source_receipts:
            with Path(expected['path']).open('rb') as stream:
                actual=hashlib.file_digest(stream,'sha256').hexdigest()
            _require(actual==expected['sha256'], 'DSTATCOM_SITE_AUTHORITY_SOURCE_DRIFT')
        tx_kva=self.phase_rating_kva*self.settings.coupling_transformer_kva_factor
        primary_current=tx_kva/s.nominal_kv_ln
        self.names=[]
        for phase in s.phases:
            suffix=f'_p{phase}';tx=self.prefix+suffix+'_tx';gen=self.prefix+suffix+'_var';loss=self.prefix+suffix+'_loss'
            cable=self.prefix+suffix+'_lead'
            # Equivalent phase/neutral loop impedance; each module has its own
            # full-rated neutral return and grounded transformer reference.
            _command(e,f'New Line.{cable} phases=1 bus1={s.pcc_bus}.{phase} bus2={self.primary_bus}.{phase} '
                f'r1=0.00002 x1=0.00001 r0=0.00002 x0=0.00001 c1=0 c0=0 length=5 units=m normamps={primary_current:.17g} emergamps={primary_current:.17g}')
            _command(e,f'New Transformer.{tx} phases=1 windings=2 '
                f'buses=[{self.primary_bus}.{phase}.0 {self.converter_bus}.{phase}.0] conns=[wye wye] '
                f'kvs=[{s.nominal_kv_ln:.17g} {s.nominal_kv_ln:.17g}] kvas=[{tx_kva:.17g} {tx_kva:.17g}] '
                f'%Rs=[{self.settings.coupling_transformer_winding_r_percent:.17g} {self.settings.coupling_transformer_winding_r_percent:.17g}] '
                f'xhl={self.settings.coupling_transformer_xhl_percent:.17g} '
                f'%noloadloss={self.settings.coupling_transformer_no_load_loss_percent:.17g} '
                f'%imag={self.settings.coupling_transformer_magnetizing_current_percent:.17g} '
                f'normhkva={tx_kva:.17g} emerghkva={tx_kva:.17g}')
            _command(e,f'New Generator.{gen} phases=1 bus1={self.converter_bus}.{phase}.0 conn=wye '
                f'kv={s.nominal_kv_ln:.17g} kw=0 kvar=0 kva={self.phase_rating_kva:.17g} '
                'model=1 status=fixed vminpu=0.5 vmaxpu=1.5 enabled=yes')
            _command(e,f'New Load.{loss} phases=1 bus1={self.converter_bus}.{phase}.0 conn=wye '
                f'kv={s.nominal_kv_ln:.17g} kw={self.loss_kw(0):.17g} kvar=0 model=1 vminpu=0.5 vmaxpu=1.5')
            self.names.append(dict(phase=phase,transformer=tx,generator=gen,loss_load=loss,cable=cable))
        _command(e,'MakeBusList')
        for bus in (self.primary_bus,self.converter_bus):
            _command(e,f'SetkVBase bus={bus} kvln={s.nominal_kv_ln:.17g}')
        _require(original_nodes<=set(map(str,e.Circuit.AllNodeNames())), 'DSTATCOM_ORIGINAL_NODE_REMOVAL_FORBIDDEN')
        _require(original_elements<=set(map(str,e.Circuit.AllElementNames())), 'DSTATCOM_ORIGINAL_ELEMENT_REMOVAL_FORBIDDEN')
        compiled=[]
        for name in self.names:
            e.Circuit.SetActiveElement('Transformer.'+name['transformer'])
            normal=float(e.Properties.Value('NormAmps'))
            _require(abs(normal-primary_current)<=1e-14*primary_current,
                'DSTATCOM_COMPILED_COUPLING_CURRENT_RATING_MISMATCH')
            compiled.append(dict(phase=name['phase'],coupling_compiled_NormalAmps=normal))
        return dict(version=VERSION,site=s.to_dict(),names=self.names,
            topology='THREE_DISTINCT_GROUNDED_SINGLE_PHASE_CONVERTER_MODULES_THROUGH_DEDICATED_1_TO_1_ISOLATION_BANK',
            installation_bus=s.pcc_bus,sensing_bus=s.pcc_bus,mv_parent_metadata_only=s.mv_parent_bus,
            primary_kv_ln=s.nominal_kv_ln,secondary_kv_ln=s.nominal_kv_ln,
            converter_total_kva=s.rating_kvar,converter_phase_kva=self.phase_rating_kva,
            coupling_phase_kva=tx_kva,coupling_bank_kva=3*tx_kva,
            primary_and_secondary_transformer_current_rating_a=primary_current,
            compiled_coupling_nameplates=compiled,
            converter_phase_current_rating_a=self.phase_rating_kva/s.nominal_kv_ln,
            original_service_transformers=service,original_nodes_preserved=True,original_elements_preserved=True,
            original_service_capacity_not_bypassed=True,
            neutral_current_rating='Each independent module/transformer grounded neutral must carry full phase current; no shared undersized neutral assumed',
            dedicated_lead=dict(length_m=5,loop_r_ohm_per_m=.00002,loop_x_ohm_per_m=.00001,
                current_rating_a=primary_current,engineering_assumption=True,
                representation='Independent phase/neutral loop equivalent; solid-ground reference; no harmonic or earthing impedance model'),
            engineering_assumptions=self.settings.engineering_assumptions())

    def loss_kw(self,q):
        u=float(q)/self.phase_rating_kva
        return self.phase_rating_kva*(self.settings.converter_standby_loss_fraction
            +self.settings.converter_full_output_variable_loss_fraction*u*u)

    def _capacity(self,voltage_pu):
        rating=self.phase_rating_kva;operating=rating*self.settings.operating_kva_fraction
        current_limit=rating/self.spec.nominal_kv_ln*self.settings.operating_current_fraction
        apparent=min(operating,current_limit*self.spec.nominal_kv_ln*voltage_pu)
        low,high=0.,rating
        for _ in range(45):
            mid=(low+high)/2
            if math.hypot(mid,self.loss_kw(mid))<=apparent:low=mid
            else:high=mid
        return low

    def apply_q(self,q_by_phase,voltage_pu=None,dt_seconds=None):
        requested=list(map(float,q_by_phase));_require(len(requested)==3 and _finite(requested), 'DSTATCOM_FINITE_PHASE_Q_REQUIRED')
        voltage=(bus_voltages(self.engine,self.converter_bus,self.spec.phases,self.spec.nominal_kv_ln)
            if voltage_pu is None else list(map(float,voltage_pu)))
        _require(len(voltage)==3 and _finite(voltage) and min(voltage)>0, 'DSTATCOM_POSITIVE_LOCAL_VOLTAGE_REQUIRED')
        dt=self.settings.feedback_step_seconds if dt_seconds is None else float(dt_seconds)
        _require(math.isfinite(dt) and dt>0, 'DSTATCOM_POSITIVE_CAUSAL_FEEDBACK_DURATION_REQUIRED')
        caps=[self._capacity(v) for v in voltage]
        slew=self.phase_rating_kva*self.settings.ramp_fraction_of_phase_rating_per_second*dt
        limited=[max(-cap,min(cap,max(old-slew,min(old+slew,q)))) for q,cap,old in zip(requested,caps,self.q_state)]
        # The whole-bank constraint counts all three apparent powers, including
        # real converter losses, rather than summing nominal phase Q limits.
        total=sum(math.hypot(q,self.loss_kw(q)) for q in limited)
        whole=self.spec.rating_kvar*self.settings.operating_kva_fraction
        _require(total<=whole+1e-8, 'DSTATCOM_WHOLE_CONVERTER_APPARENT_CAPACITY')
        for q,name in zip(limited,self.names):
            self.engine.Generators.Name(name['generator']);self.engine.Generators.kW(0.);self.engine.Generators.kvar(q)
            self.engine.Loads.Name(name['loss_load']);self.engine.Loads.kW(self.loss_kw(q));self.engine.Loads.kvar(0.)
        self.q_state=limited
        result=dict(requested_Q_supply_kvar=requested,applied_Q_supply_kvar=limited,
            Q_saturated=[abs(q)>cap+1e-8 for q,cap in zip(requested,caps)],
            at_Q_capacity=[abs(q)>=cap-self.settings.q_convergence_kvar for q,cap in zip(limited,caps)],phase_Q_capacity_kvar=caps,
            converter_loss_kw=[self.loss_kw(q) for q in limited],ramp_limit_kvar=slew,
            total_converter_apparent_kva=total,whole_operating_limit_kva=whole)
        self.last_limit_receipt=result;self.command_history.append(result)
        return result

    def measure(self):
        e=self.engine;settings=self.settings;v=bus_voltages(e,self.spec.pcc_bus,self.spec.phases,self.spec.nominal_kv_ln)
        cv=bus_voltages(e,self.converter_bus,self.spec.phases,self.spec.nominal_kv_ln)
        primary_v=bus_voltages(e,self.primary_bus,self.spec.phases,self.spec.nominal_kv_ln)
        phases=[]
        for index,name in enumerate(self.names):
            phase=name['phase'];gen=_element(e,'Generator.'+name['generator']);loss=_element(e,'Load.'+name['loss_load']);tx=_element(e,'Transformer.'+name['transformer']);cable=_element(e,'Line.'+name['cable'])
            gs,ls=_terminal_power(gen),_terminal_power(loss)
            actual_q=-gs.imag;loss_p=ls.real
            current=abs(_phase_current(gen,phase)+_phase_current(loss,phase))
            apparent=abs(gs+ls)
            rating_current=self.phase_rating_kva/self.spec.nominal_kv_ln
            e.Transformers.Name(name['transformer']);e.Transformers.Wdg(1);tx_kva=float(e.Transformers.kVA());tx_current=tx['normal_amps']
            tx_nameplate_current=tx_kva/self.spec.nominal_kv_ln
            tx_kva_each=[abs(_terminal_power(tx,t)) for t in range(2)]
            tx_current_each=[abs(_phase_current(tx,phase,t)) for t in range(2)]
            cable_current=max(abs(_phase_current(cable,phase,t)) for t in range(2))
            e.Lines.Name(name['cable']);cable_rating=float(e.Lines.NormAmps())
            original_solver_tolerance=float(e.Solution.Convergence()) if hasattr(e.Solution,'Convergence') else float(e.Solution.Tolerance())
            power_comparison_tolerance=max(settings.numerical_power_readback_tolerance_kva,2*original_solver_tolerance*max(1.,abs(self.q_state[index]),self.loss_kw(self.q_state[index])))
            e.Generators.Name(name['generator']);nominal_q=float(e.Generators.kvar());nominal_p=float(e.Generators.kW())
            nominal_kva=float(e.Generators.kVARated())
            e.Transformers.Name(name['transformer']);coupling_windings=[]
            for winding in (1,2):
                e.Transformers.Wdg(winding)
                coupling_windings.append(dict(winding=winding,kva=float(e.Transformers.kVA()),kv=float(e.Transformers.kV())))
            installed_normal=next(r['coupling_compiled_NormalAmps'] for r in self.installation_receipt['compiled_coupling_nameplates'] if r['phase']==phase)
            coupling_unchanged=(all(w['kva']==self.installation_receipt['coupling_phase_kva'] and w['kv']==self.spec.nominal_kv_ln for w in coupling_windings)
                and tx_current==installed_normal)
            # OpenDSS stores var internally, then divides by 1000 in the kvar
            # accessor. Allow only that measured IEEE-754 round-trip (2 ULP),
            # independently of the much larger AC convergence comparison.
            command_comparison_tolerance=2*math.ulp(self.q_state[index])
            sign_ok=abs(nominal_q-self.q_state[index])<=command_comparison_tolerance and nominal_p==0 and abs(actual_q-self.q_state[index])<=power_comparison_tolerance and abs(gs.real)<=power_comparison_tolerance and abs(loss_p-self.loss_kw(self.q_state[index]))<=power_comparison_tolerance
            checks=dict(Q_P_sign_and_constant_power_readback=sign_ok,
                converter_nameplate_kva_unchanged=nominal_kva==self.phase_rating_kva,
                coupling_nameplate_and_normalamps_unchanged=coupling_unchanged,
                dedicated_lead_nameplate_unchanged=cable_rating==self.installation_receipt['dedicated_lead']['current_rating_a'],
                converter_phase_kva=apparent<=self.phase_rating_kva,
                converter_phase_current=current<=rating_current,
                converter_voltage=settings.actual_voltage_min_pu<=cv[index]<=settings.actual_voltage_max_pu,
                PCC_voltage=settings.actual_voltage_min_pu<=v[index]<=settings.actual_voltage_max_pu,
                coupling_primary_voltage=settings.actual_voltage_min_pu<=primary_v[index]<=settings.actual_voltage_max_pu,
                coupling_transformer_kva=max(tx_kva_each)<=tx_kva,
                coupling_transformer_current=max(tx_current_each)<=min(tx_current,tx_nameplate_current),
                dedicated_lead_current=cable_current<=cable_rating,
                modeled_converter_loss_nonnegative=loss_p>=0)
            phases.append(dict(phase=phase,Q_supply_kvar=actual_q,
                nominal_Q_readback_kvar=nominal_q,nominal_P_readback_kw=nominal_p,
                nominal_converter_kva_readback=nominal_kva,coupling_winding_nameplate_readbacks=coupling_windings,
                nominal_command_readback_tolerance_kvar=command_comparison_tolerance,
                power_readback_comparison_tolerance_kva=power_comparison_tolerance,
                original_DSS_convergence_tolerance=original_solver_tolerance,DSS_solver_tolerance_changed=False,Q_command_kvar=self.q_state[index],
                converter_loss_kw=loss_p,converter_apparent_kva=apparent,converter_current_a=current,
                converter_phase_current_rating_a=rating_current,converter_current_utilization=current/rating_current,
                converter_kva_utilization=apparent/self.phase_rating_kva,PCC_voltage_pu=v[index],
                converter_voltage_pu=cv[index],coupling_primary_voltage_pu=primary_v[index],
                coupling_transformer_kva=tx_kva_each,coupling_transformer_phase_rating_kva=tx_kva,
                coupling_transformer_current_a=tx_current_each,coupling_transformer_current_rating_a=tx_current,
                coupling_transformer_nameplate_phase_current_a=tx_nameplate_current,
                coupling_transformer_loss_kw=tx['losses'][0]/1000,
                dedicated_lead_current_a=cable_current,dedicated_lead_rating_a=cable_rating,
                dedicated_lead_loss_kw=cable['losses'][0]/1000,
                neutral_current_a=current,neutral_required_rating_a=rating_current,checks=checks,PASS=all(checks.values())))
        services=[]
        for name in self.spec.service_transformers:
            service=_element(e,'Transformer.'+name)
            _require(service['phases']==3, 'DSTATCOM_THREE_PHASE_ORIGINAL_SERVICE_REQUIRED')
            e.Transformers.Name(name);e.Transformers.Wdg(1)
            kva=float(e.Transformers.kVA());normal=service['normal_amps'];primary_kv=float(e.Transformers.kV())
            nameplate_phase_current=kva/(math.sqrt(3)*primary_kv)
            phase_currents=[abs(_phase_current(service,p,0)) for p in self.spec.phases]
            phase_kva=[abs(complex(*service['powers'][2*j:2*j+2])) for j in range(service['conductors'])
                if service['nodes'][j] in self.spec.phases]
            terminal_kva=[abs(_terminal_power(service,t)) for t in range(service['terminals'])]
            installed=next(row for row in self.installation_receipt['original_service_transformers'] if row['name']==name)
            winding_audits=[]
            for terminal in range(service['terminals']):
                e.Transformers.Wdg(terminal+1)
                winding_kva=float(e.Transformers.kVA());winding_kv=float(e.Transformers.kV())
                expected=installed['windings'][terminal]
                changed=winding_kva!=expected['kVA'] or winding_kv!=expected['kV']
                phase_current_rating=winding_kva/(math.sqrt(3)*winding_kv)
                actual_currents=[abs(_phase_current(service,p,terminal)) for p in self.spec.phases]
                start=terminal*service['conductors']
                actual_phase_kva=[abs(complex(*service['powers'][2*j:2*j+2]))
                    for j in range(start,start+service['conductors']) if service['nodes'][j] in self.spec.phases]
                winding_audits.append(dict(winding=terminal+1,nameplate_kva=winding_kva,nameplate_kv=winding_kv,
                    actual_phase_current_a=actual_currents,nameplate_phase_current_a=phase_current_rating,
                    actual_phase_apparent_kva=actual_phase_kva,nameplate_phase_kva=winding_kva/3,
                    original_rating_changed=changed,PASS=not changed
                        and max(actual_currents)<=phase_current_rating and max(actual_phase_kva)<=winding_kva/3
                        and terminal_kva[terminal]<=winding_kva))
            services.append(dict(name=name,primary_phase_current_a=phase_currents,compiled_primary_NormalAmps=normal,
                nameplate_primary_phase_current_a=nameplate_phase_current,primary_phase_apparent_kva=phase_kva,
                nameplate_phase_kva=kva/3,
                terminal_apparent_kva=terminal_kva,original_winding_kva=kva,
                PASS=max(phase_currents)<=min(normal,nameplate_phase_current)
                    and max(phase_kva)<=kva/3 and max(terminal_kva)<=kva and all(w['PASS'] for w in winding_audits),
                windings=winding_audits,original_rating_changed=any(w['original_rating_changed'] for w in winding_audits),
                net_MESS_AIDC_DSTATCOM_flow_included=True))
        total=sum(p['converter_apparent_kva'] for p in phases)
        return dict(site_id=self.spec.site_id,endpoint_id=self.spec.endpoint_id,device_id=self.spec.device_id,pcc_bus=self.spec.pcc_bus,PASS=all(p['PASS'] for p in phases) and total<=self.spec.rating_kvar and all(t['PASS'] for t in services),
            phases=phases,original_service_transformers=services,total_converter_apparent_kva=total,converter_nameplate_kva=self.spec.rating_kvar,
            total_converter_loss_kw=sum(p['converter_loss_kw'] for p in phases),
            total_coupling_transformer_loss_kw=sum(p['coupling_transformer_loss_kw'] for p in phases),
            total_dedicated_lead_loss_kw=sum(p['dedicated_lead_loss_kw'] for p in phases),
            original_service_capacity_not_bypassed=True,installation=self.installation_receipt)


def install(engine,spec,settings=None):
    spec=SiteSpec.from_dict(spec) if isinstance(spec,dict) else spec
    settings=ControllerSettings.from_dict(settings) if isinstance(settings,dict) else settings or ControllerSettings()
    _require(isinstance(spec,SiteSpec) and isinstance(settings,ControllerSettings), 'DSTATCOM_TYPED_FROZEN_SPEC_AND_SETTINGS_REQUIRED')
    return DStatcomDevice(engine,spec,settings)
