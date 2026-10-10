"""One immutable date/policy, one independent process, no optimization."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys
import time
import traceback

sys.path.insert(0, 'D:/v42voltage')
from v42_voltage_control.authority import (
    archive_source, frozen_plan_permit, preserved_plan_binding, source_files,
    verify_frozen_infrastructure,
)
from v42_voltage_control.integration import record
from v42_voltage_control.replay import run_frozen, preserved_sources, raw_metrics
from v42_b3_joint.contracts import digest

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)

def summarize(audit_receipt, raw_path):
    audit = read(audit_receipt['path'])
    rows = read(audit['slots_receipt']['path'])
    if len(rows) != 96 or [r['slot'] for r in rows] != list(range(96)):
        raise PermissionError('LITERAL_CHRONOLOGICAL_96_REQUIRED')
    frames = [r['physical'] for r in rows]
    controls = [r['settled_original_controls'] for r in rows]
    metric = raw_metrics(raw_path)
    whole = dict(
        voltage_violation_cells=sum(f['voltage_violation_cells'] for f in frames),
        Vmin=min(f['voltage_min_pu'] for f in frames),
        Vmax=max(f['voltage_max_pu'] for f in frames),
        line_current_violation_cells=sum(f['line_current_violation_cells'] for f in frames),
        transformer_current_violation_cells=sum(f['transformer_current_violation_cells'] for f in frames),
        transformer_nameplate_current_violation_cells=sum(f['transformer_nameplate_current_violation_cells'] for f in frames),
        transformer_kva_violation_cells=sum(f['transformer_kva_violation_cells'] for f in frames),
        max_line_loading_percent=metric['actual_maximum_line_loading_percent'],
        loss_energy_slot_end_estimate_kWh=sum(f['losses_W_var'][0] for f in frames)*.25/1000,
        converged_slots=sum(c['solution_converged'] for c in controls),
        control_complete_slots=sum(r['control_actions_done_as_of_current_time'] for r in rows),
        Original7_AUTO_all96=all(c['all_seven_RegControls_enabled'] for c in controls),
        Fixed_ON_original_caps_all96=all(all(c['states']==[1] for c in row['settled_original_controls']['capacitors']) for row in rows),
        SVR_hardware_PASS_all96=all(r['svr'] is None or (r['svr']['hardware_PASS'] and r['svr']['added_nodes_voltage_PASS']) for r in rows),
        old_and_added_node_phase_count=len(frames[0]['nodes']),
        native_physical_solve_count=sum(r['time_control']['physical_solve_count'] for r in rows),
        Original7_slot_end_tap_change_count=metric['regulator_tap_change_count'],
    )
    whole['upper_voltage_margin_pu']=1.05-whole['Vmax']
    whole['lower_voltage_margin_pu']=whole['Vmin']-.95
    return rows, whole

def main(args):
    started = time.perf_counter()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    queue = read(args.queue)
    matches = [j for j in queue['jobs'] if j['arm'] == args.arm and j['day'] == args.day]
    if len(matches) != 1:
        raise PermissionError('ONE_EXACT_FROZEN_DATE_POLICY_REQUIRED')
    job = matches[0]
    before = {}
    for key, item in job['original_frozen_input_receipts'].items():
        current = record(item['path'])
        if current['sha256'] != item['sha256'] or current['bytes'] != item['bytes']:
            raise PermissionError('ORIGINAL_FROZEN_RECEIPT_DRIFT:' + key)
        before[key] = current
    source_map = source_files()
    sha = digest(source_map)
    infra = record(args.infrastructure)
    _, scenario = verify_frozen_infrastructure(infra, sha)
    freeze_doc = read(args.infrastructure)
    scenario_path = freeze_doc['scenario']['path']
    ref_path = Path(args.ref_scenario).resolve()
    write(out/'JOB_SOURCE_PROVENANCE.json', dict(
        schema='V42_AC_ONLY_FROZEN_DAY_PROVENANCE_V1', job=job,
        source_SHA=sha, scenario_SHA=scenario['scenario_SHA'],
        infrastructure=infra, driver=record(__file__), queue=record(args.queue),
        configuration=args.configuration,
        original_frozen_receipts=before, new_Planning_optimization=False,
        historical_plan_reuse_for_physical_diagnosis_only=True,
        Native_optimizer_calls=0, independent_holdout_claim=False,
    ))
    shutil.copyfile(__file__, out/'DRIVER_USED.py')
    archive_source(out/'SOURCE_EPOCH', source_SHA=sha,
        external_receipts=preserved_sources()+[record(__file__),record(args.queue),infra,record(scenario_path),record(ref_path),record(args.ref_time_scenario)])
    ref_time = None
    timing=dict(source_and_input_preparation_seconds=time.perf_counter()-started)
    stage_started=time.perf_counter()
    if args.arm == 'B0':
        from v42_voltage_control.b0_replay import load_historical_original, replay_pair
        payload = load_historical_original(args.day,job['original_operations_folder'])
        receipts = {Path(r['path']).name:r for r in payload['sources'][:6]}
        receipts['Actual_exogenous'] = payload['sources'][6]
        binding = preserved_plan_binding('B0',args.day,receipts,preserved_sources())
        with frozen_plan_permit('B0',args.day,sha,scenario,infrastructure_receipt=infra,preserved_plan=binding):
            on = replay_pair(args.day,job['original_operations_folder'],out/'PAIR',scenario=scenario,source_SHA=sha)
        audit_receipt = on['hardware_audit_receipt']
        raw_path = out/'PAIR/ON/FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz'
        off_bit = on['OFF_exact_reproduction']['PASS']
        timing['B0_STATIC_REF_AND_SVR_pair_seconds']=time.perf_counter()-stage_started
        if args.configuration == 'SVR4':
            from v42_voltage_control.b0_replay import _original_actual
            from v42_voltage_control.integration import scenario_scope
            time_scenario = read(args.ref_time_scenario)
            stage_started=time.perf_counter()
            with frozen_plan_permit('B0',args.day,sha,time_scenario,infrastructure_receipt=infra,preserved_plan=binding):
                with scenario_scope(time_scenario,out/'REF_TIME/PHYSICAL',source_SHA=sha,arm='B0',day=args.day) as observer:
                    _original_actual(payload,out/'REF_TIME/FRESH')
            ref_raw = out/'REF_TIME/FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz'
            _, ref_metric = summarize(observer.receipt,ref_raw)
            ref_time = dict(configuration='REF_TIME',metric=ref_metric,physical_audit=observer.receipt,raw_AC=record(ref_raw))
            timing['REF_TIME_including_audit_seconds']=time.perf_counter()-stage_started
    else:
        request = job['original_frozen_input_receipts']['request']['path']
        run_frozen(request,job['original_operations_folder'],out/'REF',
            scenario_path=ref_path,frozen_replay_infrastructure=infra)
        timing['STATIC_REF_replay_including_archive_seconds']=time.perf_counter()-stage_started
        stage_started=time.perf_counter()
        on = run_frozen(request,job['original_operations_folder'],out/'SVR',
            scenario_path=scenario_path,off_result_path=out/'REF/REPLAY_RESULT.json',
            frozen_replay_infrastructure=infra)
        timing['SVR_replay_including_archive_seconds']=time.perf_counter()-stage_started
        timing['SVR_actual_backend_and_validation_seconds']=on['wall_seconds']
        audit_receipt = on['physical_audit']
        raw_path = Path(on['raw_AC_receipt']['path'])
        off_bit = read(out/'REF/REPLAY_RESULT.json')['OFF_original_AC_bit_exact']
        if args.configuration == 'SVR4':
            stage_started=time.perf_counter()
            ref = run_frozen(request,job['original_operations_folder'],out/'REF_TIME',
                scenario_path=args.ref_time_scenario,off_result_path=out/'REF/REPLAY_RESULT.json',
                frozen_replay_infrastructure=infra)
            _, ref_metric = summarize(ref['physical_audit'],ref['raw_AC_receipt']['path'])
            ref_time = dict(configuration='REF_TIME',metric=ref_metric,physical_audit=ref['physical_audit'],raw_AC=ref['raw_AC_receipt'])
            timing['REF_TIME_including_archive_and_audit_seconds']=time.perf_counter()-stage_started
            timing['REF_TIME_actual_backend_and_validation_seconds']=ref['wall_seconds']
    rows, whole = summarize(audit_receipt,raw_path)
    passed = (off_bit is True and whole['converged_slots']==96 and whole['control_complete_slots']==96
        and whole['Original7_AUTO_all96'] and whole['Fixed_ON_original_caps_all96']
        and whole['SVR_hardware_PASS_all96'] and all(whole[k]==0 for k in (
            'voltage_violation_cells','line_current_violation_cells','transformer_current_violation_cells','transformer_nameplate_current_violation_cells','transformer_kva_violation_cells')))
    failures = []
    for row in rows:
        for node in row['physical']['nodes']:
            voltage = node['voltage_pu']
            if not .95 <= voltage <= 1.05:
                failures.append(dict(slot_0based=row['slot'],slot_1based=row['slot']+1,
                    node_phase=node['node_phase'],voltage_pu=voltage,
                    kind='LOWER' if voltage<.95 else 'UPPER',
                    exceedance_pu=max(.95-voltage,voltage-1.05),
                    original_regulators=row['settled_original_controls']['original_regulators'],
                    SVR=row['svr']['devices']))
    if source_files()!=source_map or any(record(r['path'])!=r for r in before.values()):
        raise PermissionError('SOURCE_OR_PRESERVED_PLAN_MUTATED')
    result = dict(schema='V42_AC_ONLY_MONTHLY_FROZEN_DAY_RESULT_V1',status='PASS' if passed else 'PHYSICAL_FAIL',
        PASS=passed,arm=args.arm,day=args.day,scope='EXISTING_FROZEN_PLAN_ACTUAL_ONLY',
        configuration=args.configuration,
        source_SHA=sha,scenario_SHA=scenario['scenario_SHA'],infrastructure=infra,
        metric=whole,raw_AC=record(raw_path),physical_audit=audit_receipt,
        OFF_original_arrays_bit_exact=off_bit,Native_optimizer_calls=0,
        Actual_PQ_repair=0,Planning_reoptimized=False,new_model_E2E_qualified=False,
        original_inputs_unchanged=True,failures=failures,
        REF_time_controlled=ref_time,
        wall_seconds=time.perf_counter()-started,
        timing=timing,Fresh_context_count=3 if args.configuration=='SVR4' else 2,
        measurement_scope='96 chronological slot-end measurements; not continuous transient certification',
        loss_energy_method='sum(final slot loss W)*0.25h; not within-slot event integration')
    write(out/'AC_ONLY_DAY_RESULT.json',result)
    print(json.dumps({k:result[k] for k in ('arm','day','status','metric','wall_seconds')},ensure_ascii=False),flush=True)

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    for name in ('queue','arm','day','output','infrastructure','ref-scenario','ref-time-scenario','configuration'):
        p.add_argument('--'+name,required=True)
    args=p.parse_args()
    try:
        main(args)
    except Exception as error:
        folder=Path(args.output)
        if folder.exists() and not (folder/'AC_ONLY_DAY_RESULT.json').exists():
            write(folder/'AC_ONLY_DAY_RESULT.json',dict(schema='V42_AC_ONLY_MONTHLY_FROZEN_DAY_FAILURE_V1',
                arm=args.arm,day=args.day,status='IMPLEMENTATION_OR_SOURCE_FAILURE',PASS=False,
                configuration=args.configuration,
                metric=None,Native_optimizer_calls=0,new_model_E2E_qualified=False,error=repr(error)))
        traceback.print_exc()
        raise SystemExit(1)
