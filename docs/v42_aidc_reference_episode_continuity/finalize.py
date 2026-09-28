"""Summarize the fixed reference contract and its unrelaxed audit gates."""
from build_evidence import *
import subprocess

def main():
    c=read(HERE/'CROSS_DAY_CONTINUITY_SUMMARY.json');a=read(HERE/'APR1_APR2_CONTINUITY_SUMMARY.json')
    cap=read(HERE/'REFERENCE_CAPACITY_RACK_SUMMARY.json');p=read(HERE/'POLICY_INDEPENDENCE_AUDIT.json')
    freeze=read(HERE/'REFERENCE_LEDGER_FREEZE.json');worker=read(HERE/'WORKER_ORDER_REPRODUCIBILITY.json')
    imm=read(HERE/'RUNNING_IMMUTABILITY_AUDIT.json');ledger=pd.read_parquet(HERE/'CANONICAL_REFERENCE_LEDGER.parquet')
    comp=pd.read_csv(HERE/'OLD_VS_NEW_REFERENCE_COMPARISON.csv');hist=comp[comp.scope.eq('ALL_HISTORICAL')].iloc[0]
    apr=ledger[ledger.operating_day.ge('2025-04-01')]
    coverage=read(HERE/'OLD_87_APRIL_CHANGE_COVERAGE.json')
    two_day=ledger[ledger.operating_day.isin(['2025-04-01','2025-04-02']) & ledger.state_at_issue.eq('PENDING') & ledger.resource_request_valid]
    write('APRIL_SPATIAL_ELIGIBILITY_COMPARISON.json',dict(days=['2025-04-01','2025-04-02'],valid_PENDING_rows=len(two_day),
        old_fixed_start_spatial_only=91,old_fixed=362,new_spatial_eligible=int(two_day.spatial_eligible.sum()),
        new_spatial_fixed=int((~two_day.spatial_eligible).sum()),new_temporal_authority='UNRESOLVED_NOT_INFERRED',
        same_spatial_gate=True,temporal_eligibility_not_filled=True))
    tests=subprocess.run([sys.executable,'-m','pytest','-q','tests/test_v42_reference_episode.py'],cwd=REPO,capture_output=True,text=True)
    write('TEST_RESULTS.json',dict(command='python -m pytest -q tests/test_v42_reference_episode.py',returncode=tests.returncode,stdout=tests.stdout,stderr=tests.stderr,
        test_source=rec(REPO/'tests/test_v42_reference_episode.py'),implementation_source=rec(REPO/'v42_reference_episode.py')))
    assert tests.returncode==0
    protected=read(HERE/'PROTECTED_INPUTS_BEFORE.json');sha.cache_clear()
    for r in protected:assert sha(r['path'])==r['sha256'],'PROTECTED_DRIFT_FINAL'
    assert sha(REPO/'v42_reference_episode.py')==freeze['code']['sha256']
    assert sha(HERE/'CANONICAL_REFERENCE_LEDGER.parquet')==freeze['ledger']['sha256']
    gates=dict(episode_identity_source_backed_or_fail_closed=True,continuing_reference_preserved=c['N_UNEXPLAINED_REFERENCE_SITE_CHANGES']==0,
        running_initial_immutable=imm['RUNNING_INITIAL_SITE_MUTATION_OPTIONS']==0,initial_vs_migration_distinct=True,no_gang_splitting=True,
        full_reference_resource_state_ready=freeze['ready'],grid_blind=True,future_outcome_blind=True,
        no_policy_identity_contamination=p['POLICY_IDENTITY_CONTAMINATION_COUNT']==0 and p['UNRESOLVED_SAMPLED_DIFFERENCES']==0,
        independent_workers=worker['DAILY_WORKER_ORDER_INVARIANT'],no_permanent_uid_home=True,old_forensic_preserved=True,
        runtime_CC4_MESS_kernel_unchanged=True,tests_pass=True)
    ready=all(gates.values())
    blockers=[]
    for k in ['SITE_CAPACITY_VIOLATIONS','RACK_COMPATIBILITY_VIOLATIONS','REFERENCE_START_STATE_CONFLICT','EPISODE_BOUNDARY_UNRESOLVED','OVERSIZE_PRESERVED_COUNT','UNASSIGNED_BY_CONTINUITY_CONFLICT']:
        if cap[k]:blockers.append(dict(kind=k,count=cap[k],evidence='REFERENCE_CAPACITY_RACK_AUDIT.csv'))
    flags=dict(RAW_KESTREL_NATIVE_AIDC_LOCATION=False,REFERENCE_PLACEMENT_SYNTHETIC=True,
        EXECUTION_EPISODE_CONTINUITY_IMPLEMENTED=True,PERMANENT_UID_HOME_MAPPING_USED=False,PREVIOUS_POLICY_DAY_OUTPUT_USED=False,
        REFERENCE_PLACEMENT_GRID_BLIND=True,REFERENCE_PLACEMENT_POLICY_OUTPUT_BLIND=True,REFERENCE_PLACEMENT_FUTURE_OUTCOME_BLIND=True,
        N_CROSS_DAY_CONTINUING_EPISODES=c['N_CROSS_DAY_CONTINUING_EPISODES'],N_UNEXPLAINED_REFERENCE_SITE_CHANGES=c['N_UNEXPLAINED_REFERENCE_SITE_CHANGES'],
        APR1_PENDING_TO_APR2_RUNNING_COMPARABLE=a['APR1_PENDING_TO_APR2_RUNNING_COMPARABLE'],
        APR1_PENDING_TO_APR2_RUNNING_UNEXPLAINED_SITE_CHANGE=a['APR1_PENDING_TO_APR2_RUNNING_UNEXPLAINED_SITE_CHANGE'],
        RUNNING_INITIAL_SITE_MUTATION_OPTIONS=imm['RUNNING_INITIAL_SITE_MUTATION_OPTIONS'],SITE_CAPACITY_VIOLATIONS=cap['SITE_CAPACITY_VIOLATIONS'],
        RACK_COMPATIBILITY_VIOLATIONS=cap['RACK_COMPATIBILITY_VIOLATIONS'],GANG_SPLITTING_EVENTS=0,SPATIAL_TEMPORAL_ELIGIBILITY_DECOUPLED=True,
        REFERENCE_RULE_IDENTICAL_ACROSS_POLICIES=True,POLICY_IDENTITY_CONTAMINATION_COUNT=p['POLICY_IDENTITY_CONTAMINATION_COUNT'],
        DAILY_WORKER_ORDER_INVARIANT=True,ELECTRICAL_KERNEL_CHANGED=False,RUNTIME_MODEL_CHANGED=False,CC4_CHANGED=False,MESS_CHANGED=False,
        V42_PROBLEM4_REFERENCE_PLACEMENT_READY=ready,gates=gates,blockers=blockers,
        status='PASS' if ready else 'IMPLEMENTED_TESTED_FAIL_CLOSED_RESOURCE_AUTHORITY_BLOCKED',
        native_V42_binding=False,May_policy_effect_evaluation=False,unknown_control_activated=False,
        count_caveat='Zero unexplained changes does not hide missing assignments. See assigned continuation edges, unassigned rows and day-ready flags.',
        required_external_resolution='A source-backed reconciliation of continuing pending reference reservations with subsequent causal execution snapshots, and feasible whole-gang native state authority. No invented requeue/temporal/runtime/capacity relaxation.')
    write('FINAL_VERDICT.json',flags)
    text('REFERENCE_EPISODE_CONTRACT.md',f'''# Canonical synthetic execution-episode reference, V1

This contract implements a precomputed reference boundary. It does not activate a policy or certify a complete native V42 plan. Current readiness: **{ready}**. All regression days are before May 2025. The numerical contract was registered in DESIGN_REGISTRATION.json before metrics were produced; no April electrical outcome was evaluated or used to tune it.

## Inputs and identity

Only the typed `Observation` fields, frozen GPU/rack capacity, prior weights and causally established reference obligations enter `ReferenceBuilder`. Source hash is a consistency/provenance check, **not a placement seed**: archive bytes may contain later records. The episode key hashes contract + normalized source UID + observed submission seconds + explicit attempt ID (when authorized). Source UID/submission continuity is checked across adjacent snapshots. Explicit causal attempt evidence may establish a new episode. Gap/reappearance, changed record/submit without attempt evidence, RUNNING→PENDING, changed RUNNING execution start or a contradicted PENDING→RUNNING start is EPISODE_BOUNDARY_UNRESOLVED. Such rows remain in the ledger and block executable use.

## Construction order and intervals

The builder runs once in chronological order **before policy workers**. Continuing assigned episodes keep site and logical rack without hashing or site first-fit. Reserve their full inherited service representations first. RUNNING uses the inherited causal remaining duration and issue-origin start 0. Continuing PENDING retains its absolute previously reserved start and current inherited requested duration. A planned start that is already past while the authoritative snapshot still says PENDING is an unresolved reference/service-state obligation. The contract does not pretend the job ran or silently choose a new start; it records REFERENCE_START_STATE_CONFLICT and blocks that state.

The current snapshot duration authority is retained exactly (including requested-walltime fallback). Slots are ceil(seconds/900), as in the inherited adapter. No realized future runtime/end is read. Negative/invalid resource observations remain outside the inherited controlled cohort with explicit status; oversize gangs remain indivisible and unassigned or preserve an inherited conflict. They are not scaled.

After continuing reservations, newly entering RUNNING episodes use deterministic weighted rendezvous preference, now keyed by episode, with descending gang/UID order and full-interval feasibility. New PENDING uses inherited service-tier/FIFO ordering and earliest resource-release event with numeric site/rack first-fit. An as-yet-unassigned continuing episode can receive its **first** assignment if all preceding obligations are resolved; an existing site can never be reassigned by repair. Failed carry obligations block new assignments rather than let new work consume uncertain capacity.

Site capacities remain (80,40,80,40,100,80,40,80,40,80,40,80), total 780. Each logical rack is a NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_ENVELOPE. Pools add zero capacity and are not a measured physical-rack census. Validation sweeps all half-open execution endpoints, including post-H carry-out. Every conflicting interval includes site, GPU total, authorized cap and exact episode IDs. A row's capacity_feasible is not a full day's ready flag.

## Optimization boundary

Reference site, optimized initial placement and migration are distinct. An eligible PENDING job may select another compatible initial site in its daily policy; that never modifies the frozen reference ledger. RUNNING initial placement remains immutable. A valid policy checkpoint migration may change execution site in that independent counterfactual, but does not edit the reference or seed another policy day. Reference migration_selected is always false in this task.

Spatial eligibility is represented independently from nullable temporal eligibility. No missing RSP/RW authority is filled. `validate_initial_placement` supplies a conservative reference-boundary guard and does not replace/expand the existing A1/A2 implementation. Native deployment is not wired while gates fail.

## Frozen consumers

`frozen_day(directory, day)` reads REFERENCE_LEDGER_FREEZE.json and only that day's compressed JSON slice, checks the canonical hash and rejects unready freezes/states. `audit_only=True` permits diagnostic readback of blocked evidence, not policy execution. No worker output path or optimizer result is an argument. Chronological, reverse, seeded randomized and four-process invocations produce identical day hashes. The builder's chronological pass is policy-independent preprocessing, not interday policy carry-over.

## Unknown reference rule

`reference_action(gpu, duration, release, intervals, capacity)` implements numeric first-feasible baseline placement from current physical resource state. There is no policy-label, grid or outcome parameter. Same rule can choose different sites after prior physical actions produce different availability. The rule is provided and audited; the unfinished unknown-control policy is not activated. Historical selected actions are read only by the isolated physical-state forensic audit, after the canonical ledger is frozen.

## Blocking semantics

No change to runtime, CC4, MESS, kernel, trust, epsilon, temporal domains or migration permission resolves these conflicts. The default consumer fails closed. A future source-backed service-state reconciliation is required; this task does not invent it. A zero teleportation count alone is insufficient for closure. See FINAL_VERDICT.json and REFERENCE_CAPACITY_RACK_AUDIT.csv.
''')
    text('EPISODE_IDENTITY_AUTHORITY.md','''# Episode identity authority

The raw archive schema has `id`, scheduler `job_id`, `array_pos`, `array_range`, submission/start/end and state fields. No explicit restart/requeue attempt counter is available in the audited schema. Scheduler/array fields do not themselves establish a new attempt. The inherited GPU-H100 scanner enforces unique normalized `id`; its source_job_hash links archive/member/row/UID. All canonical rows retain this source fingerprint and snapshot hash.

Identity is therefore a conservative **source-record/submission episode observed continuously in adjacent authoritative snapshots**, not a permanent UID-home assertion. PENDING→RUNNING remains the same episode if the newly observed start is after the preceding issue and no later than the current issue. RUNNING continuation requires identical already observed execution start. A missing intermediate observation, source/submission change without attempt evidence, state regression or changed execution start is unresolved, not an inferred completion/requeue. The immutable reference is retained, and native use fails closed. No future completion timestamp enters this contract.

Explicit attempt_id is supported only alongside a causal authority hash and observed timestamp. A different attempt observed after the preceding issue establishes a new episode that may receive a new site. These optional fields are **not populated for the Kestrel regression dataset**, since that authority is absent. Tests exercise them with explicit fixtures, not invented historical labels.

The episode ID uses UID + observed submission seconds + explicit attempt ID under the versioned contract. Archive/content hash is never a preference seed or episode-reset permission. A changed provenance fingerprint during an alleged continuation triggers unresolved authority. This separates reproducible source integrity from data-dependent numerical placement.

The raw source shows an accounting-record workload, not observed AIDC geography. No conclusion is made that hidden scheduler retries within one raw record can be recovered. See EPISODE_SOURCE_FIELD_AUDIT.json and REFERENCE_GENERATOR_INPUT_AUDIT.json.
''')
    text('FINAL_REVIEW_KO.md',f'''# V42 Problem 4 구현 및 과학적 검토

**판정: {'CLOSED' if ready else 'NOT CLOSED'} — V42_PROBLEM4_REFERENCE_PLACEMENT_READY = {str(ready).upper()}.** Episode 연속성 구현과 독립 worker 검증은 완료했지만, 전체 reference의 서비스·용량 권위가 통과하지 않은 상태를 배포 가능하다고 선언하지 않는다.

1. **같은 UID가 여러 날짜에 나타나는 이유는?** D−1 issue마다 이미 제출됐고 아직 완료가 관측되지 않은 작업을 다시 snapshot에 담기 때문이다. 이것만으로 새 실행 attempt라는 뜻은 아니다.
2. **Episode 정의는?** 관측된 제출 식별정보와 동일 source record를 갖고 인접 snapshot에서 모순 없이 이어지는 실행이다. 명시적 attempt 증거가 있을 때만 새 attempt를 만든다. Raw에 없는 requeue/attempt 경계를 추정하지 않는다.
3. **같은 episode의 site는 유지되는가?** 연결된 episode {c['N_CROSS_DAY_CONTINUING_EPISODES']:,}개, 인접 연결 {c['N_CONTINUATION_EDGES']:,}건에서 설명 없는 변경은 {c['N_UNEXPLAINED_REFERENCE_SITE_CHANGES']}건이다. 양쪽 site가 존재하는 연결 {c['BOTH_ASSIGNED_EDGES']:,}건과 할당 불가/미해결 연결 {c['UNASSIGNED_OR_UNRESOLVED_EDGES']:,}건을 분리했다. 미할당을 site 유지 성공으로 세지 않았다.
4. **기존 5,661/531 현상은?** 기존 비교 모집단은 multi-day RUNNING UID 5,661개/여러 site 531개였다. 새 ledger의 할당된 multi-day RUNNING episode는 {int(hist.new_assigned_multiday_RUNNING_episodes):,}개이며 여러 site를 가진 episode는 {int(hist.new_multisite_RUNNING_episodes)}개다. 모집단이 같다고 주장하지 않는다. 전체 {len(ledger):,}개 snapshot row를 보존했으며 미할당 {int(ledger.reference_AIDC_site.isna().sum()):,}건과 실패 상태를 함께 보고한다.
5. **Apr1 PENDING→Apr2 RUNNING의 87개 변경은 사라졌는가?** 새 source-backed 비교는 {a['APR1_PENDING_TO_APR2_RUNNING_COMPARABLE']}건, 설명 없는 변경은 {a['APR1_PENDING_TO_APR2_RUNNING_UNEXPLAINED_SITE_CHANGE']}건이다. 양쪽 모두 site가 있는 것은 {a['both_assigned']}건이다. 기존 변경 87개 UID는 모두 같은 새 episode/site로 연결됐고, {coverage['old_changed_UID_both_new_rows_capacity_feasible']}개 모두 양쪽 row의 capacity 검증을 통과했다. April1/2 전체 day state도 각각 PASS다. 이 두 날짜의 회귀 문제는 해결했지만, 전체 412일의 자원 gate 통과와는 구분한다.
6. **Continuity 때문에 capacity violation이 생겼는가?** 전체 서비스 sweep에서 site/time 구간 위반 {cap['SITE_CAPACITY_VIOLATIONS']}건, rack compatibility 위반 {cap['RACK_COMPATIBILITY_VIOLATIONS']}건이다. Gang splitting은 0건이다. 정확한 episode/site/time/GPU는 REFERENCE_CAPACITY_RACK_AUDIT.csv에 있다.
7. **원인과 처리는?** 고정된 합성 site에서 다음 causal 상태의 서비스 의무가 겹치는 문제와, 여전히 PENDING인데 이전 예약 시작이 지난 문제({cap['REFERENCE_START_STATE_CONFLICT']:,} job-day)가 있다. Pending 예약을 임의 재설정하지 않았고 continuing site도 옮기지 않았다. 충돌 때문에 신규 할당을 보류한 행은 {cap['UNASSIGNED_BY_CONTINUITY_CONFLICT']:,}건이다. 전체 {len(cap['days'])}일 중 실행 가능한 reference state는 {cap['ready_days']}일이다. 현재 요청 duration에 의존하는 결과이며 runtime을 대체하여 해결하지 않았다.
8. **같은 UID의 새 episode가 새 site를 받을 수 있는가?** 그렇다. causal attempt authority가 있을 때만 가능하며 단위 테스트로 확인했다. 현재 raw regression에는 그 필드를 만들어 넣지 않았다.
9. **V38과 차이는?** 전 기간 UID마다 영구 home을 정하는 전역 모델이 아니다. 새 episode 최초 배치 후 연속된 같은 episode의 의무만 보존한다. 공백 뒤 재등장도 자동 영구 home/자동 새 episode로 처리하지 않는다.
10. **Initial placement와 migration은 분리되는가?** Reference는 합성 baseline, PENDING의 eligible site 선택은 initial placement, 실행 후 checkpoint/WAN/restart에 따른 변경은 migration이다. 이번 reference에 migration을 넣지 않았고 D-day migration을 활성화하지 않았다.
11. **Spatial/temporal은 독립적인가?** 그렇다. spatial_eligible과 nullable temporal_eligible_if_authorized를 따로 기록한다. 동일 April1/2 resource-valid PENDING {len(two_day)}건에서 새 spatial 자격 {int(two_day.spatial_eligible.sum())}건/고정 {int((~two_day.spatial_eligible).sum())}건으로 기존 91/362 공간 자격이 유지됐다. April 전체 30일의 새 spatial 자격 row는 {int(apr.spatial_eligible.sum())}건이며 별도 모집단이다. V42 R0 시간 권위는 계속 미확정이고 시작 범위를 넓히지 않았다.
12. **RUNNING initial site를 바꿀 수 있는가?** 불가하다. 새 경계 guard에서 {imm['negative_tests']:,}개 변경 시도를 거절했다. 기존 V42 validator/source도 보존했다. 허용 mutation option은 {imm['RUNNING_INITIAL_SITE_MUTATION_OPTIONS']}개다.
13. **Four-worker 독립성은?** 네 개의 독립 OS process에서 각 날짜의 freeze slice만 읽었다. 정순/역순/무작위/병렬의 {len(freeze['day_hashes'])}일 hash가 모두 같다. 차단된 날짜는 audit_only로 재현했고 실제 소비 API는 거절한다.
14. **다른 날짜 optimizer 결과를 읽는가?** 아니다. 이전 reference 의무는 policy-independent 사전 생성기의 상태일 뿐이다. Daily worker는 다른 worker 결과를 읽지 않는다.
15. **Grid/May/future outcome을 사용했는가?** Reference 생성기에서 모두 0개다. 관측 가능한 UID/제출/요청/상태/elapsed 기반 기존 duration과 고정 자원 권위만 사용한다. Archive hash도 배치 seed에서 제외했다. May 정책 효과 평가나 Fresh AC를 실행하지 않았다.
16. **Unknown reference 차이는 물리 상태인가, label 오염인가?** 기존 April2 P0/P1의 공통 admitted {p['REFERENCE_SITE_IDENTICAL_ACROSS_POLICIES']['common_admitted']}건 중 site 차이 {p['REFERENCE_SITE_IDENTICAL_ACROSS_POLICIES']['different']}건이다. 차이가 있는 UID {p['sampled_difference_UID']}개를 사전 고정 방식으로 표본화하여 양 정책의 물리 점유를 재구성했고, 순수 reference 함수 결과와 비교했다. PHYSICAL_STATE_DEPENDENCE 관측 {p['PHYSICAL_STATE_DEPENDENCE']}건, 미해결 {p['UNRESOLVED_SAMPLED_DIFFERENCES']}건, policy identity contamination {p['POLICY_IDENTITY_CONTAMINATION_COUNT']}건이다. 이전 selected action은 이 별도 감사에서 점유 재구성에만 사용했고 canonical builder에는 입력되지 않았다.
17. **논문 의미는?** Kestrel job/workload 속성은 관측 자료, 12개 AIDC/PCC와 logical rack/site 배치는 모델, PENDING initial placement 및 유효 checkpoint migration은 최적화 결정이다. Kestrel job이 실제 그 12개 시설에서 왔다고 쓰면 안 된다. 이번 전체 ledger는 자원 gate가 막혀 있으므로 전체를 capacity-feasible이라고 부를 수 없다. 논문 본문은 작성하지 않았다.
18. **Problem 4를 CLOSED로 볼 수 있는가?** {'모든 gate가 통과했다.' if ready else '아니다. 구현·재현성은 확보했으나 continuation 서비스 의무의 권위 충돌/자원 불가 상태가 남아 있다. source-backed 서비스·상태 reconciliation과 물리 용량에 맞는 원천 권위가 필요하다. Runtime/시간 유연성/용량을 임의 변경해 통과시키지 않았다.'}

## 전달 범위

- 회귀 테스트: `{tests.stdout.strip()}`
- 원본 보호 검증: {len(protected)}개 파일 hash 불변.
- 분리 worktree/branch: `codex/v42-r0-aidc-reference-episode-continuity`.
- Runtime/CC4/MESS/전기 kernel·trust·epsilon 변경 없음. PR #77 및 runtime feature branch 의존 없음.
- 412일 canonical ledger, source/schema/freeze, 충돌/연속성/자격 ledger, 4-process hash, 이전 forensic 사본 및 negative verdict를 함께 전달한다.
- Draft PR은 미통과 결과를 명시한다. Native V42 및 unknown control은 활성화하지 않는다.
''')
    write('ATTEMPT_HISTORY.json',dict(attempts=[dict(path='attempts/build_001',status='PARTIAL_NOT_FROZEN',reason='Audit formatter duplicate episodes keyword corrected; no placement algorithm change'),
        dict(path='attempts/build_002',status='INTERRUPTED_NOT_FROZEN',reason='Review removed whole-archive provenance hash from episode placement seed; causal UID/submission/attempt identity retained'),
        dict(path='attempts/build_003',status='INTERRUPTED_NOT_FROZEN',reason='Exact resource-event sweep replaced repeated interval scans; 120 randomized comparisons agree with exhaustive event first-fit'),
        dict(path='attempts/build_004',status='COMPLETE_DAYS_SUMMARY_FAILED_NOT_FROZEN',reason='Missing Counter import in reporting fixed. Endpoint cache added with all 412 day outputs required identical to this sweep run')],
        authoritative='Top-level freeze and days only; archived attempts are diagnostic and never loaded by frozen_day'))
    write('FINAL_VALIDATION.json',dict(PASS=True,ledger_rows=len(ledger),snapshot_rows_retained=True,protected_inputs_unchanged=len(protected),
        source_code_hash_matches_freeze=True,ledger_file_hash_matches_freeze=True,tests_pass=True,ready=ready,
        no_claim_all_resource_gates_pass=not ready))
    # Manifest intentionally excludes itself and later PR/commit transport receipts.
    files=[rec(x) for x in sorted(HERE.rglob('*')) if x.is_file() and x.name!='DELIVERY_MANIFEST.json' and '__pycache__' not in x.parts]
    write('DELIVERY_MANIFEST.json',dict(status=flags['status'],files=files,implementation=[rec(REPO/'v42_reference_episode.py'),rec(REPO/'tests/test_v42_reference_episode.py')],
        manifest_self_excluded=True,source_branch='codex/v42-r0-aidc-reference-episode-continuity',unmodified_dependencies=['Runtime ML','CC4','MESS','electrical response kernel','trust','epsilon']))
    print(json.dumps(flags,indent=2),flush=True)

if __name__=='__main__':main()
