"""Finalize bounded diagnostic evidence without re-running production."""
import gzip,json,re,shutil
from collections import Counter
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from .flex_diagnostic import OUT,WORK,A0,B0,RUNTIME,DAY

def run():
    scan=read(OUT/'SINGLE_MOVE_SCAN.json');base=scan['B0']
    certs=json.loads(gzip.open(WORK/'SINGLE_MOVE_FULL_ROW_CERTIFICATES.json.gz','rt').read())
    cohorts=read(A0/'EXACT_JOB_EQUIVALENCE_AUDIT.json')['cohorts']
    uidgroup={u:g for g,c in enumerate(cohorts) for u in c['members']}
    manifest=read(A0/'V41R1_FULL_CANDIDATE_MANIFEST.json')
    metadata={r['job_id']:r for r in manifest['jobs']}
    refs=read(RUNTIME/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json');byuid={r['job_uid']:r for r in refs}
    activation=read(OUT/'B1_VARIABLE_ACTIVATION_AUDIT.json')
    prior=OUT/'B1_VARIABLE_ACTIVATION_BOUND_REPLAY.json'
    if not prior.exists():shutil.copyfile(OUT/'B1_VARIABLE_ACTIVATION_AUDIT.json',prior)
    allfree=set(v for c in certs for v in c['changed_decision_variables'])
    for label,run in activation['production_runs'].items():
        freevars=set();freecandidates=set();fixed_count=0
        for item in run['neighborhoods']:
            h=read(item['historical_receipt']['path']);opened=set(h['free_cohorts']);valid=[]
            for c in certs:
                if uidgroup[c['uid']] not in opened:continue
                ok=True
                for lock in h['higher_priority_locks']:
                    n=lock['name'];b=lock['rhs'];v=c['vector']
                    if n=='PRIMARY_EXACT_VALUE_LOCK':ok &= 1000*v[0]<=b+1e-9
                    elif n=='V41_MEAN_H4_SHORTFALL_LOCK':ok &= v[1]<=b+1e-9
                    elif n=='MIGRATION_EXACT_LOCK':ok &= v[2]==b
                    elif n=='REFERENCE_DEVIATION_EXACT_LOCK':ok &= v[3]==b
                    else:raise ValueError(n)
                if ok:valid.append(c)
            variables=set(v for c in valid for v in c['changed_decision_variables'])
            raw={(c['uid'],c['option_index']) for c in valid}|{(c['uid'],'B0_REFERENCE') for c in valid}
            p5=h['objective_stage']=='QUATERNARY_STABLE_TIE'
            fixed=h['free_candidate_count'] if p5 else 0
            item.update(certified_actually_free_variables=len(variables),certified_actually_free_candidate_lower_bound=len(raw),
                visited_but_fixed_proven_count=fixed,remaining_admissibility='UNKNOWN_NOT_INFERRED_FROM_LB_UB',
                free_witnesses=[dict(uid=c['uid'],option_index=c['option_index']) for c in valid])
            freevars.update(variables);freecandidates.update(raw);fixed_count+=fixed
        run.update(certified_actually_free_unique_variables_lower_bound=len(freevars),
            certified_actually_free_unique_candidates_lower_bound=len(freecandidates),
            visited_but_fixed_candidate_occurrences_proven=fixed_count,
            fixed_reason_distribution={'REQUIRED_HIGHER_PRIORITY_P3_ZERO_P4_ZERO_LOCKS':fixed_count,'FO_FAILED_TO_RESTORE_ORIGINAL_BOUNDS':0},
            untested_joint_admissibility='UNKNOWN; not classified as fixed or infeasible')
    activation.update(full_original_model_certified_actually_free_variable_lower_bound=len(allfree),
        actual_free_certificate_source=record(WORK/'SINGLE_MOVE_FULL_ROW_CERTIFICATES.json.gz'),
        full_admissibility_census_complete=False,required_lex_locks_are_not_unfixing_defects=True)
    write_json(OUT/'B1_VARIABLE_ACTIVATION_AUDIT.json',activation)
    def selected(path):
        value=read(path);rows=read(value['jobs']['path']) if isinstance(value,dict) and isinstance(value.get('jobs'),dict) else value['jobs'] if isinstance(value,dict) else value
        pre=[];mig=[];running=[];pending=[]
        from .migration import state_at_d00
        for r in rows:
            u=r['job_uid'];old=byuid[u];initial=r.get('initial_AIDC',r['AIDC_site'])
            if initial!=old['AIDC_site']:pre.append(u)
            if r.get('migration_selected'):
                mig.append(u);(running if state_at_d00(old)=='RUNNING' else pending).append(u)
        return dict(prestart_relocations=len(pre),running_migrations=len(mig),D00_RUNNING_migrations=len(running),
            PENDING_becomes_RUNNING_migrations=len(pending),initial_IDC_different_jobs=pre,checkpoint_migrated_jobs=mig)
    best=read(OUT/'FRESH_COUPLED_CERTIFICATE_CHECK_ORIGINAL_MODEL_WITNESS.json')
    pair=read(OUT/'PAIR_ORIGINAL_MODEL_WITNESS.json');triple=read(OUT/'CAPACITY_RELEASE_TRIPLE_PROBES.json')
    prod=read(A0/'ACCEPTED_AIDC.json');counts=selected(A0/'ACCEPTED_AIDC.json')
    electrical=read(OUT/'ELECTRICAL_RESPONSIVENESS.json')
    from .migration import state_at_d00
    eligible=Counter(state_at_d00(byuid[r['job_id']]) for r in manifest['jobs'] if r['can_migrate'])
    report=dict(status='DIAGNOSTIC_COMPLETE',day=DAY,primary_root_cause='COMPUTATIONAL_LOCAL_BASIN',
        B0_P1_P5=base,production_B1_P1_P5=prod['OBJECTIVE_VECTOR'],production_selected=counts,
        nominal_raw_candidate_count=manifest['final_authoritative_candidates'],
        search_eligible_raw_candidate_count=manifest['final_authoritative_candidates']-7,
        fixed_singleton_raw_candidates=7,eligible_migration_jobs_by_D00_state=dict(eligible),
        nominal_migration_options=manifest['RUNNING_migration_candidates'],nominal_job_OD_arcs=manifest['total_destination_arcs'],
        actually_free_variables_certified_lower_bound=len(allfree),activation=activation,
        model_feasible_single_alternatives=scan['feasible_single_job_alternative_count'],
        global_model_feasible_alternative_count='NOT_EXHAUSTIVELY_ENUMERATED; certified alternatives are lower bounds',
        PENDING_jobs_with_single_alternative_initial_site=scan['PENDING_jobs_with_alternative_initial_site'],
        D00_RUNNING_jobs_with_single_migration=scan['D00_RUNNING_jobs_with_feasible_migration'],
        PENDING_jobs_with_single_checkpoint_migration=scan['PENDING_jobs_with_feasible_checkpoint_migration'],
        single_move=scan,best_pair=pair,best_triple=triple,best_coupled=best,diagnostic_best_selected=selected(OUT/'FRESH_COUPLED_CERTIFICATE_CHECK_ORIGINAL_MODEL_WITNESS.json'),
        forced_propagation='PASS: JOB->GPU/RACK->IT/PCC/QCC->INJECTION->PLANNING_LINE/VOLTAGE',electrical=electrical,
        non_B0_feasible=True,non_B0_P1_no_worse=True,non_B0_P1_P2_no_worse=True,
        cross_region=read(OUT/'CROSS_REGION_ESCAPE_TEST.json'),
        acceptance_rule=dict(equal_full_objective_rejected=True,equal_P1_better_P2_accepted=True,
            neutral_P1_P2_prestart_restructuring_exists=True,that_prestart_has_worse_P4=True,
            monotonic_lex_improving_path_to_verified_pair_exists=True,neutral_intermediate_required=False,
            monotonic_acceptance_trap_confirmed=False),
        ablations={n:read(OUT/(n+'.json')) for n in ['ABLATION_PRESTART_ONLY','ABLATION_MIGRATION_ONLY']},
        local_certificate=read(OUT/'LOCAL_CERTIFICATE_CONSISTENCY.json'),
        interpretation='Valid improvements exploit unchanged UID-serial WAN waiting and post-horizon service. Not proof of efficient spatial balancing or global optimality.',
        production_FO_change_required=True,scientific_model_change_required=False,
        linkage_defect=False,unfixing_defect=False,Actual_used_for_search=False,Full_May_started=False)
    evidence=[record(p) for p in sorted(OUT.glob('*.json')) if p.name not in ('V41R1_MAY04_B1_FLEXIBILITY_DIAGNOSTIC.json','DIAGNOSTIC_FREEZE.json')]
    report['evidence']=evidence
    write_json(OUT/'V41R1_MAY04_B1_FLEXIBILITY_DIAGNOSTIC.json',report)
    lines=['# May-04 B1 flexibility diagnostic','',
        '**주원인: COMPUTATIONAL_LOCAL_BASIN.** 기존 F&O가 원래 B1 모델에서 가능한 개선을 놓쳤습니다.',
        '원래 변수 경계를 복구하지 않은 결함이나 AIDC/전력망 연결 결함은 발견되지 않았습니다. 과학적 feasible set 변경은 필요하지 않습니다.','',
        '| 결과 | P1 | P2 GPUh | P3 | P4 | P5 |','|---|---:|---:|---:|---:|---:|']
    for name,v in [('B0 / 기존 production B1',base),('최선 단일 작업',scan['best']['ALL']['vector']),('검증된 pair',pair['vector']),('검증된 triple',triple['best']['vector']),('검증된 coupled witness',best['vector'])]:
        lines.append('| '+name+' | '+' | '.join(str(x) for x in v)+' |')
    lines+=['',f"명목 후보 {manifest['final_authoritative_candidates']:,}개 중 단일 작업 변경으로 가능한 대안 658개를 모두 전체 MPS 행·일반 제약·정수성·GPU·rack·WAN·전력으로 검증했습니다. 단일 변경 P1 개선은 0개, 동일 P1은 658개입니다.",
        f"PENDING 초기 사이트 대안이 있는 작업은 단일 변경 범위에서 26개, checkpoint migration 대안이 있는 PENDING 작업은 99개입니다. D00 RUNNING의 단일 이동은 0개지만 공동 이동에서는 가능합니다.",
        f"전체 원래 모델에서 두 admissible 값을 증명한 결정 변수는 최소 {len(allfree):,}개입니다. 모든 공동 조합의 실제 자유도를 전수 인증한 숫자는 아닙니다. 열린 LB/UB 수와 구분했습니다.",
        '과거 157개 부분문제에서 열린 변수의 LB/UB 복구 누락은 0개입니다. P5의 P3=0/P4=0 잠금에 따른 암묵적 고정은 정상적인 lexicographic 제약입니다. 나머지 미인증 조합은 UNKNOWN으로 기록했습니다.','',
        f"기존 production 선택: prestart {counts['prestart_relocations']}개, checkpoint migration {counts['running_migrations']}개. 명목 migration 옵션 {manifest['RUNNING_migration_candidates']:,}개와 선택 건수는 다릅니다.",
        f"D00 상태별 eligible migration 작업: {dict(eligible)}. 검증된 최선 diagnostic 선택: {report['diagnostic_best_selected']}.",
        '강제 변경 테스트에서 execution site, rack/GPU, IT, PCC P/Q, injection, line loading 및 voltage가 모두 반응했습니다.',
        '세 non-B0 존재성 검사(순수 feasibility / P1 유지 / P1·P2 유지)는 모두 원래 모델에서 검증됐습니다.','',
        '최대 부하: line.sw2::A, A상, D18:00(issue slot 96), rho=0.5383475197373216. 이때 12 IDC가 전부 GPU-full입니다.',
        '| IDC | P 방향 / kW | Q 방향 / kvar | 실제 AIDC 고정 PF 방향 / kW |','|---|---:|---:|---:|']
    for r in electrical['table']:lines.append(f"| {r['IDC']} | {r['co_located_P_load_sensitivity']:.9g} | {r['co_located_Q_load_sensitivity']:.9g} | {r['critical_fixed_PF_load_sensitivity']:.9g} |")
    lines+=['','P/Q 열은 co-located certified MESS P/Q 제어 열을 사용한 별도의 진단 perturbation입니다. AIDC 고정 PF 열의 정확한 분해라고 주장하지 않습니다. 검색 우선순위는 직접 AIDC 열을 사용하며 후보를 제거하지 않습니다.',
        '발견된 pair는 먼저 P1 유지·P2 개선 단계를 거쳐 더 낮은 P1로 갈 수 있습니다. 비개선 중간 해를 반드시 수락해야 하는 trap은 입증되지 않았습니다. 공동 해를 하나의 제안으로 탐색할 이유는 충분합니다.',
        'Cross-region 추가 강제 검사는 coupled 검사에서 이미 B0를 벗어났으므로 조건이 발동하지 않았습니다(ΔP1: N/A).',
        'Placement-only 25개 작업 검사에서는 B0 그대로였습니다. Migration-only 검사는 더 낮은 P1을 찾았습니다. 전체 placement 전역 최적성/전체 B1 전역 최적성을 solver gap으로 주장하지 않습니다.',
        '**해석상 중요한 점:** pair의 RUNNING job 8725925는 checkpoint 이후 92슬롯(23시간) 대기합니다. UID 순서의 WAN 직렬화가 늦은 PENDING 이동을 먼저 처리하며, 일부 작업량이 day horizon 밖으로 이동합니다. 원래 제약과 전체 safe compute service를 만족하지만 순수한 공간적 부하 분산 효과로 해석하면 안 됩니다.',
        '**인증 불일치:** 앞선 coupled solve의 zero-gap bound 0.5366498148764607은 동일한 25개 작업에서 원래 전체 행을 통과한 0.5363128252782274 해와 모순됩니다. 해당 최적성 주장은 철회했습니다. Fresh model 재검사는 더 좋은 해를 확인했지만 전역 최적성 근거로 사용하지 않습니다. Migration-only raw proposal은 PWL residual 1.0455e-9로 원래 1e-9 기준을 초과했으며, 독립 재구성한 전체 assignment만 PASS로 인정했습니다.',
        '과거 3% gap 재현 및 후속 첫 개선 탐색 수정 결과는 별도 FIRST_IMPROVEMENT 보고서에 연결합니다. 5월 전체 실행은 보류 상태입니다.',
        '', '세부 경로와 SHA-256: [machine-readable report](V41R1_MAY04_B1_FLEXIBILITY_DIAGNOSTIC.json).']
    (OUT/'V41R1_MAY04_B1_FLEXIBILITY_DIAGNOSTIC.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('DIAGNOSTIC_REPORT_COMPLETE',len(allfree),flush=True)

if __name__=='__main__':run()
