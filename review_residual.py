"""Generate the bounded experiment report from durable, audited receipts."""
from fractions import Fraction
from v42_pr134_b1.common import read
from v42_a_stage_residual.policy import OUT,STATIC

def run():
    r=read(OUT/'PHASE1_RESULT.json');v=read(OUT/'VERIFICATION.json');freeze=read(OUT/'SOURCE_FREEZE.json')
    d=read(OUT/'MASTER_SOLVE_DIAGNOSTICS.json')['solves'];b=read(OUT/'BATCH_DECISION_TRACE.json')['batches']
    current=OUT/'M19/R0/POSTSOLVE_ATTRIBUTION/RESIDUAL_ATTRIBUTION.json'
    a=read(current if current.exists() else OUT/'HISTORICAL_OPTIMAL_R2/RESIDUAL_ATTRIBUTION.json')
    audit=read(OUT/'TARGETED_CLASS_AUDIT.json')['classes']
    compact=[x.get('compact_migration_recovery',{}) for x in audit]
    stats={k:sum(c.get(k,0) for c in compact) for k in ('blocks_examined','paths_evaluated','exact_tail_terms_evaluated','nonnegative_blocks_pruned','physical_paths_covered_by_exact_pruning')}
    fmt=lambda x:format(float(Fraction(x)),'.17g')
    text=f'''# May19 residual-directed + migration-inclusive Phase-I

최종 판정: **{r['classification']}**. 과학적 상태 **{r['scientific_status']}**. Phi=0 도달: **{r['ACTIVE_DOMAIN_FEASIBLE']}**.
중단 사유: `{r.get('stop_reason','bounded experiment completed')}`.

PR176 exact base `1b34350663b972aeeaeb3a1c20596cbc0dd34b65`에서 새 Draft PR로 적층한다. 실행 source HEAD `{freeze['git_head']}`. 최종 게시 HEAD/URL은 GitHub PR 본문과 외부 `FINAL_PUBLICATION_RECEIPT.json`에 기록한다. 실행 source archive와 실제 모델·raw 데이터 SHA는 `SOURCE_FREEZE.json`, `SHA256_MANIFEST.json`에 보존한다.

May19 한 번, cumulative 1200초, Threads=1/native, pricing worker {r['selected_workers']}개. 모든 이전 48개 활성화와 전체 scientific candidate domain을 보존했다. 물리식·Runtime·CC4·GPU·WAN·grid·허용오차·목적함수·Phi weight 변경은 0건이다. P1·다른 날짜·full A1·Planning/Actual/Fresh AC·production 실행은 0건이다. 150/150 closure를 주장하지 않는다.

초기 새 최적 Phi: `{r.get('initial_phi')}`. 마지막 인증된 Phi: `{r['final_certified_phi']}`.
저장된 이전 PR176 R2 최적점은 먼저 별도로 분해했다. 이전 최적점을 마지막 expanded 모델의 최적점이라고 부르지 않았으며, 새 initial master를 따로 풀었다. 모든 master에 이전 feasible point의 inclusion witness PASS가 있다. Raw Phi 증가가 있어도 feasible 이전 동일-Phi point가 보존되면 실제 악화로 해석하지 않는다. 이 실험의 1% materiality gate에는 raw before/after 값을 그대로 사용한다.

| Master | Native status | Raw Phi | Exact Phi | Zero |
|---|---:|---:|---|---|
'''
    for x in d:text+=f"| {x['iteration']} | {x['status']} | {x['Phi']:.17g} | `{x['exact_Phi']}` | {x['certified_zero']} |\n"
    text+='\n| Batch | STAY | Migration | Size | Phi before | Phi after | Relative reduction | Re-solved |\n|---|---:|---:|---:|---:|---:|---:|---|\n'
    for x in b:
        reduction=None if x['relative_Phi_reduction'] is None else str(100*x['relative_Phi_reduction'])+'%'
        text+=f"| {x['iteration']} | {x['STAY']} | {x['migration']} | {x['batch_size']} | {x['Phi_before']} | {x['Phi_after']} | {reduction} | {x['re_solved']} |\n"
    text+=f'''
확정 activation rounds: {r['activation_rounds']}. 실제 활성화 STAY {r['activated_STAY']}, migration {r['activated_migration']}. Batch는 completed targeted migration 조회와 bounded physical recovery 후에만 선택했다. 최대64, migration 최대32; 검증된 migration이 남는 동안 STAY 최대32. 정확한 class+coupling 효과를 deduplicate하고 residual score→exact rc→identity로 결정한다.

조회한 unique classes {r['unique_classes_queried']}; 완료된 STAY native queries {r['STAY_queries_completed']}, migration native queries {r['migration_queries_completed']}; concrete recovery 완료 class-rounds {r['recovery_classes_completed']}.
독립 검증된 negative concrete STAY {r['negative_STAY']}, migration {r['negative_migration']}. Unmaterialized negative-query directions {r['unmaterialized_negative_blocks']}.
Compact physical recovery: blocks examined {stats['blocks_examined']}, paths evaluated {stats['paths_evaluated']}, exact reusable tail terms {stats['exact_tail_terms_evaluated']}, exact nonnegative block pruning {stats['nonnegative_blocks_pruned']}, covered physical paths by exact pruning {stats['physical_paths_covered_by_exact_pruning']}. Native-point-supported physical migration paths additionally examined {sum(x.get('migration_support_paths_examined',0) for x in audit)}.

각 migration-capable target class의 full compact MIGRATION-only LP(q-sum=N)를 STAY-only LP(q-sum=0)보다 먼저 풀었다. 임시 조회 제약은 scientific model을 변경하거나 후보를 삭제하지 않는다. Native query의 물리 경로 전체 coverage와 bounded concrete recovery의 개별 경로 검사 수를 구분한다. Class당 최대4 STAY·2 migration recovery는 수집 quota이며 domain closure가 아니다. Unmaterialized 값은 음수 인증 bound가 있지만 물리 concrete witness를 회수하지 못한 query 방향 수다. 모든 물리 음수 block의 전수 개수는 미측정이다. Quota 밖의 negative directions도 삭제하지 않는다.

잔차 분해 기준 Phi `{a['exact_Phi']}` ({'새 initial optimal R0' if current.exists() else '저장된 historical optimal R2'}). Signed raw artificial contribution을 그대로 합산했다. Positive weighted sum `{a['positive_weighted_sum']}`; negative roundoff offset `{a['negative_weighted_sum']}`. Raw clipping/rounding/weight 수정은 없다.

| Original row family | Exact weighted Phi | Float |
|---|---|---:|
'''
    for k,x in a['by_original_row_family'].items():text+=f'| {k} | `{x}` | {fmt(x)} |\n'
    text+='\n| Time slot | Weighted Phi |\n|---|---:|\n'
    for k,x in sorted(a['by_time'].items()):text+=f'| {k} | {fmt(x)} |\n'
    text+='\n| Site/node grouping | Weighted Phi |\n|---|---:|\n'
    for k,x in a['by_site'].items():text+=f'| {k} | {fmt(x)} |\n'
    text+='\n| Phi concentration | Minimum rows | Cumulative positive share |\n|---|---:|---:|\n'
    for k,x in a['concentration'].items():text+=f"| {k}% | {x['minimum_row_count']} | {100*x['cumulative_share']:.9f}% |\n"
    text+='\n| Top original row | Time | Node | Weighted artificial | Cumulative share |\n|---|---:|---|---:|---:|\n'
    for x in a['top_rows'][:16]:text+=f"| {x['row']} | {x['time']} | {x['node']} | {fmt(x['weighted_artificial'])} | {100*x['cumulative_positive_share']:.9f}% |\n"
    text+=f'''
GPU/Runtime/WAN/CC4/grid별 직접 artificial attribution: `{a['by_coupling_category']}`. 해당 전압 행은 공유 global grid 행이므로 workload class/AIDC별 독점적 인과 Phi 배분은 식별되지 않는다. 정확한 node/site mapping과 원래 resource-binding 계수로 계산한 heuristic influence를 별도 보고한다. `RESIDUAL_ATTRIBUTION.json`의 모든150개 class 순위와 target IDs, `RESIDUAL_ROWS.csv`, `TARGETED_CLASS_AUDIT.json`에 세부 근거가 있다. Influence는 순위에만 쓰며, admissibility는 original physical membership/local primal/coupling/exact rc<-1e-8의 독립 PASS에만 따른다.

최종 original active 모델 rows/cols/nnz: {r['final_original_model']['rows']:,} / {r['final_original_model']['cols']:,} / {r['final_original_model']['nnz']:,}.
Master 및 pricing의 실제 rows/cols/nnz·factor·RSS는 `ACTUAL_NATIVE_MODEL_SIZE_TRACE.csv`, master auxiliary sizes는 `MODEL_SIZE_TRACE.csv`에 있다. 최대 factor nnz {r['maximum_factor_nnz']:,}; 최대 factor memory {r['maximum_factor_memory_GB']} GB.
Native calls {r['native_calls']}; 모든 native Runtime 합 {r['native_seconds']:.6f}s; Work 합 {r['Work']:.12f}. 실행 wall {r['elapsed_wall_seconds']:.6f}s; 누적 accounting {r['accounted_seconds']:.6f}s; 1200초 초과 persistence/cleanup {max(0,r['accounted_seconds']-1200):.6f}s. Budget reset/sweep/automatic extension 없음. Static reconstruction/qualification과 종료 후 read-only audit는 실행 budget 밖이며 native optimize를 하지 않았다.

검증: synthetic tests173 PASS, tiny1/4-worker raw X/Pi/RC/Slack·exact certificates 동일. 실제 raw native audit {v['native_calls']}, query certificates 재계산 {v['query_certificates_recomputed']}, active normalization potentials 재계산 {v['active_local_potentials_recomputed']}, concrete 후보 재검증 {v['valid_concrete_candidates_recomputed']}. `VERIFICATION.json` PASS. Frozen original matrix/weights와 sequential activation 재구성, 이전 point inclusion, 모든 source archive bytes를 검증했다.

'''
    if r['classification']=='PHASE1_RESIDUAL_DIRECTED_NONMATERIAL':text+='첫 diversified batch의 Phi 감소가1% 미만이므로 요청대로 이 Phase-I pricing architecture의 추가 알고리즘 투자를 중단했다. 두 번째 batch 및 추가 native 실행은 하지 않았다.\n'
    elif r['classification']=='PHASE1_TRACTABILITY_FAIL':text+='1200초/engineering 제한 내 materiality 판단을 완료하지 못했다. 전체 scientific domain infeasibility 증명이나 NONMATERIAL 결론으로 해석하지 않는다. 추가 실행 없이 중단했다.\n'
    else:text+='지정된 decision/budget gate에서 중단했다. 자동 후속 실행은 없다.\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8',newline='\n')
    body=f'''Tests one May19 residual-directed, migration-inclusive Phase-I experiment stacked on [Draft PR176](https://github.com/BeaverVillage/MobileESS/pull/176), exact base `1b34350663b972aeeaeb3a1c20596cbc0dd34b65`.

Result: **{r['classification']}**. Initial Phi `{r.get('initial_phi')}` → final certified Phi `{r['final_certified_phi']}`; zero `{r['ACTIVE_DOMAIN_FEASIBLE']}`. Activated {r['activated_STAY']} STAY / {r['activated_migration']} migration across {r['activation_rounds']} batches. {r['accounted_seconds']:.6f}s accounted, {r['native_seconds']:.6f}s native Runtime, Work {r['Work']:.12f}.

Migration-only exact compact pricing precedes STAY for each target. Independent physical/local/coupling/exact-negative-price checks govern admission; deterministic residual ranking governs up-to64 selection. Original science, frozen Phi weights, tolerances and full domain are retained; all48 prior activations remain. One1200s budget, Threads1, max4 workers, no reset/sweep/followup. No P1 or other dates/pipelines/production.

Validation:173 tests PASS; exact tiny1/4-worker raw/certificate equivalence; read-only audit PASS ({v['native_calls']} raw calls, {v['query_certificates_recomputed']} query certificates, {v['valid_concrete_candidates_recomputed']} concrete candidates). Executed source HEAD `{freeze['git_head']}`. Full Korean report: `docs/v42_a_stage_phase1_residual_migration_20261008/FINAL_REVIEW_KO.md`; immutable source/raw/model records in SHA256 manifest.
'''
    (STATIC/'PR_BODY.md').write_text(body,encoding='utf8',newline='\n')

if __name__=='__main__':run()
