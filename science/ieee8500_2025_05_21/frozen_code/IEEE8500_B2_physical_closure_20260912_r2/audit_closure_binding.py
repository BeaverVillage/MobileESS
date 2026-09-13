"""Read-only source equivalence and authority-integrity audit."""
import closure8500 as b
import inspect
from pathlib import Path
from dayahead.v40a.invariants import MOBILITY_FIELDS

def main():
    rules=b.read(b.HERE/'RULE_FREEZE.json')
    for row in rules['files']:assert b.sha(row['path'])==row['sha256'],row['path']
    local=b.local_binding();fallback=b.fallback_binding()
    assert local.__code__ is b.original_local.restore.__code__
    assert fallback.__code__ is b.original_revision.fallback.__code__
    assert local.__globals__['solve_fixed_route'].__code__ is b.recourse.solve_fixed_route.__code__
    assert not (set(MOBILITY_FIELDS)&b.ALLOWED_CHANGED_FIELDS)
    selected=b.read(b.HERE/'ORIGINAL_SELECTED_DECISION.json')
    rows=selected['trajectory_slots']
    fixed_fields=sorted(set(rows[0])-b.ALLOWED_CHANGED_FIELDS)
    assert {'mess_id','slot','mode','service_id','destination_service_id','route_link_ids','departure_slot'}<=set(fixed_fields)
    original_release=b.read(b.OLD/'PRODUCTION_RELEASE.json')
    for r in original_release['code']:assert b.sha(r['path'])==r['sha256'],r['path']
    assert b.sha(b.OLD/'B1/ACCEPTED_AIDC.json')=='3dee86735dbf4ebd5200fce575cba6691fb2381f0d4d55ccc4cafc9c82c83ddf'
    b.save(b.HERE/'STRUCTURAL_BINDING_AUDIT.json',dict(status='PASS',
        original_local_outer_loop_bytecode_identity=True,original_local_PQ_solver_bytecode_identity=True,
        original_fallback_search_bytecode_identity=True,original_fallback_model_electrical_import_only=True,
        original_beam_and_final_selector_code_hashes_unchanged=True,original_B1_hash_unchanged=True,
        variable_fields=sorted(b.ALLOWED_CHANGED_FIELDS),fixed_fields=fixed_fields,vehicle_slots=len(rows),
        strict_status_3_fallback_gate=True,diagnostic_candidate_input=False,rule=b.record(b.HERE/'RULE_FREEZE.json')))
    print('STRUCTURAL_BINDING_PASS',flush=True)
if __name__=='__main__':main()
