"""Read-only prior-model/seed checks for the single corrected-budget rerun."""
from fast_prepare import *
from v41r4_search_runtime import BASE_RUN,BASE_OUT,MAY_RUN,MAY_OUT,HELPERS
import sys,time,os,xml.etree.ElementTree as ET
import numpy as np
from dayahead.paper_analysis.storage import write_json

def model(day):
    import gurobipy as gp
    from dayahead.v41r1.feasible_seed import row_audit
    root=BASE_RUN/day/'B1/dayahead/A0'
    a=read(root/'ACCEPTED_AIDC.json');cp=a['solver_stages'][-1]['checkpoint']
    assert record(cp['path'])==cp
    source=root/'PRIMARY_MODEL.mps.gz';proof=read(root/'MODEL_PERSISTENCE.json')
    assert record(source)['sha256']==proof['gzip_sha256']
    import gzip,shutil
    raw=MAY_OUT/'regression/unpacked_models'/day/'PRIMARY_MODEL.mps';raw.parent.mkdir(parents=True,exist_ok=True)
    if not raw.exists():
        with gzip.open(source,'rb') as src,raw.open('xb') as dst:shutil.copyfileobj(src,dst)
    assert record(raw)['sha256']==proof['uncompressed']['sha256']
    started=time.perf_counter();m=gp.read(str(raw));m.Params.OutputFlag=0
    m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
    try:
        with np.load(root/'POLICY_FEASIBLE_SEED.npz') as z:
            assert z['names'].tolist()==m.getAttr('VarName',m.getVars())
        with np.load(cp['path']) as z:values=z['values'].copy()
        check=row_audit(m,values);assert check['status']=='PASS'
        domain=read(root/'V41R1_FULL_CANDIDATE_MANIFEST.json')
        assert domain['candidate_set_SHA']==read(BASE_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')['candidate_set_SHA']
        negative=None
        if day=='2025-05-04':
            index=next(v.index for v in m.getVars() if v.VarName.startswith('GPU['))
            bad=values.copy();bad[index]+=1
            negative=row_audit(m,bad);assert negative['status']=='FAIL'
        save(MAY_OUT/'regression'/f'PREVIOUS_B1_SEED_{day}.json',dict(status='PASS',day=day,
            model=record(source),checkpoint=cp,original_model_row_substitution=check,
            corrupt_seed_rejected=None if negative is None else negative['status']=='FAIL',
            candidate_set_SHA=domain['candidate_set_SHA'],candidate_count=domain['final_authoritative_candidates'],
            prior_objective_vector=a['OBJECTIVE_VECTOR'],seconds=time.perf_counter()-started,
            optimizer_calls=0,Actual_reads=0,model_variables=m.NumVars,model_constraints=m.NumConstrs))
        print('PREVIOUS_B1_SEED_PASS',day,flush=True)
    finally:m.dispose()

def finish():
    folder=MAY_OUT/'regression';xml=folder/'SEARCH_BUDGET_TESTS.xml';tree=ET.parse(xml)
    assert len(tree.findall('.//testcase'))==19 and not tree.findall('.//failure') and not tree.findall('.//error')
    seeds=[]
    for day in ('2025-05-02','2025-05-03','2025-05-04'):
        p=folder/f'PREVIOUS_B1_SEED_{day}.json';assert read(p)['status']=='PASS';seeds.append(record(p))
    ranking=folder/'CACHED_RANKING_EXACT_TEST.json';ranking_value=read(ranking)
    assert ranking_value['status']=='PASS' and ranking_value['all_S_and_active_arrays_bitwise_equal']
    assert ranking_value['top_20_rankings_exact']
    assert ranking_value['source']==record(ROOT/'v41r4_search_runtime.py')
    from v41r4_search_io import archive_replace,install
    directory=(folder/'long_path'/('a'*90)/('b'*90)).resolve()
    prefix=lambda p:'\\\\?\\'+str(p)
    os.makedirs(prefix(directory),exist_ok=True)
    source=directory/'RESTRICTED_VALUES.csv';target=directory/'RESTRICTED_VALUES.K200.ATTEMPT1.csv'
    if not os.path.exists(prefix(target)):
        with open(prefix(source),'xb') as f:f.write(b'path archive exact bytes\n')
        archive_replace(source,target)
    with open(prefix(target),'rb') as f:assert f.read()==b'path archive exact bytes\n'
    install()
    from dayahead.v40h.identity import verify_manifest
    verify_manifest(read(BASE_OUT/'MAY_CAMPAIGN_RELEASE.json')['source'])
    verify_manifest(read(BASE_OUT/'MAY_CAMPAIGN_RELEASE_V2.json')['additional_source'])
    save(folder/'SEARCH_BUDGET_REGRESSION_GATE.json',dict(status='PASS',unit_tests=19,test_result=record(xml),
        previous_B1_seed_proofs=seeds,cached_ranking_proof=record(ranking),original_numerical_sources_unchanged=True,
        NEW_VARIABLES=0,NEW_CONSTRAINTS=0,OBJECTIVES_CHANGED=False,RANKINGS_CHANGED=False,
        alpha_BG=1.15,coefficient_generation_calls=0,optimizer_calls=0,
        B1_A0_and_B3_A1_same_budget_engine=True,search_seconds=1800,
        overhead_charged_to_search=False,one_no_improvement_sweep_stops_stage=True,
        partial_sweep_time_limit='TIME_LIMIT_UNCERTIFIED',automatic_quality_reruns=0,
        Windows_long_path_archive_test='PASS',long_path_length=len(str(target)),
        source=[record(ROOT/p) for p in HELPERS]))
    print('SEARCH_BUDGET_RELEASE_GATE_PASS',flush=True)

if __name__=='__main__':
    if sys.argv[1]=='finish':finish()
    else:model(sys.argv[1])
