"""Full May, four independent dates, one fixed loop-budget run per AIDC stage."""
from fast_prepare import *
from v41r4_loop_runtime import BASE_RUN,BASE_OUT,PREVIOUS_OUT,MAY_RUN,MAY_OUT,LOGS,HELPERS,install_reports
from v41r4_loop_budget import adapted,VERSION
import v41r4_campaign as original


def release():
    from dayahead.v40h.identity import manifest,verify_manifest
    base=read(BASE_OUT/'MAY_CAMPAIGN_RELEASE.json');previous=read(PREVIOUS_OUT/'MAY_CAMPAIGN_RELEASE_V3.json')
    verify_manifest(previous['source'])
    source=manifest([Path(r['path']) for r in previous['source']['files']]+[ROOT/p for p in HELPERS],ROOT)
    path=MAY_OUT/'MAY_CAMPAIGN_RELEASE_V4.json'
    if path.exists():
        result=read(path);assert result['source']==source;return result
    gate=MAY_OUT/'regression/LOOP_WALL_CLOCK_REGRESSION_GATE.json';evidence=read(gate)
    assert evidence['status']=='PASS' and evidence['source']==[record(ROOT/p) for p in HELPERS]
    assert record(evidence['test_result']['path'])==evidence['test_result']
    for name in ('MAY_CAMPAIGN_RELEASE.json','MAY_CAMPAIGN_RELEASE_V2.json'):copy(BASE_OUT/name,MAY_OUT/name)
    result=dict(base,version=VERSION,source=source,outputs=str(MAY_RUN),logs=str(LOGS),
        previous_release=record(PREVIOUS_OUT/'MAY_CAMPAIGN_RELEASE_V3.json'),
        B1_A0_search_loop_wall_seconds=1800,B3_A1_search_loop_wall_seconds=1800,
        lex_stage_seconds=[900,480,180,120,120],no_stagnation_early_stop=True,no_objective_floor_early_stop=True,
        M1_MF_original_budget_unchanged=True,B3_chain=['new B1 reuse A0','M1','B1-equivalent A1 with fixed M1','MF'],
        initialization='Same-day B0 reference for every B1; B3 A0 reuses newly completed same-day B1',
        reuse_completed_policies=['B0','B2'],rerun_all_31_days=['B1','B3'],previous_B1_seed_reuse=False,
        stop_rule='Fixed 1800-second continuous search loop, return best independently validated feasible incumbent',
        automatic_quality_reruns=0,one_time_preparation_outside_search_timer=True,
        candidate_science_changed=False,rankings_changed=False,objectives_changed=False,constraints_changed=False,
        source_gate=record(gate),old_results_retained=True,old_B1_B3_result_use='SUPERSEDED_BUDGET_COMPARISON_ONLY')
    save(path,result);return result


def main():
    install_reports()
    run=adapted(original.main,[("str(ROOT/'v41r4_worker.py')","str(ROOT/'v41r4_loop_worker.py')"),
        ("str(ROOT/'v41r4_bootstrap')","str(ROOT/'v41r4_search_bootstrap')")],
        dict(MAY_RUN=MAY_RUN,MAY_OUT=MAY_OUT,LOGS=LOGS,release=release))
    return run()


if __name__=='__main__':main()
