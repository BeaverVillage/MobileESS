"""Complete, axis-checked electrical tables; observation never issues a solve."""
from contextlib import contextmanager
import math
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import write_json
from .data import issue_time
from .persistence import table
from .reserve import require


def axis(day):
    return pd.date_range(issue_time(day) + pd.Timedelta(hours=6), periods=96, freq='15min')


def full_axis(frame, identifiers, expected, slots=96):
    expected = list(expected)
    require(len(frame) == len(expected)*slots and not frame.duplicated(['slot', *identifiers]).any(), 'INCOMPLETE_SCIENTIFIC_AXIS')
    expect = {tuple(x) for x in expected}
    for slot in range(slots):
        require(set(frame.loc[frame.slot == slot, identifiers].itertuples(index=False, name=None)) == expect,
                'MISSING_TOPOLOGY_OR_TIME_SLOT:' + str(slot))


@contextmanager
def observe():
    from dayahead.v28r2 import opendss_backend as backend
    previous_v, previous_b = backend._voltage_vector, backend._branch_measurement
    rows = dict(voltage_angles=[], branch=[], system=[])
    def voltage(odd, nodes):
        result = previous_v(odd, nodes)
        names = tuple(str(n).lower() for n in odd.Circuit.AllNodeNames())
        z = np.asarray(odd.Circuit.AllBusVolts(), float).reshape(-1, 2)
        require(len(names) == len(z), 'OPENDSS_ANGLE_AXIS')
        angles = dict(zip(names, np.degrees(np.arctan2(z[:, 1], z[:, 0]))))
        rows['voltage_angles'].append([float(angles[n.lower()]) for n in nodes])
        rows['system'].append(list(map(float, odd.Circuit.TotalPower()[:2])))
        return result
    def branch(odd, b):
        result = previous_b(odd, b)
        # The inherited reader already selected the correct element/winding.
        # Reading its arrays does not change engine selections or state.
        conductors = int(odd.CktElement.NumConductors())
        buses = [str(x).split('.', 1)[0].lower() for x in odd.CktElement.BusNames()]
        terminal = buses.index(str(b.parent_bus).lower())
        nodes = list(map(int, odd.CktElement.NodeOrder()))
        local = next(i for i in range(conductors) if nodes[terminal*conductors+i] == 'ABC'.index(b.phase)+1)
        position = terminal*conductors+local
        powers = odd.CktElement.Powers()
        if b.branch_id.startswith('line.'):
            limit = float(odd.Lines.NormAmps())
        else:
            kva, kv = float(odd.Transformers.kVA()), float(odd.Transformers.kV())
            limit = kva / (math.sqrt(3)*kv) if odd.CktElement.NumPhases() >= 2 else kva/kv
        require(abs(result[1] - result[0]/limit) < 1e-12, 'OBSERVER_BRANCH_RATING_DRIFT')
        rows['branch'].append(dict(line_id=b.branch_id, from_bus=b.parent_bus, to_bus=b.child_bus,
            phase=b.phase, current_limit_A=limit, P_flow_kW=float(powers[2*position]), Q_flow_kvar=float(powers[2*position+1])))
        return result
    backend._voltage_vector, backend._branch_measurement = voltage, branch
    try:
        yield rows
    finally:
        backend._voltage_vector, backend._branch_measurement = previous_v, previous_b


def persist(output, day, policy, stage, result, observation, components_path):
    result.validate(); dates = axis(day); nodes = result.node_names; branches = result.branch_names
    n, b = len(nodes), len(branches)
    angle = np.asarray(observation['voltage_angles'], float)
    require(angle.shape == (96, n) and len(observation['branch']) == 96*b, 'GRID_OBSERVATION_COVERAGE')
    vf = pd.DataFrame(dict(target_day=day, policy=policy, stage=stage, slot=np.repeat(np.arange(96), n),
        timestamp=dates.repeat(n), bus=np.tile([x.rsplit('.', 1)[0] for x in nodes], 96),
        node=np.tile(nodes, 96), phase=np.tile(result.node_phases, 96), voltage_pu=result.voltage_pu.ravel(),
        voltage_angle_degrees=angle.ravel()))
    vf['voltage_lower_margin_pu'] = vf.voltage_pu-.95; vf['voltage_upper_margin_pu'] = 1.05-vf.voltage_pu
    vf['violation'] = (vf.voltage_pu < .95-1e-9) | (vf.voltage_pu > 1.05+1e-9)
    bf = pd.DataFrame(observation['branch'])
    require(bf.line_id.tolist() == list(branches)*96 and bf.phase.tolist() == list(result.branch_phases)*96,
            'GRID_BRANCH_OBSERVER_ORDER')
    bf['target_day'] = day; bf['policy'] = policy; bf['stage'] = stage
    bf['slot'] = np.repeat(np.arange(96), b); bf['timestamp'] = dates.repeat(b)
    bf['kind'] = np.tile(result.branch_kinds, 96)
    bf['current_A'] = result.phase_current_a.ravel(); bf['loading_pu'] = result.phase_current_loading_pu.ravel()
    bf['transformer_total_kVA_loading_pu'] = result.transformer_total_kva_loading_pu.ravel()
    bf['thermal_margin_A'] = bf.current_limit_A-bf.current_A; bf['violation'] = bf.loading_pu > 1+1e-9
    full_axis(vf, ['node', 'phase'], zip(nodes, result.node_phases))
    full_axis(bf, ['line_id', 'phase'], zip(branches, result.branch_phases))
    native = pd.read_parquet(components_path).sort_values('slot').reset_index(drop=True)
    require(native.slot.tolist() == list(range(96)), 'FEEDER_COMPONENT_SLOT_COVERAGE')
    sf = native.copy(); sf['timestamp'] = dates; sf['target_day'] = day; sf['policy'] = policy; sf['stage'] = stage
    total = np.asarray(observation['system'], float); require(total.shape == (96, 2), 'FEEDER_POWER_AXIS')
    # Keep the engine's native source-terminal sign, and explicitly record
    # import as its negative. Net component load and loss give an independent check.
    sf['OpenDSS_source_terminal_P_kW'] = total[:, 0]; sf['OpenDSS_source_terminal_Q_kvar'] = total[:, 1]
    sf['feeder_import_P_kW'] = -total[:, 0]; sf['feeder_import_Q_kvar'] = -total[:, 1]
    sf['loss_P_kW'] = result.losses_kw_kvar[:, 0]; sf['loss_Q_kvar'] = result.losses_kw_kvar[:, 1]
    sf['Vmin_pu'] = result.voltage_pu.min(axis=1); sf['Vmax_pu'] = result.voltage_pu.max(axis=1)
    lines = np.asarray(result.branch_kinds) == 'line'
    sf['rho_max'] = result.phase_current_loading_pu[:, lines].max(axis=1)
    sf['max_line_current_A'] = result.phase_current_a[:, lines].max(axis=1)
    sf['voltage_violation_count'] = vf.groupby('slot').violation.sum().to_numpy()
    sf['line_current_violation_count'] = bf[bf.kind == 'line'].groupby('slot').violation.sum().to_numpy()
    for i in range(result.regulator_taps.shape[1]): sf[f'regulator_tap_{i}'] = result.regulator_taps[:, i]
    for i in range(result.capacitor_states.shape[1]): sf[f'capacitor_state_{i}'] = result.capacitor_states[:, i]
    receipts = {name: table(output / filename, frame) for name, filename, frame in (
        ('voltage', 'BUS_PHASE_VOLTAGES.parquet', vf), ('current', 'BRANCH_PHASE_CURRENTS.parquet', bf),
        ('system', 'FEEDER_SYSTEM_96.parquet', sf))}
    contract = dict(schema='V41_FULL_GRID_V1', target_day=day, policy=policy, stage=stage, slots=96,
        bus_phase_count=n, branch_phase_count=b, voltage_rows=96*n, current_rows=96*b,
        node_axis=list(zip(nodes, result.node_phases)), branch_axis=list(zip(branches, result.branch_phases)),
        units='voltage pu/angle degrees, current A, P kW, Q kvar, loading pu',
        transformer_total_kVA_loading_null_for_lines=True, observer_additional_solve_calls=0,
        feeder_sign='Import is negative Circuit.TotalPower (power into all circuit source terminals)', tables=receipts)
    write_json(output / 'GRID_AXIS_CONTRACT.json', contract)
    return vf, bf, sf


def planning(output, day, policy, stage, context, controls):
    from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading, is_dominated_mess_current_row
    dates = axis(day); vr=[]; br=[]
    for t, c in enumerate(context.coefficients):
        x = controls[t]; voltage = np.sqrt(c.voltage_constant+c.voltage_matrix.T@x)
        loading = anchored_polygon_loading(c, x); current = c.current_constant+c.current_matrix.T@x
        p = c.flow_p_constant+c.flow_p_matrix@x; q = c.flow_q_constant+c.flow_q_matrix@x
        for name, v in zip(context.nodes, voltage, strict=True):
            vr.append(dict(slot=t, timestamp=dates[t], node=str(name), voltage_pu=float(v),
                lower_margin_pu=float(v-.95), upper_margin_pu=float(1.05-v)))
        for k, name in enumerate(c.branch_names):
            br.append(dict(slot=t, timestamp=dates[t], branch_phase=name, P_flow_kW=p[k], Q_flow_kvar=q[k],
                polygon_loading_pu=loading[k], affine_current_loading_pu=current[k],
                active_current_constraint=not is_dominated_mess_current_row(name),
                transformer_rating_kVA=c.transformer_ratings[k], flow_polygon_limit=c.branch_limits[k]))
    vf, bf = pd.DataFrame(vr), pd.DataFrame(br)
    full_axis(vf, ['node'], [(str(n),) for n in context.nodes])
    full_axis(bf, ['branch_phase'], [(n,) for n in context.coefficients[0].branch_names])
    table(output / 'PLANNING_BUS_PHASES.parquet', vf); table(output / 'PLANNING_BRANCH_PHASES.parquet', bf)
    cf = pd.DataFrame(controls, columns=context.coefficients[0].control_names)
    cf.insert(0, 'timestamp', dates); cf.insert(0, 'slot', range(96))
    table(output / 'PLANNING_CONTROLS_96.parquet', cf)
    write_json(output / 'PLANNING_AUTHORITY.json', dict(target_day=day, policy=policy, stage=stage,
        coefficient_SHA256=[c.coefficient_sha256 for c in context.coefficients],
        current_A='NOT_A_PLANNING_VARIABLE; full measured current is in Fresh/Actual tables',
        no_new_surrogate_or_constraints=True))
