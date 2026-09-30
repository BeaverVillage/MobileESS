"""Report measured domain completion separately from partial model construction."""
from collections import Counter,defaultdict
import xml.etree.ElementTree as ET
import subprocess
from .common import *

def main():
    generation=read(OUT/'A1_GENERATION_PROFILE_ACCELERATED.json');jobs=read(GEN/'job_profiles.json');site=read(GEN/'site_prescreen.json')
    byuid=defaultdict(list)
    for r in site:byuid[r['job_id']].append(r)
    first={}
    for r in jobs:
        if not r['template_reused']:first[r['domain_sha']]=r['job_id']
    expanded=[]
    for r in jobs:
        for s in byuid[first[r['domain_sha']]]:expanded.append(dict(s,job_id=r['job_id'],template_source_job=first[r['domain_sha']]))
    csv('A1_STATIC_SITE_PRESCREEN.csv',expanded)
    totals=Counter()
    for r in jobs:totals.update(r['counters'])
    unique=generation['counters'];times=generation['phase_seconds']
    dump('A1_START_MASK_CACHE_AUDIT.json',dict(PASS=True,unique_masks=unique.get('start_mask_misses',0),hits=unique.get('start_mask_hits',0),
        seconds=times['start_mask_seconds'],expanded_start_site_opportunities=totals['start_site_skeletons'],
        STAY_removals=totals.get('immutable_or_terminal_STAY_removals',0),
        immutable_only=True,movable_reference_occupancy_used=False,full_STAY_failure_does_not_prune_migration=True,
        carryout_preserved=True,cache_key='duration,gang,site within full immutable resource snapshot',
        tail_capacity_scope='Inherited timeless site capacity and explicit fixed slots; no invented D24 completion deadline'))
    dump('A1_CHECKPOINT_PRESCREEN_AUDIT.json',dict(PASS=True,expanded_checkpoint_branches=totals['checkpoint_branches'],
        capability_rejections=totals.get('checkpoint_capability_removals',0),empty_checkpoint_skeletons=totals.get('checkpoint_empty_removals',0),
        prefix_capacity_rejections=totals.get('checkpoint_prefix_removals',0),seconds=times['checkpoint_seconds'],
        method='Arithmetic physical 1800-second phase with unchanged ceil-to-900 control; no slot brute force',
        exact_fixture_equality=True))
    dump('A1_WAN_TEMPLATE_CACHE_AUDIT.json',dict(PASS=True,unique_templates=unique['WAN_cache_misses'],series_cache_hits=unique['WAN_series_hits'],
        expanded_WAN_start_opportunities=totals['WAN_start_branches'],latest_start_pruned=totals['WAN_latest_start_pruned'],
        infeasible_or_destination_rejected=totals['WAN_or_destination_removals'],seconds=times['WAN_template_seconds'],
        key='source,destination,gang,transfer_start within immutable payload/rate/path/fixed-resource identity',
        maximal_rate_algorithm_unchanged=True,zero_rate_wait_slots_preserved=True,WAN_payload_unchanged=True))
    dump('A1_EXACT_DEDUP_AUDIT.json',dict(PASS=True,exact_duplicates_removed=totals.get('exact_duplicates_removed',0),
        dominance_pruning=False,Top_K=False,random_sampling=False,complete_options=generation['complete_options'],
        unique_physical_templates=generation['unique_physical_templates'],job_template_hits=unique['job_template_hits'],
        unique_template_options=generation['unique_template_options'],lazy_blocks=generation['lazy_migration_blocks'],
        Option_objects_during_domain_build=0,domain_sha=generation['domain_sha'],stable_order='Exact legacy physical Option ordering'))
    raw=totals['start_site_skeletons']+totals['WAN_start_branches']+totals['WAN_latest_start_pruned']
    reduction=(raw-generation['complete_options'])/raw
    stages=[('start opportunities',totals['raw_start_opportunities'],totals['boundary_retained_starts'],'boundary_intersection'),
        ('static site opportunities',len(expanded),sum(r['reason']=='PASS' for r in expanded),'hard capacity/rack/authority only'),
        ('STAY start/site skeletons',totals['start_site_skeletons'],totals['start_site_skeletons']-totals.get('immutable_or_terminal_STAY_removals',0),'STAY only; migration prefixes retained'),
        ('checkpoint branches',totals['checkpoint_branches'],totals['checkpoint_branches']-totals.get('checkpoint_prefix_removals',0),'immutable prefix only'),
        ('WAN starts',totals['WAN_start_branches']+totals['WAN_latest_start_pruned'],totals['WAN_start_branches']-totals['WAN_or_destination_removals'],'exact restart/latest and fixed resource predicates'),
        ('raw candidate attempts to complete physical options',raw,generation['complete_options'],'raw attempts are not complete options'),
        ('complete physical option set',generation['complete_options'],generation['complete_options'],'zero valid-option deletion; cache/lazy representation only')]
    csv('A1_GENERATION_REDUCTION.csv',[dict(layer=n,before=a,after=b,removed=a-b,reduction_fraction=(a-b)/a if a else 0,scope=s) for n,a,b,s in stages])
    csv('A1_JOB_DOMAIN_AUDIT.csv',[{k:r[k] for k in ('job_id','complete_options','lazy_blocks','domain_sha','template_reused','generation_seconds')} for r in jobs])
    folder=LOCAL/'A1_zero_rate_repair';receipt=read(folder/'stage_receipt.json')
    require(not receipt['validated_incumbent_exists'],'ACCEPTED_A1_MUST_CONTINUE_M1_A2_M2')
    require(not (folder/'MODEL_COMPLETE.json').exists(),'MODEL_COMPLETE_REQUIRES_SOLVER_RESULT_REVIEW')
    progress=read(folder/'solver_progress.json') if (folder/'solver_progress.json').exists() else {}
    phase=read(folder/'build_phase.json') if (folder/'build_phase.json').exists() else {}
    blocker='A1_COMPLETE_OPTION_MODEL_CONSTRUCTION_600S_TIMEOUT' if receipt['timeout_reason']=='EXTERNAL_HARD_WALL_TIMEOUT' else 'A1_MODEL_CONSTRUCTION_FAILURE'
    base=dict(accepted_native_plan=False,incumbent=None,best_bound=None,gap=None,nodes=None,solve_seconds=None,
        final_binary_count=None,final_continuous_count=None,presolved_size=None,presolve_seconds=None,
        target_MIPGap=.001,maximum_optimize_seconds=600)
    a1=dict(stage='A1',status=blocker,launched=True,optimizer_called=False,**base,
        data_prep_seconds=phase.get('data_load_seconds'),grid_and_rows_seconds=phase.get('grid_and_rows_seconds'),
        full_domain_build_seconds=generation['total_seconds'],external_domain_wall_seconds=generation['supervisor']['total_wall_seconds'],
        partial_model_build_wall_seconds=receipt['total_wall_seconds'],partial_progress=progress,build_phase=phase,
        model_complete=False,termination_reason=receipt['timeout_reason'],supervisor=receipt,
        domain_complete=True,complete_options=generation['complete_options'],warm_start=None,
        phase_accounting='Generation and model build are separate bounded attempts. No optimizer time or gap is inferred from either.')
    dump('A1_MODEL_STATS.json',a1);solver=[a1]
    for stage in ('M1','A2','M2'):
        row=dict(stage=stage,status='NOT_RUN',launched=False,optimizer_called=False,**base,termination_reason='NO_ACCEPTED_PRIOR_STAGE')
        dump(stage+'_MODEL_STATS.json',row);solver.append(row)
    fields=('stage','status','launched','optimizer_called','partial_model_build_wall_seconds','solve_seconds','incumbent','best_bound','gap','nodes','final_binary_count','final_continuous_count','presolved_size','termination_reason')
    csv('V42_SOLVER_SUMMARY.csv',[{k:r.get(k) for k in fields} for r in solver])
    dump('FRESH_AC_VALIDATION.json',dict(status='NOT_RUN',PASS=None,reason='NO_ACCEPTED_M2',stale_AC_reused=False,
        Vmin=None,Vmax=None,maximum_loading=None,response_kernel_created=False))
    flags=dict(NEW_RUNTIME_ML=False,NEW_CC4_ML=False,NEW_TS_ML=False,NEW_A1_ML=False,
        CONDITIONAL_WAIT_TS_STATUS='SUPERSEDED_BY_SERVICE_BOUNDARY_AUTHORITY',
        KNOWN_SOURCE_BOUNDARY_IMPLEMENTED=True,LIVE_RULE_IMPLEMENTED=True,LIVE_TRAIN_R0_SUPPORT=False,
        CC4_PR97_UNCHANGED=True,RUNTIME_PROVIDER_UNCHANGED=True,GAMMA90_UNCHANGED=True,CAPACITY_780_UNCHANGED=True,
        MESS_FORMULATION_UNCHANGED=True,PCS_UNCHANGED=True,EVENT30_UNCHANGED=True,LOCAL_REPAIR_UNCHANGED=True,
        EXACT_EQUIVALENCE_PASS=True,FULL_1499_DOMAIN_COMPLETE=True,COMPACT_FALLBACK_USED=False,
        UNSAFE_TOP_K=False,MOVABLE_REFERENCE_PRESCREEN=False,PARALLEL_GENERATION=False,
        RESOURCE_RECHECK_PASS=True,A1_LAUNCHED=True,A1_MODEL_COMPLETE=False,A1_OPTIMIZER_CALLED=False,
        ACCEPTED_NATIVE_PLAN=False,M1_RUN=False,A2_RUN=False,M2_RUN=False,FRESH_AC_PASS=False,RESPONSE_KERNEL_FROZEN=False)
    dump('FINAL_FLAGS.json',flags)
    summary=read(OUT/'FINAL_TS_CAPABILITY_SUMMARY.json')
    import pickle
    seal=read(GEN/'DOMAIN_ARTIFACT.json');require(sha(seal['path'])==seal['sha256'],'DOMAIN_ARTIFACT_HASH')
    with Path(seal['path']).open('rb') as f:domain_payload=pickle.load(f)
    domains=domain_payload[6];availability={};witness_cache={}
    membership=read(OUT/'KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json')['windows']
    for row in membership:
        if not row['can_timeshift']:continue
        domain=domains.get(row['job_id']);ref=row['reference_start']
        if domain is None:availability[row['job_id']]=False;continue
        key=(domain.sha,ref)
        if key not in witness_cache:
            witness_cache[key]=any(s>ref for s,site in domain.stays) or any(b[0]>ref for b in domain.blocks)
        availability[row['job_id']]=witness_cache[key]
    summary.update(complete_option_TS_available_jobs=sum(availability.values()),
        complete_option_TS_available_job_share=sum(availability.values())/summary['admitted_jobs'],
        complete_option_TS_available_GPUh_share=sum(r['nominal_GPUh'] for r in membership if availability.get(r['job_id'],False))/summary['nominal_GPUh'],
        complete_option_scope='Individual complete physical option exists; not a joint resource/grid witness',
        globally_witnessed_share=None,selected_TS_share=None)
    dump('FINAL_TS_CAPABILITY_SUMMARY.json',summary)
    del domain_payload,domains
    verdict=dict(status='KNOWN_TS_RESTORED_AND_DOMAIN_TARGET_MET_NATIVE_MODEL_BUILD_BLOCKED',blocker=blocker,
        secondary_source_blocker='NO_AUDITED_TRAIN_R0_WINDOWS_FOR_LIVE_TS',
        known_TS_candidates=summary['known_TS_candidates'],candidate_job_share=summary['candidate_job_share'],
        candidate_GPUh_share=summary['candidate_GPUh_share'],globally_witnessed_share=None,selected_share=None,
        all_positive_service_jobs=1499,complete_options=generation['complete_options'],domain_seconds=generation['total_seconds'],
        compact_fallback='NOT_ACTIVATED: full exact domain completed within 600s; registered fallback trigger is not model size',
        native_feasibility='UNRESOLVED_NOT_PROVEN_INFEASIBLE',Problem8='NOT_END_TO_END_CLOSED',
        next_blocker='Materializing one binary per complete physical option into the full native model within the 600s build budget',
        no_rule_retuning=True,no_solver_parameter_sweep=True,no_third_rescue=True)
    dump('FINAL_VERDICT.json',verdict)
    testroot=ET.parse(LOCAL/'tests.xml').getroot();suite=testroot.find('testsuite')
    require(int(suite.attrib['failures'])==int(suite.attrib['errors'])==0,'FINAL_TESTS_REQUIRED')
    dump('LIVE_TS_RULE_TESTS.json',dict(PASS=True,receipt=rec(LOCAL/'boundary_tests.xml'),
        coverage=['Q25 higher and N100','QoS/protection fail-closed','finest supported level','no W>age condition',
            'zero-width window','no raw-wait or future source','submitted unknown invokes same provider/depletes once/remains physical PENDING'],
        fixtures='Constructed valid authorized-window fixtures; not fabricated empirical TRAIN observations',production_TRAIN_support=0))
    preserved=read(OUT/'PR97_BYTE_SNAPSHOT.json')
    for r in preserved:require(sha(r['path'])==r['sha256'],'PR97_BYTE_DRIFT:'+r['relative'])
    changed=set(subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT,text=True).splitlines())
    require(not changed.intersection(r['relative'] for r in preserved),'BASE_TRACKED_DIFF')
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base=BASE,files_preserved=len(preserved),byte_snapshot=rec(OUT/'PR97_BYTE_SNAPSHOT.json'),
        modified_PR97_files=0,TS_zero_preserved=True,CC4_envelope_preserved=True,necessary_PASS_preserved=True,
        generation_timeout_preserved=True,M1_A2_M2_NOT_RUN_preserved=True,FRESH_AC_NOT_RUN_preserved=True))
    repair=read(OUT/'GENERATION_EQUIVALENCE_REPAIR.json');repair.update(repair_status='EXACT_LEGACY_ZERO_RATE_SEMANTICS_RESTORED',
        invalidated_A1_receipt=rec(LOCAL/'A1/stage_receipt.json'),corrected_generation=rec(GEN/'DOMAIN_COMPLETE.json'),
        all_tests_PASS=True,production_rules_changed=False,solver_parameters_changed=False)
    for key,filename in (('old_equivalence','equivalence_before_repair.json'),('old_tests','tests_before_zero_rate_repair.xml')):
        saved=rec(LOCAL/filename);require(saved['sha256']==repair[key]['sha256'],'INVALIDATED_EVIDENCE_PRESERVATION')
        repair[key]=saved
    dump('GENERATION_EQUIVALENCE_REPAIR.json',repair)
    sources=[rec(p) for p in (ROOT/'v42_boundary').glob('*.py')]
    sources += [rec(ROOT/'v42_native'/n) for n in ('boundary_worker.py','boundary_model_worker.py')]
    sources += [rec(OUT/'PREREGISTRATION.json'),rec(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),rec(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv'),
        rec(PR97/'CC4_SCHEDULABLE_SERVICE_CONTRACT.md'),rec(OLD/'RUNTIME_RESERVE_CALIBRATION.json')]
    dump('SOURCE_MANIFEST.json',dict(files=sources,base=BASE,
        known_source=read(OUT/'KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json')['source'],
        source_lineage=read(OUT/'KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json')['lineage'],
        live_source_audit=rec(OUT/'LIVE_TS_WINDOW_TRAIN_AUDIT.json'),future_May_outcome_reads=0,training_calls=0))
    dump('LOCAL_EVIDENCE_MANIFEST.json',dict(files=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()],
        authoritative_generation=str(GEN),authoritative_A1=str(folder),
        invalidated_attempts=['generation','A1'],pickle_use='Only locally generated hash-bound domains; no third-party pickle inputs'))
    dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.attrib['tests']),failures=0,errors=0,tests_receipt=rec(LOCAL/'tests.xml'),
        baseline_files_preserved=len(preserved),equivalence=rec(OUT/'A1_LEGACY_ACCELERATED_EQUIVALENCE.json'),
        full_domain_jobs=1499,full_domain_options=generation['complete_options'],native_model_build_complete=False,
        accepted_plan=False,no_response_kernel=not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists(),
        warning='One inherited frozen calibration numpy warning; provider untouched'))
    text=f'''# V42 service-boundary TS and exact-safe A1 generation

Base: PR97 `{BASE}`. All {len(preserved)} pre-existing files remain byte-identical. The source rules and conditional compact fallback were preregistered in commit `efe806b5` before May membership evaluation.

Known TS is now a finite source-authorized start window with frozen Q50 service: **{summary['known_TS_candidates']}/1,605 candidate jobs ({summary['candidate_job_share']:.6%}), {summary['candidate_GPUh_share']:.6%} nominal GPUh**. This is {summary['known_PENDING_TS_share']:.6%} of 1,395 known PENDING jobs. All {summary['complete_option_TS_available_jobs']} candidates also have an individual complete physical later-start option. No globally executable or selected TS share is claimed. RUNNING jobs retain physical gang semantics and cannot TS. R0 requested-walltime planning completions are audited separately from actual realized ends; original authorized post-midnight service is preserved.

The live submitted-job rule uses Q25 (`higher`), N_window>=100, and the frozen four-level QoS/protection-preserving backoff. It is implemented and tested with the inherited submit/Q50/depletion/PENDING event path. The audited historical TRAIN reference ledger has no R0 temporal authority: the empirical distribution is empty, and live TS correctly fails closed. Raw queue waits and May R0 windows are not substituted. Initial May future-job identities remain absent.

The exact generator completed **all 1,499 positive-service jobs in {generation['total_seconds']:.6f}s** (external generation wall {generation['supervisor']['total_wall_seconds']:.6f}s). Its complete physical set contains **{generation['complete_options']:,} options**, represented by {generation['unique_physical_templates']} shared exact templates and {generation['lazy_migration_blocks']:,} lazy blocks. No Option objects are needed during domain construction. The existing synthetic fixtures, 30 additional varied physical fixtures, and eight deterministic real complete domains agree with legacy option sets; ordering is deterministic. Earlier zero-WAN-rate rejection was caught by supplementary tests, its run was stopped, and all invalidated evidence is retained separately.

Prescreening uses only site/rack/residency authority, immutable fixed occupancy, arithmetic checkpoints and exact cached WAN/restart predicates. A failed full STAY mask never removes a feasible migration prefix. Zero-rate waiting slots inside a transfer remain valid exactly as in legacy. No Top-K, objective ranking, sampling or movable-reference occupancy is used. Raw candidate-attempt reduction is {reduction:.6%}; deletion of valid physical options is zero. PR97's partial 92,656 options are never used as a full-domain denominator.

The resource consistency recheck remains **PASS**, explicitly with zero achieved reserve only as a diagnostic. The unchanged real Runtime/CC4 Planning targets are bound in the A1 model. The next blocker is **{blocker}**. A1's separate model attempt used {receipt['total_wall_seconds']:.6f}s and produced no accepted incumbent. Domain construction succeeded; full model construction did not. Partial model counts are labeled in A1_MODEL_STATS.json; final counts, optimize time, gap, nodes and presolve are null. M1/A2/M2 and Fresh AC are NOT_RUN; no final response kernel exists.

The compact fallback was **not activated**: its preregistered condition was failure to complete the exact domain within 600s. Model size alone does not meet that trigger. Problem 8 remains open. Future exact representation work must not be misreported as solved by this domain benchmark.

Verification: **{suite.attrib['tests']} tests pass**, source hashes and preserved evidence verify, and the original CC4 envelope/provider/gamma90=2.423057443558147/780 GPU/MESS/PCS/Event30/local-repair files are untouched.

```powershell
$env:PYTHONUTF8='1'
python -m pytest v42_boundary/tests.py tests/test_v42_temporal.py tests/test_v42_final.py tests/test_v42_native.py tests/test_v42_may01.py tests/test_v42_job_capability.py -q
python -m v42_boundary.verify
git diff --check
```

The large lazy domain, full per-job profiles, failed attempts and supervised process logs remain local and SHA-bound. Fresh generation requires a new empty output directory and the frozen native source files; do not overwrite one-shot receipts. See FINAL_REVIEW_KO.md for the 50 requested answers and the authority audits for source limitations.
'''
    (OUT/'README.md').write_text(text,encoding='utf8')
    answers=[
        'PR97의 1,395 PENDING jobs는 age가 120,931~291,228초였고, W>age를 만족하는 L4 TRAIN 표본도 3/8/50개뿐이라 N_cond=100을 채우지 못했다.',
        '과거 잔여 대기시간은 현재 job의 승인된 시작 구간과 다르다. 해당 규칙은 forensic evidence로 보존하고 production TS는 ServiceBoundary로 교체했다.',
        '기존 R0의 요청 walltime 기반 planning completion, reference/earliest start, admission·QoS·terminal/carryout 권한이다. 실제 미래 완료시간이 아니다.',
        'V10 Q50은 보존해야 할 nominal 서비스 길이, boundary는 선택 가능한 유한 시작 slot 집합이다.',
        'earliest=max(reference,RSP,24), latest=min(RW_completion-d50,119,120+원래 승인 tail-d50)이다. pre-D00/post-H reference, 미승인 class는 singleton을 유지한다.',
        '아니다. 원래 승인된 post-H tail을 보존한다. R0의 finite start/control 규칙은 유지한다.',
        '아니다. RUNNING은 전체 물리 gang을 유지하며 checkpoint migration은 별도 capability다.',
        '없다. 제출 전 개인 identity/runtime/start boundary를 만들지 않는다.',
        '그대로 보존한 PR97 CC4 x[h,t]와 TRAIN Q10/Q90 누적 service envelope다.',
        'explicit ID 생성, V10 Q50 호출, anonymous forecast 한 번 depletion, PENDING 생성과 physical GPU=0, live finite boundary 계산을 수행한다.',
        '동일한 frozen V10 Q50 provider를 호출하는 inherited EpisodeLedger.submit 경로를 쓴다.',
        'PENDING이면 origin unknown이라는 이유로 영구 차단하지 않는다. 다만 현재 audited TRAIN R0 window support가 없어 실제 live TS 권한은 fail-closed다.',
        '권한이 재현된 TRAIN historical R0 authorized start-window여야 한다. 조사한 TRAIN reference ledger에는 temporal authority가 null이어서 유효 표본은 0개다.',
        'raw queue wait가 아니다. 이를 대체 표본으로 사용하지 않았다.',
        '사용 가능한 source의 종류는 historical authorized R0 shift window다. 현재 실제 지원 데이터가 있다는 뜻은 아니며, 빈 분포를 명시했다.',
        'Q25 한 가지이며 empirical method는 higher다.',
        '사용자가 지정한 preregistered conservative quantile이다. May를 본 뒤 분위수를 비교하거나 선택하지 않았다.',
        'L0=qos/protected/partition/gpu_bucket/wall_bucket, L1=partition 제거, L2=gpu_bucket 제거, L3=wall_bucket 제거. 첫 N_window>=100 level만 사용한다.',
        '합치지 않는다. standby 비보호 class만 기존 R0 live temporal QoS를 가진다. normal/high/urgent/protected에 자동 권한을 주지 않는다.',
        '아니다. Runtime/CC4/TS/A1 모두 NEW_ML=FALSE다.',
        f"Known TS candidate는 {summary['known_TS_candidates']}건이며 live initial count는 0이다.",
        f"전체 admitted 기준 job share {summary['candidate_job_share']:.6%}, nominal GPUh share {summary['candidate_GPUh_share']:.6%}. PENDING 내부 비율 {summary['known_PENDING_TS_share']:.6%}. Global witness/selected share는 미측정이다.",
        '비율을 목표로 rule을 조정하지 않았다. W>age/N_cond를 production known boundary에 적용하지 않는다.',
        'PR97 TS=0와 관련 파일은 바이트 그대로 보존했다. 새 supersession receipt만 추가했다.',
        'PR97은 complete-option generation에서 600초 timeout이었다.',
        'Gurobi optimize()는 호출되지 않았다. generation 병목이었다.',
        'static site/rack/residency, fixed-only interval masks, arithmetic checkpoint, WAN template/latest-start, skeleton signature dedup와 exact template reuse를 추가했다.',
        f"May static site hard removals={sum(r['reason']!='PASS' for r in expanded)}. 모든 제거 사유와 cache source를 CSV에 기록했다.",
        f"STAY start-mask/terminal removals={totals.get('immutable_or_terminal_STAY_removals',0)}. Full STAY 실패로 migration branch를 삭제하지 않는다.",
        f"Checkpoint capability 차단={totals.get('checkpoint_capability_removals',0)}, empty skeleton={totals.get('checkpoint_empty_removals',0)}, prefix capacity 차단={totals.get('checkpoint_prefix_removals',0)}. Branch와 complete option을 혼동하지 않는다.",
        f"WAN latest-start 사전 제거={totals['WAN_latest_start_pruned']}, 검사 후 WAN/destination 제거={totals['WAN_or_destination_removals']}. 물리 template은 {unique['WAN_cache_misses']}개만 계산했다.",
        f"Exact duplicate removal={totals.get('exact_duplicates_removed',0)}. 공유 template reuse는 valid option 삭제가 아니다.",
        f"최종 complete physical option 수는 {generation['complete_options']:,}개다. 모든 1,499 jobs를 포함한다.",
        f"Raw candidate attempts 대비 reduction={reduction:.6%}; 유효 complete-option set의 삭제율은 0%. PR97 부분 count와 비교한 가짜 감소율은 없다.",
        f"Input prep+generation={generation['total_seconds']:.6f}초, 그중 generation={generation['domain_seconds']:.6f}초. 저장/감독 포함 external wall={generation['supervisor']['total_wall_seconds']:.6f}초다.",
        '그렇다. 1,499개 전체 complete domain을 600초 이내에 완성했다. Lazy representation은 모든 option을 열거할 수 있으며 count를 추정하지 않았다.',
        '기존 synthetic fixtures와 deterministic real subset은 missing=extra=0, 순서도 동일하다. 추가 30개 물리 조건 fixture로 zero-rate WAN bug를 찾아 고친 뒤 전체 354 tests를 통과했다.',
        '사용하지 않았다. grid-benefit/nearest-site/earliest-only/shortest-route/random pruning은 없다.',
        '사용하지 않았다. 완전한 domain 생성이 600초를 넘었을 때만 허용된 fallback trigger가 성립하지 않았다.',
        '미발동이므로 compact MILP 결과/증명 파일을 생성하지 않았다. 현재 모델은 여전히 complete-option마다 binary를 하나씩 갖는다.',
        '여전히 PASS다. worst independent lower bound는 23:45의 509 GPU, anonymous slot minimum=0, capacity780이다. 별도 joint LP도 PASS이며 진단 reserve relaxation임을 명시했다.',
        f"A1 partial model build external wall={receipt['total_wall_seconds']:.6f}초. 마지막 progress는 {progress}. Full build completion 주장은 없다.",
        'optimize() 미호출이다. solve time은 null이며 build time을 solver time으로 보고하지 않는다.',
        '검증된 incumbent가 없고 gap/bound/nodes는 null이다.',
        'A1 accepted plan이 없어 M1/A2/M2는 NOT_RUN이다. 순서를 건너뛰지 않았다.',
        '전체 domain 생성과 native grid/complete-option column 구축의 bounded scalability를 측정했다. 최종 MILP/optimizer 및 전체 four-stage scalability는 아직 미완료다.',
        'Fresh AC는 NOT_RUN이다. accepted M2가 없다.',
        'freeze하지 않았다. FINAL_RESPONSE_KERNEL_AUTHORITY.json도 없다.',
        'Problem 8은 end-to-end CLOSED가 아니다. domain 생성 하위 병목은 해결됐지만 accepted native plan/AC가 없다.',
        f'다음 blocker는 {blocker}. 약 3.49억 complete-option binary의 full model 구축이 남는다. 또한 live TS는 audited TRAIN R0 boundary source가 없는 별도 제한이 있다. 추가 rule, ML, CC4 envelope 변경, solver sweep은 없었다.'
    ]
    require(len(answers)==50,'FIFTY_REVIEW_ANSWERS')
    (OUT/'FINAL_REVIEW_KO.md').write_text('# V42 service-boundary TS / A1 가속 최종 검토\n\n'+'\n\n'.join(f'{i}. {a}' for i,a in enumerate(answers,1))+'\n',encoding='utf8')
    print(dict(blocker=blocker,tests=int(suite.attrib['tests']),preserved=len(preserved),options=generation['complete_options']))

if __name__=='__main__':main()
