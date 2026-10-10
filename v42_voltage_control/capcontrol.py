"""Native single-step voltage CapControls for the four original IEEE123 caps.

Only new control objects are installed. Original capacitor connections, kvar,
step counts, and source-initial ON states are never written. C83 PTPhase=MAX
measures line-to-neutral voltage and protects the highest phase of its physical
600-kvar bank; it does not promise independent three-phase compensation.
"""
import copy
import json
import math

from v42_b3_joint.contracts import canonical, digest, require, require_sha

SCHEMA = 'V42_NATIVE_VOLTAGE_CAPCONTROL_CONTRACT_V1'
ORIGINAL = dict(c83=dict(bus='83', phases=3, kvar=600., kv=4.16),
                c88a=dict(bus='88.1', phases=1, kvar=50., kv=2.402),
                c90b=dict(bus='90.2', phases=1, kvar=50., kv=2.402),
                c92c=dict(bus='92.3', phases=1, kvar=50., kv=2.402))
DEVICE_FIELDS = {'name','capacitor','monitor_element','monitor_terminal','bus','phases','kvar','kv',
                 'num_steps','pt_phase','nominal_primary_ln_v','secondary_nominal_voltage_v','ptratio',
                 'on_pu','off_pu','delay_on_seconds','delay_off_seconds','minimum_on_seconds',
                 'minimum_off_seconds','deadtime_seconds'}
CONTRACT_FIELDS = {'schema','variant','status','development_dates','devices','contract_SHA'}


def validate_contract(contract):
    """Complete canonical roundtrip; omitted fields are not defaulted."""
    value = json.loads(canonical(contract))
    require(set(value) == CONTRACT_FIELDS and value['schema'] == SCHEMA,
            'CAP_COMPLETE_VERSIONED_CONTRACT_REQUIRED')
    require(value['variant'] in ('A1','A2'), 'CAP_A1_OR_A2_VARIANT_REQUIRED')
    require(value['status'] in ('DEVELOPMENT_CANDIDATE','FROZEN'), 'CAP_EXPLICIT_DESIGN_STATUS_REQUIRED')
    require(isinstance(value['development_dates'], list) and bool(value['development_dates'])
            and len(set(value['development_dates'])) == len(value['development_dates']),
            'CAP_DISCLOSED_DEVELOPMENT_DATES_REQUIRED')
    from datetime import date
    for day in value['development_dates']:
        require(date.fromisoformat(day).isoformat() == day and
                (day.startswith('2025-04-') or day in ('2025-05-01','2025-05-28')),
                'CAP_NO_FUTURE_EVALUATION_TUNING_DATA')
    require_sha(value['contract_SHA'])
    require(digest({k:v for k,v in value.items() if k != 'contract_SHA'}) == value['contract_SHA'],
            'CAP_CONTRACT_SHA_DRIFT')
    expected = ['c83'] if value['variant'] == 'A1' else list(ORIGINAL)
    require(isinstance(value['devices'],list) and [r.get('capacitor') for r in value['devices']] == expected,
            'CAP_CANONICAL_ORIGINAL_EQUIPMENT_AXIS_REQUIRED')
    for row in value['devices']:
        require(set(row) == DEVICE_FIELDS, 'CAP_COMPLETE_DEVICE_FIELDS_REQUIRED')
        ref = ORIGINAL[row['capacitor']]
        require(row['name'] == 'v42_cap_'+row['capacitor'] and row['monitor_element'] == 'Capacitor.'+row['capacitor']
                and row['monitor_terminal'] == 1, 'CAP_NATIVE_LOCAL_MONITOR_REQUIRED')
        require(all(row[k] == ref[k] for k in ('bus','phases','kvar','kv')) and row['num_steps'] == 1,
                'CAP_ORIGINAL_CONNECTION_RATING_SINGLE_STEP_REQUIRED')
        require(row['pt_phase'] == ('MAX' if row['phases'] == 3 else '1'), 'CAP_PHYSICAL_MONITORED_PHASE_REQUIRED')
        numbers = DEVICE_FIELDS - {'name','capacitor','monitor_element','bus','pt_phase'}
        require(all(type(row[k]) in (int,float) and math.isfinite(row[k]) for k in numbers),
                'CAP_FINITE_EXPLICIT_PARAMETERS_REQUIRED')
        require(row['nominal_primary_ln_v'] > 0 and row['secondary_nominal_voltage_v'] == 120.
                and row['ptratio'] == row['nominal_primary_ln_v']/120., 'CAP_LN_PT_CALIBRATION_REQUIRED')
        require(.95 < row['on_pu'] < 1 < row['off_pu'] < 1.05, 'CAP_INTERNAL_HYSTERESIS_WITHIN_UNCHANGED_BAND')
        require(row['minimum_on_seconds'] > 0 and row['minimum_off_seconds'] > 0
                and row['delay_off_seconds'] >= row['minimum_on_seconds']
                and row['deadtime_seconds'] >= row['minimum_off_seconds']
                and row['delay_on_seconds'] > 0, 'CAP_NATIVE_MINIMUM_HOLD_AND_DELAY_REQUIRED')
        require(all(float(row[k]).is_integer() for k in ('delay_on_seconds','delay_off_seconds',
                'minimum_on_seconds','minimum_off_seconds','deadtime_seconds')),
                'CAP_INTEGRAL_SECOND_NATIVE_QUEUE_TIMING_REQUIRED')
    return value


def _physical(engine, name):
    engine.Capacitors.Name(name)
    require(engine.Circuit.SetActiveElement('Capacitor.'+name) >= 0, 'CAP_ORIGINAL_ELEMENT_MISSING')
    buses = list(engine.CktElement.BusNames())
    return dict(name=name, bus=buses[0].lower(), buses=[b.lower() for b in buses],
                enabled=bool(engine.CktElement.Enabled()), phases=int(engine.CktElement.NumPhases()),
                delta=bool(engine.Capacitors.IsDelta()),
                kvar=float(engine.Capacitors.kvar()), kv=float(engine.Capacitors.kV()),
                num_steps=int(engine.Capacitors.NumSteps()), states=[int(x) for x in engine.Capacitors.States()])


def candidate_contract(engine, variant, *, on_pu=.99, off_pu=1.03,
                       delay_on_seconds=30., delay_off_seconds=300.,
                       minimum_on_seconds=300., minimum_off_seconds=300.,
                       development_dates=('2025-04-30','2025-05-01','2025-05-28')):
    """Engineering candidate, never silently classified as a frozen design."""
    require(variant in ('A1','A2'), 'CAP_EXPLICIT_VARIANT_REQUIRED')
    rows = []
    for name in (['c83'] if variant == 'A1' else list(ORIGINAL)):
        ref = ORIGINAL[name]
        physical = _physical(engine,name)
        require(all(physical[k] == ref[k] for k in ('bus','phases','kvar','kv'))
                and physical['num_steps'] == 1, 'CAP_CANDIDATE_ORIGINAL_CAP_REQUIRED')
        require(engine.Circuit.SetActiveBus(ref['bus'].split('.')[0]) >= 0, 'CAP_MONITOR_BUS_MISSING')
        nominal = float(engine.Bus.kVBase())*1000.
        rows.append(dict(name='v42_cap_'+name,capacitor=name,monitor_element='Capacitor.'+name,
            monitor_terminal=1,**ref,num_steps=1,pt_phase='MAX' if ref['phases']==3 else '1',
            nominal_primary_ln_v=nominal,secondary_nominal_voltage_v=120.,ptratio=nominal/120.,
            on_pu=on_pu,off_pu=off_pu,delay_on_seconds=delay_on_seconds,delay_off_seconds=delay_off_seconds,
            minimum_on_seconds=minimum_on_seconds,minimum_off_seconds=minimum_off_seconds,
            deadtime_seconds=minimum_off_seconds))
    result = dict(schema=SCHEMA,variant=variant,status='DEVELOPMENT_CANDIDATE',
                  development_dates=list(development_dates),devices=rows)
    result['contract_SHA'] = digest(result)
    return validate_contract(result)


class CapControlBank:
    def __init__(self, engine, contract, clock=None):
        self.engine, self.contract, self.clock = engine, validate_contract(contract), clock
        require(int(engine.Solution.ControlMode()) == 2, 'CAP_NATIVE_TIME_MODE_REQUIRED')
        require(int(engine.CapControls.Count()) == 0, 'CAP_FRESH_NO_PREEXISTING_CONTROLLER_REQUIRED')
        require(not any(token in n.lower() for n in engine.Circuit.AllElementNames()
                for token in ('dstat','statcom')), 'CAP_RETIRED_DEVICE_FORBIDDEN')
        require({n.lower() for n in engine.Capacitors.AllNames()} == set(ORIGINAL),
                'CAP_EXACT_ORIGINAL_FOUR_REQUIRED')
        self.original_physical = [_physical(engine,n) for n in ORIGINAL]
        for row in self.original_physical:
            ref = ORIGINAL[row['name']]
            require(row['enabled'] and not row['delta'] and row['num_steps'] == 1 and row['states'] == [1]
                    and all(row[k] == ref[k] for k in ('bus','phases','kvar','kv')),
                    'CAP_SOURCE_INITIAL_ORIGINAL_FIXED_ON_REQUIRED')
        self.last_state = {n:1 for n in ORIGINAL}
        self.state_since_seconds = {n:0. for n in ORIGINAL}
        self.switch_counts = {n:0 for n in ORIGINAL}
        self.transitions = []
        self.minimum_hold_violations = []
        self.last_observed_seconds = 0.
        self.initial_state = dict(states=copy.deepcopy(self.last_state),absolute_seconds=0.,
                                  namespace=getattr(clock,'namespace',None),
                                  source_initial_state='original four physical single-step capacitors ON',
                                  previous_namespace_state_read=False)
        for row in self.contract['devices']:
            engine.Circuit.SetActiveBus(row['bus'].split('.')[0])
            require(float(engine.Bus.kVBase())*1000. == row['nominal_primary_ln_v'],
                    'CAP_COMPILED_BUS_LN_BASE_DRIFT')
            command = (f"New CapControl.{row['name']} Capacitor={row['capacitor']} "
                f"Element={row['monitor_element']} Terminal=1 Type=Voltage "
                f"PTRatio={row['ptratio']:.17g} PTPhase={row['pt_phase']} "
                f"ONsetting={120.*row['on_pu']:.17g} OFFsetting={120.*row['off_pu']:.17g} "
                f"Delay={row['delay_on_seconds']:.17g} DelayOFF={row['delay_off_seconds']:.17g} "
                f"DeadTime={row['deadtime_seconds']:.17g} VoltOverride=No EventLog=Yes Enabled=Yes")
            engine.Text.Command(command)
        self.readback = self._controls()
        require([_physical(engine,n) for n in ORIGINAL] == self.original_physical,
                'CAP_INSTALL_CHANGED_PHYSICAL_CAP_OR_STATE')

    def _controls(self):
        require({n.lower() for n in self.engine.CapControls.AllNames()} ==
                {r['name'] for r in self.contract['devices']}, 'CAP_UNDECLARED_NATIVE_CONTROLLER')
        result = []
        for ref in self.contract['devices']:
            e = self.engine
            e.CapControls.Name(ref['name'])
            e.Circuit.SetActiveElement('CapControl.'+ref['name'])
            row = dict(name=e.CapControls.Name().lower(),capacitor=e.CapControls.Capacitor().lower(),
                monitor_element=e.CapControls.MonitoredObj().lower(),monitor_terminal=int(e.CapControls.MonitoredTerm()),
                mode=int(e.CapControls.Mode()),ptratio=float(e.CapControls.PTRatio()),
                onsetting=float(e.CapControls.ONSetting()),offsetting=float(e.CapControls.OFFSetting()),
                delay_on_seconds=float(e.CapControls.Delay()),delay_off_seconds=float(e.CapControls.DelayOff()),
                deadtime_seconds=float(e.CapControls.DeadTime()),voltage_override=bool(e.CapControls.UseVoltOverride()),
                pt_phase=e.Properties.Value('PTPhase').upper(),enabled=bool(e.CktElement.Enabled()))
            expected = dict(name=ref['name'],capacitor=ref['capacitor'],monitor_element=ref['monitor_element'].lower(),
                monitor_terminal=1,mode=1,ptratio=ref['ptratio'],onsetting=120.*ref['on_pu'],
                offsetting=120.*ref['off_pu'],delay_on_seconds=ref['delay_on_seconds'],
                delay_off_seconds=ref['delay_off_seconds'],deadtime_seconds=ref['deadtime_seconds'],
                voltage_override=False,pt_phase=ref['pt_phase'],enabled=True)
            require(row == expected, 'CAP_NATIVE_CONTROLLER_PARAMETER_READBACK_DRIFT:'+ref['name'])
            result.append(row)
        return result

    def observe_at(self, absolute_seconds):
        require(math.isfinite(absolute_seconds) and absolute_seconds >= self.last_observed_seconds,
                'CAP_CHRONOLOGICAL_TIME_OBSERVATIONS_REQUIRED')
        devices = self.measure()['devices']
        controlled = {r['capacitor']:r for r in self.contract['devices']}
        for row in devices:
            name, state = row['name'], row['states'][0]
            previous = self.last_state[name]
            if state != previous:
                require(name in controlled, 'CAP_UNCONTROLLED_FIXED_ON_SWITCHED')
                elapsed = absolute_seconds-self.state_since_seconds[name]
                minimum = controlled[name]['minimum_on_seconds' if previous else 'minimum_off_seconds']
                event = dict(capacitor=name,absolute_seconds=absolute_seconds,previous_state=previous,
                             state=state,previous_state_hold_seconds=elapsed,minimum_hold_seconds=minimum,
                             physical_step_kvar=row['kvar'],minimum_hold_PASS=elapsed >= minimum)
                self.transitions.append(event)
                if not event['minimum_hold_PASS']: self.minimum_hold_violations.append(event)
                self.last_state[name] = state
                self.state_since_seconds[name] = absolute_seconds
                self.switch_counts[name] += 1
        self.last_observed_seconds = absolute_seconds
        return self.measure()

    def measure(self):
        controls = self._controls()
        devices = []
        controlled = {r['capacitor']:r for r in self.contract['devices']}
        for reference in self.original_physical:
            row = _physical(self.engine,reference['name'])
            require({k:v for k,v in row.items() if k != 'states'} ==
                    {k:v for k,v in reference.items() if k != 'states'} and row['states'] in ([0],[1]),
                    'CAP_PHYSICAL_RATING_CONNECTION_OR_SINGLE_STEP_DRIFT')
            if row['name'] not in controlled:
                require(row['states'] == [1], 'CAP_UNCONTROLLED_FIXED_ON_CHANGED')
            self.engine.Circuit.SetActiveBus(row['bus'].split('.')[0])
            nodes = list(self.engine.Bus.Nodes())
            magnitudes = list(self.engine.Bus.VMagAngle())[::2]
            measured = {int(n):float(v) for n,v in zip(nodes,magnitudes) if n in (1,2,3)}
            if row['phases'] == 3:
                phase_volts = [measured[n] for n in (1,2,3)]
            else:
                phase_volts = [measured[int(row['bus'].split('.')[1])]]
            row.update(controlled=row['name'] in controlled,phase_voltages_ln_v=phase_volts,
                       cumulative_switch_count=self.switch_counts[row['name']])
            if row['name'] in controlled:
                ref = controlled[row['name']]
                row.update(measured_control_voltage_v=max(phase_volts)/ref['ptratio'],
                           measured_control_voltage_pu=max(phase_volts)/ref['nominal_primary_ln_v'])
            devices.append(row)
        return dict(schema='V42_NATIVE_CAPCONTROL_READBACK_V1',contract_SHA=self.contract['contract_SHA'],
                    variant=self.contract['variant'],devices=devices,native_controllers=controls,
                    cumulative_switch_count=sum(self.switch_counts.values()),transitions=copy.deepcopy(self.transitions),
                    minimum_hold_violations=copy.deepcopy(self.minimum_hold_violations),
                    observed_through_seconds=self.last_observed_seconds,
                    minimum_on_enforcement='native OFFDelay >= minimumON; no manual switch',
                    minimum_off_enforcement='native DeadTime; earliest close includes ONDelay',
                    manual_cap_or_tap_setters=0,PASS=not self.minimum_hold_violations)


def install(engine, contract, *, clock=None):
    return CapControlBank(engine,contract,clock)
