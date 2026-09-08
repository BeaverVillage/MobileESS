"""Integration gates on real persisted pilot evidence; no synthetic PASS fixtures."""
from pathlib import Path
import numpy as np
import pytest
from dayahead.paper_analysis.storage import read
from dayahead.v41.preflight import record
from dayahead.v41r2.authority import OUT,DAY
from dayahead.v41.data import RUNTIME

def test_regenerated_coefficient_dependency_and_mapper():
    a=read(OUT/'V41R2_ELECTRICAL_COEFFICIENT_DEPENDENCY_AUDIT.json')
    assert a['status']=='PASS' and a['new_B0_PCC_anchor_exact_equality']
    assert a['duplicate_mapping']==0 and a['P_conservation']==a['Q_conservation']=='PASS'
    assert a['measured_OpenDSS_calls']==23234
    assert a['readback']==a['source_hash']=='PASS'

def test_full_candidates_seed_and_lexicographic_incumbent():
    a=read(OUT/'V41R2_FULL_CANDIDATE_REENUMERATION.json');s=read(OUT/'V41R2_B1_SEARCH_ACCEPTANCE.json')
    assert a['status']=='PASS' and a['independently_reenumerated_from_full_domain'] and a['fixed_reference_starts']
    assert s['seed']=='PASS' and s['current_incumbent_preserved'] and s['optimization_seconds']<=1800
    assert s['source_preserved'] and s['critical_recomputed_after_acceptance']

@pytest.mark.parametrize('policy',['B0','B1'])
@pytest.mark.parametrize('stage',['dayahead','actual'])
def test_actual_full_axis_physics_and_persistence(policy,stage):
    from dayahead.v41.campaign import verify_receipt
    from dayahead.v41.scientific_archive import verify_manifest
    root=RUNTIME/DAY/policy/stage
    verify_receipt(root/(stage.upper()+'_RECEIPT.json'));verify_manifest(root/'SCIENTIFIC_MANIFEST.json')
    a=read(root/('FRESH_RESULT.json' if stage=='dayahead' else 'ACTUAL_RESULT.json'))
    v=a['summary'];assert v['convergence_count']==96 and not v['physical_violation']
    assert .95<=v['Vmin_pu']<=v['Vmax_pu']<=1.05
    assert v['rho_max_AC']<=1 and v['transformer_phase_current_loading_max']<=1 and v['transformer_total_kva_loading_max']<=1
    if stage=='actual':assert a['Actual_optimizer_calls']==0 and a['final_execution_feasibility']['status']=='PASS'

def test_every_policy_power_conserves_and_hashes_reopen():
    a=read(OUT/'V41R2_ALL_POWER_AND_PCC_AUDIT.json');assert a['status']=='PASS'
    for r in a['results'].values():
        assert r['aggregate_conservation_residual_kW']<=2e-12 and r['conservation_residual_kW']<=2e-12
        assert record(r['components']['path'])==r['components']
        assert all(s['rating_kVA']==1500 and s['violation_count']==0 for s in r['sites'])

def test_no_full_may_outputs():
    assert [p.name for p in RUNTIME.iterdir() if p.is_dir() and p.name.startswith('2025-')]==[DAY]
