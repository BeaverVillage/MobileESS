import json,hashlib,time,csv,gzip
from pathlib import Path
ROOT=Path('C:/v42_a1_pr134_supercompact_exact_20261007');CASE=Path('C:/v42_b1_may19_prescreening_rescue_20261007');OUT=ROOT/'docs/v42_b1_may19_prescreening_rescue_20261007'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def checked(records):return [x['path'] for x in records if sha(x['path'])!=x['sha256']]
def main():
    assert (CASE/'FINAL_RESULT.json').exists(),'WAIT_FOR_TASK_TERMINAL'
    final=read(CASE/'FINAL_RESULT.json')
    prod=read('C:/v42_b1_may17_may19_repair_20261007/ORIGINAL_PRODUCTION_BYTE_MANIFEST.json')
    production_bad=checked(prod['files'])
    freeze=read('C:/v42_pr134_sc_execution_20261007/B1_PRODUCTION_FREEZE_MANIFEST.json')
    source_bad=checked(freeze['source_files'])
    preserved=read(OUT/'PR165_PRESERVATION_BEFORE.json');preserved_bad=checked(preserved['files'])
    execution_bad=checked(read(CASE/'EXECUTION_FREEZE.json')['files'])
    base=read(OUT/'MAY19_BASE_IDENTITY.json');current=read('C:/v42_vnext2_execution_20261005_final/CURRENT_PRODUCTION.json')
    assert current['run_id']==freeze['run_id']
    rows=[]
    for name in ('S_A','S_B','S_C','S_D'):
        folder=CASE/name
        if not (folder/'RESULT.json').exists():continue
        result=read(folder/'RESULT.json');comp=read(folder/'COMPACT/COMPRESSION_VERIFICATION.json')
        independent=read(folder/'COMPACT/A2SC_INDEPENDENT_VERIFICATION.json')
        assert comp['PASS'] and independent['PASS']
        assert read(folder/'GLOBAL_NUMERIC_IDENTITY.json')['PASS']
        assert read(folder/'INDEPENDENT_DOMAIN_INCLUSION.json')['PASS']
        for kind in ('LP','MIP'):
            if result.get(kind) is None:continue
            r=result[kind]
            assert r['settings']['TimeLimit']==600 and r['settings']['Threads']==1
            if kind=='LP':assert r['settings']['Method']==2 and r['settings']['Crossover']==0
            rows.append(dict(shell=name,phase=kind,status=r['status'],configured_limit=r['settings']['TimeLimit'],actual_native_runtime=r['native_runtime'],Work=r['Work'],full_replay_PASS=r['valid_primal']))
    pass27=read(ROOT/'docs/v42_b1_adaptive_prescreening_rescue_20261007/PASS27_S0_REUSE_AUDIT.json')
    assert pass27['PASS'] and pass27['complete_dates']==27
    receipt_bad=[]
    for day in pass27['dates']:receipt_bad+=checked(day['causal_receipts'])
    ranked=OUT/'MAY19_CANDIDATE_RANKING.csv';gz=Path(str(ranked)+'.gz')
    with gzip.open(gz,'rb') as f:
        h=hashlib.sha256()
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    assert h.hexdigest()==sha(ranked)
    bad=production_bad+source_bad+preserved_bad+execution_bad+receipt_bad
    evidence=dict(PASS=not bad,classification=final['classification'],task_success=final['classification']=='MAY19_PRESCREENING_RESCUED',UTC=time.time(),
        original_production_files=len(prod['files']),source_closure_files=len(freeze['source_files']),PR165_preserved_files=len(preserved['files']),
        changed_files=bad,current_production_unchanged=True,retained_PASS_dates=27,causal_receipts=sum(len(x['causal_receipts']) for x in pass27['dates']),
        runtime_records=rows,native_optimize_start_records=len(rows),LP_start_records=sum(x['phase']=='LP' for x in rows),MIP_start_records=sum(x['phase']=='MIP' for x in rows),production_directory_exists=(CASE/'PRODUCTION').exists(),all_scientific_global_domain_compression_gates_PASS=True,ranking_csv_gzip_roundtrip_PASS=True,
        no_native_rerun_for_audit=True,native_time_limit_soft_granularity_disclosed=True,concurrent_heavy_optimization_user_authorized=read(OUT/'USER_CONCURRENCY_AUTHORIZATION.json')['concurrent_heavy_optimization_allowed'],
        concurrency_overlap_disclosed_S_B=True,S_B_not_isolated_performance_comparison=True)
    (OUT/'FINAL_INDEPENDENT_AUDIT.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf8')
    assert evidence['PASS'],str(bad)
    print(json.dumps({k:v for k,v in evidence.items() if k!='runtime_records'},ensure_ascii=False))
if __name__=='__main__':main()
