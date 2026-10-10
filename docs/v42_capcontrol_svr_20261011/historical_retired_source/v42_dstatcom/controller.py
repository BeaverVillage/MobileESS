"""Causal present-voltage feedback, bounded Q state and original regulator coordination."""
import hashlib
import json
import math
from .device import bus_voltages
from .settings import ControllerSettings

VERSION = 'V42_DSTATCOM_TAP_AWARE_CAUSAL_NETWORK_FEEDBACK_V3'


def droop_q(voltage_pu, phase_rating_kva, settings):
    """Q+ supplies the network; Q- absorbs. No look-ahead or optimization."""
    if not math.isfinite(voltage_pu) or voltage_pu<=0:
        raise ValueError('DSTATCOM_POSITIVE_FINITE_LOCAL_MEASUREMENT_REQUIRED')
    maximum=phase_rating_kva*settings.droop_saturation_fraction_of_phase_rating
    if voltage_pu<settings.deadband_lower_pu:
        utilization=min(1.,(settings.deadband_lower_pu-voltage_pu)/
            (settings.deadband_lower_pu-settings.supply_saturation_pu))
        return maximum*utilization
    if voltage_pu>settings.deadband_upper_pu:
        utilization=min(1.,(voltage_pu-settings.deadband_upper_pu)/
            (settings.absorb_saturation_pu-settings.deadband_upper_pu))
        return -maximum*utilization
    return 0.


def hysteretic_droop_q(voltage_pu,phase_rating_kva,settings,previous_mode,previous_applied_q):
    """Schmitt state uses the last limited command, never an integral request."""
    if type(previous_mode) is not int or previous_mode not in (-1,0,1) or not math.isfinite(previous_applied_q):
        raise ValueError('DSTATCOM_VALID_BOUNDED_CONTROLLER_STATE_REQUIRED')
    raw=droop_q(voltage_pu,phase_rating_kva,settings)
    mode=previous_mode;width=settings.hysteresis_release_width_pu
    if mode==1 and voltage_pu>=settings.deadband_lower_pu+width:mode=0
    if mode==-1 and voltage_pu<=settings.deadband_upper_pu-width:mode=0
    if mode==0:
        if voltage_pu<settings.deadband_lower_pu:mode=1
        elif voltage_pu>settings.deadband_upper_pu:mode=-1
    if mode==1:
        target=raw if voltage_pu<settings.deadband_lower_pu else max(0.,previous_applied_q)
    elif mode==-1:
        target=raw if voltage_pu>settings.deadband_upper_pu else min(0.,previous_applied_q)
    else:target=0.
    maximum=phase_rating_kva*settings.droop_saturation_fraction_of_phase_rating
    return max(-maximum,min(maximum,target)),mode


def original_control_state(engine):
    from v42_regcontrol import authority
    source=authority.source();inventory=source['inventory'](engine)
    authority.assert_inventory(inventory)
    taps,caps=source['native_state'](engine)
    return dict(regulator_names=[r['name'] for r in inventory['regulators']],
        all_7_RegControls_enabled=all(r['enabled'] for r in inventory['regulators']) and len(inventory['regulators'])==7,
        regulator_settings_SHA=authority.digest(authority.regulator_parameters(inventory)),
        regulator_taps=list(map(float,taps)),capacitor_states=list(map(int,caps)),
        CapControl_count=inventory['CapControl_count'], control_actions_done=bool(engine.Solution.ControlActionsDone()),
        solution_converged=bool(engine.Solution.Converged()),
        ControlIterations=int(engine.Solution.ControlIterations()),Solution_Iterations=int(engine.Solution.Iterations()),
        Solution_TotalIterations=int(engine.Solution.TotalIterations()),
        MostIterationsDone=int(engine.Solution.MostIterationsDone()),
        configured_MaxControlIterations=int(engine.Solution.MaxControlIterations()),
        configured_MaxIterations=int(engine.Solution.MaxIterations()),
        original_control_settings_changed=False,Planning_tap_replay=False)


class SupersededV2LocalVoltVarController:
    def __init__(self,devices,settings=None,*,source_SHA=None):
        self.devices=list(devices)
        self.settings=ControllerSettings.from_dict(settings) if isinstance(settings,dict) else settings or ControllerSettings()
        if not self.devices or len({d.spec.device_id for d in self.devices})!=len(self.devices):
            raise ValueError('DSTATCOM_NONEMPTY_UNIQUE_INSTALLED_SITE_SET_REQUIRED')
        if any(d.settings!=self.settings for d in self.devices):
            raise ValueError('DSTATCOM_COMMON_FROZEN_DEVICE_AND_CONTROLLER_SETTINGS_REQUIRED')
        if self.settings.feedback_step_seconds*self.settings.maximum_feedback_iterations>900:
            raise ValueError('DSTATCOM_FEEDBACK_DURATION_MUST_FIT_15_MINUTE_SLOT')
        self.source_SHA=source_SHA;self.slot_records=[]
        self.phase_modes={d.spec.device_id:[1 if q>0 else -1 if q<0 else 0 for q in d.q_state] for d in self.devices}

    def _targets(self,device):
        v=bus_voltages(device.engine,device.spec.pcc_bus,device.spec.phases,device.spec.nominal_kv_ln)
        converter_v=bus_voltages(device.engine,device.converter_bus,device.spec.phases,device.spec.nominal_kv_ln)
        modes=self.phase_modes[device.spec.device_id]
        evaluated=[hysteretic_droop_q(value,device.phase_rating_kva,self.settings,mode,q)
            for value,mode,q in zip(v,modes,device.q_state)]
        raw=[pair[0] for pair in evaluated]
        self.phase_modes[device.spec.device_id]=[pair[1] for pair in evaluated]
        targets=[max(-device._capacity(value),min(device._capacity(value),q)) for value,q in zip(converter_v,raw)]
        return v,converter_v,targets

    def settle_slot(self,engine,slot):
        if type(slot) is not int or not 0<=slot<96 or slot!=len(self.slot_records):
            raise ValueError('DSTATCOM_ONE_SEQUENTIAL_96_SLOT_ACTUAL_TRAJECTORY_REQUIRED')
        if any(d.engine is not engine for d in self.devices):
            raise ValueError('DSTATCOM_ISOLATED_ORIGINAL_ENGINE_IDENTITY_REQUIRED')
        initial=original_control_state(engine)
        if not initial['solution_converged'] or not initial['control_actions_done']:
            raise ValueError('DSTATCOM_ORIGINAL_SLOT_AC_OR_CONTROL_NONCONVERGENCE')
        initial_q={d.spec.device_id:list(d.q_state) for d in self.devices}
        initial_modes={key:list(value) for key,value in self.phase_modes.items()}
        trace=[];stable=0;converged=False;cycle_repeats=0;reason='MAXIMUM_LOCAL_FEEDBACK_ITERATIONS'
        settings=self.settings
        for iteration in range(settings.maximum_feedback_iterations):
            prior_voltages=[];applied=[]
            for device in self.devices:
                volts,converter_volts,targets=self._targets(device);prior_voltages.extend(volts)
                requested=[old+settings.damping*(target-old) for old,target in zip(device.q_state,targets)]
                applied.append(dict(site_id=device.spec.site_id,endpoint_id=device.spec.endpoint_id,device_id=device.spec.device_id,
                    hysteresis_phase_modes=list(self.phase_modes[device.spec.device_id]),
                    **device.apply_q(requested,converter_volts,settings.feedback_step_seconds)))
            engine.Solution.SolveSnap()
            state=original_control_state(engine)
            if not state['solution_converged'] or not state['control_actions_done']:
                raise ValueError('DSTATCOM_FEEDBACK_AC_OR_ORIGINAL_CONTROL_NONCONVERGENCE')
            if state['regulator_settings_SHA']!=initial['regulator_settings_SHA'] or state['capacitor_states']!=[1,1,1,1]:
                raise ValueError('DSTATCOM_ORIGINAL_REGULATOR_OR_FIXED_CAPACITOR_MUTATION')
            final_voltages=[];q_residual=0.;q_vector=[]
            for device in self.devices:
                volts,converter_volts,targets=self._targets(device);final_voltages.extend(volts);q_vector.extend(device.q_state)
                q_residual=max(q_residual,max(abs(a-b) for a,b in zip(device.q_state,targets)))
            v_change=max(abs(a-b) for a,b in zip(prior_voltages,final_voltages))
            current=dict(iteration=iteration+1,simulated_feedback_elapsed_seconds=(iteration+1)*settings.feedback_step_seconds,
                applied=applied,voltages_pu=final_voltages,Q_supply_kvar=q_vector,
                maximum_Q_fixed_point_residual_kvar=q_residual,maximum_voltage_step_pu=v_change,
                original_controls=state)
            trace.append(current)
            stable=stable+1 if q_residual<=settings.q_convergence_kvar and v_change<=settings.voltage_convergence_pu else 0
            if stable>=settings.stable_iterations_required:
                converged=True;reason='LOCAL_PHASE_DROOP_FIXED_POINT';break
            if len(trace)>=6:
                repeated=max(abs(a-b) for a,b in zip(q_vector,trace[-3]['Q_supply_kvar']))<=settings.q_convergence_kvar
                moving=max(abs(a-b) for a,b in zip(q_vector,trace[-2]['Q_supply_kvar']))>2*settings.q_convergence_kvar
                cycle_repeats=cycle_repeats+1 if repeated and moving else 0
                if cycle_repeats>=3:
                    reason='LOCAL_CONTROLLER_OSCILLATION_DETECTED';break
        hardware=[device.measure() for device in self.devices]
        final=original_control_state(engine)
        result=dict(version=VERSION,slot=slot,source_SHA=self.source_SHA,
            PASS=converged and all(device['PASS'] for device in hardware),controller_converged=converged,
            convergence_reason=reason,ControlActionsDone=final['control_actions_done'],
            solution_converged=final['solution_converged'],iterations=len(trace),
            additional_feedback_solve_count=len(trace),total_physical_solve_count=1+len(trace),
            original_logical_slot_solve_count=1,simulated_feedback_elapsed_seconds=len(trace)*settings.feedback_step_seconds,
            initial_original_controls=initial,final_original_controls=final,initial_Q_state_by_device=initial_q,
            initial_controller_modes_by_device=initial_modes,
            final_controller_modes_by_device={key:list(value) for key,value in self.phase_modes.items()},
            original_7_RegControls_settings_SHA=initial['regulator_settings_SHA'],
            original_controls_preserved=initial['regulator_settings_SHA']==final['regulator_settings_SHA'],
            regulator_taps=final['regulator_taps'],capacitor_states=final['capacitor_states'],
            maximum_Q_fixed_point_residual_kvar=trace[-1]['maximum_Q_fixed_point_residual_kvar'],
            maximum_voltage_step_pu=trace[-1]['maximum_voltage_step_pu'],
            saturation_present=any(any(command['Q_saturated']) or any(command['at_Q_capacity']) for row in trace for command in row['applied']),
            final_devices=hardware,iteration_trace=trace,settings=settings.to_dict(),
            controller_has_no_future_input=True,Native_optimizer_calls=0,MESS_PQ_repair_calls=0,
            anti_windup='TRACK_LIMITED_APPLIED_COMMAND_NO_UNSATURATED_INTEGRAL_STATE',
            integral_accumulator_present=False,hysteresis_enabled=True,
            MESS_PCS_capacity_shared=False,original_MESS_AIDC_plan_changed=False)
        self.slot_records.append(result)
        return result


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def network_observation(engine,settings):
    """Read all energized phases and every line/TX terminal; never solve or tune."""
    from .device import _element
    names=list(map(str,engine.Circuit.AllNodeNames()))
    magnitudes=list(map(float,engine.Circuit.AllBusMagPu()))
    if len(names)!=len(magnitudes):raise ValueError('DSTATCOM_COMPLETE_NETWORK_VOLTAGE_AXIS_REQUIRED')
    voltages={name.lower():v for name,v in zip(names,magnitudes) if int(name.rsplit('.',1)[1]) in (1,2,3)}
    if not voltages or any(not math.isfinite(v) or v<=0 for v in voltages.values()):
        raise ValueError('DSTATCOM_FINITE_ENERGIZED_FULLNETWORK_PHASES_REQUIRED')
    thermal={};ratings={};adjacency={}
    for name in engine.Circuit.AllElementNames():
        lower=name.lower()
        if not lower.startswith(('line.','transformer.')):continue
        element=_element(engine,name);n=element['conductors'];nph=element['phases']
        buses=[bus.split('.')[0].lower() for bus in element['buses']]
        for a in buses:
            adjacency.setdefault(a,set()).update(b for b in buses if b!=a)
        if lower.startswith('line.'):
            rating=element['normal_amps']
            if not math.isfinite(rating) or rating<=0:raise ValueError('DSTATCOM_FINITE_ORIGINAL_LINE_RATING_REQUIRED')
            ratings[lower]=dict(normal_amps=rating)
            for t in range(element['terminals']):
                for j in range(n):
                    position=t*n+j;phase=element['nodes'][position]
                    if phase not in (1,2,3):continue
                    current=abs(complex(*element['currents'][2*position:2*position+2]))
                    thermal[f'{lower}/terminal{t+1}/phase{phase}/current']=current/rating
        else:
            engine.Transformers.Name(name.split('.',1)[1]);windings=[]
            for t in range(element['terminals']):
                engine.Transformers.Wdg(t+1);kva=float(engine.Transformers.kVA());kv=float(engine.Transformers.kV())
                if not math.isfinite(kva+kv) or kva<=0 or kv<=0:
                    raise ValueError('DSTATCOM_FINITE_TRANSFORMER_WINDING_RATING_REQUIRED')
                amps=kva/(math.sqrt(3)*kv) if nph>1 else kva/kv
                if t==0:amps=min(amps,element['normal_amps'])
                windings.append(dict(kva=kva,kv=kv,phase_current_a=amps))
                powers=[]
                for j in range(n):
                    position=t*n+j;phase=element['nodes'][position]
                    if phase not in (1,2,3):continue
                    current=abs(complex(*element['currents'][2*position:2*position+2]))
                    power=complex(*element['powers'][2*position:2*position+2]);powers.append(power)
                    thermal[f'{lower}/winding{t+1}/phase{phase}/current']=current/amps
                    thermal[f'{lower}/winding{t+1}/phase{phase}/kva']=abs(power)/(kva/nph)
                thermal[f'{lower}/winding{t+1}/total_kva']=abs(sum(powers))/kva
            ratings[lower]=dict(windings=windings,normal_amps=element['normal_amps'])
    if any(not math.isfinite(value) or value<0 for value in thermal.values()):
        raise ValueError('DSTATCOM_FINITE_FULLNETWORK_CURRENT_AND_KVA_REQUIRED')
    low,high=settings.actual_voltage_min_pu,settings.actual_voltage_max_pu
    vexcess={k:max(low-v,v-high,0.) for k,v in voltages.items()}
    texcess={k:max(v-1.,0.) for k,v in thermal.items()}
    worst=max(vexcess,key=vexcess.get)
    merit=sum(v*v for v in vexcess.values())+.05**2*sum(v*v for v in texcess.values())
    summary=dict(voltage_phase_count=len(voltages),voltage_violation_count=sum(v>0 for v in vexcess.values()),
        minimum_voltage_pu=min(voltages.values()),maximum_voltage_pu=max(voltages.values()),
        worst_voltage_node=worst,worst_voltage_pu=voltages[worst],maximum_voltage_exceedance_pu=vexcess[worst],
        thermal_cell_count=len(thermal),thermal_violation_count=sum(v>0 for v in texcess.values()),
        maximum_thermal_utilization=max(thermal.values(),default=0.),hard_constraint_merit=merit,
        maximum_line_current_utilization=max((v for k,v in thermal.items() if k.startswith('line.')),default=0.),
        maximum_transformer_phase_current_utilization=max((v for k,v in thermal.items() if k.startswith('transformer.') and k.endswith('/current')),default=0.),
        maximum_transformer_phase_kva_utilization=max((v for k,v in thermal.items() if k.startswith('transformer.') and k.endswith('/kva')),default=0.),
        maximum_transformer_total_kva_utilization=max((v for k,v in thermal.items() if k.startswith('transformer.') and k.endswith('/total_kva')),default=0.),
        PASS=all(v==0 for v in vexcess.values()) and all(v==0 for v in texcess.values()),
        voltage_band_unchanged=[low,high],all_original_and_added_nodes_included=True,
        all_original_and_added_line_terminals_and_transformer_windings_included=True)
    return dict(voltages=voltages,thermal=thermal,voltage_excess=vexcess,thermal_excess=texcess,
        ratings_SHA=_digest(ratings),observation_SHA=_digest(dict(voltages=voltages,thermal=thermal)),
        adjacency={k:sorted(v) for k,v in adjacency.items()},summary=summary)


def _step_is_safe(before,after,settings):
    """No new failed phase/current cell is accepted while repairing the old ones."""
    new_v=[key for key,value in after['voltage_excess'].items()
        if value>0 and before['voltage_excess'].get(key,0.)==0]
    new_t=[key for key,value in after['thermal_excess'].items()
        if value>0 and before['thermal_excess'].get(key,0.)==0]
    improved=after['summary'].get('controller_hysteresis_safe',after['summary']['PASS']) or after['summary'].get('control_merit',after['summary']['hard_constraint_merit'])<(
        before['summary'].get('control_merit',before['summary']['hard_constraint_merit'])*(1-settings.network_feedback_relative_improvement))
    initial_envelope=before.get('initial_slot_exceedance_envelope_pu',before['summary']['maximum_voltage_exceedance_pu'])
    before_peak=before['summary']['maximum_voltage_exceedance_pu'];after_peak=after['summary']['maximum_voltage_exceedance_pu']
    recovering=before_peak>initial_envelope
    bounded=after_peak<before_peak if recovering else after_peak<=initial_envelope
    safe=not new_v and not new_t and improved and after['summary'].get('all_converter_current_kva_and_sign_PASS',True) and bounded
    return dict(accepted=bool(safe),hard_merit_improved=bool(improved),
        newly_failed_voltage_nodes=new_v,newly_failed_thermal_cells=new_t,
        initial_slot_exceedance_envelope_pu=initial_envelope,
        recovery_after_irreversible_automatic_control_history=recovering,
        bounded_peak_or_strict_recovery=bool(bounded))


class LocalVoltVarController:
    """Bounded causal coordinate feedback using only present automatic AC results.

    One finite phase Q trial is applied at a time. Full-network electrical
    measurements and exact original regulator sensors decide whether to retain
    it. Failed trials restore Q only; automatic regulator history is retained.
    This is feedback, with no free-Q OPF, future trajectory or tap manipulation.
    """
    def __init__(self,devices,settings=None,*,source_SHA=None):
        self.devices=list(devices)
        self.settings=ControllerSettings.from_dict(settings) if isinstance(settings,dict) else settings or ControllerSettings()
        if not self.devices or len({d.spec.device_id for d in self.devices})!=len(self.devices):
            raise ValueError('DSTATCOM_NONEMPTY_UNIQUE_INSTALLED_SITE_SET_REQUIRED')
        if any(d.settings!=self.settings for d in self.devices):
            raise ValueError('DSTATCOM_COMMON_FROZEN_DEVICE_AND_CONTROLLER_SETTINGS_REQUIRED')
        if self.settings.feedback_step_seconds*self.settings.maximum_feedback_iterations>900:
            raise ValueError('DSTATCOM_FEEDBACK_DURATION_MUST_FIT_15_MINUTE_SLOT')
        self.source_SHA=source_SHA;self.slot_records=[];self.response_columns={};self.ratings_SHA=None;self.voltage_latches={}
        self.slot_voltage_exceedance_envelope=None
        self.phase_modes={d.spec.device_id:[1 if q>0 else -1 if q<0 else 0 for q in d.q_state] for d in self.devices}

    def _observe(self,engine,initial):
        from . import regcontrol
        state=original_control_state(engine)
        if not state['solution_converged'] or not state['control_actions_done']:
            raise ValueError('DSTATCOM_FEEDBACK_AC_OR_ORIGINAL_CONTROL_NONCONVERGENCE')
        if (state['regulator_settings_SHA']!=initial['regulator_settings_SHA']
                or not state['all_7_RegControls_enabled'] or state['capacitor_states']!=[1,1,1,1]):
            raise ValueError('DSTATCOM_ORIGINAL_REGULATOR_OR_FIXED_CAPACITOR_MUTATION')
        network=network_observation(engine,self.settings)
        if self.slot_voltage_exceedance_envelope is None:
            self.slot_voltage_exceedance_envelope=network['summary']['maximum_voltage_exceedance_pu']
        network['initial_slot_exceedance_envelope_pu']=self.slot_voltage_exceedance_envelope
        # Schmitt repair state is activated by a real hard-limit violation,
        # then released a small distance inside the unchanged hard band.
        # Healthy PCCs are never all driven toward a common low target.
        controls={};width=self.settings.hysteresis_release_width_pu
        for node,v in network['voltages'].items():
            mode=self.voltage_latches.get(node,0)
            if v>self.settings.actual_voltage_max_pu:mode=-1
            elif v<self.settings.actual_voltage_min_pu:mode=1
            elif mode==-1 and v<=self.settings.actual_voltage_max_pu-width:mode=0
            elif mode==1 and v>=self.settings.actual_voltage_min_pu+width:mode=0
            self.voltage_latches[node]=mode
            controls[node]=(max(v-(self.settings.actual_voltage_max_pu-width),0.) if mode==-1 else
                max(self.settings.actual_voltage_min_pu+width-v,0.) if mode==1 else 0.)
        network['control_excess']=controls
        network['summary']['active_voltage_hysteresis_count']=sum(v!=0 for v in self.voltage_latches.values())
        network['summary']['control_merit']=sum(v*v for v in controls.values())+.05**2*sum(v*v for v in network['thermal_excess'].values())
        network['summary']['controller_hysteresis_safe']=network['summary']['PASS'] and not any(self.voltage_latches.values())
        if self.ratings_SHA is None:self.ratings_SHA=network['ratings_SHA']
        if network['ratings_SHA']!=self.ratings_SHA:raise ValueError('DSTATCOM_ORIGINAL_OR_ADDED_HARDWARE_RATING_MUTATION')
        # Each actual trial must expose converter current/apparent power too,
        # rather than relying on the larger coupling-transformer rating.
        hardware=[d.measure() for d in self.devices]
        converter_checks={row['device_id']:dict(
            maximum_phase_current_utilization=max(p['converter_current_utilization'] for p in row['phases']),
            maximum_phase_kva_utilization=max(p['converter_kva_utilization'] for p in row['phases']),
            total_kva_utilization=row['total_converter_apparent_kva']/row['converter_nameplate_kva'],
            finite_added_nameplates_unchanged=all(p['checks']['converter_nameplate_kva_unchanged']
                and p['checks']['coupling_nameplate_and_normalamps_unchanged']
                and p['checks']['dedicated_lead_nameplate_unchanged'] for p in row['phases']),
            Q_P_sign_and_constant_power_readback=all(p['checks']['Q_P_sign_and_constant_power_readback'] for p in row['phases']))
            for row in hardware}
        converter_pass=all(max(r['maximum_phase_current_utilization'],r['maximum_phase_kva_utilization'],r['total_kva_utilization'])<=1
            and r['Q_P_sign_and_constant_power_readback'] and r['finite_added_nameplates_unchanged'] for r in converter_checks.values())
        network['summary']['all_converter_current_kva_and_sign_PASS']=converter_pass
        network['summary']['maximum_converter_phase_current_utilization']=max(r['maximum_phase_current_utilization'] for r in converter_checks.values())
        network['summary']['maximum_converter_phase_kva_utilization']=max(r['maximum_phase_kva_utilization'] for r in converter_checks.values())
        network['summary']['maximum_converter_total_kva_utilization']=max(r['total_kva_utilization'] for r in converter_checks.values())
        network['summary']['PASS']=network['summary']['PASS'] and converter_pass
        network['summary']['controller_hysteresis_safe']=network['summary']['controller_hysteresis_safe'] and converter_pass
        return dict(network=network,controls=state,regulators=regcontrol.snapshot(engine,source_SHA=self.source_SHA),
            hardware=hardware,converter_checks=converter_checks)

    @staticmethod
    def _distance(graph,start,end):
        visited={start};front=[start]
        for distance in range(len(graph)+1):
            if end in front:return distance
            front=[n for node in front for n in graph.get(node,[]) if n not in visited]
            visited.update(front)
            if not front:break
        return len(graph)+1

    def _prediction(self,before,key,step):
        from . import regcontrol
        column=self.response_columns.get(key);predicted=None
        same_taps=column and all(abs(r['tap']-column['reference_after_taps'][r['name']])<1e-12
            for r in before['regulators']['regulators'])
        if column and column['no_observed_tap_changes'] and same_taps:
            predicted={}
            for row in before['regulators']['regulators']:
                response=column['winding_response'].get(row['name'])
                if not response:continue
                projected={}
                for field in (regcontrol.VOLTAGES,regcontrol.CURRENTS):
                    projected[field]=[[a+step*da,b+step*db] for (a,b),(da,db) in zip(row[field],response[field])]
                predicted[row['name']]=projected
        result=regcontrol.predict_tap_response(before['regulators'],predicted_winding_state=predicted)
        result['candidate_Q_step_kvar']=step
        result['observed_response_column_available']=column is not None
        result['response_column_basis']=None if column is None else column['basis']
        result['candidate_projection_is_conditional']=predicted is not None
        result['response_column_tap_operating_point_matches']=bool(same_taps)
        return result

    def _candidates(self,before,attempted):
        network=before['network'];summary=network['summary'];settings=self.settings
        worst=max(network['control_excess'],key=network['control_excess'].get)
        bus,phase_text=worst.rsplit('.',1);phase=int(phase_text)
        voltage=network['voltages'][worst];over=voltage>settings.actual_voltage_max_pu
        if self.voltage_latches.get(worst)==-1:over=True
        thermal_only=not any(network['control_excess'].values()) and summary['thermal_violation_count']>0
        worst_thermal=max(network['thermal_excess'],key=network['thermal_excess'].get) if thermal_only else None
        target=(settings.actual_voltage_max_pu-settings.network_feedback_voltage_target_margin_pu if over
            else settings.actual_voltage_min_pu+settings.network_feedback_voltage_target_margin_pu)
        candidates=[]
        for device in self.devices:
            distance=self._distance(network['adjacency'],bus,device.spec.pcc_bus.lower())
            for index in range(3):
                key=(device.spec.device_id,index);column=self.response_columns.get(key)
                response=None if not column else (column['thermal_response'].get(worst_thermal) if thermal_only
                    else column['voltage_response'].get(worst))
                if response and abs(response)>1e-9:
                    error=(.98-network['thermal'][worst_thermal]) if thermal_only else target-voltage
                    step=max(-settings.network_feedback_max_step_kvar,min(settings.network_feedback_max_step_kvar,error/response))
                    score=(0,distance,0 if index+1==phase else 1)
                    choices=[step,-math.copysign(settings.network_feedback_probe_kvar,step)]
                else:
                    direction=-math.copysign(1.,device.q_state[index]) if thermal_only and device.q_state[index] else -1. if over else 1.
                    score=(1,distance,0 if index+1==phase else 1)
                    choices=[direction*settings.network_feedback_probe_kvar,-direction*settings.network_feedback_probe_kvar]
                for order,step in enumerate(choices):
                    direction=1 if step>0 else -1
                    count=attempted.get((key,direction),0)
                    step=math.copysign(max(settings.network_feedback_min_step_kvar,abs(step)/2**count),step)
                    if count>3:continue
                    prediction=self._prediction(before,key,step)
                    # A measured next-action prediction is a risk indicator,
                    # not a claim about the final automatic tap or AC safety.
                    raises=sum(r['action']=='RAISE' and r['state_basis']=='PREDICTED_WINDING_STATE'
                        for r in prediction['regulators']) if over else 0
                    predicted_penalty=0.
                    projected_worsens=0
                    if column and column['no_observed_tap_changes']:
                        projected={n:v+step*column['voltage_response'].get(n,0.) for n,v in network['voltages'].items()}
                        predicted_penalty=sum(max(settings.actual_voltage_min_pu-v,v-settings.actual_voltage_max_pu,0.)**2 for v in projected.values())
                        projected_worsens=int(predicted_penalty>network['summary']['hard_constraint_merit'])
                    # A known phase column that worsens the whole network must
                    # not indefinitely outrank a nearby unexplored phase.
                    candidates.append((projected_worsens,raises,score[1],score[2],score[0],order,count,predicted_penalty,device,index,step,prediction))
        candidates.sort(key=lambda row:row[:-4])
        return candidates

    def _learn(self,before,after,key,step):
        from . import regcontrol
        pre={r['name']:r for r in before['regulators']['regulators']};post={r['name']:r for r in after['regulators']['regulators']}
        winding={};changes={}
        for name,row in pre.items():
            changes[name]=post[name]['tap']-row['tap']
            winding[name]={field:[[(b[0]-a[0])/step,(b[1]-a[1])/step] for a,b in zip(row[field],post[name][field])]
                for field in (regcontrol.VOLTAGES,regcontrol.CURRENTS)}
        self.response_columns[key]=dict(basis='CAUSALLY_OBSERVED_FULL_ORIGINAL_AUTOMATIC_SOLVESNAP_Q_STEP',
            voltage_response={n:(after['network']['voltages'][n]-v)/step for n,v in before['network']['voltages'].items()},
            winding_response=winding,no_observed_tap_changes=all(abs(v)<1e-12 for v in changes.values()),
            thermal_response={n:(after['network']['thermal'][n]-v)/step for n,v in before['network']['thermal'].items()},
            reference_after_taps={r['name']:r['tap'] for r in after['regulators']['regulators']},
            observed_tap_changes=changes,observed_Q_step_kvar=step,
            operating_point_observation_SHA=before['network']['observation_SHA'])
        return changes

    def _solve_record(self,engine,before,initial,trace,kind,*,action=None,prediction=None):
        engine.Solution.SolveSnap()
        after=self._observe(engine,initial)
        pre={r['name']:r for r in before['regulators']['regulators']}
        changes={r['name']:r['tap']-pre[r['name']]['tap'] for r in after['regulators']['regulators']}
        comparisons=[]
        if prediction:
            for row in prediction['regulators']:
                delta=changes[row['name']]
                comparisons.append(dict(name=row['name'],predicted_next_action=row['action'],
                    measured_complete_SolveSnap_tap_change_pu=delta,
                    measured_complete_SolveSnap_direction='RAISE' if delta>1e-12 else 'LOWER' if delta< -1e-12 else 'NO_ACTION',
                    next_action_vs_final_tap_difference_pu=None if row.get('next_static_tap_change_pu') is None
                        else delta-row['next_static_tap_change_pu'],
                    final_tap_prediction_status='UNKNOWN_COMPLETE_NETWORK_CONTROL_RESAMPLING_NOT_PREDICTED'))
        from . import regcontrol
        limited=regcontrol.compare_settled_taps(prediction,after['regulators']) if prediction else None
        sensor_errors=[]
        if prediction:
            post={r['name']:r for r in after['regulators']['regulators']}
            for row in prediction['regulators']:
                if row.get('sensor') is not None and post[row['name']].get('sensor') is not None:
                    expected=row['sensor']['compensated_voltage_V'];measured=post[row['name']]['sensor']['compensated_voltage_V']
                    sensor_errors.append(dict(name=row['name'],state_basis=row['state_basis'],
                        predicted_compensated_voltage_V=expected,measured_after_automatic_compensated_voltage_V=measured,
                        prediction_error_V=measured-expected))
        queue=[]
        for reg in before['regulators']['regulators']:
            steps=abs(changes[reg['name']])/reg['tap_increment'] if reg['tap_increment'] else None
            delay=float(reg['properties']['Delay']);tapdelay=float(reg['properties']['TapDelay'])
            queue.append(dict(name=reg['name'],original_Delay_queue_seconds=delay,original_TapDelay_queue_seconds=tapdelay,
                observed_net_tap_increments=steps,net_tap_change_based_delay_indicator_seconds=delay+tapdelay*steps if steps else 0.,
                is_physical_elapsed_time_or_rigorous_upper_bound=False))
        change=max(abs(after['network']['voltages'][n]-v) for n,v in before['network']['voltages'].items())
        compact_prediction=None
        if prediction:
            compact_prediction={k:v for k,v in prediction.items() if k not in ('primary_sources','regulators')}
            compact_prediction['regulators']=[{**{k:v for k,v in r.items() if k not in ('sensor','unknown_reasons')},
                'unknown_reasons':r.get('unknown_reasons',[]),
                'sensor':None if r.get('sensor') is None else {k:r['sensor'][k] for k in (
                    'selected_phase_1based','compensated_voltage_V','lower_deadband_margin_V','upper_deadband_margin_V')}}
                for r in prediction['regulators']]
        row=dict(iteration=len(trace)+1,kind=kind,action=action,
            original_automatic_SolveSnap=True,Q_only_rollback=kind=='Q_ONLY_ROLLBACK',tap_setter_calls=0,
            network=after['network']['summary'],network_observation_SHA=after['network']['observation_SHA'],
            converter_current_kva_and_sign=after['converter_checks'],
            maximum_voltage_step_pu=change,regulator_tap_changes=changes,
            regulator_prediction_before_solve=compact_prediction,regulator_prediction_vs_final=comparisons,
            LIMITED_next_action_vs_settled_tap_comparison=limited,regulator_sensor_prediction_errors=sensor_errors,
            original_regulator_queue_delay_indicators=queue,
            physical_timing_compliance='UNKNOWN_STATIC_ELECTRICAL_SEQUENCE_NOT_REAL_TIME_VALIDATED',
            original_controls=after['controls'])
        trace.append(row)
        return after

    def settle_slot(self,engine,slot):
        if type(slot) is not int or not 0<=slot<96 or slot!=len(self.slot_records):
            raise ValueError('DSTATCOM_ONE_SEQUENTIAL_96_SLOT_ACTUAL_TRAJECTORY_REQUIRED')
        if any(d.engine is not engine for d in self.devices):raise ValueError('DSTATCOM_ISOLATED_ORIGINAL_ENGINE_IDENTITY_REQUIRED')
        initial=original_control_state(engine)
        if not initial['solution_converged'] or not initial['control_actions_done']:
            raise ValueError('DSTATCOM_ORIGINAL_SLOT_AC_OR_CONTROL_NONCONVERGENCE')
        initial_q={d.spec.device_id:list(d.q_state) for d in self.devices};initial_modes={k:list(v) for k,v in self.phase_modes.items()}
        self.slot_voltage_exceedance_envelope=None
        current=self._observe(engine,initial);initial_network=current['network']['summary'];trace=[];attempted={}
        settings=self.settings;stable=0;converged=False;reason='MAXIMUM_TAP_AWARE_NETWORK_FEEDBACK_ITERATIONS'
        accepted=0;rejected=0;stalled=0
        while len(trace)<settings.maximum_feedback_iterations:
            if current['network']['summary']['controller_hysteresis_safe']:
                after=self._solve_record(engine,current,initial,trace,'UNCHANGED_Q_SCHMITT_HOLD_CONFIRMATION',
                    prediction=self._prediction(current,None,0.))
                stable=stable+1 if after['network']['summary']['controller_hysteresis_safe'] and trace[-1]['maximum_voltage_step_pu']<=settings.voltage_convergence_pu else 0
                current=after
                if stable>=settings.stable_iterations_required:
                    converged=True;reason='FULLNETWORK_SAFE_AUTOMATIC_CONTROL_HYSTERESIS_HOLD';break
                continue
            stable=0
            # Leave room for the mandatory Q-only rollback and AUTO re-solve.
            if len(trace)+2>settings.maximum_feedback_iterations:
                self._solve_record(engine,current,initial,trace,'ITERATION_LIMIT_OBSERVATION',prediction=self._prediction(current,None,0.));break
            candidates=self._candidates(current,attempted)
            if not candidates:reason='FINITE_SAFE_Q_ACTIONS_EXHAUSTED';break
            chosen=candidates[0];device,index,step,prediction=chosen[-4:];key=(device.spec.device_id,index)
            old=list(device.q_state);requested=list(old);requested[index]+=step
            limit=device.apply_q(requested,dt_seconds=settings.feedback_step_seconds);actual_step=device.q_state[index]-old[index]
            attempted[(key,1 if step>0 else -1)]=attempted.get((key,1 if step>0 else -1),0)+1
            if abs(actual_step)<1e-10:
                stalled+=1
                if stalled>len(self.devices)*6:reason='ALL_FINITE_Q_ACTIONS_AT_PHYSICAL_CAPACITY';break
                continue
            before=current
            action=dict(device_id=device.spec.device_id,phase=index+1,requested_step_kvar=step,
                applied_step_kvar=actual_step,applied=limit)
            # Recalculate using actual limited step before the real AUTO solve.
            prediction=self._prediction(before,key,actual_step)
            after=self._solve_record(engine,before,initial,trace,'CAUSAL_Q_TRIAL',action=action,prediction=prediction)
            tap_changes=self._learn(before,after,key,actual_step)
            safety=_step_is_safe(before['network'],after['network'],settings);trace[-1]['safety']=safety
            trace[-1]['learned_response_tap_changes']=tap_changes
            if safety['accepted']:
                accepted+=1;current=after;attempted={};stalled=0
            else:
                rejected+=1;restore=device.apply_q(old,dt_seconds=settings.feedback_step_seconds)
                current=self._solve_record(engine,after,initial,trace,'Q_ONLY_ROLLBACK',
                    action=dict(device_id=device.spec.device_id,phase=index+1,restored_requested_Q_kvar=old,applied=restore),
                    prediction=self._prediction(after,key,device.q_state[index]-(old[index]+actual_step)))
                trace[-1]['tap_history_restored']=False
                trace[-1]['rollback_network_equals_pretrial']=current['network']['observation_SHA']==before['network']['observation_SHA']
                trace[-1]['path_dependence_observed']=any(abs(r)>1e-12 for r in trace[-1]['regulator_tap_changes'].values()) or not trace[-1]['rollback_network_equals_pretrial']
        hardware=current['hardware'];final=current['controls']
        self.phase_modes={d.spec.device_id:[1 if q>0 else -1 if q<0 else 0 for q in d.q_state] for d in self.devices}
        result=dict(version=VERSION,slot=slot,source_SHA=self.source_SHA,
            PASS=converged and current['network']['summary']['PASS'] and all(d['PASS'] for d in hardware),
            controller_converged=converged,convergence_reason=reason,ControlActionsDone=final['control_actions_done'],
            solution_converged=final['solution_converged'],iterations=len(trace),
            additional_feedback_solve_count=len(trace),total_physical_solve_count=1+len(trace),original_logical_slot_solve_count=1,
            computational_AC_trial_count=len(trace),simulated_feedback_elapsed_seconds=None,
            converter_command_time_seconds=sum(row['kind'] in ('CAUSAL_Q_TRIAL','Q_ONLY_ROLLBACK') for row in trace)*settings.feedback_step_seconds,
            converter_command_time_is_regulator_elapsed_time=False,
            physical_timing_compliance='UNKNOWN_STATIC_ELECTRICAL_SEQUENCE_NOT_REAL_TIME_VALIDATED',
            regulator_physical_elapsed_time_validated=False,STATIC_queue_delay_not_physical_feedback_seconds=True,
            initial_original_controls=initial,final_original_controls=final,initial_Q_state_by_device=initial_q,
            initial_controller_modes_by_device=initial_modes,final_controller_modes_by_device=self.phase_modes,
            original_7_RegControls_settings_SHA=initial['regulator_settings_SHA'],original_controls_preserved=True,
            regulator_taps=final['regulator_taps'],capacitor_states=final['capacitor_states'],
            maximum_voltage_step_pu=trace[-1]['maximum_voltage_step_pu'] if trace else 0.,
            maximum_Q_fixed_point_residual_kvar=None,saturation_present=any(any(d.last_limit_receipt['Q_saturated']) for d in self.devices if d.last_limit_receipt),
            initial_fullnetwork=initial_network,final_fullnetwork=current['network']['summary'],
            final_fullnetwork_voltage_pu=current['network']['voltages'],final_fullnetwork_thermal_utilization=current['network']['thermal'],
            final_regulator_sensors=current['regulators'],accepted_Q_trials=accepted,rejected_Q_trials=rejected,
            final_devices=hardware,iteration_trace=trace,settings=settings.to_dict(),
            controller_has_no_future_input=True,Native_optimizer_calls=0,MESS_PQ_repair_calls=0,
            anti_windup='TRACK_LIMITED_APPLIED_COMMAND_NO_UNSATURATED_INTEGRAL_STATE',integral_accumulator_present=False,
            hysteresis_enabled=True,hysteresis_semantics='HOLD_ACTUAL_LIMITED_Q_WHILE_FULLNETWORK_SAFE; REENTER_ON_PRESENT_NETWORK_VIOLATION',
            superseded_V2_local_gain_law_executed=False,global_Actual_OPF_or_MILP_calls=0,
            tap_setter_calls=0,disabled_original_regulator_calls=0,fixed_tap_powerflow_calls=0,
            MESS_PCS_capacity_shared=False,original_MESS_AIDC_plan_changed=False)
        self.slot_records.append(result)
        return result


Controller = LocalVoltVarController
