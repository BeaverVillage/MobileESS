"""Hash-gated B3 activation. Never runs B0/B1/B2 search or uses diagnostics."""
from common8500 import *
import shutil,inspect
import mess_runtime
OLD=P.parent/'IEEE8500_v41r4_production_20260911_r2'
CLOSURE=P.parent/'IEEE8500_B2_physical_closure_20260912_r2'
def copy_checked(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    assert not dest.exists()
    shutil.copyfile(source,dest);assert sha(source)==sha(dest)
    return dict(source=record(source),copy=record(dest))
def main():
    install_output_paths();assert not (P/'PRODUCTION_RELEASE.json').exists()
    verify()
    old_release=read(OLD/'PRODUCTION_RELEASE.json')
    assert sha(OLD/'PRODUCTION_RELEASE.json')=='5f8f48e2dc26c3b135d2cfec0dcf7d937b81d79aca2440ab15de6f874bc678c4'
    for f in old_release['code']:assert sha(f['path'])==f['sha256'],f['path']
    assert sha(CLOSURE/'FINAL_REPORT_SHA256_MANIFEST.json')=='ed77772bf5ea9e4cde18981ba08428b232c7225a6b2a6e5c4bcab54a065a7daf'
    for f in read(CLOSURE/'FINAL_REPORT_SHA256_MANIFEST.json')['files']:assert sha(f['path'])==f['sha256'],f['path']
    b2=read(CLOSURE/'B2_RESTORED_ACCEPTANCE.json');assert b2['status']=='PASS' and not b2['diagnostic_candidate_used']
    b1=read(OLD/'B1/ACCEPTED_AIDC.json');authority=read(OLD/'B1/FINAL_AUTHORITY.json')
    assert authority['status']=='PASS' and authority['search_budget_seconds']==14400
    assert sha(OLD/'B1/ACCEPTED_AIDC.json')=='3dee86735dbf4ebd5200fce575cba6691fb2381f0d4d55ccc4cafc9c82c83ddf'
    copies=[]
    for relative in ['B0/FINAL.json','B0/POWER.npz','B1/ACCEPTED_AIDC.json','B1/FINAL_AUTHORITY.json',
        'B1/FINAL_POWER.npz','B1/POLICY_FEASIBLE_SEED.npz','B1/SCALABILITY_METRICS.json',
        'B1/POLICY_FEASIBLE_SEED_AUDIT.json','B1/final_exact/AC_VALIDATION.json']:
        copies.append(copy_checked(OLD/relative,P/relative))
    checkpoint=b1['solver_stages'][-1]['checkpoint'];assert sha(checkpoint['path'])==checkpoint['sha256']
    assignment=P/'B1/final_checkpoint.npz';copies.append(copy_checked(Path(checkpoint['path']),assignment))
    bundle=dict(status='FINAL_B1_INDEPENDENTLY_VALIDATED',candidate_stream_sha256=EXPECTED,
        binding_gate_sha256=sha(BIND/'IEEE8500_V41R4_AIDC_BINDING_PASS.json'),assignment=record(assignment),
        variable_names=record(P/'B1/POLICY_FEASIBLE_SEED.npz'))
    save(P/'FINAL_B1_REUSE.json',dict(status='PASS',B1_search_calls=0,copies=copies,seed_bundle=bundle,
        original_authority=record(OLD/'B1/FINAL_AUTHORITY.json')))
    save(P/'B2/FINAL_AUTHORITY.json',dict(status='PASS',P1=b2['planning_grid']['rho_max'],AC=b2['AC'],
        closure_authority=record(CLOSURE/'B2_RESTORED_ACCEPTANCE.json'),primary_status='FROZEN_PRIMARY_FRESH_FAIL',
        original_selected_state=b2['original_state'],new_B2_search_calls=0))
    # The search function is byte-for-byte the original frozen source. Only
    # MF's overwritten cleanup tuple is renamed; no objective/selection changes.
    source=(OLD/'mess_runtime.py').read_text(encoding='utf-8')
    expected=source.replace('before=(old.add_grid,old.evaluate_grid);','prior_functions=(old.add_grid,old.evaluate_grid);').replace('finally:old.add_grid,old.evaluate_grid=before','finally:old.add_grid,old.evaluate_grid=prior_functions')
    assert (P/'mess_runtime.py').read_text(encoding='utf-8')==expected
    for name in ['common8500.py','aidc_runtime.py','mess_grid8500.py','grid8500.py','ranking8500.py']:
        assert sha(P/name)==sha(OLD/name),name
    for f in P.glob('*.py'):compile(f.read_text(encoding='utf-8'),str(f),'exec')
    rules=read(OLD/'PRODUCTION_RULES.json')
    rules.update(stage_order=['FINAL_B1_REUSE_AS_A0','B3_M1_FULL_MESS_SEARCH','B3_A1_FIXED_M1_14400_SECONDS','B3_MF_FIXED_ROUTE_PQ','CLEAN_96_SLOT_EXACT_AC'],
        B0_B1_B2_rerun=False,B2_required_closure_gate=record(CLOSURE/'B2_RESTORED_ACCEPTANCE.json'),
        final_selection_semantics_unchanged=True,diagnostic_candidate_input=False,automatic_restart=False,
        failure_policy='Fail closed on failed exact gate or any exception; preserve all checkpoints; never select another beam candidate to repair a failed final selection.')
    save(P/'PRODUCTION_RULES.json',rules)
    inputs=[record(P/'FINAL_B1_REUSE.json'),record(P/'B2/FINAL_AUTHORITY.json'),record(CLOSURE/'FINAL_REPORT_SHA256_MANIFEST.json')]
    inputs += [r['copy'] for r in copies]
    save(P/'PRODUCTION_RELEASE.json',dict(status='FROZEN_AUTHORIZED',authorized_by='User: B3 시작해',created_unix=time.time(),
        code=[record(f) for f in sorted(P.glob('*.py'))],inherited_code=old_release['code'],inputs=inputs,
        rules=record(P/'PRODUCTION_RULES.json'),preflight_manifest=record(PREF/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json'),
        original_release=record(OLD/'PRODUCTION_RELEASE.json'),runtime_only_fix='Rename MF saved-function tuple to prevent overwrite by grid metrics dictionary in finally; MF optimization and selection unchanged.'))
    save(P/'PRODUCTION_RELEASE_SHA256.json',record(P/'PRODUCTION_RELEASE.json'))
    state(status='READY',stage='B3_READY_FINAL_B1_REUSE',B1_rerun=False,B2_rerun=False,A1_budget_seconds=14400)
    print('B3_RELEASE_FROZEN',sha(P/'PRODUCTION_RELEASE.json'),flush=True)
if __name__=='__main__':main()
