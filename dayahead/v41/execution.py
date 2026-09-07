"""Policy-day entry points. Actual is reachable only across a verified seal."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
import numpy as np

from dayahead.paper_analysis.storage import read, write_json, write_npz, digest
from dayahead.v40h.identity import manifest, verify_manifest, verify_file
from dayahead.v40g_segments.canonical import import_frozen, identities, planning_power
from dayahead.v40a.grid import evaluate_grid, controls_from_trajectory
from .data import RUNTIME, SOURCE_REPO, issue_time
from .preflight import ROOT, OUT, record
from .reserve import require, bind, diagnostics

RUNS = RUNTIME / 'pilot' if os.environ.get('V41_PILOT') == '1' else RUNTIME


def now(): return datetime.now(timezone.utc).isoformat()


def science():
    paths = list((ROOT / 'dayahead/v41').glob('*.py'))
    paths += [ROOT / p for p in ('dayahead/v40g/optimizer.py','dayahead/v40g/domain.py',
        'dayahead/v40g_segments/canonical.py','dayahead/v40g_segments/b3.py','dayahead/v40h/feedback.py','dayahead/v40a/feedback.py',
        'dayahead/v40h/pre_day_complete.py')]
    paths += [p for p in (ROOT/'dayahead/v41r1').glob('migration*.py')]
    paths += [p for p in (ROOT/'dayahead/v41r1').glob('*.py') if p.name in (
        'feasible_seed.py','exact_aggregation.py','candidate_manifest.py','bounded_solver.py',
        'bounded_mess.py','bounded_runtime.py','early_stop.py')]
    paths += [ROOT/'dayahead/v40h/recourse.py']
    return manifest(paths, ROOT)


def commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def verify_dayahead(day, policy):
    path = RUNS / day / policy / 'dayahead/DAYAHEAD_RECEIPT.json'
    receipt = read(path)
    require(receipt.get('schema')=='V41_PHASE_RECEIPT_V1','LEGACY_DAYAHEAD_RECEIPT_FORBIDDEN')
    require(receipt['status'] == 'COMPLETE', 'DAYAHEAD_NOT_COMPLETE')
    retained_sources=None
    if receipt['science']['manifest_SHA'] == science()['manifest_SHA']:
        verify_manifest(receipt['science'])
    else:
        from .retention import validate
        retained_sources=validate(receipt,science())
    for file in receipt['files'].values():
        require(record(file['path']) == file, 'DAYAHEAD_OUTPUT_HASH_DRIFT')
    from .scientific_archive import verify_manifest as verify_scientific_manifest
    verify_scientific_manifest(path.parent/'SCIENTIFIC_MANIFEST.json')
    from dayahead.v40h.identity import verify_bound_files
    generation=read(path.parent/'GENERATION_INPUT_IDENTITY.json')
    if retained_sources is None: verify_bound_files(generation)
    else:
        from .retention import verify_bound
        verify_bound(generation,retained_sources)
    frozen = read(receipt['files']['decision']['path'])
    require(frozen['decision_SHA'] == digest(frozen['decision']), 'DAYAHEAD_DECISION_CONTENT_DRIFT')
    return frozen['decision'], receipt


def validate_reused_base(base, snapshot_record, common, context):
    require(base['ML_snapshot']==snapshot_record,'POLICY_SPECIFIC_ML_INPUT_FORBIDDEN')
    require(base['electrical']==context.v41_electrical_certificate,'B1_A0_CURRENT_ELECTRICAL_GENERATION_MISMATCH')
    require(base['common_service_SHA']==common['COMMON_DA_DURATION_SHA'],'B1_A0_CURRENT_SERVICE_AUTHORITY_MISMATCH')


def off_commands():
    from dayahead.v35.execution import MESS_INITIAL
    from dayahead.mess_physics import E_INITIAL_KWH, CAPACITY_KWH
    return [dict(mess_id=m, slot=t, service_id=s, p_kw=0., q_kvar=0., mode='CONNECTED',
        departure_slot=None, origin_service_id=None, destination_service_id=None, route_link_ids=[],
        connection_ready_slot=None, battery_energy_kwh=E_INITIAL_KWH, soc_fraction=E_INITIAL_KWH / CAPACITY_KWH)
        for t in range(96) for m, s in sorted(MESS_INITIAL.items())]


def command_arrays(rows):
    ids = sorted({r['mess_id'] for r in rows}); by = {(r['slot'], r['mess_id']): r for r in rows}
    require(len(by) == 384 and len(rows) == 384, 'FROZEN_MESS_COMMAND_AXIS')
    p = np.array([[by[t, m]['p_kw'] for m in ids] for t in range(96)])
    q = np.array([[by[t, m]['q_kvar'] for m in ids] for t in range(96)])
    locations = np.array([[by[t, m]['service_id'] or 'TRANSIT_UNAVAILABLE' for m in ids] for t in range(96)])
    return p, q, ids, locations


def m1_identity(day, jobs, pcc, context):
    from dayahead.v40h.cache import execution_identity
    from dayahead.v40a.invariants import digest as mess_digest
    inventory = read(SOURCE_REPO / 'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json')
    traffic = inventory['traffic'][day]
    segment = identities(jobs); power = planning_power(jobs, context)
    values = dict(campaign_SHA=digest({'V41_science': science()['manifest_SHA'], 'ML': context.v41_ml_snapshot_sha256}),
        A0_decision_SHA=segment['canonical_decision_SHA'], A0_segment_SHA=segment['segment_and_event_SHA'],
        A0_GPU_SHA=mess_digest(power['gpu']), A0_PCC_SHA=mess_digest(pcc),
        electrical_coefficients=[c.coefficient_sha256 for c in context.coefficients],
        traffic_forecast=traffic['forecast'], road_graph={'files':inventory['road_graph'],'canonical_SHA':traffic['forecast']['graph_SHA']}, route_table=traffic['route_table'],
        service_road_mapping=inventory['road_graph']['service_nodes'], mobility_physics=inventory['MESS_mobility'],
        MESS_electrical=inventory['MESS_electrical'], connection_delay={'source': inventory['MESS_mobility']},
        route_energy={'source': inventory['MESS_mobility']}, MESS_PCC_mapping=inventory['service_PCC_mapping'],
        K=200, beam_width=2, fallback_widths=[4], seed=2, WorkLimit_tiers=[60, 180, 300],
        solver_settings={'Threads': 4, 'route_search_workers': 1}, source_manifest=science(),
        V41_ML_snapshot_SHA=context.v41_ml_snapshot_sha256)
    return execution_identity(values)


def run_m1(day, jobs, context, output):
    if getattr(context,'v41_bounded_compute',None):
        from dayahead.v41r1.bounded_mess import run
        return run(day,jobs,context,output)
    from dayahead.v40h.mobility import search_once
    from dayahead.v40h.beam_driver import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    pcc = planning_power(jobs, context)['pcc']; identity = m1_identity(day, jobs, pcc, context)
    write_json(output / 'M1_IDENTITY.json', identity)
    def progress(value):
        write_json(output / 'M1_PROGRESS.json', dict(at=now(), detail=value))
    from .solver_observer import observe
    with observe(output.parent / 'optimization/solver_passes', 'M1'):
        result = search_once(ROOT, day, pcc, context, output, progress, identity)
    from .scientific_archive import document
    document(output / 'M1_RESULT.json', result)
    return MessTrajectory(tuple(_restore_slots(result['trajectory_slots']))), result


def dayahead(day, policy):
    require(policy in ('B0', 'B1', 'B2', 'B3'), 'UNKNOWN_POLICY')
    output = RUNS / day / policy / 'dayahead'
    if (output / 'DAYAHEAD_RECEIPT.json').exists():
        return verify_dayahead(day, policy)[1]
    require(not (output / 'FROZEN_JOINT_DECISION.json').exists(), 'PRESERVE_INCOMPLETE_DAYAHEAD_FREEZE')
    from .snapshot import create
    from .common import build
    from .electrical import load
    snapshot_path, snapshot_seal = create(day)
    context = load(day); bind(context, snapshot_path, snapshot_seal['snapshot']['sha256'])
    from dayahead.v41r1.bounded_runtime import activate
    activate(context,policy,output)
    from .persistence import optimizer_rows
    from dayahead.v41r1.migration_persistence import pre_solve
    persistence = pre_solve(day, snapshot_path, context.capacity)
    source = science(); started = now()
    write_json(output / 'DAYAHEAD_STARTED.json', dict(day=day, policy=policy, started_at=started,
        scientific_commit=commit(), source=source, snapshot=snapshot_seal['snapshot'],
        electrical=context.v41_electrical_certificate))
    try:
        reference, common = build(day, snapshot_path, context.capacity)
        from dayahead.v41r1.migration_audit import persist as persist_migration_domain
        persist_migration_domain(output/'authority/migration_before_solve',day,policy,reference,import_frozen(reference),context)
        from . import scientific_archive as archive
        from .solver_observer import observe as observe_solver
        classes, requests = archive.input_archive(output, day, policy, context, snapshot_path, common, commit())
        generation=archive.document(output/'GENERATION_INPUT_IDENTITY.json',dict(schema='V41_GENERATION_INPUT_V1',
            target_day=day,policy=policy,source=source,ML_snapshot=record(snapshot_path),
            common_service_SHA=common['COMMON_DA_DURATION_SHA'],electrical=context.v41_electrical_certificate,
            input_manifest=record(output/'authority/INPUT_MANIFEST.json'),captured_before_optimizer=True,Actual_reads=0))
        canonical_reference = import_frozen(reference)
        power0 = planning_power(canonical_reference, context)
        if getattr(context,'v41_bounded_compute',None) and policy in ('B0','B1'):
            from dayahead.v41r1.feasible_seed import policy_reference
            policy_reference(reference,context,output/'policy_seed',policy)
        objective = None; stages = {}; trajectory = None; traces = {}; previous_stage = None
        def trace(name, current, mess=None, allowed=(), frozen=(), info=None):
            nonlocal previous_stage
            cmds=off_commands() if mess is None else [asdict(s) for s in mess.slots]
            value=archive.stage(output,name,current,cmds,context=context,allowed=allowed,frozen=frozen,previous=previous_stage,info=info)
            traces[name]=value; previous_stage=value
        if policy == 'B0':
            jobs = canonical_reference
            from .objectives import evaluate
            objective = evaluate(reference, reference, context)
        elif policy == 'B1':
            from dayahead.v40g.optimizer import solve
            with observe_solver(output / 'optimization/solver_passes', 'A0'):
                result = solve(reference, power0['pcc'], context, output / 'A0')
            require(result['status'] == 'PASS', 'B1_JOINT_SOLVE_FAILED')
            jobs = import_frozen(result['jobs']); stages['A0'] = result
            from .objectives import evaluate
            objective = evaluate(reference, result['jobs'], context)
            require(np.allclose(objective['OBJECTIVE_VECTOR'], result['OBJECTIVE_VECTOR'], rtol=0, atol=1e-9), 'B1_OBJECTIVE_RECALCULATION')
        else:
            base_policy = 'B0' if policy == 'B2' else 'B1'
            base, base_receipt = verify_dayahead(day, base_policy)
            validate_reused_base(base,snapshot_seal['snapshot'],common,context)
            jobs = deepcopy(base['AIDC_decision'])
            if getattr(context,'v41_bounded_compute',None):
                from dayahead.v41r1.feasible_seed import policy_reference
                policy_reference(jobs,context,output/'policy_seed',policy)
            stages['BASE_OBJECTIVE'] = read(RUNS / day / base_policy / 'dayahead/optimization/OBJECTIVE_LEDGER.json')
            stages['A0_REUSE'] = dict(source_policy=base_policy, source=record(RUNS / day / base_policy / 'dayahead/DAYAHEAD_RECEIPT.json'),
                AIDC_decision_SHA=identities(jobs)['canonical_decision_SHA'], additional_A0_optimization_calls=0)
            if policy == 'B2':
                trace('A0_OUTPUT',jobs,frozen=('exact B0 reference AIDC','common runtime and ML'))
                trace('M1_INPUT',jobs,allowed=('MESS route/discrete/P/Q/SoC',),frozen=('AIDC',))
                trajectory, stages['M1'] = run_m1(day, jobs, context, output / 'M1')
                trace('M1_OUTPUT',jobs,trajectory,allowed=('MESS route/discrete/P/Q/SoC',),frozen=('AIDC',),info=stages['M1'])
            else:
                trace('A0_OUTPUT',jobs,frozen=('exact accepted B1 decision','common runtime and ML'))
                optimizer_rows(output / 'A0', context.v41_ml_snapshot, context.v41_ml_snapshot_sha256,
                               diagnostics(context.v41_ml_snapshot, context.capacity, planning_power(jobs, context)['gpu']))
                from dayahead.v40g_segments.b3 import coordinate_segments
                from dayahead.v40h.feedback import solve_feedback
                from dayahead.v40h.recourse import solve_fixed_route
                def m1_callback(pcc, certificate):
                    trace('M1_INPUT',jobs,allowed=('MESS route/discrete/P/Q/SoC',),frozen=('AIDC',),info=certificate)
                    found, info=run_m1(day,jobs,context,output/'M1')
                    trace('M1_OUTPUT',jobs,found,allowed=('MESS route/discrete/P/Q/SoC',),frozen=('AIDC',),info=info)
                    return found,info
                def a1_callback(current,mess):
                    trace('A1_INPUT',current,mess,allowed=('authorized PENDING site/start',),frozen=('M1 grid/PQ','RUNNING site/start/end/migration','terminal','ML'))
                    with observe_solver(output/'optimization/solver_passes','A1'):
                        result=solve_feedback(current,mess,context)
                    context.v41_a1_reference_choices=(deepcopy(current),deepcopy(result['jobs']))
                    trace('A1_CANDIDATE_OUTPUT',result['jobs'],mess,allowed=('authorized PENDING site/start',),frozen=('M1 grid/PQ','RUNNING site/start/end/migration'),info=result)
                    return result
                def mf_callback(pcc,mess,certificate):
                    # Accepted A1 is determined by the existing coordinator;
                    # its exact PCC/segment certificate is retained here.
                    archive.document(output/'optimization/stages/MF_INPUT_CERTIFICATE.json',dict(
                        AIDC=certificate,frozen_M1=mess,PCC=pcc,allowed_to_change=['P/Q/SoC'],frozen=['route/discrete','AIDC']))
                    with observe_solver(output/'optimization/solver_passes','MF'):
                        if getattr(context,'v41_bounded_compute',None):
                            matches=[rows for rows in context.v41_a1_reference_choices if np.array_equal(planning_power(rows,context)['pcc'],pcc) and all(certificate.get(k)==v for k,v in identities(rows).items())]
                            require(bool(matches),'MF_ACCEPTED_AIDC_REFERENCE_NOT_FOUND')
                            context.v41_current_jobs=matches[-1]
                        return solve_fixed_route(pcc,mess,context)
                coordinated = coordinate_segments(jobs, context,
                    m1_callback, a1_callback, mf_callback,
                    {'V41_ML_snapshot_SHA': context.v41_ml_snapshot_sha256,
                     'electrical': context.v41_electrical_certificate, 'common_service_SHA': common['COMMON_DA_DURATION_SHA']})
                jobs = coordinated['a1']; trajectory = coordinated['mf']; stages['COORDINATION'] = coordinated
                trace('A1_OUTPUT',jobs,coordinated['m1'],frozen=('M1 grid/PQ','RUNNING site/start/end/migration'),info={'accepted':coordinated['AIDC_FEEDBACK_ACCEPTED']})
                trace('MF_INPUT',jobs,coordinated['m1'],allowed=('P/Q/SoC',),frozen=('route/discrete','AIDC'))
                trace('MF_CANDIDATE_OUTPUT',jobs,coordinated['mf_candidate_result']['trajectory'],allowed=('P/Q/SoC',),frozen=('route/discrete','AIDC'),info=coordinated['mf_candidate_result'])
                trace('MF_OUTPUT',jobs,trajectory,allowed=('P/Q/SoC',),frozen=('route/discrete','AIDC'),info={'accepted':coordinated['FINAL_PQ_RECOURSE_ACCEPTED']})
                optimizer_rows(output / 'A1', context.v41_ml_snapshot, context.v41_ml_snapshot_sha256,
                               diagnostics(context.v41_ml_snapshot, context.capacity, planning_power(jobs, context)['gpu']))
                require(coordinated['counts']['SECOND_MESS_FULL_ROUTE_SEARCH_CALLS'] == 0, 'SECOND_ROUTE_SEARCH_FORBIDDEN')
        from dayahead.v41r1.bounded_runtime import finish
        finish(context,output)
        from dayahead.v41r1.migration_audit import persist as persist_migration
        persist_migration(output/'aidc/migration',day,policy,reference,jobs,context)
        commands = off_commands() if trajectory is None else [asdict(s) for s in trajectory.slots]
        if policy in ('B0','B1'): trace('A0_OUTPUT',jobs,info=stages.get('A0',objective))
        trace('JOINT_FREEZE',jobs,trajectory,frozen=('all AIDC/MESS decisions','ML','terminal','route/discrete'))
        archive.document(output/'optimization/STAGE_APPLICABILITY.json',dict(policy=policy,
            A0='REFERENCE' if policy=='B0' else 'OPTIMIZED' if policy=='B1' else 'EXACT_PRIOR_POLICY_REUSE',
            M1='ACTIVE' if policy in ('B2','B3') else 'NOT_APPLICABLE_MESS_OFF',
            A1='ACTIVE' if policy=='B3' else 'NOT_APPLICABLE_BY_POLICY',MF='ACTIVE' if policy=='B3' else 'NOT_APPLICABLE_BY_POLICY'))
        power = planning_power(jobs, context)
        grid = evaluate_grid(context.coefficients, controls_from_trajectory(context.coefficients, power['pcc'],
                             () if trajectory is None else trajectory.slots), context.nodes)
        require(grid['status'] == 'PASS', 'DAYAHEAD_PLANNING_GRID_FAILED')
        reserve = diagnostics(context.v41_ml_snapshot, context.capacity, power['gpu'])
        window_receipt = optimizer_rows(output, context.v41_ml_snapshot, context.v41_ml_snapshot_sha256, reserve)
        archive.document(output / 'PLANNING_RESULT.json', dict(day=day, policy=policy, grid=grid, objective=objective,
            reserve=reserve, stages=stages, AIDC_energy_kWh=float(.25 * power['pcc'].sum()),
            ML_snapshot_SHA=context.v41_ml_snapshot_sha256, Actual_reads=0, H4_window_persistence=window_receipt,
            pre_solve_persistence_audit=record(snapshot_path.parent / 'PRE_SOLVE_PERSISTENCE_AUDIT.json')))
        write_npz(output / 'FROZEN_AIDC_POWER.npz', **power)
        decision = dict(day=day, policy=policy, AIDC_decision=jobs, MESS_trajectory=commands,
            ML_snapshot=snapshot_seal['snapshot'], optimizer_scalar_sha256=context.v41_optimizer_scalars.sha256,
            common_service_SHA=common['COMMON_DA_DURATION_SHA'], electrical=context.v41_electrical_certificate,
            Actual_authority='V41_COUNTERFACTUAL_ACTUAL_REPLAY_V1')
        decision_sha = digest(decision)
        write_json(output / 'FROZEN_JOINT_DECISION.json', dict(decision=decision, decision_SHA=decision_sha, frozen_at=now()))
        write_json(output / 'FROZEN_MESS_COMMANDS.json', {'MESS_trajectory': commands})
        # Scientific decisions are sealed before Fresh; no restoration optimizer.
        from dayahead.v28r2.trajectory import FrozenTrajectory
        from dayahead.v28r2.opendss_backend import run_fresh_opendss
        from dayahead.v40e.mapping import corrected_mapping
        from dayahead.v40e.readback import observe
        from .grid_archive import observe as observe_grid, persist as persist_grid
        from .mapper_audit import observe as observe_mapper
        from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
        mp, mq, mids, locations = command_arrays(commands)
        frozen_trajectory = FrozenTrajectory(day, 'DAYAHEAD', policy, power['pcc'], power['qcc'], mp, mq, tuple(mids), locations, decision_sha)
        previous = Path.cwd()
        try:
            with corrected_mapping(), observe(output / 'fresh_readback', policy, 'Fresh') as seen, observe_grid() as grid_observed, observe_mapper(output/'audit/mapper',day,'Fresh'):
                fresh = run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY, context=context.electrical,
                    voltage=context.electrical.voltage, trajectory=frozen_trajectory, output=output / 'fresh')
        finally:
            os.chdir(previous)
        write_json(output / 'FRESH_RESULT.json', dict(summary=fresh.summary, readback=seen, decision_SHA=decision_sha))
        vf,bf,sf=persist_grid(output/'grid',day,policy,'Fresh',fresh,grid_observed,output/'fresh_readback/OPENDSS_COMPONENTS_96.parquet')
        aidc_frame,job_frame=archive.aidc(output/'aidc',day,policy,jobs,power,context.capacity,classes,requests)
        import pandas as pd
        elements=pd.read_parquet(output/'fresh_readback/OPENDSS_COMPONENT_ELEMENTS.parquet')
        mess_frame=archive.mess(output/'mess',day,commands,elements=elements)
        archive.objective_ledger(output,objective,stages,grid,reserve,jobs)
        archive.freeze(output,decision_sha,context.v41_ml_snapshot_sha256,traces)
        archive.critical(output,vf,bf,sf,pd.read_parquet(output/'H4_OPTIMIZER_WINDOWS.parquet'),aidc_frame,mess_frame)
        require(not fresh.summary['physical_violation'], 'DAYAHEAD_FRESH_PHYSICAL_VIOLATION')
        scientific_manifest=archive.seal(output,'dayahead')
        require(science() == source, 'SCIENTIFIC_SOURCE_CHANGED_DURING_DAYAHEAD')
        receipt = dict(schema='V41_PHASE_RECEIPT_V1',status='COMPLETE', day=day, policy=policy, started_at=started, completed_at=now(),
            scientific_commit=commit(), science=source, ML_snapshot_SHA=context.v41_ml_snapshot_sha256,
            decision_SHA=decision_sha, files={k: record(output / p) for k, p in dict(
                decision='FROZEN_JOINT_DECISION.json', planning='PLANNING_RESULT.json', power='FROZEN_AIDC_POWER.npz',
                mess='FROZEN_MESS_COMMANDS.json', fresh='FRESH_RESULT.json', joint_freeze='JOINT_FREEZE_RECEIPT.json',
                scientific_manifest='SCIENTIFIC_MANIFEST.json',generation='GENERATION_INPUT_IDENTITY.json').items()})
        write_json(output / 'DAYAHEAD_RECEIPT.json', receipt)
        return receipt
    finally:
        context.electrical.voltage.close(); context.electrical.current.close()


def actual(day, policy):
    # This check precedes importing or opening any realized input reader.
    decision, da_receipt = verify_dayahead(day, policy)
    output = RUNS / day / policy / 'actual'
    require(not (output / 'ACTUAL_RECEIPT.json').exists(), 'PRESERVE_COMPLETED_ACTUAL')
    source = science(); started = now()
    write_json(output / 'ACTUAL_BOUNDARY_RECEIPT.json', dict(day=day, policy=policy, opened_at=started,
        verified_day_ahead_receipt=record(RUNS / day / policy / 'dayahead/DAYAHEAD_RECEIPT.json'),
        decision_SHA=da_receipt['decision_SHA'], source=source))
    from .electrical import load
    context = load(day)
    bind(context, Path(decision['ML_snapshot']['path']), decision['ML_snapshot']['sha256'])
    import gurobipy as gp
    old_optimize = gp.Model.optimize
    def forbidden(*a, **k): raise RuntimeError('ACTUAL_REOPTIMIZATION_FORBIDDEN')
    gp.Model.optimize = forbidden
    try:
        from dayahead.v40d_actual.inputs import observations, capacity
        from dayahead.v40d_actual.exogenous import load as load_exogenous
        from dayahead.v40d_actual.rack_dispatch import Rack
        from .actual_dispatch import replay_jobs, power_from_execution, persist as persist_dispatch
        from .actual import realized_workload
        from dayahead.v40d_actual.mobility_inputs import actual_mobility
        obs = observations(SOURCE_REPO / 'dayahead/artifacts/v40d_actual_realized_replay')
        authority, _, *unused = capacity(SOURCE_REPO)
        racks = [Rack(r['aidc_id'], r['rack_pool_id'], int(r['compatibility_GPU_limit'])) for r in authority['logical_Rack_pools']]
        replay = replay_jobs(decision['AIDC_decision'], obs, issue_time=issue_time(day),
                             site_capacity=context.capacity.site_capacity, racks=racks,wan=context.wan)
        write_json(output / 'ACTUAL_JOB_REPLAY.json', replay)
        persist_dispatch(output,replay,obs,issue_time(day),context.capacity.site_capacity,racks)
        require(replay['capacity_audit']['status'] == 'PASS', 'FROZEN_ACTUAL_CAPACITY_VIOLATION')
        exo = load_exogenous(SOURCE_REPO, day)
        write_json(output / 'ACTUAL_EXOGENOUS_AUTHORITY.json', exo['authority'])
        power = power_from_execution(ROOT, replay, context.capacity.site_capacity, exo['weather'])
        write_npz(output / 'ACTUAL_AIDC_POWER.npz', occupancy=power['occupancy'], IT=power['IT'], PCC_P=power['PCC_P'], PCC_Q=power['PCC_Q'])
        from .persistence import table, optimizer_rows
        from . import scientific_archive as archive
        table(output / 'ACTUAL_AIDC_TIMESERIES.parquet', power['frame'])
        mess = actual_mobility(SOURCE_REPO, {'day': day, 'case': 'B3',
            'final_PQ_source': str(RUNS / day / policy / 'dayahead/FROZEN_MESS_COMMANDS.json')})
        table(output / 'ACTUAL_MESS_TIMESERIES.parquet', archive.scalar_frame(mess['frame'].to_dict('records')))
        write_json(output / 'ACTUAL_MESS_AUDIT.json', {k: v for k, v in mess.items() if k not in ('frame', 'p', 'q', 'locations')})
        from dayahead.v40e.mapping import corrected_mapping
        from dayahead.v40e.readback import observe
        from dayahead.v40d_actual.grid_replay import replay as grid_replay
        from .grid_archive import observe as observe_grid, persist as persist_grid
        from .mapper_audit import observe as observe_mapper
        previous = Path.cwd()
        try:
            with corrected_mapping(), observe(output / 'actual_readback', policy, 'Actual') as seen, observe_grid() as grid_observed, observe_mapper(output/'audit/mapper',day,'Actual'):
                result, binding = grid_replay(ROOT, day, policy, context, power, exo, mess,
                    digest({'decision': da_receipt['decision_SHA'], 'jobs': replay['job_ledger']}), output / 'grid')
        finally:
            os.chdir(previous)
        workload_path = RUNTIME / 'actual_inputs' / day / 'REALIZED_WORKLOAD.json'
        if workload_path.exists():
            workload = read(workload_path)
        else:
            workload = realized_workload(day, workload_path.parent); write_json(workload_path, workload)
        da = read(RUNS / day / policy / 'dayahead/PLANNING_RESULT.json')
        headroom = np.array(da['reserve']['H_available_GPUh']); actual_work = np.array(workload['H4_actual_GPUh'])
        score = dict(realized_H4_GPUh=actual_work.tolist(), frozen_headroom_GPUh=headroom.tolist(),
            realized_shortfall_GPUh=np.maximum(actual_work - headroom, 0).tolist(), future_scheduling_calls=0)
        from .persistence import actual_rows
        snapshot = read(decision['ML_snapshot']['path'])
        coverage = actual_rows(output, snapshot, actual_work)
        pending = [r for r in replay['job_ledger'] if r['state_at_issue'] == 'PENDING']
        predicted = np.array([r['safe_duration_seconds'] for r in pending]); truth = np.array([r['actual_runtime_seconds'] for r in pending])
        gpu = np.array([r['requested_GPU'] for r in pending])
        runtime = dict(PENDING_N=len(pending), runtime_coverage=float(np.mean(truth <= predicted)),
            GPU_weighted_coverage=float(np.sum(gpu * (truth <= predicted)) / gpu.sum()),
            GPU_under_seconds=float(np.sum(gpu * np.maximum(truth - predicted, 0))),
            GPU_over_seconds=float(np.sum(gpu * np.maximum(predicted - truth, 0))),
            mean_slot_error=float(np.mean(np.ceil(predicted / 900) - np.ceil(truth / 900))))
        summary = dict(status='REPLAY_COMPLETE', summary=result.summary, binding=binding, readback=seen,
            frozen_future_workload_score=score, H4_raw_vs_actionable_coverage=coverage,
            realized_workload_source=record(workload_path), runtime_diagnostics=runtime,
            counters=replay['counters'], power_audit=power['power_audit'], Actual_optimizer_calls=0,
            execution_delay_KPIs=replay['execution_delay_KPIs'],
            execution_rate=replay['execution_rate'],
            raw_contention_classification=replay['raw_runtime_contention']['classification'],
            final_execution_feasibility=replay['exact_execution_feasibility'],
            AIDC_energy_kWh=float(.25 * power['PCC_P'].sum()), decision_SHA=da_receipt['decision_SHA'])
        write_json(output / 'ACTUAL_RESULT.json', summary)
        da_output=RUNS/day/policy/'dayahead'
        archive.actual_inputs(output,day,decision,da_output,obs,exo,mess,workload)
        actual_authority=read(output/'authority/AUTHORITY_MANIFEST.json')
        actual_authority.update(scientific_commit=commit(),Actual_source_manifest=source,
            frozen_DayAhead_producer_commit=da_receipt['scientific_commit'])
        archive.document(output/'authority/AUTHORITY_MANIFEST.json',actual_authority)
        import pandas as pd
        classes=pd.read_parquet(da_output/'authority/JOB_CLASSES.parquet').set_index('job_id')
        requests=pd.read_parquet(da_output/'authority/JOB_REQUEST_INPUTS.parquet').set_index('job_id')
        aidc_frame,job_frame=archive.aidc(output/'aidc',day,policy,replay['job_ledger'],power,context.capacity,classes,requests,actual=True)
        elements=pd.read_parquet(da_output/'fresh_readback/OPENDSS_COMPONENT_ELEMENTS.parquet')
        archive.mess(output/'mess',day,decision['MESS_trajectory'],realized=mess,elements=elements)
        vf,bf,sf=persist_grid(output/'grid',day,policy,'Actual',result,grid_observed,output/'actual_readback/OPENDSS_COMPONENTS_96.parquet')
        measured=diagnostics(snapshot,context.capacity,power['occupancy'])
        optimizer_rows(output,snapshot,decision['ML_snapshot']['sha256'],measured)
        h4=pd.read_parquet(output/'H4_OPTIMIZER_WINDOWS.parquet')
        coverage_frame=pd.read_parquet(output/'H4_ACTUAL_WINDOW_EVALUATION.parquet')
        combined=h4.merge(coverage_frame.drop(columns=['RAW_R85_B2_GPUh','ACTIONABLE_H4_GPUh']),
                         on=['window_start','window_end'],validate='one_to_one')
        table(output/'H4_COMPLETE_WINDOW_RESULTS.parquet',combined)
        archive.document(output/'ACTUAL_RESERVE_DIAGNOSTIC_AUTHORITY.json',dict(
            source='Frozen scalar reserve evaluated against Actual occupancy; xi is arithmetic evaluation only',
            Actual_optimizer_calls=0,snapshot_hash=decision['ML_snapshot']['sha256']))
        archive.critical(output,vf,bf,sf,h4,aidc_frame,mess['frame'],actual=True)
        archive.comparisons(output,da_output)
        archive.seal(output,'actual')
        require(science() == source, 'SCIENTIFIC_SOURCE_CHANGED_DURING_ACTUAL')
        receipt = dict(schema='V41_PHASE_RECEIPT_V1',status='COMPLETE', day=day, policy=policy, started_at=started, completed_at=now(),
            scientific_commit=commit(), science=source, decision_SHA=da_receipt['decision_SHA'],
            day_ahead=record(RUNS / day / policy / 'dayahead/DAYAHEAD_RECEIPT.json'),
            files={k: record(output / name) for k, name in dict(result='ACTUAL_RESULT.json', jobs='ACTUAL_JOB_REPLAY.json',
                power='ACTUAL_AIDC_POWER.npz', boundary='ACTUAL_BOUNDARY_RECEIPT.json',
                scientific_manifest='SCIENTIFIC_MANIFEST.json').items()})
        write_json(output / 'ACTUAL_RECEIPT.json', receipt)
        archive.complete_unit(output.parent)
        return receipt
    finally:
        gp.Model.optimize = old_optimize
        context.electrical.voltage.close(); context.electrical.current.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--day', required=True)
    parser.add_argument('--policy', choices=['B0', 'B1', 'B2', 'B3'], required=True)
    parser.add_argument('--phase', choices=['dayahead', 'actual'], required=True)
    parser.add_argument('--campaign-sha')
    args = parser.parse_args()
    receipt = {'dayahead': dayahead, 'actual': actual}[args.phase](args.day, args.policy)
    print(args.day, args.policy, args.phase, receipt['status'], flush=True)
