"""One independent corrected-budget run per May date/policy, detached externally."""
from fast_prepare import *
from v41r4_search_runtime import BASE_RUN,BASE_OUT,MAY_RUN,MAY_OUT,LOGS,HELPERS,install_reports
from v41r4_search_budget import adapted
import v41r4_campaign as original


def release():
    from dayahead.v40h.identity import manifest,verify_manifest
    base=read(BASE_OUT/'MAY_CAMPAIGN_RELEASE.json')
    previous=read(BASE_OUT/'MAY_CAMPAIGN_RELEASE_V2.json')
    verify_manifest(base['source']);verify_manifest(previous['additional_source'])
    source=manifest([Path(r['path']) for r in base['source']['files']+previous['additional_source']['files']]+[ROOT/p for p in HELPERS],ROOT)
    path=MAY_OUT/'MAY_CAMPAIGN_RELEASE_V3.json'
    if path.exists():
        result=read(path);assert result['source']==source;verify_manifest(source);return result
    gate=MAY_OUT/'regression/SEARCH_BUDGET_REGRESSION_GATE.json'
    evidence=read(gate)
    assert evidence['status']=='PASS'
    assert evidence['source']==[record(ROOT/p) for p in HELPERS], 'REGRESSION_SOURCE_DRIFT'
    for item in [evidence['test_result'],evidence['cached_ranking_proof'],*evidence['previous_B1_seed_proofs']]:
        assert record(item['path'])==item, 'REGRESSION_EVIDENCE_DRIFT'
    for name in ('MAY_CAMPAIGN_RELEASE.json','MAY_CAMPAIGN_RELEASE_V2.json'):
        copy(BASE_OUT/name,MAY_OUT/name)
    result=dict(base,version='V41R4_ACTUAL_FO_SEARCH_SECONDS_SINGLE_RERUN',source=source,
        previous_release=record(BASE_OUT/'MAY_CAMPAIGN_RELEASE_V2.json'),outputs=str(MAY_RUN),logs=str(LOGS),
        B1_A0_actual_search_seconds=1800,B3_A1_actual_search_seconds=1800,
        M1_MF_original_budget_unchanged=True,search_budget_excludes_all_non_solver_work=True,
        stop_rule='One complete predefined no-improvement sweep after LAST material improvement; otherwise TIME_LIMIT_UNCERTIFIED',
        automatic_quality_reruns=0,May02_May03_May04_B1_rerun_once=True,
        initialization='Previous valid same-day alpha1.15 B1 incumbent, checked against all original model rows',
        candidate_science_changed=False,rankings_changed=False,objectives_changed=False,constraints_changed=False,
        source_gate=record(gate),old_B1_results_retained=str(BASE_RUN),old_B1_result_use='INITIAL_INCUMBENT_ONLY')
    save(path,result);return result


def main():
    install_reports()
    run=adapted(original.main,[("str(ROOT/'v41r4_worker.py')","str(ROOT/'v41r4_search_worker.py')"),
        ("str(ROOT/'v41r4_bootstrap')","str(ROOT/'v41r4_search_bootstrap')")],
        dict(MAY_RUN=MAY_RUN,MAY_OUT=MAY_OUT,LOGS=LOGS,release=release))
    return run()

if __name__=='__main__':main()
