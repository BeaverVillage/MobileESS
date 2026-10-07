"""Read-only result report, separate from all frozen native execution sources."""
import csv, sys
from pathlib import Path
from v42_pr134_b1.common import atomic, read
from v42_a_stage_early.policy import OUT, STATIC
from v42_a_stage_early import BASE

def run(pr_url):
    r=read(OUT/'PHASE1_RESULT.json');v=read(OUT/'VERIFICATION.json');d=read(OUT/'MASTER_SOLVE_DIAGNOSTICS.json')
    batches=list(csv.DictReader((OUT/'PRICING_BATCH_TRACE.csv').open(encoding='utf8')))
    calls=read(OUT/'NATIVE_CALLS.json')['calls']
    per_round=[]
    for folder in sorted((OUT/'M19').glob('R*'),key=lambda p:int(p.name[1:])):
        receipts=[read(p) for p in folder.rglob('EXACT_PRICING.json')]
        native=[c for c in calls if Path(c['folder']).is_relative_to(folder) and c['component']=='LOCAL_PRICING']
        consumed=[p for p in folder.rglob('PRICING_RESULT.json')]
        per_round.append(dict(iteration=folder.name,completed_batches=len(consumed),
            consumed_classes=sum(read(p)['fully_priced_classes'] for p in consumed),
            durable_exact_class_receipts=len(receipts),unique_exact_classes=len({p['class_id'] for p in receipts}),
            valid_negative_candidates=sum(p['candidate'] is not None for p in receipts),
            negative_block_unmaterialized=sum(p['status']=='NEGATIVE_BLOCK_UNMATERIALIZED' for p in receipts),
            native_pricing_calls=len(native),optimal_native_pricing_calls=sum(c['status']==2 for c in native),
            actual_native_classes=[Path(c['folder']).name for c in native],
            exact_receipt_class_ids=[p['class_id'] for p in receipts]))
    atomic(OUT/'PRICING_CLASS_CENSUS.json',dict(PASS=True,rounds=per_round,
        total_consumed_classes=sum(p['consumed_classes'] for p in per_round),
        total_durable_exact_receipts=sum(p['durable_exact_class_receipts'] for p in per_round),
        actual_native_pricing_calls=sum(p['native_pricing_calls'] for p in per_round),
        native_lookahead_and_incomplete_batch_calls_included=True,
        analytical_zero_column_class_has_no_native_call=True))
    size=list(csv.DictReader((OUT/'MODEL_SIZE_TRACE.csv').open(encoding='utf8')))
    text='# PR174 corrected May19 rerun 최종 검토\n\n'
    text+=f"분류: **{r['classification']}** / 과학적 상태 **{r['scientific_status']}**. 종료 사유: {r.get('stop_reason','stagnation / zero gate')}.\n\n"
    text+=f"정확한 base HEAD: `{BASE}` ([Draft PR174](https://github.com/BeaverVillage/MobileESS/pull/174)). 실제 실행 소스 HEAD: `{r['source_commit']}`. [새 Draft PR]({pr_url}).\n\n"
    text+='May19를 단 한 번 실행했다. 900초 누적 예산, Threads=1, 최대4 pricing workers, 고정16-column/24-class 규칙, 연속3회1% 미만 stagnation 규칙을 유지했다. 원래 초기 모델에서 시작했으며 이전 실험 raw point를 warm start로 재사용하지 않았다.\n\n'
    text+='| Master | status | raw Phi | native s | Work | certified zero |\n|---|---:|---:|---:|---:|---|\n'
    for row in d['solves']:
        phi='UNAVAILABLE' if row['raw_Phi'] is None else format(row['raw_Phi'],'.17g')
        text+=f"| {row['iteration']} | {row['status']} | {phi} | {row['native_seconds']} | {row['Work']} | {row['certified_zero']} |\n"
    text+='\nOPTIMAL(status2) solve만 인증된 궤적에 포함한다. TIME_LIMIT9 / INTERRUPTED11의 저장된 raw point는 진단값이며 최적값 인증이 아니다. zero는 unchanged1e-8 기준 및 원래 artificial-free rows/bounds1e-6 replay를 함께 요구한다.\n\n'
    values={
        '인증된 Phi trajectory':r['phase1_trajectory'], 'Phase-I master solves':r['phase1_master_solves'],
        'activation rounds':r['activation_rounds'], '활성화 STAY / migration':(r['activated_STAY'],r['activated_migration']),
        '완료 partial batches':r['partial_pricing_batches'],
        'iteration별 consumed / exact receipts / valid negative / actual native class calls':[(p['iteration'],p['consumed_classes'],p['durable_exact_class_receipts'],p['valid_negative_candidates'],p['native_pricing_calls']) for p in per_round],
        'native seconds / Work':(r['native_seconds'],v['actual_native_Work']),
        'wall / accounted / persistence overshoot seconds':(r['elapsed_wall_seconds'],r['accounted_seconds'],v['soft_stop_overshoot']),
        'final original active rows/cols/nnz':r['final_original_model'],
        'maximum factor nnz / estimated GB':(r['maximum_factor_nnz'],r['maximum_factor_memory_GB']),
        'certified Phi=0 / stagnation':(r['ACTIVE_DOMAIN_FEASIBLE'],r['stagnation']),
        'prior-point witnesses':[(w['iteration'],w['PASS'],w['previous_Phi'],w['mapped_Phi']) for w in d['prior_inclusion_witnesses']],
        '1-worker/4-worker exact equivalence':read(OUT/'PARALLEL_PRICING_EQUIVALENCE.json')['exact_equal'],
        'verification / qualification tests':(v['PASS'],read(OUT/'SYNTHETIC_TESTS.json')['tests']),
        '영구 삭제 / physics or tolerance 변경':(0,0),
    }
    for key,value in values.items(): text+=f'- **{key}:** {value}\n'
    text+='\n| Iteration | original rows / cols / nnz | auxiliary rows / cols / nnz | active STAY / migration |\n|---|---|---|---|\n'
    for row in size:
        text+=f"| {row['iteration']} | {row['original_rows']} / {row['original_cols']} / {row['original_nnz']} | {row['auxiliary_rows']} / {row['auxiliary_cols']} / {row['auxiliary_nnz']} | {row['active_STAY']} / {row['active_migration']} |\n"
    text+='\nraw Phi가 증가해도 이전 해가 같은 Phi로 확장 모델에 포함되면 실제 악화로 분류하지 않는다. 이전 raw 해를 보존하고 별도의 포함 증명을 검증했다. raw Phi는 덮어쓰지 않으며, stagnation 감소율도 raw Phi 그대로 적용했다.\n\n'
    text+='P1, final closure, May17/May12/May10, production/Planning/Actual/Fresh AC는 미실행이다. 어떤 과학적 후보도 영구 삭제하지 않았다. 완전150/150 closure, full-domain infeasibility, integer feasibility 또는 production acceptance를 주장하지 않는다. 재실행, parameter sweep 또는 자동 후속 실행은 하지 않았다.\n\n'
    text+='가격 완료 클래스와 실제 lookahead/중단 배치의 호출은 PRICING_CLASS_CENSUS.json 및 NATIVE_RUN_SOURCES.csv에 구분한다. 모든 실제 native 모델 크기/factor/RSS는 ACTUAL_NATIVE_MODEL_SIZE_TRACE.csv에 기록한다. 추가 solve 없이 저장된 자료만 재검증했다.\n\n'
    text+='활성화 수는 독립 검증된 concrete class-column 수다. 각 column은 해당 클래스의 모든 job을 같은 물리 경로에 배정한다. 실제 native primitive 변수 증가 수는 모델 cols 차이로 별도 기록한다.\n\n'
    text+='총48개 활성화 중 마지막16개는 budget 종료로 재-solve되지 않았다. 마지막 인증 Phi는32개 추가 상태의 R2 값이다. R3 빌드 모델에 이전 R2 해가 동일 Phi로 포함되는지도 solve 없이 검증했다. 네 번째 optimize는 미진입이다.\n\n'
    receipt=STATIC/'FINAL_PUBLICATION_RECEIPT.json'
    text+=f"정확한 최종 HEAD / remote / Draft / clean tree는 외부 [{receipt.name}]({receipt.as_posix()})에 고정한다. 자기 commit 해시 순환참조를 피하기 위한 출판 영수증이다.\n"
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8',newline='\n')

if __name__=='__main__': run(sys.argv[1])
