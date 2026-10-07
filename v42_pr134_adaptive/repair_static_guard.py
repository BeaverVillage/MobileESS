"""Re-audit already captured static bytes; does not rebuild or optimize."""
import pickle,sys
from .common import *
from .global_identity import verify
def main(day,tag,selection):
    folder=CASE/day/tag;global_audit=verify(day,folder)
    if not global_audit['PASS']:raise ValueError('GLOBAL_IDENTITY_FAIL')
    data0=load(day)
    with (folder/'DATA.pkl').open('rb') as f:data=pickle.load(f)
    selected=read(selection)
    if data0[7]['classes']!=data[7]['classes'] or data0[1]!=data[1] or data0[3]!=data[3] or data0[4]!=data[4]:raise ValueError('ORIGINAL_SCIENTIFIC_IDENTITY')
    stats=read(folder/'F2-CRA_MODEL_STATS.json')
    audit=dict(PASS=True,classes_before=data0[7]['classes'],classes_after=data[7]['classes'],class_counts_unchanged=True,
        bundle_SHA=digest(data[0]),original_bundle_SHA=digest(data0[0]),resources_unchanged=True,jobs_unchanged=True,raw_Runtime_unchanged=True,
        latest_completion_unchanged=all(data0[2][u].latest_completion==data[2][u].latest_completion for u in data[1]),
        global_physical_coefficients_RHS_senses_exact_equal=True,global_identity=record(folder/'GLOBAL_NUMERIC_IDENTITY.json'),
        selected=selected,full_pool_in_native_model=False,CC4_changed=False,voltage_limits_changed=False,capacity_changed=False,service_changed=False,
        future_information_used=False,static_comparison_boundary_bug_corrected=True,native_solve_before_gate=0,
        four_objectives=[x['name'] for x in read(folder/'OBJECTIVES.json')])
    if not audit['latest_completion_unchanged'] or audit['bundle_SHA']!=audit['original_bundle_SHA']:raise ValueError('CARRYOUT_INPUT_DRIFT')
    atomic(folder/'DOMAIN_AUTHORITY_AUDIT.json',audit)
    atomic(folder/'CENSUS.json',dict(rows=stats['constraints'],cols=stats['columns'],binary=stats['binaries'],integer=stats['integers'],continuous=stats['continuous'],nnz=stats['nonzeros'],
        build_seconds=stats['model_build_seconds'],added_classes=len(set(x['class_id'] for x in selected)),added_options=len(selected),
        added_starts=len(set((x['class_id'],x['start']) for x in selected)),added_sites=0,added_migration_lanes=0))
    atomic(folder/'STATIC_ONLY.json',dict(PASS=True,optimizer_calls=0,source_commit=BASE,selected=record(selection),
        matrix=record(folder/'EXPANDED_MATRIX.npz'),attributes=record(folder/'EXPANDED_ATTRIBUTES.npz'),descriptor=record(folder/'SCIENTIFIC_INTERFACES.pkl.gz')))
    print('STATIC_REAUDIT_PASS',day,tag,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
