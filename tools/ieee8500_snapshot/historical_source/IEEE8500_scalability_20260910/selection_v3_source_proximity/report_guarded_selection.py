import hashlib,json
from pathlib import Path
import verify_guarded_selection as verify
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent;OLD=BASE/'selection_v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))

def run():
    first=read(ROOT/'DETERMINISM_FIRST_RUN_RECORD.json');a=first['search_summary'];b=read(ROOT/'search_summary.json')
    a.pop('elapsed_seconds');b.pop('elapsed_seconds')
    checks={n:sha(ROOT/n)==h for n,h in first['decision_log_sha256'].items()}
    assert a==b and all(checks.values())
    verify.save('DETERMINISM_VERIFICATION',{'status':'PASS','decision_summary_identical_excluding_wall_time':True,'decision_logs_byte_identical':checks,'full_procedure_replays':2,'thresholds_or_code_changed_between_runs':False})
    verify.run()
    new=read(ROOT/'AIDC01_AIDC12_IEEE8500_MAPPING.json')
    old={r['aidc_id']:r for r in read(OLD/'AIDC01_AIDC12_IEEE8500_MAPPING.json')}
    changes=[]
    for r in new:
        prev=old[r['aidc_id']]
        if r['ieee8500_bus']!=prev['ieee8500_bus']:
            changes.append({'aidc_id':r['aidc_id'],'v2_bus':prev['ieee8500_bus'],'guarded_bus':r['ieee8500_bus'],'v2_root_distance_ohm':prev['electrical_root_distance_ohm'],'guarded_root_distance_ohm':r['electrical_root_distance_ohm'],'v2_depth_hops':prev['feeder_depth_corridor_hops'],'guarded_depth_hops':r['feeder_depth_corridor_hops']})
    verify.save('CHANGED_SITES_VS_V2',changes)
    guard=read(ROOT/'ROOT_DISTANCE_GUARD_AUDIT.json');validation=read(ROOT/'SELECTION_VALIDATION.json')
    table='\n'.join(f"| {r['aidc_id']} | `{r['ieee8500_bus']}` | {r['feeder_depth_corridor_hops']} | {r['electrical_root_distance_ohm']:.9f} | {'변경' if r['ieee8500_bus']!=old[r['aidc_id']]['ieee8500_bus'] else '유지'} |" for r in new)
    delta='\n'.join(f"| {r['aidc_id']} | `{r['v2_bus']}` | `{r['guarded_bus']}` |" for r in changes)
    text=f'''# IEEE8500 source-proximity guard 재선정

**TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION**. 원래 638개 candidate의 root electrical-distance q05={guard['root_distance_q05_ohm']:.16f} ohm 미만 32개를 hard-exclude하여 606개 pool에서 동일한 v2 결정적 절차를 재실행했다. 나머지 hard criteria, Melbourne geometry 및 lexicographic ordering은 그대로 유지했다. 모든 조건을 독립 검증에서 통과했고 동일 절차 2회 실행의 mapping/decision log가 일치했다. 전역 최적성은 주장하지 않는다.

## 12-site mapping

Root는 _hvmv_sub_lsb이다. Depth는 집계 corridor hop 수, electrical root distance는 frozen impedance tree metric이다.

| AIDC | Guarded IEEE8500 host | Depth | Root distance (ohm) | v2 대비 |
|---|---|---:|---:|---|
{table}

## v2 대비 변경 site만

| AIDC | 기존 v2 | Guarded selection |
|---|---|---|
{delta}

총 {len(changes)}개 site의 bus가 변경되었고 {12-len(changes)}개는 유지되었다. 기존 12개 host 중 새로운 guard로 직접 제외되는 host는 d5710794-3_int이다. 나머지 변경은 수정된 candidate pool에서 전체 12-site deterministic procedure를 다시 수행한 결과이다. 운영 성능이 개선되었다는 판단은 하지 않는다.

638개 root-distance 분포 및 percentile 통계는 ROOT_DISTANCE_GUARD_AUDIT.json과 CANDIDATE_ROOT_DISTANCE_DISTRIBUTION.csv, 제외 32개는 ROOT_DISTANCE_EXCLUDED_CANDIDATES.csv, 수정 pool은 GUARDED_CANDIDATE_POOL.csv에 있다. 전체 좌표/depth/root distance/group은 AIDC01_AIDC12_IEEE8500_MAPPING.csv에 저장했다. 66 pair 및 geometry 검증은 ALL_66_PAIR_METRICS.csv와 SELECTION_VALIDATION.json에 있다.

selection_v2 및 모든 기존 evidence는 변경하지 않았다. V41R4 또는 May/B0-B3/voltage/loading/sensitivity/performance 결과를 읽지 않았다. AIDC load/PCC 추가, OpenDSS compile 및 B0-B3 실행은 하지 않았다. Source-proximity guard는 topology-only 제한이며 operational benefit에 대한 증거가 아니다.

실행 전 동결은 PROCEDURE_FREEZE_MANIFEST.json, 최종 hash 동결은 GUARDED_SELECTION_FREEZE_MANIFEST.json, v2 전체 파일의 사전/사후 무결성은 V2_IMMUTABILITY_BEFORE.json 및 V2_IMMUTABILITY_VERIFICATION.json에 기록한다.
'''
    (ROOT/'SOURCE_PROXIMITY_RESELECTION_REPORT.md').write_text(text,encoding='utf-8')
    print(json.dumps({'status':validation['status'],'mapping':{r['aidc_id']:r['ieee8500_bus'] for r in new},'changed_site_count':len(changes),'minimum_selected_root_distance_ohm':validation['source_proximity_guard']['minimum_selected_root_distance_ohm'],'metrics':validation['metrics']},indent=2))

if __name__=='__main__':run()
