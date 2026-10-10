"""Fresh-only paired replay of an existing immutable B1/B2/B3 frozen plan.

The preserved Operations inputs are copied byte for byte. The only optional
physical intervention is the explicitly identified CapControl/SVR scenario.
"""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import argparse
import hashlib
import json
import shutil
import time

import numpy as np

from v42_pr134_b1.common import atomic, digest, read, record
from .authority import ROOT, source_files, archive_source


def bit_equal(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()


def preserved_sources():
    from v42_pr134_b1.common import CODE
    from v42_regcontrol import authority
    from v42_regcontrol.common import resolve
    paths=[ROOT/'v42_may_campaign_native90/operations.py',ROOT/'v42_pr134_b1/replay.py',
           ROOT/'v42_regcontrol/authority.py',ROOT/'v42_regcontrol/runner.py',ROOT/'v42_thermal/authority.py',
           CODE/'dayahead/v28r2/opendss_backend.py',CODE/'dayahead/v28r2/opendss_mapping.py',
           CODE/'dayahead/v28r2/trajectory.py',Path(__file__)]
    rows=[record(path) for path in paths]
    audit=authority.source()['audit']
    for receipt in audit['static_source_graph']['files']+audit['code_read']:
        current=record(resolve(receipt))
        if current not in rows: rows.append(current)
    return rows


def raw_metrics(path):
    with np.load(path,allow_pickle=False) as arrays:
        voltage=arrays['voltage_pu']
        convergence=arrays['convergence']
        lines=arrays['branch_kinds'].astype(str)=='line'
        transformers=arrays['branch_kinds'].astype(str)=='transformer'
        ratios=arrays['phase_current_loading_pu']
        tx=arrays['transformer_total_kva_loading_pu'][:,transformers]
        if (voltage.shape[0]!=96 or ratios.shape[0]!=96 or convergence.shape!=(96,)
                or not np.isfinite(voltage).all() or not np.isfinite(ratios).all()
                or not np.isfinite(tx).all() or lines.sum()!=263):
            raise ValueError('VOLTAGE_CONTROL_ORIGINAL_FINITE_96_SLOT_AXES_REQUIRED')
        violations=np.argwhere((voltage<.95)|(voltage>1.05))
        cells=[dict(slot_0based=int(slot),slot_1based=int(slot)+1,node_phase=str(arrays['node_names'][node]),
                    voltage_pu=float(voltage[slot,node]),
                    upper_exceedance_pu=float(max(0.,voltage[slot,node]-1.05)),
                    lower_exceedance_pu=float(max(0.,.95-voltage[slot,node]))) for slot,node in violations]
        return dict(converged_slots=int(convergence.sum()),logical_slots=96,
                    voltage_min_pu=float(voltage.min()),voltage_max_pu=float(voltage.max()),
                    voltage_violation_cells=len(cells),maximum_upper_exceedance_pu=float(max(0.,voltage.max()-1.05)),
                    maximum_lower_exceedance_pu=float(max(0.,.95-voltage.min())),
                    actual_maximum_line_loading_percent=100*float(ratios[:,lines].max()),
                    line_current_violation_cells=int((ratios[:,lines]>1).sum()),
                    original_service_and_grid_transformer_current_violation_cells=int((ratios[:,transformers]>1).sum()),
                    original_service_and_grid_transformer_kva_violation_cells=int((tx>1).sum()),
                    regulator_tap_change_count=int((np.abs(np.diff(arrays['regulator_taps'],axis=0))>1e-10).sum()),
                    fixed_caps_all_ON=bool((arrays['capacitor_states']==1).all()),
                    original_branch_phase_count=int(len(lines)),original_line_phase_count=int(lines.sum()),
                    violations=cells,raw_AC_receipt=record(path))


def run_frozen(request_path,operations_root,output,*,scenario_path=None,off_result_path=None,
               development=False,design_receipt=None,frozen_replay_infrastructure=None,b3_terminal_proof=None):
    from v42_may_campaign_native90 import operations,execution
    from v42_may_campaign_native90.preflight import native_zero
    from .integration import scenario_scope,validate_scenario
    request_path,operations_root,output=map(lambda p:Path(p).resolve(),(request_path,operations_root,output))
    if output.exists():
        raise PermissionError('VOLTAGE_CONTROL_PAIRED_REPLAY_OUTPUT_NEVER_OVERWRITTEN')
    if frozen_replay_infrastructure is not None and (development or design_receipt is not None):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_REPLAY_INFRASTRUCTURE_NOT_NEW_DESIGN_OR_DEVELOPMENT')
    request=read(request_path)
    if request['arm'] not in ('B1','B2','B3'):
        raise PermissionError('VOLTAGE_CONTROL_OPERATIONS_REPLAY_ARM_REQUIRED')
    source_folder=operations_root/'ACTUAL_SOURCE/INPUT/BUNDLE'/('DAY_'+request['day'].replace('-',''))
    originals=[request_path,operations_root/'PLANNING/V42_DAYAHEAD_DECISION_FREEZE.json',
               operations_root/'ACTUAL/ACTUAL_FIXED_TRAJECTORY.npz',operations_root/'ACTUAL/ACTUAL_MESS_TRAJECTORY.npz',
               operations_root/'FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz',operations_root/'FRESH/RAW_PHYSICAL_INPUT_LOG.json',
               operations_root/'FRESH/RAW_CONTROL_LOG.json',Path(request['input_folder'])/'NATIVE_INPUT.json',
               Path(request['input_folder'])/'OPERATIONS.json']
    physical=read(operations_root/'FRESH/RAW_PHYSICAL_INPUT_LOG.json')
    originals.append(Path(physical['Actual_exogenous']['path']))
    baseline=[record(path) for path in originals]
    source_before=preserved_sources()
    execution_sources=source_files()
    execution_SHA=digest(execution_sources)
    if scenario_path is None:
        raise PermissionError('VOLTAGE_CONTROL_EXPLICIT_REF_OR_CONTROL_SCENARIO_REQUIRED')
    scenario=read(scenario_path)
    validate_scenario(scenario)
    preserved_plan=None
    if frozen_replay_infrastructure is not None:
        from .authority import preserved_plan_binding
        names=('REQUEST','PLANNING_FREEZE','ACTUAL_FIXED','ACTUAL_MESS','ORIGINAL_RAW_AC',
               'PHYSICAL_INPUT_LOG','ORIGINAL_CONTROL_LOG','NATIVE_INPUT','OPERATIONS_INPUT','Actual_exogenous')
        preserved_plan=preserved_plan_binding(request['arm'],request['day'],dict(zip(names,baseline,strict=True)),
            source_before,b3_terminal_proof=b3_terminal_proof)
    is_ref=scenario['case']=='REF'
    if not is_ref:
        if off_result_path is None:
            raise PermissionError('VOLTAGE_CONTROL_EXACT_OFF_REPLAY_REQUIRED_BEFORE_FROZEN_ON')
        off=read(off_result_path)
        if (off.get('schema')!='V42_VOLTAGE_CONTROL_SAME_FROZEN_PLAN_REPLAY_V1'
                or off.get('case') != 'REF' or off.get('OFF_original_AC_bit_exact') is not True
                or off.get('original_bindings')!=baseline or off.get('arm')!=request['arm'] or off.get('day')!=request['day']):
            raise PermissionError('VOLTAGE_CONTROL_OFF_REPLAY_AUTHORITY_DRIFT')
        if record(off['metrics']['raw_AC_receipt']['path'])!=off['metrics']['raw_AC_receipt']:
            raise PermissionError('VOLTAGE_CONTROL_OFF_RAW_RECEIPT_DRIFT')
        if frozen_replay_infrastructure is not None and (off.get('source_SHA')!=execution_SHA
            or off.get('frozen_replay_infrastructure')!=frozen_replay_infrastructure
            or off.get('preserved_plan_binding_SHA')!=preserved_plan['binding_SHA']):
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_REPLAY_SAME_SOURCE_INPUT_REF_PROOF_REQUIRED')
    output.mkdir(parents=True)
    archive=archive_source(output/'SOURCE_EPOCH',source_SHA=execution_SHA,external_receipts=source_before)
    actual=output/'ACTUAL_FROZEN_COPY';actual.mkdir()
    for name in ('ACTUAL_FIXED_TRAJECTORY.npz','ACTUAL_MESS_TRAJECTORY.npz'):
        shutil.copy2(operations_root/'ACTUAL'/name,actual/name)
        if record(actual/name)['sha256']!=record(operations_root/'ACTUAL'/name)['sha256']:
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_COPY_BYTE_DRIFT')
    fresh=output/'FRESH';fresh.mkdir()
    started=time.perf_counter();observer=None;failure=None
    def authorize(day,action):
        if day!=request['day'] or action!='FRESH_AC':
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_REPLAY_FRESH_ONLY')
        return day
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(execution,'authorize',authorize))
            denied=stack.enter_context(native_zero())
            if scenario is not None:
                from .authority import actual_permit,frozen_plan_permit
                if frozen_replay_infrastructure is not None:
                    stack.enter_context(frozen_plan_permit(request['arm'],request['day'],execution_SHA,scenario,
                        infrastructure_receipt=frozen_replay_infrastructure,preserved_plan=preserved_plan))
                else:
                    stack.enter_context(actual_permit(request['arm'],request['day'],execution_SHA,scenario,
                        development=development,design_receipt=design_receipt))
                observer=stack.enter_context(scenario_scope(scenario,output/'VOLTAGE_CONTROL_PHYSICAL',
                    source_SHA=execution_SHA,arm=request['arm'],day=request['day']))
            outcome=operations.fresh(request,operations_root/'PLANNING',actual,source_folder,fresh)
            if denied:
                raise PermissionError('VOLTAGE_CONTROL_REPLAY_OPTIMIZER_ENTRY_FORBIDDEN')
        metrics=raw_metrics(fresh/'fresh/OPENDSS_PHASE_ARRAYS.npz')
        identities={}
        if is_ref:
            with np.load(operations_root/'FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz',allow_pickle=False) as old, \
                    np.load(fresh/'fresh/OPENDSS_PHASE_ARRAYS.npz',allow_pickle=False) as new:
                identities={key:bit_equal(old[key],new[key]) for key in old.files}
            if not identities or not all(identities.values()):
                raise PermissionError('VOLTAGE_CONTROL_OFF_ORIGINAL_ALL_AC_ARRAYS_NOT_BIT_EXACT')
        if [record(path) for path in originals]!=baseline or preserved_sources()!=source_before:
            raise PermissionError('VOLTAGE_CONTROL_REPLAY_ORIGINAL_SOURCE_OR_EVIDENCE_MUTATION')
        if source_files()!=execution_sources:
            raise PermissionError('VOLTAGE_CONTROL_REPLAY_EXECUTION_SOURCE_MUTATION')
        physical=read(fresh/'RAW_PHYSICAL_INPUT_LOG.json')
        original_physical=read(operations_root/'FRESH/RAW_PHYSICAL_INPUT_LOG.json')
        if physical!=original_physical:
            raise PermissionError('VOLTAGE_CONTROL_REPLAY_EXOGENOUS_OR_FROZEN_MESS_INPUT_MUTATION')
        original_PASS=(metrics['converged_slots']==96 and metrics['voltage_violation_cells']==0
            and metrics['line_current_violation_cells']==0
            and metrics['original_service_and_grid_transformer_current_violation_cells']==0
            and metrics['original_service_and_grid_transformer_kva_violation_cells']==0
            and (metrics['fixed_caps_all_ON'] or scenario['case'] in ('A1','A2','C')))
        hardware_PASS=observer.result['hardware_and_controller_PASS'] if observer else True
        result=dict(schema='V42_VOLTAGE_CONTROL_SAME_FROZEN_PLAN_REPLAY_V1',
            comparison_class='SAME_FROZEN_PLAN_ORIGINAL_STATIC_REF' if is_ref else 'SAME_FROZEN_PLAN_'+scenario['case'],
            arm=request['arm'],day=request['day'],case=scenario['case'],time_mode=scenario['time_mode'],
            VOLTAGE_CONTROL_enabled=not is_ref,
            source_SHA=execution_SHA,execution_sources=execution_sources,
            frozen_replay_infrastructure=frozen_replay_infrastructure,
            preserved_plan_binding_SHA=None if preserved_plan is None else preserved_plan['binding_SHA'],
            frozen_plan_replay_scope='EXISTING_FROZEN_PLAN_NATIVE_ZERO_REPLAY' if frozen_replay_infrastructure else None,
            new_Planning_Actual_E2E_qualified=False,
            scenario_SHA=scenario['scenario_SHA'] if scenario else None,
            OFF_original_AC_bit_exact=bool(identities) and all(identities.values()),
            OFF_original_AC_array_identity=identities,original_bindings=baseline,original_sources=source_before,
            original_inputs_unchanged=True,Native_optimizer_calls=0,Actual_reoptimization=0,
            Native_zero_denied_attempts=denied,
            MESS_PQ_repair=0,Planning_reoptimized=False,Planning_band_pu=[.95,1.05],Actual_band_pu=[.95,1.05],
            metrics=metrics,original_physical_PASS=original_PASS,hardware_and_controller_PASS=hardware_PASS,
            Full_AC_Physical_PASS=original_PASS and hardware_PASS,
            fresh_result=outcome,hardware_audit=observer.receipt if observer else None,
            physical_audit=observer.receipt,raw_AC_receipt=metrics['raw_AC_receipt'],logical_Fresh_slots=96,
            PASS=original_PASS and hardware_PASS,source_archive=archive,DSTATCOM_object_count=0,
            historical_original_physical_sources_preserved=True,
            current_execution_source_is_new=True,independent_holdout_claim=False,
            wall_seconds=time.perf_counter()-started)
        atomic(output/'REPLAY_RESULT.json',result)
        return result
    except Exception as error:
        failure=dict(schema='V42_VOLTAGE_CONTROL_FROZEN_REPLAY_FAILURE_V1',status='IMPLEMENTATION_OR_VALIDATION_FAILURE',
            arm=request['arm'],day=request['day'],error=repr(error),VOLTAGE_CONTROL_enabled=scenario is not None,
            Full_AC_Physical_PASS=False,original_bindings=baseline,Native_optimizer_calls=0,
            wall_seconds=time.perf_counter()-started,hardware_audit=observer.receipt if observer else None)
        atomic(output/'REPLAY_FAILURE.json',failure)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('request');parser.add_argument('operations');parser.add_argument('output')
    parser.add_argument('--scenario');parser.add_argument('--off-result')
    parser.add_argument('--development',action='store_true')
    parser.add_argument('--design')
    parser.add_argument('--frozen-replay-infrastructure')
    parser.add_argument('--b3-terminal-proof')
    args=parser.parse_args()
    result=run_frozen(args.request,args.operations,args.output,scenario_path=args.scenario,off_result_path=args.off_result,
        development=args.development,design_receipt=record(args.design) if args.design else None,
        frozen_replay_infrastructure=record(args.frozen_replay_infrastructure) if args.frozen_replay_infrastructure else None,
        b3_terminal_proof=record(args.b3_terminal_proof) if args.b3_terminal_proof else None)
    brief={key:result[key] for key in ('arm','day','VOLTAGE_CONTROL_enabled','Full_AC_Physical_PASS')}
    brief['metrics']={key:value for key,value in result['metrics'].items() if key!='violations'}
    brief['complete_result']=str(Path(args.output).resolve()/'REPLAY_RESULT.json')
    print(json.dumps(brief,ensure_ascii=False))
