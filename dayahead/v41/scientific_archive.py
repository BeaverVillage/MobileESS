"""Durable scientific chain, policy/day identity, and fail-closed read-back."""
from dataclasses import asdict, is_dataclass
from pathlib import Path
import importlib.metadata
import json
import math
import os
import platform
import shutil
import sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from dayahead.paper_analysis.storage import read, write_json, atomic, canonical, digest
from .data import RUNTIME, SOURCE_REPO, issue_time
from .preflight import ROOT, OUT, record
from .reserve import require, OBJECTIVE_HIERARCHY
from .persistence import table, verify_table
from .grid_archive import axis, full_axis

SCHEMA = 'V41_COMPLETE_SCIENTIFIC_PERSISTENCE_V1'


def native(value):
    if is_dataclass(value): return native(asdict(value))
    if isinstance(value, dict): return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [native(v) for v in value]
    if isinstance(value, np.ndarray): return native(value.tolist())
    if isinstance(value, np.generic): return native(value.item())
    if isinstance(value, float) and not math.isfinite(value): return {'nonfinite_value': str(value)}
    if isinstance(value, Path): return str(value)
    if hasattr(value, 'isoformat'): return value.isoformat()
    return value


def document(path, value):
    value = native(value); write_json(path, value)
    require(read(path) == value, 'JSON_EXACT_READBACK:' + str(path))
    return record(path)


def copy_atomic(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        require(record(source)['sha256'] == record(destination)['sha256'], 'IMMUTABLE_COPY_DRIFT')
    else:
        with source.open('rb') as stream, atomic(destination) as target:
            shutil.copyfileobj(stream, target, 8*1024*1024)
    require(record(source)['sha256'] == record(destination)['sha256'], 'COPIED_BYTES_DRIFT')
    return record(destination)


def republish_atomic(path):
    before = record(path)
    # Windows cannot replace a destination while our source handle is open.
    with atomic(path) as target:
        with path.open('rb') as stream:
            shutil.copyfileobj(stream, target, 8*1024*1024)
    require(record(path) == before, 'ATOMIC_REPUBLICATION_BYTES_DRIFT')


def scalar_frame(rows):
    return pd.DataFrame([{k: json.dumps(native(v), sort_keys=True, ensure_ascii=False) if isinstance(v, (dict, list, tuple, np.ndarray))
                         else v for k, v in row.items()} for row in rows])


def input_archive(output, day, policy, context, snapshot_path, common, scientific_commit):
    ml = read(snapshot_path.parent / 'PRE_SOLVE_PERSISTENCE_AUDIT.json')
    for entry in ml['tables'].values(): verify_table(entry)
    snapshot = read(snapshot_path)
    sources = SOURCE_REPO / 'dayahead/artifacts/v37_r4a_per_day_aidc/days' / day
    request_columns = ['id', 'state_at_issue', 'submit_time', 'wallclock_req', 'gpus_requested', 'nodes_req',
                       'processors_req', 'memory_req', 'partition', 'qos', 'known_running_start']
    requests = pd.read_parquet(sources / 'V37_R4A_D1_SNAPSHOT.parquet', columns=request_columns)
    require(requests.submit_time.le(issue_time(day)).all(), 'DA_INPUT_NONCAUSAL_SUBMIT')
    requests['job_id'] = requests.id.astype(str)
    request_receipt = table(output / 'authority/JOB_REQUEST_INPUTS.parquet', requests)
    classes = pd.read_parquet(sources / 'V37_R4A_JOB_LEDGER.parquet', columns=['job_id', 'workload_class', 'protected', 'temporal_flexible'])
    classes.job_id = classes.job_id.astype(str)
    class_receipt = table(output / 'authority/JOB_CLASSES.parquet', classes)
    background = context.electrical.legacy_context[2]
    weather_path = next(Path(p) for p in context.input_shas if str(p).endswith('gfs_d1_weather.parquet'))
    weather = pd.read_parquet(weather_path)
    weather_receipt = table(output / 'authority/DAYAHEAD_WEATHER_96.parquet', weather)
    require(len(weather)==96, 'DAYAHEAD_WEATHER_AXIS')
    exo = document(output / 'authority/DAYAHEAD_EXOGENOUS_INPUTS.json',
        dict(schema=SCHEMA, target_day=day, role='DAYAHEAD_ONLY', background=background,
             weather=weather.to_dict(orient='list'), weather_source=record(weather_path),
             electrical_input_sources=context.input_shas))
    copy_atomic(snapshot_path, output / 'ml/ML_SNAPSHOT.json')
    for key in ('runtime_predictions', 'h4_windows'):
        copy_atomic(ml['tables'][key]['path'], output / 'ml' / Path(ml['tables'][key]['path']).name)
    document(output / 'ml/TRAINING_MEMBERSHIP_REFERENCE.json', ml['tables']['training_membership'])
    common_identity = dict(ML_snapshot_hash=record(snapshot_path)['sha256'],
        runtime_prediction_table_hash=ml['tables']['runtime_predictions']['sha256'],
        H4_raw_table_hash=ml['tables']['h4_windows']['sha256'], H4_cap_table_hash=ml['tables']['h4_windows']['sha256'],
        exogenous_DayAhead_input_hash=exo['sha256'], electrical_base_data_hash=context.v41_electrical_identity,
        common_service_hash=common['COMMON_DA_DURATION_SHA'])
    # This location is shared by policies but separated between pilot/full runs.
    daily = output.parent.parent / 'COMMON_INPUT_IDENTITY.json'
    if daily.exists(): require(read(daily) == common_identity, 'B0_B3_COMMON_INPUT_HASH_MISMATCH')
    else: document(daily, common_identity)
    document(output / 'authority/COMMON_INPUT_IDENTITY.json', common_identity)
    input_manifest = dict(schema=SCHEMA, role='DAYAHEAD_ONLY', Actual_reads=0, target_day=day,
        materialized_daily_slices=[request_receipt, class_receipt, weather_receipt, exo],
        sources=[record(sources / 'V37_R4A_D1_SNAPSHOT.parquet'), record(sources / 'V37_R4A_JOB_LEDGER.parquet')],
        ML=ml, common_input_receipt=common, electrical_certificate=context.v41_electrical_certificate,
        timestamps_UTC=[axis(day)[0].isoformat(), axis(day)[-1].isoformat()],
        units=dict(requests='GPU/node/core counts; memory in native Slurm request units; wallclock timedelta',
                   electrical='kW/kvar, voltage pu, current A', runtime='seconds and 900-second slots', H4='GPUh'))
    input_ref = document(output / 'authority/INPUT_MANIFEST.json', input_manifest)
    environment = dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
        packages={name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'pyarrow', 'lightgbm', 'gurobipy', 'OpenDSSDirect.py')})
    authority = dict(schema=SCHEMA, target_day=day, policy=policy, issue_time=issue_time(day),
        scientific_commit=scientific_commit, interface_freeze_commit=scientific_commit,
        commit_role='SOURCE_COMMIT_AT_EXECUTION; final interface receipt links pilot source manifest',
        ML_snapshot_hash=common_identity['ML_snapshot_hash'], input_manifest_hash=input_ref['sha256'],
        optimization_configuration_identity=record(ROOT / 'dayahead/v40g/optimizer.py'),
        electrical_configuration_identity=context.v41_electrical_certificate,
        policy_registry_identity=record(OUT / 'V41_POLICY_REGISTRY_FREEZE.json'), solver_environment_identity=environment,
        common_input_identity=common_identity)
    document(output / 'authority/AUTHORITY_MANIFEST.json', authority)
    return classes.set_index('job_id'), requests.set_index('job_id')


def aidc(output, day, policy, jobs, power, capacity, classes, requests, *, actual=False):
    from dayahead.v40g_segments.canonical import occupancy
    ids = list(capacity.aidc_ids); dates = axis(day)
    gpu = np.asarray(power['occupancy'] if actual else power['gpu'])
    it = np.asarray(power['IT'] if actual else power['it'])
    p = np.asarray(power['PCC_P'] if actual else power['pcc']); q = np.asarray(power['PCC_Q'] if actual else power['qcc'])
    require(gpu.shape == it.shape == p.shape == q.shape == (96, len(ids)), 'AIDC_SCIENTIFIC_AXIS')
    rows=[]
    for job in jobs:
        uid=job['job_uid']; row=dict(job)
        row.update(job_id=uid, admitted=job['AIDC_site'] != 'UNASSIGNED',
            workload_class=str(classes.loc[uid].workload_class), protected=bool(classes.loc[uid].protected),
            temporal_flexible=bool(classes.loc[uid].temporal_flexible),
            requested_nodes=int(requests.loc[uid].nodes_req), requested_cores=float(requests.loc[uid].processors_req),
            requested_memory_native=requests.loc[uid].memory_req)
        row['scheduled_start_UTC'] = issue_time(day)+pd.Timedelta(seconds=job['start_slot']*900)
        row['scheduled_end_UTC'] = issue_time(day)+pd.Timedelta(seconds=job['end_slot']*900)
        completion=job.get('actual_execution_end') if actual else job['end_slot']
        row['completion_lateness_vs_frozen_RW_seconds'] = None if completion is None else max(0, completion-job['RW_completion_slot'])*900
        rows.append(row)
    jf = scalar_frame(rows)
    table(output / 'JOB_DECISIONS.parquet', jf); document(output / 'JOB_DECISION_PAYLOAD.json', jobs)
    sf = pd.DataFrame(dict(target_day=day, policy=policy, slot=np.repeat(np.arange(96), len(ids)), timestamp=dates.repeat(len(ids)),
        IDC_id=np.tile(ids,96), GPU_capacity=np.tile([capacity.site_capacity[s] for s in ids],96),
        known_scheduled_GPU=gpu.ravel(), IT_load_kW=it.ravel(), PCC_P_kW=p.ravel(), PCC_Q_kvar=q.ravel()))
    sf['available_GPU_capacity'] = sf.GPU_capacity-sf.known_scheduled_GPU
    sf['future_work_headroom_GPU'] = sf.available_GPU_capacity
    fixed_jobs=[r for r in jobs if classes.loc[r['job_uid']].protected]
    flexible_jobs=[r for r in jobs if not classes.loc[r['job_uid']].protected]
    fixed,_=occupancy(fixed_jobs, ids, actual=actual); flexible,_=occupancy(flexible_jobs, ids, actual=actual)
    require(np.array_equal(fixed+flexible,gpu), 'AIDC_WORKLOAD_CLASS_CONSERVATION')
    sf['fixed_workload_GPU'] = fixed.ravel(); sf['flexible_workload_GPU'] = flexible.ravel()
    full_axis(sf, ['IDC_id'], [(s,) for s in ids]); table(output / 'SITE_TRAJECTORIES_96.parquet', sf)
    _, contributions=occupancy(jobs, ids, actual=actual)
    table(output / 'JOB_SLOT_OCCUPANCY.parquet', pd.DataFrame(contributions))
    document(output / 'AIDC_FIELD_AUTHORITY.json', dict(schema=SCHEMA, rows=len(jobs), site_slots=len(sf),
        slot_origin='daily tables: target-day midnight; decision start/end slots: issue-time origin',
        fixed_flexible_rule='protected flag in frozen V37 job-class authority',
        absent_unmodeled_fields=['per-job CPU/host power', 'time-indexed SLA/debt variable', 'site allocation of global H4 reserve',
                                 'additional PUE multiplier'], C1_applications=1,
        completion_lateness_role='evaluation versus existing RW completion; not a new objective variable',
        units=dict(GPU='count', P='kW', Q='kvar', service='seconds, 900-second slots, GPUh'), Actual=actual))
    return sf, jf


def mess(output, day, commands, *, realized=None, elements=None):
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    from dayahead.v40a.invariants import MOBILITY_FIELDS
    a=MessElectricalAuthority.from_repository(); dates=axis(day)
    rows=[]; routes=[]
    for c in commands:
        route={k: c[k] for k in MOBILITY_FIELDS if k in c}
        routes.append(route)
        row=dict(c, timestamp=dates[c['slot']], route_discrete_state_hash=digest(route),
            connected=c['mode']=='CONNECTED', charge_power_kW=max(-c['p_kw'],0), discharge_power_kW=max(c['p_kw'],0),
            active_power_limit_kW=a.active_power_limit_kw if c['mode']=='CONNECTED' else 0.,
            PCS_limit_kVA=a.pcs_kva if c['mode']=='CONNECTED' else 0.,
            energy_min_kWh=a.energy_min_kwh, energy_max_kWh=a.energy_max_kwh)
        if c.get('energy_safe_kwh') is not None:
            row['mobility_energy_kWh'] = c['energy_safe_kwh'] if c['departure_slot']==c['slot'] and c['mode']=='TRANSIT' else 0.
        if elements is not None and c['service_id']:
            suffix=c['service_id'].lower().replace('aidc','idc')
            buses=elements.loc[(elements.slot==c['slot']) & (elements.component=='MESS') &
                elements.element.str.endswith('_'+suffix), 'OpenDSS_bus'].unique().tolist()
            require(len(buses)==1, 'MESS_ELECTRICAL_BUS_MAPPING')
            row['electrical_bus']=buses[0]
        rows.append(row)
    frame=scalar_frame(rows); ids=sorted(frame.mess_id.unique())
    full_axis(frame,['mess_id'],[(m,) for m in ids]); require(len(ids)==4, 'MESS_FLEET_AXIS')
    table(output / 'DISCRETE_STATES.parquet', scalar_frame(routes))
    table(output / 'TRAJECTORIES_96.parquet', frame)
    route_ref=document(output / 'FROZEN_ROUTE_DISCRETE.json', dict(rows=routes, route_discrete_SHA=digest(routes)))
    if realized is not None:
        actual_frame=scalar_frame(realized['frame'].to_dict('records')); actual_frame['timestamp']=[dates[t] for t in actual_frame.slot]
        full_axis(actual_frame,['mess_id'],[(m,) for m in ids]); table(output / 'ACTUAL_TRAJECTORIES_96.parquet', actual_frame)
        document(output / 'REALIZED_TRAVERSALS.json', dict(moves=realized['moves'], frozen_routes=route_ref,
            route_search_calls=0, frozen_command_SHA=realized['frozen_commands_SHA']))
    return frame


def stage(output, name, jobs, commands, *, context, allowed, frozen, previous=None, info=None):
    from dayahead.v40g_segments.canonical import identities, planning_power
    from dayahead.v40a.invariants import MOBILITY_FIELDS
    value=dict(schema=SCHEMA, stage=name, AIDC_decision=jobs, MESS_commands=commands,
        AIDC_identity=identities(jobs), MESS_discrete_hash=digest([{k:r[k] for k in MOBILITY_FIELDS if k in r} for r in commands]),
        PQ_hash=digest([{k:r[k] for k in ('mess_id','slot','service_id','p_kw','q_kvar')} for r in commands]),
        allowed_to_change=allowed, frozen=frozen, ML_snapshot_hash=context.v41_ml_snapshot_sha256, info=info)
    value['changes_from_previous'] = None if previous is None else {
        key: native(previous[key]) != native(value[key]) for key in ('AIDC_identity','MESS_discrete_hash','PQ_hash')}
    document(output / 'optimization/stages' / f'{name}.json', value)
    from dayahead.v40a.grid import controls_from_trajectory
    from types import SimpleNamespace
    from .grid_archive import planning
    power=planning_power(jobs,context)
    controls=controls_from_trajectory(context.coefficients,power['pcc'],[SimpleNamespace(**c) for c in commands])
    planning(output / 'optimization/stages' / name, context.day, output.parent.name, name, context, controls)
    return value


def objective_ledger(output, objective, stages, final_grid, final_reserve, final_jobs):
    candidate=objective
    if candidate is None and 'COORDINATION' in stages:
        c=stages['COORDINATION']; candidate=c['a1_candidate_result'] if c['AIDC_FEEDBACK_ACCEPTED'] else None
    if candidate is None:
        # B2 uses exactly the prior B0 AIDC objective components; B3 rejected
        # A1 uses exactly its prior B1 components. MESS changes only P1.
        candidate=stages.get('BASE_OBJECTIVE')
    require(candidate is not None and len(candidate['OBJECTIVE_VECTOR'])==5, 'FINAL_OBJECTIVE_VECTOR_MISSING')
    vector=list(candidate['OBJECTIVE_VECTOR']); vector[0]=final_grid['rho_max']; vector[1]=final_reserve['mean_xi_GPUh']
    require(int(vector[2])==sum(bool(r.get('migration_selected')) for r in final_jobs), 'OBJECTIVE_MIGRATION_TRACE')
    ledger=dict(schema=SCHEMA, OBJECTIVE_VECTOR=vector, hierarchy=list(OBJECTIVE_HIERARCHY),
        stages=stages, component_source=candidate, objective_is_vector=True, scalar_penalty=None,
        M1_MF_authority='existing bounded rho objective; P2/P3/P4/P5 AIDC components held fixed during MESS',
        solver_pass_receipts=[record(p) for p in sorted((output / 'optimization/solver_passes').glob('*.json'))])
    document(output / 'optimization/OBJECTIVE_LEDGER.json', ledger)
    return ledger


def freeze(output, decision_sha, snapshot_sha, stages):
    receipt=dict(schema=SCHEMA, DayAhead_decision_SHA=decision_sha, ML_snapshot_SHA=snapshot_sha,
        AIDC_decision=record(output/'aidc/JOB_DECISION_PAYLOAD.json'),
        MESS_route_discrete=record(output/'mess/FROZEN_ROUTE_DISCRETE.json'),
        grid_PQ_commands=record(output/'FROZEN_MESS_COMMANDS.json'),
        AIDC_PQ_commands=record(output/'FROZEN_AIDC_POWER.npz'),
        Joint_decision=record(output/'FROZEN_JOINT_DECISION.json'),
        stage_snapshots={p.stem:record(p) for p in sorted((output/'optimization/stages').glob('*.json'))},
        Actual_data_opened=False)
    require(set(stages) <= set(receipt['stage_snapshots']), 'STAGE_SNAPSHOT_MISSING')
    document(output/'optimization/STAGE_TRANSITION_LEDGER.json', dict(schema=SCHEMA, stages=receipt['stage_snapshots']))
    return document(output/'JOINT_FREEZE_RECEIPT.json', receipt)


def critical(output, voltage, branch, system, h4, site, mess_frame, *, actual=False):
    rows=[]
    def event(name, frame, field, unit, maximum=True):
        index=frame[field].idxmax() if maximum else frame[field].idxmin(); r=frame.loc[index]
        rows.append(dict(event=name, value=float(r[field]), unit=unit,
            location=json.dumps(native({k:r[k] for k in ('slot','timestamp','node','line_id','phase','IDC_id','mess_id','window_start','window_end') if k in r}),sort_keys=True)))
    lines=branch[branch.kind=='line']
    event('rho_max',lines,'loading_pu','pu'); event('minimum_voltage',voltage,'voltage_pu','pu',False)
    event('maximum_voltage',voltage,'voltage_pu','pu'); event('maximum_line_current',lines,'current_A','A')
    event('maximum_H4_shortfall',h4,'reserve_shortfall_xi_GPUh','GPUh')
    event('maximum_AIDC_load',site,'PCC_P_kW','kW')
    event('maximum_MESS_discharge',mess_frame,'P_EXEC' if actual else 'discharge_power_kW','kW')
    return table(output/'audit/CRITICAL_PHYSICAL_EVENTS.parquet',pd.DataFrame(rows))


def artifact_entry(path, root, stage):
    entry=record(path); extension=path.suffix.lower(); rows=None; schema=None
    if extension=='.parquet':
        frame=pd.read_parquet(path); rows=len(frame); schema=str(pq.read_schema(path))
    elif extension=='.json':
        value=read(path); rows=len(value) if isinstance(value,list) else None
        schema=value.get('schema', SCHEMA) if isinstance(value,dict) else SCHEMA
    elif extension=='.npz':
        with np.load(path,allow_pickle=False) as z:
            schema={k:dict(shape=list(z[k].shape),dtype=str(z[k].dtype)) for k in z.files}
    elif extension=='.csv':
        try:
            frame=pd.read_csv(path); rows=len(frame); schema=list(frame.columns)
        except pd.errors.EmptyDataError:
            rows=0; schema=[]
    else:
        # Text solver logs and model files are provenance, never replacements
        # for the required numerical tables.
        with path.open('rb') as stream:
            while stream.read(8*1024*1024): pass
        schema='NATIVE_PROVENANCE_BYTES'
    require(record(path)==entry,'ARTIFACT_CHANGED_DURING_READBACK')
    return dict(relative_path=path.relative_to(root).as_posix(),artifact_type=extension.lstrip('.'),
        row_count=rows,sha256=entry['sha256'],bytes=entry['bytes'],schema_version=schema,
        stage=stage,unit='column names and FIELD_AUTHORITY/AXIS_CONTRACT define scientific units',readback=True)


def verify_manifest(path):
    path=Path(path); receipt=read(path); root=path.parent
    require(receipt['schema']==SCHEMA and receipt['status']=='PASS','INVALID_SCIENTIFIC_MANIFEST')
    names={entry['relative_path'] for entry in receipt['artifacts']}
    excluded={path.name,'UNIT_RECEIPT.json'}
    if path.name=='SCIENTIFIC_MANIFEST.json': excluded.update(('DAYAHEAD_RECEIPT.json','ACTUAL_RECEIPT.json'))
    existing={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.parent==root and p.name not in excluded}
    existing.update(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.parent!=root)
    require(existing==names,'ORPHAN_OR_MISSING_SCIENTIFIC_ARTIFACT')
    for entry in receipt['artifacts']:
        file=root/entry['relative_path']; file.resolve().relative_to(root.resolve())
        require(artifact_entry(file,root,entry['stage'])==entry,'SCIENTIFIC_ARTIFACT_READBACK_DRIFT:'+str(file))
    return receipt


def seal(output, phase):
    base=['authority/AUTHORITY_MANIFEST.json','authority/INPUT_MANIFEST.json','authority/COMMON_INPUT_IDENTITY.json',
          'aidc/JOB_DECISIONS.parquet','aidc/JOB_DECISION_PAYLOAD.json','aidc/SITE_TRAJECTORIES_96.parquet',
          'mess/DISCRETE_STATES.parquet','mess/TRAJECTORIES_96.parquet','mess/FROZEN_ROUTE_DISCRETE.json',
          'grid/BUS_PHASE_VOLTAGES.parquet','grid/BRANCH_PHASE_CURRENTS.parquet','grid/FEEDER_SYSTEM_96.parquet',
          'grid/GRID_AXIS_CONTRACT.json','audit/CRITICAL_PHYSICAL_EVENTS.parquet','H4_OPTIMIZER_WINDOWS.parquet']
    if phase=='dayahead':
        base += ['ml/ML_SNAPSHOT.json','ml/PENDING_RUNTIME_PREDICTIONS.parquet','ml/H4_WINDOW_PREDICTIONS.parquet',
                 'ml/TRAINING_MEMBERSHIP_REFERENCE.json','optimization/OBJECTIVE_LEDGER.json',
                 'optimization/STAGE_TRANSITION_LEDGER.json','JOINT_FREEZE_RECEIPT.json','FROZEN_JOINT_DECISION.json']
    else:
        base += ['authority/ACTUAL_SOURCE_MANIFEST.json','authority/ACTUAL_RUNTIME_INPUTS.parquet',
                 'authority/ACTUAL_EXOGENOUS_96.parquet','mess/ACTUAL_TRAJECTORIES_96.parquet','mess/REALIZED_TRAVERSALS.json',
                 'H4_ACTUAL_WINDOW_EVALUATION.parquet','comparison/DAYAHEAD_VS_ACTUAL.parquet',
                 'comparison/AIDC_SLOT_DELTAS.parquet','comparison/MESS_SLOT_DELTAS.parquet',
                 'comparison/MESS_TRAVEL_DELTAS.parquet',
                 'comparison/GRID_SLOT_DELTAS.parquet','ACTUAL_BOUNDARY_RECEIPT.json']
    for name in base: require((output/name).is_file(),'REQUIRED_SCIENTIFIC_FILE_MISSING:'+name)
    sf=pd.read_parquet(output/'aidc/SITE_TRAJECTORIES_96.parquet')
    full_axis(sf,['IDC_id'],[(s,) for s in sorted(sf.IDC_id.unique())]); require(sf.IDC_id.nunique()==12,'AIDC_SITE_COUNT')
    mf=pd.read_parquet(output/'mess/TRAJECTORIES_96.parquet')
    full_axis(mf,['mess_id'],[(m,) for m in sorted(mf.mess_id.unique())]); require(mf.mess_id.nunique()==4,'MESS_COUNT')
    gc=read(output/'grid/GRID_AXIS_CONTRACT.json')
    full_axis(pd.read_parquet(output/'grid/BUS_PHASE_VOLTAGES.parquet'),['node','phase'],gc['node_axis'])
    full_axis(pd.read_parquet(output/'grid/BRANCH_PHASE_CURRENTS.parquet'),['line_id','phase'],gc['branch_axis'])
    h4=pd.read_parquet(output/'H4_OPTIMIZER_WINDOWS.parquet')
    require(len(h4)==81 and h4.window_start.is_unique and (h4.service_level==.85).all(),'H4_COMPLETE_AXIS')
    path=output/'SCIENTIFIC_MANIFEST.json'
    paths=[p for p in sorted(output.rglob('*')) if p.is_file() and p!=path and p.name not in ('DAYAHEAD_RECEIPT.json','ACTUAL_RECEIPT.json')]
    require(not any(p.suffix=='.tmp' for p in paths),'UNFINISHED_SCIENTIFIC_WRITE')
    # Publish inherited producer files with a final durable atomic replacement
    # once all producers have closed them; bytes and scientific values unchanged.
    for p in paths:
        republish_atomic(p)
    entries=[artifact_entry(p,output,phase) for p in paths]
    document(path,dict(schema=SCHEMA,status='PASS',phase=phase,required=base,artifacts=entries,
        complete_temporal_coverage=True,exact_readback=True,scientific_file_count=len(entries)))
    verify_manifest(path)
    return record(path)


def complete_unit(root):
    root=Path(root)
    for phase in ('dayahead','actual'):
        verify_manifest(root/phase/'SCIENTIFIC_MANIFEST.json')
        receipt=read(root/phase/(phase.upper()+'_RECEIPT.json'))
        require(receipt['status']=='COMPLETE','UNIT_PHASE_NOT_COMPLETE')
        for entry in receipt['files'].values(): require(record(entry['path'])==entry,'UNIT_PHASE_FILE_DRIFT')
    da=read(root/'dayahead/authority/COMMON_INPUT_IDENTITY.json'); ac=read(root/'actual/authority/COMMON_INPUT_IDENTITY.json')
    require(da==ac,'ACTUAL_COMMON_INPUT_CHANGED')
    path=root/'UNIT_SCIENTIFIC_MANIFEST.json'
    entries=[artifact_entry(p,root,p.relative_to(root).parts[0]) for p in sorted(root.rglob('*'))
             if p.is_file() and p!=path and p.name!='UNIT_RECEIPT.json']
    document(path,dict(schema=SCHEMA,status='PASS',artifacts=entries,common_identity=da,
        all_required_phase_outputs_reopened=True,Actual_dayahead_separated=True))
    verify_manifest(path)
    return record(path)


def actual_inputs(output, day, decision, da_output, obs, exo, mess_result, workload):
    boundary=read(output/'ACTUAL_BOUNDARY_RECEIPT.json')
    joint=read(da_output/'JOINT_FREEZE_RECEIPT.json')
    require(joint['DayAhead_decision_SHA']==boundary['decision_SHA'] and not joint['Actual_data_opened'], 'ACTUAL_WITHOUT_CAUSAL_FREEZE')
    runtime_path=SOURCE_REPO/'dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet'
    uid=sorted(j['job_uid'] for j in decision['AIDC_decision'])
    runtime=pd.DataFrame([obs[j] for j in uid]); runtime['job_id']=uid
    runtime_ref=table(output/'authority/ACTUAL_RUNTIME_INPUTS.parquet',runtime)
    ef=exo['weather'].reset_index(drop=True).copy(); ef.insert(0,'timestamp',axis(day)); ef.insert(0,'slot',range(96))
    ef['demand_MW']=exo['demand_mw']; ef['PV_MW']=exo['pv_mw']
    exo_ref=table(output/'authority/ACTUAL_EXOGENOUS_96.parquet',ef)
    contributors=workload['source_membership']; require(contributors is not None,'ACTUAL_ARRIVAL_MEMBERSHIP_MISSING')
    verify_table(contributors['daily_slice'])
    copy_atomic(contributors['daily_slice']['path'],output/'authority/ACTUAL_WORKLOAD_CONTRIBUTORS.parquet')
    traffic=[]
    for source in {r['actual_traffic_source']['path']:r['actual_traffic_source'] for r in mess_result['moves']}.values():
        require(record(source['path'])==source,'ACTUAL_TRAFFIC_HASH_DRIFT')
        f=pd.read_parquet(source['path'],columns=['slot5','reduced_link_id','final_tt_sec'])
        traffic.append(dict(source=source,slice=table(output/'authority/ACTUAL_TRAFFIC_INPUTS.parquet',f),
                            unit='seconds per 5-min link entry',slots=288))
    sources=dict(schema=SCHEMA,role='ACTUAL_ONLY_AFTER_VERIFIED_JOINT_FREEZE',target_day=day,
        verified_joint_freeze=record(da_output/'JOINT_FREEZE_RECEIPT.json'),
        runtime=dict(source=record(runtime_path),slice=runtime_ref,units='UTC start/end; seconds'),
        exogenous=dict(sources=exo['authority'],slice=exo_ref,units='regional demand/PV MW, temperature C, relative humidity percent'),
        arriving_workload=contributors,traffic=traffic,
        traffic_applicability='USED_FOR_FROZEN_ROUTES' if traffic else 'NO_TRAVEL_COMMITMENTS_NO_TRAFFIC_READER_CALLED',
        timestamps_UTC=[axis(day)[0].isoformat(),axis(day)[-1].isoformat()],Actual_optimizer_calls=0)
    document(output/'authority/ACTUAL_SOURCE_MANIFEST.json',sources)
    document(output/'authority/INPUT_MANIFEST.json',sources)
    common=read(da_output/'authority/COMMON_INPUT_IDENTITY.json')
    document(output/'authority/COMMON_INPUT_IDENTITY.json',common)
    auth=read(da_output/'authority/AUTHORITY_MANIFEST.json')
    auth.update(role='ACTUAL',input_manifest_hash=record(output/'authority/INPUT_MANIFEST.json')['sha256'],
                exact_DayAhead_freeze=record(da_output/'JOINT_FREEZE_RECEIPT.json'))
    document(output/'authority/AUTHORITY_MANIFEST.json',auth)


def delta_table(output, name, da, actual, keys, fields):
    require(not da.duplicated(keys).any() and not actual.duplicated(keys).any(), 'DUPLICATE_COMPARISON_AXIS')
    joined=da[keys+fields].merge(actual[keys+fields],on=keys,suffixes=('_dayahead','_actual'),validate='one_to_one',how='outer',indicator=True)
    require((joined['_merge']=='both').all(),'DAYAHEAD_ACTUAL_AXIS_MISMATCH')
    joined=joined.drop(columns='_merge')
    for col in fields: joined[col+'_delta']=joined[col+'_actual']-joined[col+'_dayahead']
    table(output/name,joined)
    return joined


def comparisons(output, da_output):
    site_da=pd.read_parquet(da_output/'aidc/SITE_TRAJECTORIES_96.parquet'); site_ac=pd.read_parquet(output/'aidc/SITE_TRAJECTORIES_96.parquet')
    delta_table(output/'comparison','AIDC_SLOT_DELTAS.parquet',site_da,site_ac,['slot','IDC_id'],
        ['known_scheduled_GPU','future_work_headroom_GPU','IT_load_kW','PCC_P_kW','PCC_Q_kvar'])
    mda=pd.read_parquet(da_output/'mess/TRAJECTORIES_96.parquet').rename(columns={'p_kw':'P_EXEC','q_kvar':'Q_EXEC','soc_fraction':'SoC_before'})
    mac=pd.read_parquet(output/'mess/ACTUAL_TRAJECTORIES_96.parquet')
    delta_table(output/'comparison','MESS_SLOT_DELTAS.parquet',mda,mac,['slot','mess_id'],['P_EXEC','Q_EXEC','SoC_before'])
    travel=travel_comparisons(output/'comparison',mda,read(output/'mess/REALIZED_TRAVERSALS.json')['moves'])
    gda=pd.read_parquet(da_output/'grid/FEEDER_SYSTEM_96.parquet'); gac=pd.read_parquet(output/'grid/FEEDER_SYSTEM_96.parquet')
    delta_table(output/'comparison','GRID_SLOT_DELTAS.parquet',gda,gac,['slot'],
        ['rho_max','Vmin_pu','Vmax_pu','max_line_current_A','feeder_import_P_kW','feeder_import_Q_kvar','loss_P_kW','loss_Q_kvar'])
    hda=pd.read_parquet(da_output/'H4_OPTIMIZER_WINDOWS.parquet'); hac=pd.read_parquet(output/'H4_OPTIMIZER_WINDOWS.parquet')
    delta_table(output/'comparison','H4_WINDOW_DELTAS.parquet',hda,hac,['window_start','window_end'],
        ['ACTIONABLE_H4_GPUh','available_headroom_GPUh','reserve_shortfall_xi_GPUh'])
    bda=pd.read_parquet(da_output/'grid/BRANCH_PHASE_CURRENTS.parquet'); bac=pd.read_parquet(output/'grid/BRANCH_PHASE_CURRENTS.parquet')
    delta_table(output/'comparison','BRANCH_PHASE_DELTAS.parquet',bda,bac,['slot','line_id','phase'],
        ['current_A','loading_pu','P_flow_kW','Q_flow_kvar'])
    vda=pd.read_parquet(da_output/'grid/BUS_PHASE_VOLTAGES.parquet'); vac=pd.read_parquet(output/'grid/BUS_PHASE_VOLTAGES.parquet')
    delta_table(output/'comparison','BUS_PHASE_DELTAS.parquet',vda,vac,['slot','node','phase'],['voltage_pu','voltage_angle_degrees'])
    jda=pd.read_parquet(da_output/'aidc/JOB_DECISIONS.parquet'); jac=pd.read_parquet(output/'aidc/JOB_DECISIONS.parquet')
    delta_table(output/'comparison','JOB_OUTCOME_DELTAS.parquet',jda,jac,['job_id'],['completion_lateness_vs_frozen_RW_seconds'])
    rows=[]
    def metric(name,a,b,unit,relative=False):
        rows.append(dict(metric=name,dayahead=float(a),actual=float(b),delta=float(b-a),unit=unit,
            relative_delta_if_meaningful=float((b-a)/a) if relative and abs(a)>1e-12 else None))
    metric('AIDC_energy',site_da.PCC_P_kW.sum()*.25,site_ac.PCC_P_kW.sum()*.25,'kWh',True)
    metric('GPU_occupancy',site_da.known_scheduled_GPU.sum()*.25,site_ac.known_scheduled_GPU.sum()*.25,'GPUh',True)
    metric('H4_mean_shortfall',hda.reserve_shortfall_xi_GPUh.mean(),hac.reserve_shortfall_xi_GPUh.mean(),'GPUh')
    metric('rho_max',gda.rho_max.max(),gac.rho_max.max(),'pu')
    metric('Vmin',gda.Vmin_pu.min(),gac.Vmin_pu.min(),'pu'); metric('Vmax',gda.Vmax_pu.max(),gac.Vmax_pu.max(),'pu')
    metric('maximum_line_current',gda.max_line_current_A.max(),gac.max_line_current_A.max(),'A',True)
    metric('feeder_import_energy',gda.feeder_import_P_kW.sum()*.25,gac.feeder_import_P_kW.sum()*.25,'kWh',True)
    metric('MESS_discharge_energy',np.maximum(mda.P_EXEC,0).sum()*.25,np.maximum(mac.P_EXEC,0).sum()*.25,'kWh',True)
    metric('MESS_travel_time',travel.travel_seconds_dayahead.sum(),travel.travel_seconds_actual.sum(),'seconds',True)
    metric('MESS_mobility_energy',travel.mobility_energy_kWh_dayahead.sum(),travel.mobility_energy_kWh_actual.sum(),'kWh',True)
    metric('completion_lateness_vs_RW',jda.completion_lateness_vs_frozen_RW_seconds.sum(),jac.completion_lateness_vs_frozen_RW_seconds.sum(),'job_seconds')
    return table(output/'comparison/DAYAHEAD_VS_ACTUAL.parquet',pd.DataFrame(rows))


def travel_comparisons(output, commands, moves):
    """Compare the existing safe route forecast with fixed-route realized travel."""
    departures=commands[commands.departure_slot.eq(commands.slot)]
    expected={(r.mess_id,int(r.slot)):r for r in departures.itertuples()}
    require(len(expected)==len(departures), 'DUPLICATE_TRAVEL_DEPARTURE')
    require(len(moves)==len(expected) and {(m['mess_id'],int(m['departure_slot'])) for m in moves}==set(expected),
            'DAYAHEAD_ACTUAL_TRAVEL_AXIS_MISMATCH')
    columns=['mess_id','departure_slot','frozen_route_SHA','travel_seconds_dayahead','travel_seconds_actual',
             'travel_seconds_delta','arrival_slot_dayahead','arrival_slot_actual','arrival_slot_delta',
             'connection_ready_slot_dayahead','connection_ready_slot_actual','connection_ready_slot_delta',
             'mobility_energy_kWh_dayahead','mobility_energy_kWh_actual','mobility_energy_kWh_delta']
    rows=[]
    for move in moves:
        c=expected[(move['mess_id'],int(move['departure_slot']))]
        links=json.loads(c.route_link_ids) if isinstance(c.route_link_ids,str) else list(c.route_link_ids)
        require(links==move['route_link_ids'], 'ACTUAL_ROUTE_CHANGED')
        row=dict(mess_id=c.mess_id,departure_slot=int(c.slot),frozen_route_SHA=digest(links))
        for field,da,ac in (
            ('travel_seconds',c.route_safe_eta_sec,move['actual_eta_seconds']),
            ('arrival_slot',c.slot+c.route_safe_eta_sec/900,move['actual_arrival_slot']),
            ('connection_ready_slot',c.connection_ready_slot,move['actual_connection_ready_slot']),
            ('mobility_energy_kWh',c.energy_safe_kwh,move['actual_travel_energy_kWh'])):
            require(np.isfinite([da,ac]).all(), 'MISSING_AUTHORITATIVE_TRAVEL_VALUE')
            row.update({field+'_dayahead':float(da),field+'_actual':float(ac),field+'_delta':float(ac-da)})
        rows.append(row)
    frame=pd.DataFrame(rows,columns=columns)
    table(output/'MESS_TRAVEL_DELTAS.parquet',frame)
    return frame
