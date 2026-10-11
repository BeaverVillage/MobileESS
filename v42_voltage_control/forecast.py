"""Forecast-only Fresh AC for a separately frozen AIDC/MESS candidate.

This evaluator never opens Actual sources, old results, or an optimizer. The
accepted decision arrays and D1 exogenous receipt are explicit arguments. The
original OpenDSS 96-slot backend, controls and MESS mapping remain unchanged.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import inspect

import numpy as np

from v42_pr134_b1.common import atomic, digest, read, record
from v42_b3_joint.contracts import require
from .authority import checked
from .replay import raw_metrics
from .integration import assert_existing_controls

VERSION = 'V42_CAPCONTROL_SVR_FORECAST_FRESH_CANDIDATE_V1'


def forecast_inputs(day, receipt):
    value = read(checked(receipt))
    fixed_aest = timezone(timedelta(hours=10))
    target = datetime.fromisoformat(day).replace(tzinfo=fixed_aest)
    cutoff = target - timedelta(hours=6)
    for key in ('demand_issue', 'pv_issue'):
        issued = datetime.fromisoformat(value[key])
        require(issued.tzinfo is not None and issued <= cutoff,
                'CAPCONTROL_SVR_FORECAST_D1_VINTAGE_REQUIRED')
    stamps = [datetime.fromisoformat(t) for t in value['timestamps_96']]
    require(len(stamps) == 96 and all(t == target+timedelta(minutes=15*(i+1))
            for i,t in enumerate(stamps)), 'CAPCONTROL_SVR_FORECAST_EXACT_SLOT_AXIS_REQUIRED')
    for key in ('demand_mw_96','pv_mw_96'):
        array = np.asarray(value[key], dtype=float)
        require(array.shape == (96,) and np.isfinite(array).all(),
                'CAPCONTROL_SVR_FORECAST_FINITE_96_EXOGENOUS_VALUES_REQUIRED')
    return value


def accepted_arrays(physical_receipt,mess_receipt):
    with np.load(checked(physical_receipt),allow_pickle=False) as z:
        physical = {k:z[k].copy() for k in z.files}
    with np.load(checked(mess_receipt),allow_pickle=False) as z:
        mess = {k:z[k].copy() for k in z.files}
    p,q = physical['PCC_P_kw'],physical['PCC_Q_kvar']
    require(p.shape == q.shape == (96,12) and np.isfinite(p).all() and np.isfinite(q).all(),
            'CAPCONTROL_SVR_FORECAST_ACCEPTED_AIDC_AXIS_REQUIRED')
    require(list(map(str,physical['sites'])) == [f'AIDC{i:02d}' for i in range(1,13)],
            'CAPCONTROL_SVR_FORECAST_CANONICAL_AIDC_AXIS_REQUIRED')
    require(mess['P_kw'].shape == mess['Q_kvar'].shape == mess['locations'].shape == (96,4)
            and np.isfinite(mess['P_kw']).all() and np.isfinite(mess['Q_kvar']).all()
            and list(map(str,mess['unit_ids'])) == [f'MESS{i:02d}' for i in range(1,5)],
            'CAPCONTROL_SVR_FORECAST_FROZEN_MESS_AXIS_REQUIRED')
    return physical,mess


def run_fresh(day, arm, physical_receipt, mess_receipt, forecast_receipt, output, progress=None):
    """Requires the caller's independent DAYAHEAD scenario/permit scope."""
    from .bindings import original_bindings as _bindings
    authority,background,isolated_compile,native_zero,backend,mapping,FrozenTrajectory,CODE = _bindings()
    require(arm in ('B0','B1','B2','B3'), 'CAPCONTROL_SVR_FORECAST_POLICY_REQUIRED')
    original_backend = backend.run_fresh_opendss.__code__
    source_receipts = [physical_receipt,mess_receipt,forecast_receipt]
    exo = forecast_inputs(day,forecast_receipt)
    physical,mess = accepted_arrays(physical_receipt,mess_receipt)
    p,q = physical['PCC_P_kw'],physical['PCC_Q_kvar']
    output = Path(output).resolve()
    require(not output.exists(), 'CAPCONTROL_SVR_FORECAST_FRESH_OUTPUT_NEVER_OVERWRITTEN')
    output.mkdir(parents=True)
    bg = background(exo['timestamps_96'],exo['demand_mw_96'],exo['pv_mw_96'])
    source = authority.source()
    engine,adapter,initial = authority.compile_verified()
    try:
        branches,topology = source['oriented_branches'](engine)
        nodes = tuple(sorted(n.lower() for n in engine.Circuit.AllNodeNames()
                             if n.rsplit('.',1)[-1] in ('1','2','3')))
        native = source['NativeAllocation'].from_adapter(adapter)
    finally:
        engine.Basic.ClearAll()
    context = SimpleNamespace(legacy_context=(None,None,bg,
        SimpleNamespace(factories=[SimpleNamespace(data=SimpleNamespace(branches=branches))]),None,None))
    trajectory = FrozenTrajectory(day,'DAYAHEAD',arm,p,q,mess['P_kw'],mess['Q_kvar'],
        tuple(map(str,mess['unit_ids'])),mess['locations'],digest(source_receipts))
    trajectory.validate()
    original_compile,original_voltage = authority.compile_verified,backend._voltage_vector
    compilations,applied,controls = [],[],[]

    def compile_current(_assets):
        engine,ad,inventory = isolated_compile(original_compile,output,compilations)
        native.validate_native_engine(engine)
        require(inventory == initial,'CAPCONTROL_SVR_FORECAST_SOURCE_INITIAL_STATE_DRIFT')
        return engine,ad

    def apply_current(engine,ad,_context,tr,slot):
        totals,ledger,allocation = native.apply(engine,bg,slot)
        for r in ad['pv_generators']:
            key = (str(r['bus']).lower(),'ABC'[int(r['phase'])-1])
            mapping._set_generator(engine,r['generator_name'],bg.pv_generation_kw_96[slot].get(key,0),0)
        mapping.apply_trajectory_slot(engine,dict(ad,loads=[]),_context,tr,slot)
        assert_existing_controls(engine)
        applied.append(dict(slot=slot,PCC_P_kw=tr.pcc_p_kw[slot].tolist(),PCC_Q_kvar=tr.pcc_q_kvar[slot].tolist(),
            MESS_P_kw=tr.mess_p_kw[slot].tolist(),MESS_Q_kvar=tr.mess_q_kvar[slot].tolist(),
            MESS_locations=list(map(str,tr.mess_locations_96x4[slot])),native_load_PQ=totals,allocation=allocation))

    def native_controls(engine,_voltage,slot):
        assert_existing_controls(engine)

    def measure(engine,axis):
        values = original_voltage(engine,axis)
        inventory = source['inventory'](engine)
        assert_existing_controls(engine)
        require(engine.Solution.ControlActionsDone(),'CAPCONTROL_SVR_FORECAST_ORIGINAL_CONTROLS_UNSETTLED')
        taps,caps = source['native_state'](engine)
        controls.append(dict(slot=len(controls),regulator_settings_SHA=authority.digest(authority.regulator_parameters(inventory)),
            taps=taps,caps=caps,all_7_RegControls_enabled=True,Planning_tap_replay=False,
            ControlIterations=int(engine.Solution.ControlIterations()),Iterations=int(engine.Solution.Iterations()),
            MaxControlIterations=int(engine.Solution.MaxControlIterations()),MaxIterations=int(engine.Solution.MaxIterations())))
        return values

    sources = [record(inspect.getfile(f)) for f in
        (backend.run_fresh_opendss,authority.compile_verified,mapping.apply_trajectory_slot,background,source['branch_measurement'])]
    with ExitStack() as stack:
        for key,function in (('compile_clean_engine',compile_current),('apply_trajectory_slot',apply_current),
            ('apply_frozen_native_state',native_controls),('_branch_measurement',source['branch_measurement']),('_voltage_vector',measure)):
            stack.enter_context(patch.object(backend,key,function))
        denied = stack.enter_context(native_zero())
        backend.run_fresh_opendss(repo=CODE,context=context,voltage=dict(node_names=nodes),
            trajectory=trajectory,output=output/'fresh',progress=progress)
        require(not denied,'CAPCONTROL_SVR_FORECAST_PHYSICAL_OPTIMIZER_FORBIDDEN')
    require(backend.run_fresh_opendss.__code__ is original_backend,'CAPCONTROL_SVR_FORECAST_ORIGINAL_BODY_MUTATED')
    # Match checked(): historical C: junctions resolve to the same D: file.
    # Original SHA/length stay exact; only the equivalent path is normalized.
    require(all(record(r['path']) == dict(r,path=str(Path(r['path']).resolve())) for r in source_receipts+sources),'CAPCONTROL_SVR_FORECAST_SOURCE_OR_DECISION_MUTATED')
    metrics = raw_metrics(output/'fresh/OPENDSS_PHASE_ARRAYS.npz')
    passed = (metrics['converged_slots'] == 96 and len(controls) == 96
        and not any(metrics[k] for k in ('voltage_violation_cells','line_current_violation_cells',
        'original_service_and_grid_transformer_current_violation_cells','original_service_and_grid_transformer_kva_violation_cells')))
    atomic(output/'RAW_CONTROL_LOG.json',dict(day=day,arm=arm,namespace='DAYAHEAD',source_initial_inventory=initial,slots=controls))
    atomic(output/'RAW_PHYSICAL_INPUT_LOG.json',dict(day=day,arm=arm,namespace='DAYAHEAD',slots=applied,
        forecast=forecast_receipt,alpha_BG=1.15,PV_scaled_by_alpha_BG=False,Actual_source_reads=0))
    result = dict(schema=VERSION,day=day,arm=arm,namespace='DAYAHEAD',PASS=passed,metrics=metrics,
        Native_optimizer_calls=0,Actual_source_reads=0,Actual_controller_state_reads=0,
        MESS_PQ_repair_calls=0,CAPCONTROL_SVR_MILP_variables=0,Original_96_slot_backend_body_unchanged=True,
        original_source_receipts=sources,decision_and_forecast_sources=source_receipts,source_initial_inventory=initial,topology=topology)
    atomic(output/'FORECAST_FRESH_RESULT.json',result)
    return result
