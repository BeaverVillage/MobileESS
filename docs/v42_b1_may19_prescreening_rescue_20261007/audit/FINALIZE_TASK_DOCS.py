import json,hashlib,csv
from pathlib import Path
ROOT=Path('C:/v42_a1_pr134_supercompact_exact_20261007');CASE=Path('C:/v42_b1_may19_prescreening_rescue_20261007');OUT=ROOT/'docs/v42_b1_may19_prescreening_rescue_20261007'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def record(p):return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)
def write(name,data):(OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
final=read(CASE/'FINAL_RESULT.json')
assert final['classification']=='MAY19_PRESCREENING_UNRESOLVED' and final['planned_shells_exhausted']
assert not (CASE/'SELECTED_DOMAIN.json').exists() and not (CASE/'PRODUCTION').exists()
rows=[];raw=[]
for name in ('S_A','S_B','S_C','S_D'):
    f=CASE/name;r=read(f/'RESULT.json');lp=r['LP'];c=read(f/'CENSUS.json');comp=read(f/'COMPACT/A2SC_MODEL_CENSUS.json')
    assert lp['status']==9 and not lp['valid_primal'] and r['MIP'] is None
    rows.append(dict(shell=name,restored_options=c['added_options'],same_site_options=c['added_starts'],site_prestart_options=c.get('added_prestart_site_candidates',c['added_sites']),migration_options=c.get('added_migration_candidates',0),LP_status='TIME_LIMIT',configured_TimeLimit=600,native_Runtime=lp['native_runtime'],Work=lp['Work'],barrier_iterations=lp['barrier_iterations'],max_original_row_violation=lp['original_full_replay']['max_row_violation'],max_original_bound_violation=lp['original_full_replay']['max_bound_violation'],integer_MIP_executed=False,raw_rows=c['rows'],raw_columns=c['cols'],compressed_rows=comp['rows'],compressed_columns=comp['columns']))
    raw.append(dict(shell=name,raw_point=record(f/'LP_RAW_POINT.npz'),original_matrix=record(f/'EXPANDED_MATRIX.npz'),original_attributes=record(f/'EXPANDED_ATTRIBUTES.npz'),native_names=record(f/'NATIVE_NAMES.npz'),original_full_replay=record(f/'LP_ORIGINAL_FULL_REPLAY.json'),native_log=record(f/'LP_NATIVE.log'),native_start=record(f/'LP_START.json'),valid_primal=False,certified_dual_bound_available=False,integer_upper_bound_available=False))
write('RAW_PRIMAL_EVIDENCE.json',dict(files=raw,original_tolerance=1e-5,rounded_or_clipped=False,native_optimization_repeated=False))
write('FINAL_OUTCOME.json',dict(classification=final['classification'],task_success=False,planned_shells_exhausted=True,shells=rows,total_configured_LP_budget=2400,total_actual_native_LP_runtime=sum(x['native_Runtime'] for x in rows),MIP_optimize_calls=0,normal_A1_optimize_calls=0,Planning_Actual_Fresh_started=False,whole_physical_universe_insufficiency_proven=False,globally_minimal_claimed=False))
with (OUT/'FINAL_TRIAL_SUMMARY.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
v=read(OUT/'VERIFICATION.json');v.update(PASS_scope='artifact integrity and scientific preservation only',task_success=False,rescue_acceptance_PASS=False,LP_feasible_shell=None,MIP_feasible_shell=None,latest_concurrency_authority='USER_CONCURRENCY_AUTHORIZATION.json');write('VERIFICATION.json',v)
size=read(OUT/'SIZE_ENGINEERING_AUDIT.json');last=rows[-1];rawstart=size['S38_raw'];lastc=read(CASE/'S_D/CENSUS.json');compstart=size['S38_compressed']
answers=['시작 도메인은 S38: 확장 클래스 26개, 같은 사이트 시작 옵션 38개이다. 기존 Method1 LP600초 TIME_LIMIT 기록을 보존했다.',
'LP feasible shell 없음. 네 raw LP 점 모두 원래 전체 행·bounds replay를 통과하지 못했다.',
'MIP feasible shell 없음. LP gate 미통과로 정수 MIP는 실행하지 않았다.',
'S38 대비 추가 클래스 0개. S0 대비 복원 대상으로 유지한 클래스는 26개이다.',
'S38 대비 같은 사이트 옵션 +48개, 마지막 테스트 shell의 누적 같은 사이트 옵션 86개이다.',
'사이트/PRESTART 옵션 +64개이다.',
'원래 허용된 migration 경로 옵션 +128개이다. 새 migration 과학적 권한은 만들지 않았다.']
for k,label in (('cols','raw 변수'),('binary','binary'),('rows','raw 행'),('nnz','raw nnz')):
    denom={'cols':'columns','binary':'binaries','rows':'rows','nnz':'nnz'}[k];delta=lastc[k]-rawstart[k]
    answers.append(f'{label}: S38 {rawstart[k]:,} → 마지막 테스트 S_D {lastc[k]:,}, 증가 {delta:,}. S38 compressed {compstart[denom]:,}을 분모로 한 추가량은 {100*delta/compstart[denom]:.6f}%이다.')
answers+=['CC4 변경: NO.','전압 한계 변경: NO (0.95–1.05 유지).','GPU 용량 변경: NO.','Runtime/서비스 변경: NO.','미래 정보 사용: NO.',
'정수 witness 미확보. 정수 MIP 미실행.','정수 해의 original full replay 미실행. raw LP 네 점의 original full replay는 모두 FAIL이다.',
'rho: 정수-feasible gate 미통과로 정상 production 미실행.','migration objective: 미실행.','shift objective: 미실행.','prestart objective: 미실행.',
'Planning freeze: 미실행.','Actual/Fresh: 미실행. Actual/PQ 재최적화 없음.',
'Fresh 물리 위반 개수는 판정하지 않았다. Fresh/정수 검증 자체가 미실행이며, LP 잔차를 물리 검증 PASS로 처리하지 않았다.',
'최종 분류: MAY19_PRESCREENING_UNRESOLVED. 전체 물리 후보 집합의 불가능성을 증명한 결과가 아니다.',
'최종 commit / Draft PR는 PUBLICATION_RECEIPT.json과 최종 전달에 기록한다.']
assert len(answers)==27
text='# May19 practical prescreening rescue\n\n'+ '\n\n'.join(f'{i}. {x}' for i,x in enumerate(answers,1))
text+='\n\n위 옵션 수와 마지막 census는 선택된 production 도메인이 아니라 계획상 마지막으로 테스트한 S_D를 설명한다. 첫 feasible tested shell은 확인되지 않았다. 전역 최소성을 주장하지 않는다.\n\n동시 실행은 최신 사용자 지시로 허용됐다. 각 shell의 시간은 독립 성능 비교나 속도 개선의 근거로 사용하지 않는다. 모든 LP TimeLimit은 600으로 고정했고 실제 native Runtime의 소폭 초과도 그대로 보고한다. 추가 shell, 방법 sweep, 시간 연장, 정상3600초 solve는 실행하지 않았다.\n'
(OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')
print('FINAL_DOCS_UPDATED',final['classification'],'nativeLPsum',sum(x['native_Runtime'] for x in rows))
