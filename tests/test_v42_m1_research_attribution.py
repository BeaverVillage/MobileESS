"""No-native attribution tests; keep causal assertions weaker than observations."""
import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from v42_m1_research.ub_attribution import compare


def summary(site, objective):
    windows = {w: dict(charge_AC_kWh=1., discharge_AC_kWh=1., travel_energy_kWh=0.)
               for w in ('INITIAL_0_15', 'PRECRITICAL_0_65', 'CRITICAL_66_95', 'FULL_0_95')}
    return dict(objective=objective, fleet_travel_energy_kWh=0., fleet_unavailable_slots=0,
                units={'MESS01': dict(moves=[], windows=windows, SOC_at_slots_kWh={'66': 600.},
                      raw_slot_series={'connected_site': [site]*96})})


def test_mode_only_observation_does_not_claim_causal_effect():
    c = SimpleNamespace(d={'names': np.array(['charge_mode[MESS01,0]', 'node_activity[MESS01,STA01,66]'])})
    r = compare(c, np.array([0., 1.]), np.array([1., 1.]), summary('STA01', .63), summary('STA01', .62))
    assert r['mode_change_count'] == 1
    assert r['node_activity_change_count'] == 0
    assert r['same_actual_route_pattern']
    assert r['early_mode_changes'][0]['slot'] == 0
    assert r['causal_decomposition'] == 'NOT_PROVEN'
    assert r['route_vs_mode_vs_PQ_vs_SOC_individual_contribution'] == 'NOT_PROVEN'


def test_no_optimize_or_presolve_call_in_attribution_module():
    path = Path(__file__).resolve().parents[1]/'v42_m1_research/ub_attribution.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ('optimize', 'presolve', 'setParam', 'terminate')
