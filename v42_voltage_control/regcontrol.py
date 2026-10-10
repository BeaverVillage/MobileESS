"""Read Original RegControl sensors and predict one STATIC queued tap action.

No voltage, current, tap or control setter is used. Predictions describe the
next source Sample/DoPendingAction pair at a supplied electrical state, not the
final tap after a complete SolveSnap and repeated network/control resampling.
"""
from contextlib import contextmanager
import math

import numpy as np

SCHEMA = "V42_ORIGINAL_REGCONTROL_STATIC_SENSOR_V1"
PREDICTION_SCHEMA = "V42_ORIGINAL_REGCONTROL_STATIC_NEXT_ACTION_V1"
VERSION_TOKEN = "version 0.14.5 revision 87d85c2622c8281b92255335bc7c09b11191b21d"
PRIMARY_SOURCES = [
    dict(url="https://raw.githubusercontent.com/dss-extensions/dss_capi/0.14.5/src/Controls/RegControl.pas",
         sha256="799f539669cfe70727f64d7e8fa9b96c4ba03a61860f176b62174e9cabdfe6ae", bytes=45551,
         formula_sections="GetControlVoltage; Sample; AtLeastOneTap; DoPendingAction"),
    dict(url="https://raw.githubusercontent.com/dss-extensions/dss_capi/0.14.5/src/PDElements/Transformer.pas",
         sha256="53148a652db204f033eae2422cee6be0fcd3357a035e4c5641342dd6d51c319a", bytes=69743,
         formula_sections="RecalcElementData winding VBase; GetWindingVoltages; Get_BaseVoltage"),
]
VOLTAGES = "monitored_winding_voltages_complex"
CURRENTS = "monitored_winding_currents_complex"


def _pairs(values):
    return [[float(z.real), float(z.imag)] for z in values]


def _native_complex(values):
    value = np.asarray(values)
    if np.iscomplexobj(value):
        return value.astype(complex).reshape(-1)
    value = value.astype(float).reshape(-1)
    if len(value) % 2:
        raise ValueError("REGCONTROL_INTERLEAVED_COMPLEX_LENGTH")
    return value[0::2] + 1j * value[1::2]


def _from_pairs(values):
    value = np.asarray(values, dtype=float)
    if value.ndim != 2 or value.shape[1] != 2 or not np.isfinite(value).all():
        raise ValueError("REGCONTROL_FINITE_COMPLEX_PAIRS_REQUIRED")
    return value[:, 0] + 1j * value[:, 1]


@contextmanager
def _preserve_selection(engine):
    """Object/winding selectors are restored; no physical setting is changed."""
    collections = (engine.RegControls, engine.Transformers, engine.Capacitors)
    names = [(collection, collection.Name()) for collection in collections]
    winding = int(engine.Transformers.Wdg())
    element = str(engine.CktElement.Name())
    try:
        yield
    finally:
        for collection, name in names:
            if name and str(name).lower() != "none":
                collection.Name(name)
        if winding > 0:
            engine.Transformers.Wdg(winding)
        if element:
            engine.Circuit.SetActiveElement(element)


def _unsupported(row):
    p = row["properties"]
    reasons = []
    if row.get("control_mode") not in (0, 2):
        reasons.append("UNSUPPORTED_NATIVE_CONTROL_MODE")
    if not row.get("enabled"):
        reasons.append("DISABLED_ORIGINAL_REGCONTROL")
    if p.get("Bus", "").strip():
        reasons.append("REMOTE_REGULATED_BUS_NOT_IMPLEMENTED")
    for key in ("Reversible", "Cogen"):
        if str(p.get(key, "No")).lower() in ("yes", "true", "1"):
            reasons.append(key.upper() + "_INTERNAL_MODE_NOT_EXPOSED")
    if float(p.get("VLimit", "0")) != 0:
        reasons.append("VLIMIT_NOT_IMPLEMENTED")
    if float(p.get("LDC_Z", "0")) != 0:
        reasons.append("BECKWITH_LDC_Z_NOT_IMPLEMENTED")
    if not row.get("transformer_all_conductors_closed", True):
        reasons.append("OPEN_TRANSFORMER_TERMINAL")
    if VERSION_TOKEN not in row.get("engine_version", ""):
        reasons.append("UNPINNED_DSS_ENGINE_VERSION")
    return reasons


def _sensor(row, voltages, currents):
    v, i = _from_pairs(voltages), _from_pairs(currents)
    if len(v) != row["phases"] or len(i) != row["phases"]:
        raise ValueError("REGCONTROL_MONITORED_PHASE_AXIS_REQUIRED")
    p = row["properties"]
    pt, ct = float(p["PTRatio"]), float(p["CTPrim"])
    if pt <= 0 or ct <= 0:
        raise ValueError("REGCONTROL_POSITIVE_PT_CT_REQUIRED")
    phase = str(p["PTPhase"]).lower()
    if phase in ("max", "-2"):
        selected = int(np.argmax(np.abs(v)))
    elif phase in ("min", "-3"):
        selected = int(np.argmin(np.abs(v)))
    else:
        selected = int(phase) - 1
    if not 0 <= selected < len(v):
        raise ValueError("REGCONTROL_PT_PHASE_UNSUPPORTED")
    voltage_pt = v[selected] / pt
    current_ct = i[selected] / ct
    ldc = complex(float(p["R"]), float(p["X"])) * current_ct
    compensated = voltage_pt + ldc
    magnitude = float(abs(compensated))
    target, band = float(p["VReg"]), float(p["Band"])
    return dict(selected_phase_1based=selected + 1,
        voltage_PT_complex=_pairs([voltage_pt])[0], current_CT_complex=_pairs([current_ct])[0],
        LDC_complex=_pairs([ldc])[0], compensated_voltage_complex=_pairs([compensated])[0],
        uncompensated_voltage_V=float(abs(voltage_pt)), compensated_voltage_V=float(magnitude),
        target_V=target, band_V=band, lower_threshold_V=target-band/2,
        upper_threshold_V=target+band/2, lower_deadband_margin_V=magnitude-(target-band/2),
        upper_deadband_margin_V=(target+band/2)-magnitude,
        voltage_error_V=target-magnitude, current_direction="INTO_MONITORED_TRANSFORMER_TERMINAL",
        formula="Vcontrol=Vwinding[phase]/PTRatio+(R+jX)*Iterminal[phase]/CTPrim")


def _next_static_action(reg, sensor):
    p = reg["properties"]
    inc, base, limit = float(reg["tap_increment"]), float(reg["monitored_winding_base_voltage_V"]), int(p["MaxTapChange"])
    if inc <= 0 or base <= 0 or limit < 0:
        raise ValueError("REGCONTROL_INVALID_TAP_DOMAIN")
    needs = abs(sensor["voltage_error_V"]) > sensor["band_V"] / 2.
    boost = sensor["voltage_error_V"] * float(p["PTRatio"]) / base
    pending = round(boost/inc)*inc if needs and limit else 0.
    if reg["tap_winding"] != reg["monitored_winding"]:
        pending = -pending
    steps, blocked = 0, False
    if pending:
        blocked = (pending > 0 and reg["tap"] >= reg["max_tap"]) or (pending < 0 and reg["tap"] <= reg["min_tap"])
        if not blocked:
            count = min(limit, max(1, math.trunc(.7*abs(pending)/inc)))
            steps = count if pending > 0 else -count
    after = min(reg["max_tap"], max(reg["min_tap"], reg["tap"]+steps*inc))
    return dict(action="RAISE" if steps > 0 else "LOWER" if steps < 0 else "NO_ACTION",
        out_of_band=needs, winding_boost_pu=boost, pending_tap_change_pu=pending,
        blocked_by_tap_limit=blocked, next_static_steps=steps,
        next_static_tap_change_pu=after-reg["tap"], predicted_tap_after_next_action=after,
        Delay_queue_seconds=float(p["Delay"]), TapDelay_queue_seconds=float(p["TapDelay"]))


def _approximate_settled_local(reg, state):
    """A disclosed local, constant-power model; no network solve or fitted data."""
    assumptions = ["Primary voltage and all other regulators' taps stay unchanged",
        "Monitored winding equals tapped winding",
        "All monitored winding voltages scale by local tap ratio",
        "Monitored terminal currents scale inversely by tap ratio (constant power)",
        "No network redistribution, source impedance, added losses or coupled regulator resampling modeled"]
    if reg["tap_winding"] != reg["monitored_winding"] or reg["tap"] <= 0:
        return dict(expected_settled_tap_estimate=None, settled_tap_estimate_status="UNKNOWN_LOCAL_TAP_SCALING_UNSUPPORTED",
                    settled_tap_estimate_assumptions=assumptions)
    v, i = _from_pairs(state[VOLTAGES]), _from_pairs(state[CURRENTS])
    current = dict(reg)
    taps = {float(reg["tap"])}
    limit = 2*int(reg["num_taps"])+4
    for iteration in range(limit):
        sensor = _sensor(current, _pairs(v), _pairs(i))
        action = _next_static_action(current, sensor)
        after = action["predicted_tap_after_next_action"]
        if not action["next_static_steps"] or after == current["tap"]:
            reason = "LOCAL_TAP_LIMIT" if action["blocked_by_tap_limit"] else "LOCAL_QUANTIZED_NO_ACTION" if action["out_of_band"] else "LOCAL_SENSOR_IN_BAND"
            return dict(expected_settled_tap_estimate=current["tap"], settled_tap_estimate_status="APPROXIMATE",
                settled_tap_estimate_assumptions=assumptions, settled_local_iteration_count=iteration,
                settled_local_stop_reason=reason, settled_local_compensated_voltage_V=sensor["compensated_voltage_V"],
                expected_settled_direction="RAISE" if current["tap"] > reg["tap"] else "LOWER" if current["tap"] < reg["tap"] else "NO_ACTION")
        if after in taps:
            return dict(expected_settled_tap_estimate=None, settled_tap_estimate_status="UNKNOWN_LOCAL_MODEL_CYCLE",
                        settled_tap_estimate_assumptions=assumptions, settled_local_iteration_count=iteration+1)
        ratio = after/current["tap"]
        v, i = v*ratio, i/ratio
        current["tap"] = after
        taps.add(after)
    return dict(expected_settled_tap_estimate=None, settled_tap_estimate_status="UNKNOWN_LOCAL_MODEL_ITERATION_LIMIT",
                settled_tap_estimate_assumptions=assumptions, settled_local_iteration_count=limit)


def snapshot(engine, *, source_SHA=None, scenario=None):
    """Measure the exact original seven AUTO controls without solving or tuning."""
    from v42_regcontrol import authority
    original = authority.source()
    rows = []
    with _preserve_selection(engine):
        inventory = original["inventory"](engine)
        if scenario is None:
            authority.assert_inventory(inventory)
        else:
            from .integration import assert_control_inventory
            assert_control_inventory(inventory, scenario)
        original_names = {r['name'] for r in original['expected']['regulators']}
        original_inventory = dict(inventory, regulators=[r for r in inventory['regulators'] if r['name'] in original_names])
        if VERSION_TOKEN not in inventory["engine_version"]:
            raise ValueError("REGCONTROL_VERSION_PIN_MISMATCH")
        for reg in inventory["regulators"]:
            if reg['name'] not in original_names:
                continue
            p = reg["resolved_properties"]
            winding, tap_winding = int(p["Winding"]), int(p["TapWinding"])
            engine.Transformers.Name(reg["transformer"])
            engine.Transformers.Wdg(winding)
            engine.Circuit.SetActiveElement("Transformer." + reg["transformer"])
            nph = int(engine.CktElement.NumPhases())
            ncond = int(engine.CktElement.NumConductors())
            nterm = int(engine.CktElement.NumTerminals())
            kv = float(engine.Transformers.kV())
            delta = bool(engine.Transformers.IsDelta())
            base = kv * 1000. / (math.sqrt(3.) if not delta and nph in (2, 3) else 1.)
            v = _native_complex(engine.Transformers.WdgVoltages())
            all_currents = _native_complex(engine.CktElement.Currents())
            i = all_currents[(winding-1)*ncond:(winding-1)*ncond+nph]
            monitored_bus = engine.CktElement.BusNames()[winding-1]
            closed = not any(engine.CktElement.IsOpen(t, c)
                             for t in range(1, nterm+1) for c in range(1, ncond+1))
            engine.Transformers.Wdg(tap_winding)
            low, high, count = float(engine.Transformers.MinTap()), float(engine.Transformers.MaxTap()), int(engine.Transformers.NumTaps())
            row = dict(name=reg["name"], transformer=reg["transformer"],
                enabled=reg["enabled"], properties=dict(p), settings_SHA=authority.digest(
                    next(r for r in authority.regulator_parameters(original_inventory)["regulators"] if r["name"]==reg["name"])),
                monitored_winding=winding, tap_winding=tap_winding, monitored_bus=monitored_bus,
                phases=nph, conductors_per_terminal=ncond, winding_connection="delta" if delta else "wye",
                monitored_winding_kV=kv, monitored_winding_base_voltage_V=base,
                tap=float(engine.Transformers.Tap()), min_tap=low, max_tap=high,
                num_taps=count, tap_increment=(high-low)/count if count else 0.,
                transformer_all_conductors_closed=closed, control_mode=inventory["control_mode"],
                engine_version=inventory["engine_version"], **{VOLTAGES:_pairs(v), CURRENTS:_pairs(i)})
            reasons = _unsupported(row)
            row["sensor_status"] = "UNKNOWN" if reasons else "MEASURED_SOURCE_FORMULA"
            row["unknown_reasons"] = reasons
            row["sensor"] = None if reasons else _sensor(row, row[VOLTAGES], row[CURRENTS])
            rows.append(row)
        after = original["inventory"](engine)
        if after != inventory:
            raise ValueError("REGCONTROL_OBSERVER_CHANGED_ORIGINAL_CONTROL_STATE")
    return dict(schema=SCHEMA, source_SHA=source_SHA, engine_version=inventory["engine_version"],
        primary_sources=PRIMARY_SOURCES, source_regulator_settings_SHA=authority.digest(authority.regulator_parameters(original_inventory)),
        source_capacitor_settings_SHA=authority.digest(inventory["capacitors"]),
        regulator_names=[r["name"] for r in rows], regulator_count=len(rows), regulators=rows,
        configured_MaxControlIterations=int(engine.Solution.MaxControlIterations()),
        configured_MaxIterations=int(engine.Solution.MaxIterations()),
        ControlIterations=int(engine.Solution.ControlIterations()),
        Solution_Iterations_total=int(engine.Solution.Iterations()),
        ControlActionsDone=bool(engine.Solution.ControlActionsDone()),
        solution_converged=bool(engine.Solution.Converged()),
        physical_settings_mutations=0, physical_solves=0,
        semantics="Read-only sensor; STATIC predictions do not predict native TIME queue execution")


def predict_tap_response(measurement, *, predicted_winding_state=None):
    """Calculate source next-action direction/steps or explicitly UNKNOWN."""
    candidate = predicted_winding_state is not None
    rows = []
    for reg in measurement["regulators"]:
        result = dict(name=reg["name"], transformer=reg["transformer"], tap_before=reg["tap"],
            tap_increment=reg["tap_increment"],
            state_basis="PREDICTED_WINDING_STATE" if candidate else "CURRENT_STATE_ONLY",
            expected_settled_tap_estimate=None,
            settled_tap_estimate_status="UNKNOWN_NETWORK_AND_OTHER_REGULATOR_RESAMPLING_NOT_MODELED")
        reasons = _unsupported(reg)
        if reg.get('control_mode') != 0:
            reasons.append('NATIVE_TIME_QUEUE_ACTION_IS_NOT_A_STATIC_PREDICTION')
        state = predicted_winding_state.get(reg["name"]) if candidate else reg
        if candidate and not isinstance(state, dict):
            reasons.append("PREDICTED_WINDING_STATE_MISSING")
        if reasons:
            result.update(status="UNKNOWN", unknown_reasons=reasons, action="UNKNOWN", sensor=None,
                          predicted_tap_after_next_action=None, next_static_steps=None)
            rows.append(result)
            continue
        try:
            sensor = _sensor(reg, state[VOLTAGES], state[CURRENTS])
            result.update(status="PREDICTED", unknown_reasons=[], sensor=sensor,
                          **_next_static_action(reg, sensor), **_approximate_settled_local(reg, state))
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            result.update(status="UNKNOWN", unknown_reasons=[str(error)], action="UNKNOWN", sensor=None,
                          predicted_tap_after_next_action=None, next_static_steps=None)
        rows.append(result)
    return dict(schema=PREDICTION_SCHEMA, source_SHA=measurement.get("source_SHA"), primary_sources=PRIMARY_SOURCES,
        state_basis="PREDICTED_WINDING_STATE" if candidate else "CURRENT_STATE_ONLY", regulators=rows,
        all_predictions_known=all(r["status"]=="PREDICTED" for r in rows),
        predicts_one_next_STATIC_action=True, predicts_complete_SolveSnap_final_tap=False,
        includes_approximate_local_settled_tap_model=True,
        real_time_delay_or_one_second_physical_claim=False, certifies_candidate_network_safety=False)


def compare_settled_taps(prediction, after_measurement):
    """Separate aggregate SolveSnap observations from unobserved first actions.

No unchanged-control accuracy percentage is reported. A direction agreement is
only a diagnostic over actual changed controls with a known next-action model.
It is not an exact validation of the unobserved first queued action.
"""
    after = {r["name"]: r for r in after_measurement["regulators"]}
    rows = []
    for p in prediction["regulators"]:
        current = after.get(p["name"])
        tap = None if current is None else current["tap"]
        delta = None if tap is None else tap-p["tap_before"]
        changed = None if delta is None else abs(delta) > 1e-12
        known = p["status"] == "PREDICTED" and tap is not None
        predicted_delta = p.get("next_static_tap_change_pu") if known else None
        direction_agrees = ((delta > 0)-(delta < 0) == (predicted_delta > 0)-(predicted_delta < 0)) if known and changed else None
        estimate = p.get("expected_settled_tap_estimate")
        approx_known = p.get("settled_tap_estimate_status") == "APPROXIMATE" and estimate is not None and tap is not None
        approx_delta = None if not approx_known else estimate-p["tap_before"]
        approx_direction = ((delta > 0)-(delta < 0) == (approx_delta > 0)-(approx_delta < 0)) if approx_known and changed else None
        rows.append(dict(name=p["name"], expected_next_action_tap=p.get("predicted_tap_after_next_action"),
            expected_settled_tap_estimate=p.get("expected_settled_tap_estimate"),
            actual_settled_tap=tap, actual_aggregate_tap_change=delta, actual_tap_changed=changed,
            next_action_to_settled_tap_difference=None if not known else tap-p["predicted_tap_after_next_action"],
            direction_agreement_diagnostic=direction_agrees,
            approximate_settled_tap_estimate_status=p.get("settled_tap_estimate_status"),
            approximate_settled_tap_error_steps=None if not approx_known else (estimate-tap)/p["tap_increment"],
            approximate_settled_direction_agreement=approx_direction,
            comparison_status="LIMITED_NEXT_ACTION_VS_AGGREGATE_SOLVESNAP" if known else "UNKNOWN",
            exact_next_action_accuracy=None, exact_settled_tap_prediction_accuracy=None,
            observed_first_queued_action=False, state_basis=p["state_basis"]))
    changed_rows = [r for r in rows if r["actual_tap_changed"]]
    covered = [r for r in changed_rows if r["direction_agreement_diagnostic"] is not None]
    approximate = [r for r in changed_rows if r["approximate_settled_tap_error_steps"] is not None]
    return dict(schema="V42_REGCONTROL_NEXT_ACTION_VS_SETTLED_COMPARISON_V1", regulators=rows,
        actual_changed_regulator_count=len(changed_rows), changed_case_known_prediction_count=len(covered),
        changed_case_coverage=None if not changed_rows else len(covered)/len(changed_rows),
        changed_case_direction_agreement_diagnostic=None if not covered else sum(r["direction_agreement_diagnostic"] for r in covered)/len(covered),
        approximate_settled_changed_case_coverage=None if not changed_rows else len(approximate)/len(changed_rows),
        approximate_settled_changed_case_tap_step_MAE=None if not approximate else sum(abs(r["approximate_settled_tap_error_steps"]) for r in approximate)/len(approximate),
        approximate_settled_changed_case_direction_agreement=None if not approximate else sum(r["approximate_settled_direction_agreement"] for r in approximate)/len(approximate),
        exact_next_action_accuracy=None, exact_settled_tap_prediction_accuracy=None,
        limitations="First queued actions were not observed; SolveSnap can resample the network and all seven controls repeatedly.",
        counts_unchanged_cases_as_prediction_accuracy=False)
