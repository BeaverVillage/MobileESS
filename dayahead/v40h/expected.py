"""External current B1 and M1 authority builders, independent of result files."""
from pathlib import Path
from dataclasses import asdict
from dayahead.paper_analysis.storage import read
from dayahead.v40a.invariants import digest
from .identity import REL, require, file_record, verify_bound_files, verify_file
from .freeze import expected_campaign, expected_electrical, verify_scientific_freeze
from .b1 import generation_identity
from .cache import execution_identity
from .policy import B1_SOLVER, MF_SOLVER, OBJECTIVE_HIERARCHY


def b1_expected(repo, day, electrical_certificate):
    frozen = verify_scientific_freeze(repo)
    from .electrical import load
    load(electrical_certificate, lambda: expected_electrical(repo, day))
    inventory = read(Path(repo) / REL / 'CURRENT_TRANSITIVE_INPUT_INVENTORY.json')
    common = read(Path(repo) / REL / 'common_inputs/COMMON_INPUT_INDEX.json')[day]; verify_bound_files(common)
    jobs = read(verify_file(common['B0_reference_policy']))
    wan = file_record(Path(repo) / 'dayahead/v38/wan.py')
    values = {k: frozen[k] for k in ('V40G_method_SHA', 'V40G_source_SHA', 'V40G_config_SHA')}
    values.update(common_T_DA_SHA=common['COMMON_DA_DURATION_SHA'], job_universe_SHA=digest(sorted(str(r['job_uid']) for r in jobs)),
        initial_state_SHA=digest(jobs), electrical_authority_SHA=digest(file_record(electrical_certificate)), capacity_SHA=inventory['GPU_capacity']['sha256'],
        Rack_SHA=inventory['Rack']['sha256'], WAN_SHA=digest(wan), migration_authority_SHA=digest({
            'domain': file_record(Path(repo) / 'dayahead/v40g/domain.py'), 'segments': file_record(Path(repo) / 'dayahead/v40g_segments/canonical.py')}),
        solver_settings=B1_SOLVER, objective_hierarchy=OBJECTIVE_HIERARCHY, day=day,
        input_files={'common': common, 'electrical': file_record(electrical_certificate), 'capacity': inventory['GPU_capacity'],
                     'Rack': inventory['Rack'], 'WAN': wan}, source_manifest=frozen['source_manifest'])
    return generation_identity(values)


def m1_expected(repo, day, handle, context):
    from dayahead.v37.contracts import DEFAULT_K, BEAM_WIDTH, BEAM_WIDTH_FALLBACK, K_FALLBACK
    from dayahead.v34.integrated_mess import WORK_LIMIT_TIERS, RESTRICTED_MIP_GAP
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    frozen = verify_scientific_freeze(repo); campaign = expected_campaign(repo, require_outputs=True)
    inventory = read(Path(repo) / REL / 'CURRENT_TRANSITIVE_INPUT_INVENTORY.json'); traffic = inventory['traffic'][day]
    inputs = {'campaign_SHA': campaign['identity_SHA'], 'A0_decision_SHA': handle['B1_FINAL_DECISION_SHA'],
        'A0_segment_SHA': handle['B1_FINAL_SEGMENT_SHA'], 'A0_GPU_SHA': digest(handle['power']['gpu']), 'A0_PCC_SHA': digest(handle['power']['pcc']),
        'electrical_coefficients': [c.coefficient_sha256 for c in context.coefficients], 'traffic_forecast': traffic['forecast'],
        'road_graph': {'files': inventory['road_graph'], 'canonical_SHA': traffic['forecast']['graph_SHA']}, 'route_table': traffic['route_table'],
        'service_road_mapping': inventory['road_graph']['service_nodes'], 'mobility_physics': inventory['MESS_mobility'],
        'MESS_electrical': {'files': inventory['MESS_electrical'], 'values': asdict(MessElectricalAuthority.from_repository())},
        'connection_delay': {'source': inventory['MESS_mobility'], 'rule': 'frozen route-table ready-time / conservative 15-minute adapter'},
        'route_energy': {'route_table': traffic['route_table'], 'source': inventory['MESS_mobility']},
        'MESS_PCC_mapping': inventory['service_PCC_mapping'], 'K': DEFAULT_K, 'beam_width': BEAM_WIDTH,
        'fallback_widths': {'beam': [BEAM_WIDTH_FALLBACK], 'K': list(K_FALLBACK)}, 'seed': 20260828,
        'WorkLimit_tiers': list(WORK_LIMIT_TIERS), 'solver_settings': {'full': MF_SOLVER, 'restricted_MIPGap': RESTRICTED_MIP_GAP,
            'restricted_numeric_tolerance': 1e-8, 'restricted_Threads': 4}, 'source_manifest': frozen['source_manifest'],
        'B1_generation_SHA': handle['B1_GENERATION_IDENTITY_SHA'], 'B1_file': handle['source'], 'A0_trajectory_file': handle['trajectory'],
        'electrical_generation_input_SHA': context.V40H_electrical_input_SHA,
        'electrical_certificate_SHA': context.V40H_electrical_certificate_SHA, 'causal_traffic_inputs': traffic['causal_input_files'],
        'route_generation_source': traffic['route_generation_source'], 'traffic_model': traffic['model_authority']}
    verify_bound_files(inputs)
    return execution_identity(inputs)
