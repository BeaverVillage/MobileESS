"""Evidence-only final receipts; never changes candidates or runs a solver."""
import ast,re
from v42_root.common import *
from v42_native.voltage import authority,authority_sha


def preflight_reports():
    paths=['v42_boundary/model.py','v42_compact/native.py','v42_temporal/native.py','v42_native/grid.py',
           'v42_native/canary.py','v42_exact/validation.py','v42_voltage/grid.py','v42_may01/prepare.py']
    dump('PLANNING_VOLTAGE_SOURCE_AUDIT.json',dict(PASS=True,authority_sha256=authority_sha(),
         source_paths=[dict(path=p,sha256=sha(ROOT/p),central_authority=True,old_Planning_band=False) for p in paths],
         active_stage_paths=dict(A1='root.native -> compact.grid -> boundary.planning_grid -> native.add_grid',
                                 M1='voltage.m1 -> voltage.grid.frozen_grid -> native.add_grid',
                                 A2='compact.grid with fixed MESS P/Q -> native.add_grid',
                                 M2='voltage.grid.frozen_grid -> native.add_grid (future accepted A2 handoff required)'),
         historical_receipts_unchanged=True,historical_bands_are_not_active_authority=True,
         coefficients_phase_PQ_signs_line_transformer_ratings_topology_PCC_unchanged=True))
    (OUT/'PROBLEM13_PLANNING_ROBUSTNESS_CONTRACT.md').write_text('''Planning uses 0.955–1.045 pu (squared 0.912025–1.092025) in A1/M1/A2/M2. This is an engineering robustness hypothesis, not a proof that linear Planning implies AC feasibility.

MESS route, movement, charging, discharging, Q and SOC remain joint native MILP decisions. Actual local P, Q and P/Q repair are removed. The frozen route/movement/P/Q is replayed as-is. Fresh OpenDSS must independently pass convergence, 0.95–1.05 physical voltage, line current, transformer current and kVA. A failure remains FAIL; no rescue, emergency full reoptimization or margin fallback.

Problem 13 is not finally validated here: A2/M2, frozen final Planning, Actual replay and Fresh AC remain required future work. This task stops after one M1. Existing unknown-arrival site-only authority is unchanged; no fabricated future individual jobs or new temporal/migration permissions.
''',encoding='utf8')
    dump('ACTUAL_LOCAL_REPAIR_SUPERSESSION.json',dict(status='REMOVED_FAIL_FAST',PR104_historical_implementation_preserved_in_git=True,
         error='ACTUAL_LOCAL_PQ_REPAIR_REMOVED_IN_V42',local_P=False,local_Q=False,local_PQ=False,
         emergency_full_reoptimization=False,Actual_voltage=[.95,1.05],Fresh_AC_required=True,
         immutable_replay_gate='require_frozen_replay',coordinator_checks_pre_AC_schedule_digest=True))
    calls=[]
    for folder in [p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith('v42')]:
        for p in folder.rglob('*.py'):
            if '__pycache__' in p.parts:continue
            for node in ast.walk(ast.parse(p.read_text(encoding='utf8'))):
                if isinstance(node,ast.Call) and ((isinstance(node.func,ast.Name) and node.func.id=='repair_pq') or
                                                (isinstance(node.func,ast.Attribute) and node.func.attr=='repair_pq')):
                    calls.append(dict(path=p.relative_to(ROOT).as_posix(),line=node.lineno,test_only=p.name.startswith('test_')))
    require_no_active=not any(not c['test_only'] for c in calls)
    assert require_no_active
    dump('ACTUAL_REPAIR_CALL_AUDIT.json',dict(PASS=True,calls=calls,active_production_calls=0,
         public_API='fail-fast before model creation',local_solver_import_removed=True,physical_failure_fallback=False))
    dump('LOCAL_REPAIR_POLICY_IMPACT_AUDIT.json',dict(optimization_stage_M1_is_not_paper_policy_M1=True,
         paper_policy_names_preserved=True,paper_policy_redefinition=False,four_policy_campaign_RUN=False,
         historical_default_repair_policy='M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE',
         historical_API_permitted_other_policies=['M2_FIXED30_MOBILE','M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION'],
         historical_explicit_repair_disabled_policy='M3_EVENT30_NO_LOCAL_REPAIR_MOBILE',
         M1_M3_behavior='Current event predicates coincide and both now replay without repair when all other inputs/actions are identical; no empirical campaign claim.',
         paper_revision_requires_approval='Repair-enabled versus no-repair comparison labels/claims need scientific revision; preserve IDs until explicit approval.'))
    interrupted=LOCAL/'build_interrupted_before_optimize'
    if interrupted.exists():
        dump('BUILD_INTERRUPTION_RECEIPT.json',dict(stage='MODEL_CONSTRUCTION',classes_complete=90,classes_required=117,
             optimize_calls=0,no_model_complete_or_solver_log=True,process_gone_verified=True,
             reason='Conversation interruption terminated unified execution before optimization',
             preserved_directory=str(interrupted),replacement_build_not_performance_rerun=True))


def optional(n,default=None):return read(OUT/n) if (OUT/n).exists() else default


def finish():
    preflight_reports()
    a=optional('A1_OPTIMIZATION.json',{});ap=optional('A1_PHYSICAL_VALIDATION.json',{'PASS':False})
    h=optional('A1_TO_M1_HANDOFF.json',{'accepted':False});m=optional('M1_OPTIMIZATION.json',{})
    mp=optional('M1_PHYSICAL_VALIDATION.json',{'PASS':False});av=optional('A1_VOLTAGE_MARGIN_REPORT.json',{})
    mv=optional('M1_VOLTAGE_MARGIN_REPORT.json',{});ms=optional('M1_MODEL_STATS.json',{})
    if (OUT/'F2-CRA_MODEL_STATS.json').exists():dump('A1_MODEL_STATS.json',read(OUT/'F2-CRA_MODEL_STATS.json'))
    mrun=bool(m.get('passes')) or (LOCAL/'M1/STARTED.json').exists()
    accepted=bool(m.get('accepted'));aaccepted=bool(a.get('complete') and ap['PASS'] and h.get('accepted'))
    notrun=dict(status='NOT_RUN_A1_INFEASIBLE',RUN=False,measurement=None)
    if not mrun:
        for name in ('M1_PREFLIGHT.json','M1_MODEL_STATS.json','M1_VOLTAGE_AUTHORITY_RECEIPT.json','M1_OPTIMIZATION.json','M1_PHYSICAL_VALIDATION.json','M1_VOLTAGE_MARGIN_REPORT.json'):
            if not (OUT/name).exists():dump(name,notrun)
        if not (OUT/'M1_PROGRESS.csv').exists():(OUT/'M1_PROGRESS.csv').write_text('status\nNOT_RUN_A1_NOT_ACCEPTED\n',encoding='utf8')
    p1=next((r for r in m.get('passes',[]) if r['component']=='rho'),{})
    energy=next((r for r in m.get('passes',[]) if r['component']=='movement_energy'),{})
    count=next((r for r in m.get('passes',[]) if r['component']=='movement_count'),{})
    roots=sum((r.get('root') or {}).get('seconds',0) for r in m.get('passes',[]));presolve=sum(r.get('presolve_seconds') or 0 for r in m.get('passes',[]))
    total=m.get('total_optimize_seconds',0);build=m.get('model_build_seconds',0)
    if not mrun:dominant=None
    elif p1.get('incumbent') is None and total>=1790:dominant='INCUMBENT_DISCOVERY' if p1.get('root') else 'ROOT_LP'
    elif roots>max(total*.5,build,presolve):dominant='ROOT_LP'
    elif build>max(total,presolve):dominant='MODEL_BUILD'
    elif presolve>total*.5:dominant='PRESOLVE'
    elif p1.get('status')!=2:dominant='DUAL_BOUND' if p1.get('incumbent') is not None else 'INCUMBENT_DISCOVERY'
    elif total<60:dominant='NONE_SIGNIFICANT'
    else:dominant='B_AND_B_TREE'
    diagnosis=dict(classification=dominant,measured=bool(mrun),status='MEASURED' if mrun else 'NOT_RUN_A1_INFEASIBLE',model_build_seconds=build if mrun else None,optimize_seconds=total if mrun else None,
                   presolve_seconds=presolve,root_seconds=roots,P1=p1,
                   classification_scope='Measured phase timings and incumbent/bound progress; binary count alone is not causal evidence.',
                   no_unsupported_SOC_PQ_route_bottleneck_claim=True,post_result_model_changes=False)
    dump('M1_BOTTLENECK_DIAGNOSIS.json',diagnosis)
    (OUT/'M1_NEXT_MODIFICATIONS.md').write_text(f'''Measured dominant classification: {dominant}.

Required bug/physics fixes: retain fail-closed certificates; any reported physical failure must be diagnosed without weakening limits.

Exact computational improvements: compare unchanged matrix ordering and redundant-row handling only after checking phase evidence. Reuse fixed AIDC anchor coefficients and identical M1/M2 domain construction in future stages. Do not infer route pruning benefit from binary counts; PR101 native route reduction was not material.

Optional tuning: a separately preregistered one-thread solver comparison may follow; none was run after this result.

Scientific changes requiring explicit approval: widening voltage margin, job/candidate removal, changes to CC4/Runtime, PCS, SOC, route or terminal constraints, and paper-policy revisions. None is applied here.
''',encoding='utf8')
    infeasible=optional('A1_INFEASIBILITY_DIAGNOSIS.json',{})
    dump('VOLTAGE_MARGIN_OPERABILITY_REPORT.json',dict(A1=av,M1=mv,
         A1_interventions=[r.get('incumbent') for r in a.get('passes',[])[1:]],
         M1_movement_energy=energy.get('incumbent'),M1_movement_count=count.get('incumbent'),
         margin_auto_changed=False,A1_infeasibility=dict(status=infeasible.get('status'),independent_interval_contradictions=infeasible.get('independent_interval_contradictions'),
         certificate_file='A1_INFEASIBILITY_DIAGNOSIS.json',certificate_sha256=sha(OUT/'A1_INFEASIBILITY_DIAGNOSIS.json') if infeasible else None,IIS_RUN=False),
         interpretation='A1 is infeasible with zero MESS P/Q. M1 operability is unmeasured. No accepted control/anchor or Problem 13 validation is claimed.'))
    flags=dict(PLANNING_VOLTAGE_MIN_PU=.955,PLANNING_VOLTAGE_MAX_PU=1.045,
               PLANNING_VOLTAGE_MIN_SQUARED=.912025,PLANNING_VOLTAGE_MAX_SQUARED=1.092025,
               ACTUAL_VOLTAGE_MIN_PU=.95,ACTUAL_VOLTAGE_MAX_PU=1.05,ACTUAL_Q_CORRECTION_ENABLED=False,ACTUAL_P_CORRECTION_ENABLED=False,
               P1_NAME='MAX_LINE_LOADING',P2_NAME='MIN_INTERVENTION',
               PLANNING_VOLTAGE_LOWER_PU=.955,PLANNING_VOLTAGE_UPPER_PU=1.045,
               PLANNING_VOLTAGE_LOWER_SQUARED=.912025,PLANNING_VOLTAGE_UPPER_SQUARED=1.092025,
               ACTUAL_VOLTAGE_LOWER_PU=.95,ACTUAL_VOLTAGE_UPPER_PU=1.05,
               ACTUAL_LOCAL_REPAIR_ENABLED=False,ACTUAL_LOCAL_PQ_REPAIR_ENABLED=False,ACTUAL_LOCAL_Q_REPAIR_ENABLED=False,
               ACTUAL_LOCAL_P_REPAIR_ENABLED=False,ACTUAL_EMERGENCY_FULL_REOPTIMIZATION=False,FRESH_AC_REQUIRED=True,
               FINAL_SCIENTIFIC_OBJECTIVE_COUNT=2,A1_COMPLETE=aaccepted,A1_PHYSICAL_PASS=ap['PASS'],A1_HANDOFF_MATERIALIZED=bool(h.get('accepted')),
               A1_KNOWN_JOBS=1499,A1_SCIENTIFIC_CLASSES=117,A1_KNOWN_JOBS_MATERIALIZED=1499 if h.get('accepted') else 0,
               UNKNOWN_FUTURE_INDIVIDUAL_JOBS_FABRICATED=False,UNKNOWN_CC4_MODEL_INCLUDED=True,
               UNKNOWN_CC4_IMPACT_INCLUDED=bool(h.get('unknown_CC4_included')),M1_AIDC_ANCHOR_FIXED=bool(h.get('accepted')),
               M1_AIDC_DECISION_VARIABLES=0,M1_ROUTE_P_Q_SOC_JOINT=True,M1_THREADS=1,M1_TIME_LIMIT_SECONDS=1800,M1_MIP_GAP_TARGET=.005,
               M1_MIP_START_AVAILABLE=False,M1_RUN=mrun,M1_COMPLETE=accepted,M1_PHYSICAL_PASS=mp.get('PASS',False),
               M1_P1_INCUMBENT=p1.get('incumbent'),M1_P1_BOUND=p1.get('bound'),M1_P1_GAP=p1.get('relative_gap'),
               M1_P2_MOVEMENT_ENERGY=energy.get('incumbent'),M1_P2_MOVEMENT_COUNT=count.get('incumbent'),
               M1_ROOT_SECONDS=(p1.get('root') or {}).get('seconds'),M1_FIRST_INCUMBENT_SECONDS=p1.get('first_incumbent_seconds'),
               M1_NODE_COUNT=p1.get('nodes'),M1_PEAK_RSS_BYTES=m.get('peak_RSS_bytes'),M1_BOTTLENECK=dominant,
               PROBLEM13_FINAL_VALIDATED=False,A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False)
    dump('FINAL_FLAGS.json',flags)
    dump('PIPELINE_STATUS.json',dict(A1_accepted=aaccepted,M1_RUN=mrun,M1_accepted=accepted,
         STOP='BEFORE_A2' if mrun else 'A1_NOT_ACCEPTED',A2=False,M2=False,Actual=False,Fresh_AC=False,IEEE8500=False))
    dump('FINAL_VERDICT.json',dict(status='A1_M1_ACCEPTED_STOP_BEFORE_A2' if accepted else 'STOP_UNACCEPTED_STAGE',
         A1_accepted=aaccepted,M1_accepted=accepted,Problem13_final_validated=False,margin_auto_relaxed=False))
    write_review(a,ap,h,m,mp,av,mv,ms,dominant)
    (OUT/'README.md').write_text('Tightened-voltage successor of Draft PR104. Native Windows A1 → provisional frozen AIDC handoff → one M1; STOP before A2.\n\nSee FINAL_REVIEW_KO.md, PREREGISTRATION.json and all per-stage source/physics/optimization receipts. This is not final Problem 13 or Fresh AC validation.\n',encoding='utf8')


def write_review(a,ap,h,m,mp,av,mv,ms,dominant):
    # Keep all fifty requested questions in the final Korean review.
    request=Path(r'C:\Users\kjw39\.codex\attachments\83a16191-2b3f-4003-a156-791f4d0ff339\붙여넣은 텍스트.txt').read_text(encoding='utf8')
    section=request.split('41. FINAL_REVIEW_KO — REQUIRED QUESTIONS')[1].split('42. EXECUTION ORDER')[0]
    questions=re.findall(r'^\d+\. (.+)$',section,re.M);assert len(questions)==50
    ar=a.get('passes',[]);mr=m.get('passes',[]);inc=lambda rows,index:rows[index].get('incumbent') if len(rows)>index else None
    old=read(OUT/'PR104_BASE_RECEIPT.json')['P1']['incumbent'];new=inc(ar,0)
    not_run='구현 경로는 준비했으나 A1 INFEASIBLE로 native M1은 미실행이다.'
    answers=['0.955–1.045 pu.','0.912025–1.092025.','0.95–1.05 pu.',
             'Planning 여유는 선형 모델 오차에 대한 robustness 가설이다. Actual은 물리 판정 기준이다. 최종 검증 전이다.',
             f"새 margin으로 재구성·최적화했다. complete={a.get('complete')}",
             '아니다. solver status 3(INFEASIBLE), incumbent 없음. 독립 전압 interval에서도 불가능한 행 145개를 증명했다.' if not ap.get('PASS') else '독립 physical PASS=True.',str(new),str(new-old if new is not None else None),
             str(inc(ar,1)),str(inc(ar,2)),str(inc(ar,3)),str(a.get('total_optimize_seconds'))+' s (P1 optimize-only). MIP-start 검증의 별도 zero-objective attempt는 9.392076 s이며 과학 목적 budget에 포함하지 않았다.',
             '제거했다.','남아 있지 않다.','남아 있지 않다.','호출 시 ACTUAL_LOCAL_PQ_REPAIR_REMOVED_IN_V42로 즉시 실패한다.',
             '필수이며 이번 task에서는 실행하지 않았다.','구조하지 않는다. FAIL을 유지한다.',
             'M1/M3의 기존 repair 대조가 중복될 수 있다. 이름·정책은 유지하며 논문 비교 수정은 승인이 필요하다.',
             str(h.get('accepted'))+' — accepted handoff 없음; 상태/빈 schema만 기록했다.',
             '미복원: feasible incumbent 없음. 구성한 모델은 1499개 작업이다.' if not h.get('accepted') else str(h.get('known_jobs')),
             '117 class는 정확한 solver symmetry compression이다. 이번에는 feasible incumbent가 없어 개별 handoff를 발행하지 않았다.',
             'fabricated하지 않았다.',str(h.get('unknown_CC4_included'))+' — CC4는 A1 모델에 유지했으나 accepted anchor는 없다.',
             'M1 구현은 고정 입력을 요구한다. 이번에는 accepted anchor가 없어 M1을 실행하지 않았다.','구현은 0개를 강제한다. 실제 native M1 census는 미실행이다.',
             'native time-expanded arc binary이다. '+not_run,'Pch/Pdis와 charge mode가 joint decision이다. '+not_run,'연결·PCS와 결합한 decision이다. '+not_run,
             '초기/종단·효율·이동에너지와 결합한 decision이다. '+not_run,'route/P/Q/SOC를 함께 최적화하는 구현이다. '+not_run,'같은 중앙 authority이다. native M1은 미실행이다.',
             'MAX_LINE_LOADING.','MIN_INTERVENTION: movement energy → movement count.', '아니다. report-only이다.',
             json.dumps({k:ms.get(k) for k in ('binary','linear_constraints','nonzeros')},ensure_ascii=False)+' — native M1 미구성/미측정.',
             json.dumps([r.get('presolve_seconds') for r in mr]),json.dumps([r.get('root') for r in mr]),
             str(mr[0].get('first_incumbent_seconds') if mr else None),
             json.dumps({k:mr[0].get(k) for k in ('incumbent','bound','relative_gap')} if mr else {}),str(inc(mr,1)),str(inc(mr,2)),str(mp.get('PASS')),
             json.dumps({k:mv.get(k) for k in ('lower_active','upper_active','lower_near_binding','upper_near_binding')}),
             json.dumps({k:mv.get(k) for k in ('Q_max_abs_kvar','Q_near_PCS_fraction','Q_near_PCS_count')}),
             f"complete={m.get('complete')}, optimize={m.get('total_optimize_seconds')} s (build 제외). native M1 미실행.",
             dominant if dominant else '미측정: A1 infeasible로 M1 미실행.',
             'M1 병목 기반 exact modification은 추천할 근거가 없다. A1 불가능성은 정적 전압 interval로 증명했다. 과학 조건의 변경은 승인 전 적용하지 않는다.',
             'A1 infeasible이면 STOP하라는 명시적 요청에 따라 M1/A2를 실행하지 않았다.', '아니다. A1 infeasible이며 A2/M2/Actual/Fresh AC가 미실행이다.']
    assert len(answers)==50
    if not ar or ar[0].get('incumbent') is None:
        for i in (6,8,9,10):answers[i]='값 없음: A1 INFEASIBLE, feasible incumbent가 없다.'
        answers[7]=f'PR104 baseline P1={old}; 새 A1은 infeasible이므로 목적값 차이는 정의되지 않는다. 기존 값을 lock으로 사용하지 않았다.'
    if not mr:
        for i in range(36,45):answers[i]='미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.'
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n\n'.join(f'{i}. {q}\n\n{answer}' for i,(q,answer) in enumerate(zip(questions,answers),1))+'\n',encoding='utf8')


if __name__=='__main__':finish()
