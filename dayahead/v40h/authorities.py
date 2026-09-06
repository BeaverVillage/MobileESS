"""Read-only materialization of the current transitive input closure."""
from pathlib import Path
from datetime import date, timedelta
import gzip
import hashlib
import json
import sys
import importlib.metadata
import numpy as np
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v40a.invariants import digest
from .identity import REL, CAMPAIGN, DAYS, file_record, manifest, verify_file, require, bind
from .electrical import feeder_manifest, electrical_identity, namespace_gate, ROLES


def source_paths(repo):
    repo = Path(repo)
    code = [p for folder in ('dayahead', 'pfr', 'tests') for p in (repo / folder).rglob('*.py')
            if 'artifacts' not in p.relative_to(repo).parts and '__pycache__' not in p.parts]
    return sorted(code + [repo / name for name in ('.gitattributes', 'pyproject.toml', 'requirements.txt') if (repo / name).is_file()])


def collect(repo):
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY, FROZEN_MESS_WORKTREE
    from dayahead.v28r2.electrical_context import source_root, portable_background_paths
    from dayahead.v28r2.opendss_backend import FeederAssets
    from dayahead.v28r2.source_cache import day_root
    from dayahead.grid_background_v16_2 import ALPHA_GRID, EXPECTED_SHA256
    from dayahead.v34.traffic_authority import LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED, TRAFFIC_DATA
    from dayahead.v35.execution import DEFAULT_SERVICE_MAPPING
    from dayahead.v40d_actual.inputs import capacity
    repo = Path(repo).resolve(); root = repo / REL
    def group(*names): return {name: file_record(repo / name) for name in names}
    source = manifest(source_paths(repo), repo)
    feeder = FeederAssets.from_repo(SOURCE_DATA_REPOSITORY); src = source_root(SOURCE_DATA_REPOSITORY)
    assets = feeder_manifest([src / 'opendss_assets', src / 'power_v70_p4f_contract'], [feeder.master, feeder.pcc])
    background = {}
    for name, path in vars(portable_background_paths(SOURCE_DATA_REPOSITORY, src)).items():
        if name == 'pv_reference': background[name] = {'frozen_normalization_provenance_SHA': EXPECTED_SHA256[name], 'numeric_input': False}
        else: background[name] = file_record(path)
    cap, _, rackref, capref = capacity(repo)
    road = {k: file_record(p) for k, p in [('link_order', LINK_ORDER), ('service_nodes', SERVICE_NODES), ('physical_edges', PHYSICAL), ('elevated_graph', ELEVATED)]}
    model_root = FROZEN_MESS_WORKTREE / 'dayahead/artifacts/v33m3_causal_dayahead_traffic'
    model = read(model_root / 'V33M3_FINAL_MODEL_AUTHORITY.json')
    traffic_model = {p.name: file_record(p) for p in (model_root / 'V33M3_FINAL_MODEL_AUTHORITY.json',
        model_root / model['checkpoint'], model_root / 'V33M3_SAFE_ETA_CALIBRATION.json')}
    power = group('dayahead/v39a/power.py', 'dayahead/v39a/contracts.py', 'dayahead/v28r2/c1_affine.py', 'dayahead/v28/thermal.py',
        'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json')
    generation = group('dayahead/v40e/electrical.py', 'dayahead/v40h/electrical.py', 'dayahead/v40h/numerical_context.py',
        'dayahead/run_v16_3_voltage_candidate.py', 'dayahead/run_v16_3_correction.py',
        'dayahead/full_ieee123_g11_v16_1.py', 'dayahead/v28r2/electrical_subproblem.py')
    generation['frozen_April_joint_authority'] = file_record(repo / 'dayahead/artifacts/v40g_segment_integration/april_joint_authority/V40E_CORRECTED_JOINT_VOLTAGE_AUTHORITY.json')
    generation['frozen_April_input_lineage'] = manifest([p for p in (repo / 'dayahead/artifacts/v40g_segment_integration/april_joint_authority').rglob('*') if p.is_file()], repo)
    generation['transitive_generation_source_SHA'] = source['manifest_SHA']
    alpha = {'value': ALPHA_GRID, 'authority': background['scale_contract'], 'source': file_record(repo / 'dayahead/grid_background_v16_2.py')}
    daily = {}; traffic = {}; common_inputs = {}; electrical_outputs = {}
    for day in DAYS:
        cache = day_root(SOURCE_DATA_REPOSITORY, day)
        forecast = file_record(cache / 'aemo_forecast.json'); weather = file_record(cache / 'gfs_d1_weather.parquet')
        ec = repo / 'dayahead/cache/v37_may_locked_final/electrical' / day
        vp = ec / 'data' / ('D1_AC_ANCHOR_SENSITIVITY_' + day + '.npz')
        with np.load(vp, allow_pickle=False) as z:
            anchor = {'SHA': digest(z['anchor_control']), 'role': 'EXOGENOUS_INPUT_ONLY_NOT_HISTORICAL_AC_OUTPUT',
                      'source_container': file_record(vp)}
            axes = {k: digest(z[k]) for k in ('node_names', 'control_names')}
        base = {'day': day, 'generation_source': generation, 'native_mapper': file_record(repo / 'dayahead/v40e/mapping.py'),
            'native_allocation_authority': background['runtime_adapter'], 'feeder_manifest': assets, 'OpenDSS_master': file_record(feeder.master),
            'PCC_mapping': file_record(feeder.pcc), 'service_PCC_mapping': file_record(feeder.service_mapping),
            'line_ratings': file_record(feeder.ratings), 'transformer_ratings': {'feeder_manifest_SHA': assets['manifest_SHA'], 'runtime_adapter': background['runtime_adapter']},
            'native_controls': {'policy': group('dayahead/v28r2/opendss_backend.py', 'dayahead/run_v16_3_voltage_candidate.py'), 'asset_manifest_SHA': assets['manifest_SHA']},
            'alpha_grid': alpha, 'demand': {'source': forecast, 'field': 'demand_mw_96', 'role': 'D1_FORECAST'},
            'PV': {'source': forecast, 'field': 'pv_mw_96', 'role': 'D1_FORECAST'}, 'weather': weather,
            'background_mapping': {'files': background, 'source': file_record(repo / 'dayahead/grid_background_v16_2.py'), 'mapper': file_record(repo / 'dayahead/v40e/mapping.py')},
            'AIDC_power_C1': power, 'AC_anchor_input': anchor, 'axes': {'voltage_axes': axes, 'complete_feeder_manifest_SHA': assets['manifest_SHA'], 'branch_axis_generator': generation},
            'voltage_generation': generation, 'current_generation': generation, 'transformer_generation': generation}
        daily[day] = bind('V40H_ELECTRICAL_GENERATION_V1', base, ROLES)
        certificate = repo / CAMPAIGN / 'electrical' / day / 'GENERATION_CERTIFICATE.json'
        # Existing V40E/G coefficient files are preserved; their generation
        # inputs cannot be retroactively attested with current source hashes.
        electrical_outputs[day] = {'status': 'GENERATION_REQUIRED_BEFORE_CAMPAIGN_LAUNCH',
            'required_certificate': str(certificate), 'expected_input_identity_SHA': daily[day]['identity_SHA'],
            'pre_final_coefficient_adoption_allowed': False}
        folder = repo / 'dayahead/cache/v37_may_locked_final/traffic/shared/traffic' / day
        fp, rp = folder / 'TRAFFIC_FORECAST.npz', folder / 'ROUTE_TABLE.json.gz'
        with np.load(fp, allow_pickle=False) as z: metadata = json.loads(str(z['metadata']))
        with gzip.open(rp, 'rb') as stream: route_sha = hashlib.sha256(stream.read()).hexdigest()
        target = date.fromisoformat(day)
        causal = {str(d): file_record(TRAFFIC_DATA / f'year={d.year}' / ('date=' + d.isoformat()) / 'link_tt_5min_24h.parquet')
                  for d in (target - timedelta(days=7), target - timedelta(days=1))}
        traffic[day] = {'forecast': {'file': file_record(fp), 'canonical_SHA': metadata['bundle_sha'], 'model_SHA': metadata['model_sha'], 'graph_SHA': metadata['graph_sha']},
            'route_table': {'file': file_record(rp), 'canonical_SHA': route_sha}, 'causal_input_files': causal, 'model_authority': traffic_model,
            'route_generation_source': group('dayahead/v33m/route_table.py', 'dayahead/v33m/mobility_15min_adapter.py', 'dayahead/v35/traffic_authority.py', 'dayahead/v35/execution.py')}
        ledger_root = repo / 'dayahead/artifacts/v37_r4a_per_day_aidc/days' / day
        common_inputs[day] = {'D1_snapshot': file_record(ledger_root / 'V37_R4A_D1_SNAPSHOT.parquet'),
            'causal_service_ledger': file_record(ledger_root / 'V37_R4A_JOB_LEDGER.parquet'),
            'common_T_DA_generator': file_record(repo / 'dayahead/v40f/common_service.py'),
            'old_case_result_reuse': False}
    actual_contracts = group('dayahead/v40h/actual.py', 'dayahead/v40h/pre_day_complete.py', 'dayahead/v40g_segments/actual.py',
        'dayahead/v40d_actual/contracts.py', 'dayahead/v40d_actual/exogenous.py', 'dayahead/v40d_actual/grid_replay.py',
        'dayahead/v40d_actual/rack_dispatch.py', 'dayahead/v40d_actual/power_replay.py',
        'dayahead/artifacts/v40d_actual_realized_replay/V40D_ACTUAL_REPLAY_CONTRACT.json')
    actual_root = repo / 'dayahead/artifacts/v40d_actual_realized_replay'
    realized = {'role': 'ACTUAL_ONLY; byte hashes only, never optimizer numerical inputs', 'files': {}}
    def collect_refs(node):
        if isinstance(node, dict):
            if 'path' in node and isinstance(node['path'], str) and Path(node['path']).is_file():
                realized['files'][node['path']] = file_record(node['path'])
            for child in node.values(): collect_refs(child)
        elif isinstance(node, list):
            for child in node: collect_refs(child)
    for name in ('V40D_AEMO_COMPLETENESS.json', 'V40D_WEATHER_COMPLETENESS.json'):
        path = actual_root / name; realized['files'][str(path)] = file_record(path); collect_refs(read(path))
    observed = actual_root / 'V40D_FROZEN_JOB_OBSERVATIONS.parquet'
    realized['files'][str(observed)] = file_record(observed)
    for day in DAYS:
        d = date.fromisoformat(day)
        path = TRAFFIC_DATA / f'year={d.year}' / ('date=' + day) / 'link_tt_5min_24h.parquet'
        realized['files'][str(path)] = file_record(path)
    actual_contracts['realized_input_authorities'] = realized
    actual_contracts['effective_completion_override'] = 'V40H reconstructed fixed-decision execution trace; original observed end is not a completion criterion'
    runtime = {'python': sys.version, 'packages': {}}
    for name in ('numpy', 'pandas', 'gurobipy', 'OpenDSSDirect.py', 'dss-python', 'scipy'):
        try: runtime['packages'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: runtime['packages'][name] = 'NOT_INSTALLED'
    value = {'source_manifest': source, 'full_feeder_manifest': assets, 'background': background, 'alpha_grid': alpha,
        'generation_source': generation, 'daily_electrical_identities': daily, 'electrical_generation_outputs': electrical_outputs,
        'GPU_capacity': file_record(capref['path']), 'Rack': file_record(rackref['path']), 'road_graph': road,
        'traffic': traffic, 'traffic_model': traffic_model, 'AIDC_power_C1': power, 'common_daily_source_inputs': common_inputs,
        'service_PCC_mapping': file_record(DEFAULT_SERVICE_MAPPING), 'Actual_replay': actual_contracts,
        'MESS_mobility': group('dayahead/mess_physics.py', 'dayahead/v33m/contracts.py', 'dayahead/v33m/mobility_15min_adapter.py'),
        'MESS_electrical': group('dayahead/v33m/mess_mobility_milp.py', 'pfr/slow_fast.py'),
        'Fresh_restoration': group('dayahead/v28r2/opendss_backend.py', 'dayahead/v40d/policy.py', 'dayahead/v40a/postfreeze.py'),
        'runtime_environment': runtime}
    write_json(root / 'CURRENT_TRANSITIVE_INPUT_INVENTORY.json', value)
    write_json(root / 'FULL_FEEDER_ASSET_MANIFEST.json', assets)
    write_json(root / 'DAILY_ELECTRICAL_EXPECTED_IDENTITIES.json', daily)
    # Common physical identity is explicit; realized demand/PV/weather are
    # distinct input roles, and no new physical campaign is claimed here.
    namespaces = {}
    for day, p in daily.items():
        ai = dict(p['identity']['inputs'])
        ai.update(demand={'role': 'REALIZED_AEMO', 'authority': realized}, PV={'role': 'REALIZED_PV', 'authority': realized},
                  weather={'role': 'OBSERVED_WEATHER', 'authority': realized})
        namespaces[day] = namespace_gate(p, p, bind('V40H_ELECTRICAL_GENERATION_V1', ai, ROLES))
    namespace = {**namespaces[DAYS[0]], 'days': namespaces, 'day_count': len(namespaces),
                 'scope': 'STATIC_EXPECTED_AUTHORITY_GATE; no new Planning/Fresh/Actual execution'}
    write_json(root / 'PLANNING_FRESH_ACTUAL_ELECTRICAL_IDENTITY_GATE.json', namespace)
    print('TRANSITIVE INPUT INVENTORY: 31 expected electrical identities; feeder files=' + str(len(assets['files'])), flush=True)
    return value


def load_bound_traffic(repo, day, expected):
    from dayahead.v35.execution import _load_forecast, _load_route_table
    from dayahead.v33m import load_road_graph_authority
    from dayahead.v34.traffic_authority import LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED
    forecast = expected['traffic_forecast']; route = expected['route_table']
    f = verify_file(forecast['file']); r = verify_file(route['file'])
    bundle, table = _load_forecast(f), _load_route_table(r)
    graph = load_road_graph_authority(LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED)
    require(bundle.forecast_day.isoformat() == day and bundle.canonical_sha256 == forecast['canonical_SHA'], 'TRAFFIC_CURRENT_IDENTITY')
    require(table.canonical_sha256 == route['canonical_SHA'] and bundle.graph_sha == graph.route_graph_sha, 'ROUTE_GRAPH_CURRENT_IDENTITY')
    return bundle, graph, table, (forecast['file'], route['file'])
