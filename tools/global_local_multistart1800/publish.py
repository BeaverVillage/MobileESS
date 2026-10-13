"""Publish V2 aggregate evidence at the requested root, preserving V1 ledgers."""
import shutil
from tools.global_local_multistart1800.adapter_v2 import *

def main():
    guard();review=read(DOCS/'FINAL_INDEPENDENT_REVIEW.json');assert review['PASS'] and review['Native_used']<=1800
    inherited=read(DOCS/'INHERITED_V1_NATIVE_CALLS.json')
    assert v.file_sha(inherited['old_ledger_preserved']['path'])==inherited['old_ledger_preserved']['sha256']
    references={}
    required=('SOURCE_CASE_AUTHORITY.json','PR220_WARM_START_CERTIFICATE.json','GLOBAL_ROUTE_DIVERSITY_AUDIT.json','DIVERSE_SEED_RESULTS.json',
        'MULTISTART_LOCAL_BRANCHING_RESULTS.json','COOPERATIVE_ROUTE_RESULTS.json','SEARCH_SWITCHING_POLICY.json','BEST_GLOBAL_UB_TRAJECTORY.json','BEST_MOVING_UB_TRAJECTORY.json',
        'K32_K48_INHERITED_LB_CERTIFICATE.json','LB_CANDIDATE_COMPARISON.json','FAST_LB_NATIVE_RESULT.json','FAST_LB_INDEPENDENT_CERTIFICATE.json','GLOBAL_GAP_TRAJECTORY.json',
        'NATIVE_RUNTIME_LEDGER.json','MEMORY_NUMERIC_AUDIT.json','ORIGINAL_FULL_REPLAY_CERTIFICATES.json','FINAL_INDEPENDENT_REVIEW.json','BEST_96_SLOT_MESS_PLAN.csv')
    for name in required:
        source=DOCS/name;assert source.is_file();target=V1_DOCS/name
        if not target.exists():shutil.copyfile(source,target)
        references[name]=dict(authoritative_V2=record(source),root_record_preserved_if_already_present=True)
    for name in ('GLOBAL_LOCAL_MULTISTART_DUAL1800_FINAL_KO.md','BEST_PLAN_AUDIT.json','FOUR_MESS_JOINT_ROUTE_POOL_RESULTS.json',
        'EXECUTED_ROUTE_DIVERSITY_AUDIT.json','FINAL_CRITICAL_GRID_SCAN.json','PLOT_INDEX.json'):
        target=V1_DOCS/name;assert not target.exists();shutil.copyfile(DOCS/name,target)
    for name in read(DOCS/'PLOT_INDEX.json')['plots']:
        assert not (V1_DOCS/name).exists();shutil.copyfile(DOCS/name,V1_DOCS/name)
    shutil.copyfile(DOCS/'NATIVE_RUNTIME_LEDGER.json',V1_DOCS/'COMBINED_NATIVE_RUNTIME_LEDGER.json')
    shutil.copyfile(DOCS/'FINAL_STATE.json',V1_DOCS/'FINAL_CERTIFIED_STATE.json')
    report=V1_DOCS/'GLOBAL_LOCAL_MULTISTART_DUAL1800_FINAL_KO.md'
    report.write_text(report.read_text(encoding='utf-8')+'\n\n최종 합산 Native 권위는 `v2/NATIVE_RUNTIME_LEDGER.json` 및 `COMBINED_NATIVE_RUNTIME_LEDGER.json`이다. 루트의 기존 `NATIVE_RUNTIME_LEDGER.json`은 V1 당시 스냅샷으로 변경하지 않았다. `MANDATORY_DELIVERY_REFERENCES.json`은 필수 이름별 최종 권위 파일과 SHA를 지정한다.\n',encoding='utf-8')
    write(V1_DOCS/'MANDATORY_DELIVERY_REFERENCES.json',dict(PASS=True,required=references,V1_ledger_bytes_unchanged=True,total_Native=review['Native_used'],no_budget_reset=True))
    print(json.dumps(dict(PASS=True,Native=review['Native_used'],root_report=str(report))))

if __name__=='__main__':main()
