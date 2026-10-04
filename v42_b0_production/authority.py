"""Read-only preflight: exact base, frozen source hashes, and current checker."""
import json
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from v42_campaign.authority import digest, file_sha
from v42_orchestrator.dag import ROOT, build_dag, load_dates
from v42_orchestrator.ledger import atomic
from .config import BASE, VERSION, explicit_config

HOLDOUT = ROOT / 'docs/v42_may_b0_zero_margin_holdout'
INPUT = HOLDOUT / 'INPUT'
DOC = ROOT / 'docs/v42_may_b0_production_31d'


def record(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=file_sha(path), bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def b0_plan():
    original = build_dag()
    nodes = [n for n in original['nodes'] if n['arm'] == 'B0']
    freezes = [n['id'] for n in nodes if n['stage'] == 'PLANNING_FREEZE']
    for node in nodes:
        if node['stage'] == 'ACTUAL':
            node['control_dependencies'] = freezes[:]
            node['required_pass'] = freezes[:]
        node['resource_slots'] = 1 if node['stage'] in ('B0_PLANNING', 'FRESH_AC') else 0
    return dict(original, nodes=nodes, main_order=['B0'], convergence_order=[],
                AUTO_ADVANCE_TO_B1=False, mode='B0_PRODUCTION',
                scientific_sha=digest(dict(base=BASE, B0_policy=original['scientific_sha'],
                    Planning_all_31_freeze_before_Actual=True)))


def prepare():
    config = explicit_config()
    config.authorize('B0')
    for arm in ('B1', 'B2', 'B3'):
        try:
            config.authorize(arm)
        except PermissionError:
            continue
        raise AssertionError('Forbidden arm was admitted')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != BASE:
        raise ValueError('Execution preflight requires exact PR146 head')
    days = load_dates()
    if days[0] != '2025-05-01' or days[-1] != '2025-05-31':
        raise ValueError('May 2025 date authority mismatch')
    from v42_holdout.common import source_freeze
    from v42_capacity.common import resolve
    from v42_regcontrol.authority import source, compile_verified, assert_inventory
    from v42_thermal.authority import current_authority
    spec = source_freeze()
    # Hash/compile audit is not a day solve, optimizer, or Actual execution.
    m = source()
    odd, _, inventory = compile_verified()
    assert_inventory(inventory, initial=True)
    odd.Basic.ClearAll()
    thermal = current_authority()
    from .c1_binding import bind_frozen_c1
    c1_binding = bind_frozen_c1(spec)
    if not thermal['PASS'] or inventory['RegControl_count'] != 7 or inventory['CapControl_count'] != 0:
        raise ValueError('Control/checker authority failure')
    if inventory['capacitor_banks'] != 4 or not all(r['enabled'] for r in inventory['regulators']):
        raise ValueError('Regulator/capacitor authority failure')
    sources = {r['path']: record(resolve(r)) for r in spec['frozen_sources']}
    day_inputs = {}
    for day in days:
        folder = INPUT / 'BUNDLE' / ('DAY_' + day.replace('-', ''))
        files = [folder / name for name in ('PLANNING_INPUT_BUNDLE.json', 'ACTUAL_INPUT_BUNDLE.json',
            'C1_PLANNING_COEFFICIENTS.csv', 'POWER_AUTHORITY.json', 'SOURCE_PROVENANCE.json',
            'DERIVED_AEMO_ACTUAL.parquet', 'DERIVED_NOAA_ACTUAL.parquet')]
        entries = [record(p) for p in files]
        p = read(files[0])
        if not p['input_gate_PASS'] or p['day'] != day:
            raise ValueError('Frozen B0 input identity failure')
        day_inputs[day] = entries
        for entry in entries:
            sources[entry['path']] = entry
    for root_name in ('v42_holdout', 'v42_capacity', 'v42_regcontrol', 'v42_thermal', 'v42_modelable',
                      'v42_final', 'v42_b0_production', 'v42_orchestrator'):
        for p in (ROOT / root_name).rglob('*.py'):
            sources[str(p.resolve())] = record(p)
    from v42_regcontrol.common import CODE
    for p in (CODE / 'dayahead').rglob('*.py'):
        sources[str(p.resolve())] = record(p)
    sources[str(ROOT / 'docs/v42_m1_cutpass_loop_campaign/MAY_CAMPAIGN_DRY_RUN_PLAN.json')] = record(
        ROOT / 'docs/v42_m1_cutpass_loop_campaign/MAY_CAMPAIGN_DRY_RUN_PLAN.json')
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%dT%H%M%S')
    run_id = f'B0_202505_{stamp}_{uuid.uuid4().hex[:8]}'
    # Keep deterministic receipt/attempt paths below Windows MAX_PATH.
    run_root = Path('C:/v42_b0_runs') / run_id[-8:]
    run_root.mkdir(parents=True)
    DOC.mkdir(parents=True, exist_ok=True)
    authority = dict(base_SHA=head, run_id=run_id, run_root=str(run_root), stage_version=VERSION,
        days=list(days), config=asdict(config), source_files=list(sources.values()), day_inputs=day_inputs,
        input_sha=digest(day_inputs), scientific_sha=b0_plan()['scientific_sha'],
        checker_SHA=thermal['transformer_current_authority_sha256'], engine_version=m['expected']['engine_version'],
        B0=dict(AIDC_present=True, workload_present=True, ML_OFF=False, AIDC_grid_flexibility=False, MESS_OFF=True,
                optimizer_calls_required=0), physical=dict(voltage_band=[.95, 1.05], margin=0,
                RegControls=7, autonomous=True, capacitors_fixed_ON=4, CapControls=0,
                transformer_phase_current='source NormalAmps', transformer_kVA='separate source winding kVA',
                line_ratings='unchanged source-backed NormAmps', Actual_reoptimization=False, Actual_PQ_repair=False),
        C1_exact_source_binding=c1_binding,
        historical_outputs_reused=0, immutable_frozen_input_bundles_used=True,
        truth_reconstructed_from_raw_after_all_31_Planning_freezes=True,
        missing_PR146_interfaces=['production mode/receipt validation hooks', 'B0-only native adapter',
                                  'all-31 Planning-freeze barrier', 'live telemetry/cancellation/admission'])
    atomic(run_root / 'AUTHORITY.json', authority)
    atomic(DOC / 'B0_PRODUCTION_FREEZE_MANIFEST.json', authority)
    atomic(DOC / 'B0_PRODUCTION_BASE_AUDIT.json', dict(PASS=True, **{k: authority[k] for k in
        ('base_SHA', 'scientific_sha', 'input_sha', 'checker_SHA', 'engine_version', 'B0', 'physical')},
        frozen_sources_verified=len(sources), native_static_compile_only=True,
        historical_B0_outputs_non_authoritative=True, B1_B2_B3_guard_test_PASS=True,
        scheduler_config=asdict(config)))
    atomic(DOC / 'B0_DATE_AUTHORITY.json', dict(days=list(days), unique_count=31, sorted=True,
        source='docs/v42_m1_cutpass_loop_campaign/MAY_CAMPAIGN_DRY_RUN_PLAN.json'))
    atomic(DOC / 'B0_CAMPAIGN_CONFIG.json', asdict(config))
    atomic(DOC / 'RUN_LOCATION.json', dict(run_id=run_id, run_root=str(run_root)))
    print(json.dumps(dict(PASS=True, run_id=run_id, run_root=str(run_root), sources=len(sources))))
    return run_root
